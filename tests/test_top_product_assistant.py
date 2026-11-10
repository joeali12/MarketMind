"""Top-product assistant intents — deterministic answers from upload leaders."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = Path("/home/youssef/code/test/MarketMind_Egypt_Retail_Test.csv")


def _ready_profile(**extra):
    base = {
        "session_id": "t",
        "row_count": 100,
        "column_count": 8,
        "structure": {
            "unique_customers": 10,
            "unique_products": 5,
            "unique_invoices": 20,
            "eligible_rows": 80,
            "eligible_spend": 1000.0,
        },
        "currency": {"code": "EGP", "selected": True},
        "date_format_confirmed": True,
        "profile_confirmed": True,
        "findings": [],
        "classification": {"phrase_en": "retail", "phrase_ar": "بيع", "confidence": 0.9},
    }
    base.update(extra)
    return base


def _leaders():
    return {
        "available": True,
        "currency_code": "EGP",
        "measure_note_en": "Units = sum of eligible quantity.",
        "measure_note_ar": "الكمية = مجموع الكمية المؤهلة.",
        "top_by_units": {
            "product_name": "Hibiscus Tea 50g",
            "quantity": 120.0,
            "spend": 2400.0,
            "orders": 40,
        },
        "top_by_revenue": {
            "product_name": "Premium Dates Box",
            "quantity": 30.0,
            "spend": 9000.0,
            "orders": 20,
        },
        "by_units": [],
        "by_revenue": [],
    }


def test_arabic_best_seller_by_units_names_product(monkeypatch: pytest.MonkeyPatch):
    from api.services import upload_assistant

    monkeypatch.setattr(
        "api.services.upload_assistant.gemini_key_configured", lambda: False
    )
    result = upload_assistant.answer(
        "إيه أعلى منتج اتباع؟",
        profile=_ready_profile(),
        analytics={"product_leaders": _leaders(), "segments": []},
        lang="ar",
    )
    assert result["unsupported"] is not True
    assert result["gemini_safe_intent"] == "explain_top_product_units"
    assert "Hibiscus Tea 50g" in result["answer_ar"]
    assert "120" in result["answer_ar"]
    # Must not be a generic file summary
    assert "صف و" not in result["answer_ar"] or "Hibiscus" in result["answer_ar"]
    assert result["mode"] == "grounded_facts"


def test_english_top_by_revenue(monkeypatch: pytest.MonkeyPatch):
    from api.services import upload_assistant

    monkeypatch.setattr(
        "api.services.upload_assistant.gemini_key_configured", lambda: False
    )
    result = upload_assistant.answer(
        "What is the top product by revenue?",
        profile=_ready_profile(),
        analytics={"product_leaders": _leaders(), "segments": []},
        lang="en",
    )
    assert result["gemini_safe_intent"] == "explain_top_product_revenue"
    assert "Premium Dates Box" in result["answer_en"]
    assert "9000" in result["answer_en"].replace(",", "")


def test_counts_question_does_not_claim_top_product(monkeypatch: pytest.MonkeyPatch):
    from api.services import upload_assistant

    monkeypatch.setattr(
        "api.services.upload_assistant.gemini_key_configured", lambda: False
    )
    result = upload_assistant.answer(
        "How many products are there?",
        profile=_ready_profile(),
        analytics={"product_leaders": _leaders(), "segments": []},
        lang="en",
    )
    assert result["gemini_safe_intent"] == "explain_counts"
    assert "Hibiscus" not in result["answer_en"]
    assert "5" in result["answer_en"]  # unique_products


@pytest.mark.skipif(not FIXTURE.exists(), reason="Egypt fixture missing")
def test_egypt_fixture_product_leaders_match_assistant():
    from fastapi.testclient import TestClient
    from api.main import app
    from api.services import upload_analytics

    with TestClient(app) as client:
        raw = FIXTURE.read_bytes()
        up = client.post(
            "/api/upload",
            files={"file": ("MarketMind_Egypt_Retail_Test.csv", raw, "text/csv")},
        )
        assert up.status_code == 200
        sid = up.json()["session_id"]
        client.post(
            "/api/upload/settings",
            json={
                "session_id": sid,
                "currency_code": "EGP",
                "date_format": "dayfirst",
                "confirm_date_format": True,
            },
        )
        meta = upload_analytics.get_meta_or_404(sid)
        leaders = upload_analytics.product_leaders(meta)
        assert leaders["available"] is True
        top_u = leaders["top_by_units"]
        assert top_u and top_u["product_name"]
        ask = client.post(
            "/api/upload/assistant",
            json={
                "session_id": sid,
                "question": "إيه أعلى منتج اتباع؟",
                "lang": "ar",
            },
        )
        assert ask.status_code == 200
        body = ask.json()
        answer = str(body.get("answer") or body.get("answer_ar") or "")
        assert top_u["product_name"] in answer
        assert "245" in answer
        assert body.get("unsupported") is not True
        assert body.get("mode") in {"grounded_facts", "gemini"}
        assert "unique_customers=" not in answer
        assert "Gemini ·" not in answer
        client.delete(f"/api/upload/session?session_id={sid}")
