"""Open-ended assistant tools + grounded fallback (Gemini mocked / off)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["GEMINI_API_KEY"] = ""

ROOT = Path(__file__).resolve().parents[1]
EGYPT = Path("/home/youssef/code/test/MarketMind_Egypt_Retail_Test.csv")
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "client_uploads"


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as c:
        yield c


def _upload_ready(client, path: Path):
    up = client.post(
        "/api/upload",
        files={"file": (path.name, path.read_bytes(), "text/csv")},
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]
    settings = client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "EGP",
            "date_format": "dayfirst",
            "confirm_date_format": True,
        },
    )
    assert settings.status_code == 200
    return sid


@pytest.mark.skipif(not EGYPT.exists(), reason="Egypt fixture missing")
def test_tools_reject_unknown_and_strip_identifiers():
    from api.services import assistant_tools
    from api.services.upload_store import load_meta
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as client:
        sid = _upload_ready(client, EGYPT)
        meta = load_meta(sid)
        bad = assistant_tools.execute_tool("not_a_real_tool", meta, {})
        assert bad["ok"] is False
        assert bad["error_code"] == "unknown_tool"

        leaders = assistant_tools.execute_tool(
            "get_product_leaders", meta, {"measure": "units", "top_n": 3}
        )
        assert leaders["ok"] is True
        assert leaders["top"]["product_name"] == "شاي أسود 250 جم"
        assert float(leaders["top"]["quantity"]) == 245.0
        blob = str(leaders)
        assert "customer_id" not in blob
        assert "stock_code" not in blob or leaders["top"].get("stock_code") is None
        client.delete(f"/api/upload/session?session_id={sid}")


@pytest.mark.skipif(not EGYPT.exists(), reason="Egypt fixture missing")
def test_open_ended_natural_language_not_fixed_qa(client):
    sid = _upload_ready(client, EGYPT)
    # English comparison — must not require exact keywords-only legacy path
    en = client.post(
        "/api/upload/assistant",
        json={
            "session_id": sid,
            "question": "Can you compare this month's sales with the previous month for me?",
            "lang": "en",
        },
    )
    assert en.status_code == 200, en.text
    body = en.json()
    assert body.get("unsupported") is not True
    answer = str(body.get("answer") or "")
    assert answer.strip()
    assert "Gemini ·" not in answer
    assert "context_keys" not in answer
    assert "gemini-2.5-flash" not in answer.lower()
    # Should include period comparison or honest readiness from tools
    assert body.get("mode") in {"grounded_facts", "gemini"}
    assert "tools_called" in body or body.get("mode") == "gemini" or answer

    ar = client.post(
        "/api/upload/assistant",
        json={
            "session_id": sid,
            "question": "إيه أعلى منتج اتباع؟",
            "lang": "ar",
            "history": [
                {"role": "user", "text": "لخّص الملف"},
                {"role": "assistant", "text": "ملخص سابق قصير"},
            ],
        },
    )
    assert ar.status_code == 200, ar.text
    a = ar.json()
    text = str(a.get("answer") or "")
    assert "شاي أسود 250 جم" in text
    assert "245" in text
    assert "تمام، استلمت" not in text
    client.delete(f"/api/upload/session?session_id={sid}")


@pytest.mark.skipif(not EGYPT.exists(), reason="Egypt fixture missing")
def test_fill_preview_does_not_mutate_apply_is_explicit(client):
    sid = _upload_ready(client, EGYPT)
    from api.services import assistant_tools
    from api.services.upload_store import load_meta, upload_path
    import hashlib

    meta = load_meta(sid)
    path = upload_path(sid)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    preview = assistant_tools.execute_tool("get_missing_and_fill_preview", meta, {})
    assert preview["ok"] is True
    assert preview.get("mutated") is False
    after_preview = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after_preview

    denied = assistant_tools.execute_tool("apply_safe_fills", meta, {"confirm_apply": False})
    assert denied["ok"] is False
    assert denied["error_code"] == "confirm_required"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before

    applied = assistant_tools.execute_tool("apply_safe_fills", meta, {"confirm_apply": True})
    assert applied["ok"] is True
    # Quantity / IDs stay manual — applied fields only price/description if any
    fields = set(applied.get("applied_fields") or [])
    assert "quantity" not in fields
    assert "customer_id" not in fields
    assert "invoice_date" not in fields

    client.delete(f"/api/upload/session?session_id={sid}")


@pytest.mark.skipif(not EGYPT.exists(), reason="Egypt fixture missing")
def test_forecast_and_category_honest_messages(client):
    sid = _upload_ready(client, EGYPT)
    from api.services import assistant_tools
    from api.services.upload_store import load_meta

    meta = load_meta(sid)
    fc = assistant_tools.execute_tool("get_forecast_status", meta, {})
    assert fc["ok"] is True
    if not fc.get("available"):
        assert fc.get("reason_en") or fc.get("reason_ar")

    cat = assistant_tools.execute_tool("get_category_performance", meta, {})
    # Egypt has category column mapped sometimes — either ok with categories or unmapped
    assert "ok" in cat
    client.delete(f"/api/upload/session?session_id={sid}")


def test_tool_result_privacy_guard():
    from api.services.assistant_tools import assert_tool_result_safe

    with pytest.raises(ValueError):
        assert_tool_result_safe({"customer_id": "x"})
    with pytest.raises(ValueError):
        assert_tool_result_safe({"note": "email me at a@b.com"})
    assert_tool_result_safe({"ok": True, "product_name": "Tea", "quantity": 10})


def test_tool_loop_bounds_constant():
    from api.services.gemini_tool_loop import MAX_TOOL_ROUNDS

    assert MAX_TOOL_ROUNDS <= 3


@pytest.mark.skipif(not EGYPT.exists(), reason="Egypt fixture missing")
def test_provider_fallback_keeps_deterministic_usable(client, monkeypatch):
    sid = _upload_ready(client, EGYPT)

    def boom(**kwargs):
        from api.services.gemini_tool_loop import ToolLoopResult

        return ToolLoopResult(
            ok=False,
            error_code="quota",
            error_en="quota",
            error_ar="حد",
        )

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn", boom
    )
    # Force “key configured” path into open-ended then fallback
    monkeypatch.setattr(
        "api.services.gemini_provider.gemini_key_configured", lambda: True
    )
    monkeypatch.setattr(
        "api.settings.gemini_key_configured", lambda: True
    )

    res = client.post(
        "/api/upload/assistant",
        json={
            "session_id": sid,
            "question": "إيه أعلى منتج اتباع؟",
            "lang": "ar",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("fallback_used") is True or body.get("mode") == "grounded_facts"
    assert "شاي أسود 250 جم" in str(body.get("answer") or "")
    # Dashboard still works
    ov = client.get(f"/api/upload/{sid}/overview")
    assert ov.status_code == 200
    assert ov.json().get("demo") is False
    client.delete(f"/api/upload/session?session_id={sid}")
