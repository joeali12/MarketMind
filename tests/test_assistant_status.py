"""Honest assistant status — Gemini only when key configured; answers labeled after success."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _clear_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.delenv("MARKETMIND_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MARKETMIND_LLM_API_KEY", raising=False)
    monkeypatch.setattr("api.settings.GEMINI_API_KEY", "")
    monkeypatch.setattr("api.services.gemini_provider.GEMINI_API_KEY", "")
    monkeypatch.setattr(
        "api.services.gemini_provider.gemini_key_configured", lambda: False
    )
    monkeypatch.setattr(
        "api.services.upload_assistant.gemini_key_configured", lambda: False
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    _clear_gemini(monkeypatch)
    from api.main import app

    with TestClient(app) as c:
        yield c


def test_status_grounded_without_provider(client: TestClient):
    from api.services import upload_assistant

    status = upload_assistant.provider_status()
    assert status["mode"] == "grounded_facts"
    assert status["configured"] is False
    assert status["adapter_implemented"] is True
    assert status["adapter_invoked"] is False
    assert status["api_key_configured"] is False
    assert "gemini" in status["label_en"].lower() or "grounded" in status["label_en"].lower()
    body = client.get("/api/upload/assistant/status").json()
    assert body["mode"] == "grounded_facts"
    assert body["configured"] is False
    # Env var *name* may appear in setup copy; never a secret value
    assert "AIza" not in json.dumps(body)
    assert "sk-" not in json.dumps(body)


def test_legacy_env_alone_does_not_enable_gemini(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    _clear_gemini(monkeypatch)
    monkeypatch.setenv("MARKETMIND_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MARKETMIND_LLM_API_KEY", "sk-test-not-real")
    from api.services import upload_assistant

    status = upload_assistant.provider_status()
    assert status["configured"] is False
    assert status["mode"] == "grounded_facts"
    http = client.get("/api/upload/assistant/status").json()
    assert http["configured"] is False
    assert "sk-test-not-real" not in json.dumps(http)


def test_answer_grounded_when_key_missing(monkeypatch: pytest.MonkeyPatch):
    sys.path.insert(0, str(ROOT))
    _clear_gemini(monkeypatch)
    from api.services import upload_assistant

    result = upload_assistant.answer(
        "How many rows?",
        profile={
            "session_id": "test",
            "demo": False,
            "source": "upload",
            "row_count": 10,
            "column_count": 5,
            "structure": {
                "unique_customers": 3,
                "unique_products": 4,
                "unique_invoices": 5,
                "eligible_rows": 8,
                "eligible_spend": 100.0,
            },
            "currency": {"code": "EGP", "selected": True},
            "date_format_confirmed": True,
            "profile_confirmed": True,
            "findings": [],
            "classification": {
                "phrase_en": "retail",
                "phrase_ar": "بيع",
                "confidence": 0.9,
            },
        },
        lang="en",
    )
    assert result["mode"] == "grounded_facts"
    assert result["adapter_invoked"] is False
    assert result["raw_rows_sent_externally"] is False
    assert "test-fake" not in json.dumps(result)


def test_answer_marks_gemini_on_successful_mock(monkeypatch: pytest.MonkeyPatch):
    sys.path.insert(0, str(ROOT))
    import time

    key = "test-fake-gemini-key-do-not-use"
    monkeypatch.setenv("GEMINI_API_KEY", key)
    monkeypatch.setattr("api.settings.GEMINI_API_KEY", key)
    monkeypatch.setattr("api.services.gemini_provider.GEMINI_API_KEY", key)
    monkeypatch.setattr(
        "api.services.gemini_provider.gemini_key_configured", lambda: True
    )
    monkeypatch.setattr(
        "api.services.upload_assistant.gemini_key_configured", lambda: True
    )

    from api.services.gemini_tool_loop import ToolLoopResult
    from api.services.upload_store import UploadSessionMeta

    def fake_loop(**k):
        assert k["lang"] == "en"
        assert "SECRET" not in (k.get("question") or "")
        return ToolLoopResult(
            ok=True,
            text="File has 10 rows (from tools).",
            mode="gemini",
            tools_called=["get_upload_profile"],
        )

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn", fake_loop
    )
    from api.services import upload_assistant

    meta = UploadSessionMeta(
        session_id="test",
        created_at=time.time(),
        filename="t.csv",
        extension=".csv",
        byte_size=10,
        currency_code="EGP",
        date_format="dayfirst",
        date_format_confirmed=True,
    )
    result = upload_assistant.answer(
        "How many rows are in the file?",
        profile={
            "session_id": "test",
            "row_count": 10,
            "column_count": 5,
            "structure": {
                "unique_customers": 3,
                "unique_products": 4,
                "unique_invoices": 5,
                "eligible_rows": 8,
                "eligible_spend": 100.0,
            },
            "currency": {"code": "EGP", "selected": True},
            "date_format_confirmed": True,
            "profile_confirmed": True,
            "findings": [],
            "classification": {
                "phrase_en": "retail",
                "phrase_ar": "بيع",
                "confidence": 0.9,
            },
            "preview_rows": [{"customer_id": "SECRET", "invoice": "INV1"}],
        },
        lang="en",
        meta=meta,
    )
    assert result["mode"] == "gemini"
    assert result["adapter_invoked"] is True
    assert result["fallback_used"] is False
    assert "MarketMind" in result["provider_label_en"]
    assert "AI-assisted" in result["provider_label_en"]
    assert "gemini-2.5-flash" not in json.dumps(result)
    assert key not in json.dumps(result)
    assert "SECRET" not in json.dumps(result)


def test_answer_fallback_on_provider_failure(monkeypatch: pytest.MonkeyPatch):
    sys.path.insert(0, str(ROOT))
    import time

    key = "test-fake-gemini-key-do-not-use"
    monkeypatch.setenv("GEMINI_API_KEY", key)
    monkeypatch.setattr("api.settings.GEMINI_API_KEY", key)
    monkeypatch.setattr("api.services.gemini_provider.GEMINI_API_KEY", key)
    monkeypatch.setattr(
        "api.services.upload_assistant.gemini_key_configured", lambda: True
    )

    from api.services.gemini_tool_loop import ToolLoopResult
    from api.services.upload_store import UploadSessionMeta

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn",
        lambda **k: ToolLoopResult(
            ok=False,
            error_code="quota",
            error_en="Gemini quota or rate limit was hit. Using grounded facts instead.",
            error_ar="حد استخدام",
        ),
    )
    monkeypatch.setattr(
        "api.services.gemini_tool_loop.grounded_tool_answer",
        lambda **k: {
            "answer": "File has 10 rows.",
            "tools_called": ["get_upload_profile"],
            "mutated": False,
        },
    )
    from api.services import upload_assistant

    meta = UploadSessionMeta(
        session_id="test",
        created_at=time.time(),
        filename="t.csv",
        extension=".csv",
        byte_size=10,
        currency_code="EGP",
        date_format="dayfirst",
        date_format_confirmed=True,
    )
    result = upload_assistant.answer(
        "How many rows are in the file?",
        profile={
            "session_id": "test",
            "row_count": 10,
            "column_count": 5,
            "structure": {
                "unique_customers": 3,
                "unique_products": 4,
                "unique_invoices": 5,
                "eligible_rows": 8,
                "eligible_spend": 100.0,
            },
            "currency": {"code": "EGP", "selected": True},
            "date_format_confirmed": True,
            "profile_confirmed": True,
            "findings": [],
            "classification": {
                "phrase_en": "retail",
                "phrase_ar": "بيع",
                "confidence": 0.9,
            },
        },
        lang="en",
        meta=meta,
    )
    assert result.get("unsupported") is not True
    assert result["mode"] == "grounded_facts"
    assert result["fallback_used"] is True
    assert result["fallback_code"] == "quota"
    assert key not in json.dumps(result)


def test_meta_exposes_assistant_without_key(client: TestClient):
    body = client.get("/api/meta").json()
    assert "assistant" in body
    assert body["assistant"]["provider"] == "gemini"
    assert "api_key" not in body["assistant"]
    assert body["assistant"]["api_key_configured"] is False
    assert "api_key" not in body["assistant"]
    dumped = json.dumps(body)
    assert "AIza" not in dumped
