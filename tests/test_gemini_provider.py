"""Gemini provider — mocked only; never calls the live API or needs a real key."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture()
def clear_gemini_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr("api.settings.GEMINI_API_KEY", "")
    monkeypatch.setattr("api.services.gemini_provider.GEMINI_API_KEY", "")
    monkeypatch.setattr(
        "api.services.gemini_provider.gemini_key_configured", lambda: False
    )
    yield


@pytest.fixture()
def fake_key(monkeypatch: pytest.MonkeyPatch):
    key = "test-fake-gemini-key-do-not-use"
    monkeypatch.setenv("GEMINI_API_KEY", key)
    monkeypatch.setattr("api.settings.GEMINI_API_KEY", key)
    monkeypatch.setattr("api.services.gemini_provider.GEMINI_API_KEY", key)
    monkeypatch.setattr(
        "api.services.gemini_provider.gemini_key_configured", lambda: True
    )
    yield key


def test_missing_key_returns_honest_fallback(clear_gemini_key):
    from api.services import gemini_provider

    result = gemini_provider.generate_explanation(
        safe_question="Summarize counts from CONTEXT_JSON.",
        context_json="{}",
        lang="en",
    )
    assert result.ok is False
    assert result.error_code == "missing_key"
    assert "grounded" in (result.error_en or "").lower()
    assert result.error_ar


def test_successful_mocked_response_ok(fake_key, monkeypatch: pytest.MonkeyPatch):
    from api.services import gemini_provider

    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == "gemini-2.5-flash"
            cfg = kwargs["config"]
            assert "Egyptian-friendly Arabic" in cfg.system_instruction
            assert "SAFE_TASK" in kwargs["contents"]
            assert "USER_QUESTION" not in kwargs["contents"]
            assert "Summarize spend" in kwargs["contents"]
            return SimpleNamespace(text="Eligible spend is 100 based on context.")

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs.get("api_key") == fake_key
            self.models = FakeModels()

    import google.genai as genai_mod

    monkeypatch.setattr(genai_mod, "Client", FakeClient)

    result = gemini_provider.generate_explanation(
        safe_question="Summarize spend from CONTEXT_JSON.",
        context_json='{"baseline":{"eligible_spend":100}}',
        lang="en",
    )
    assert result.ok is True
    assert "100" in result.text
    assert result.model == "gemini-2.5-flash"


@pytest.mark.parametrize(
    "exc_msg,code",
    [
        ("401 Unauthorized invalid api key", "invalid_key"),
        ("429 RESOURCE_EXHAUSTED quota exceeded", "quota"),
        ("Deadline exceeded timed out", "timeout"),
        ("connection reset by peer", "upstream"),
    ],
)
def test_provider_errors_map_to_fallback(
    fake_key, monkeypatch: pytest.MonkeyPatch, exc_msg: str, code: str
):
    from api.services import gemini_provider

    class BoomModels:
        def generate_content(self, **kwargs):
            raise RuntimeError(exc_msg)

    class BoomClient:
        def __init__(self, **kwargs):
            self.models = BoomModels()

    import google.genai as genai_mod

    monkeypatch.setattr(genai_mod, "Client", BoomClient)

    result = gemini_provider.generate_explanation(
        safe_question="task", context_json="{}", lang="en"
    )
    assert result.ok is False
    assert result.error_code == code
    assert result.error_en
    assert result.error_ar
    assert fake_key not in (result.error_en or "")
    assert fake_key not in (result.error_ar or "")
    assert fake_key not in (result.text or "")


def test_empty_response_falls_back(fake_key, monkeypatch: pytest.MonkeyPatch):
    from api.services import gemini_provider

    class EmptyModels:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text="   ")

    class EmptyClient:
        def __init__(self, **kwargs):
            self.models = EmptyModels()

    import google.genai as genai_mod

    monkeypatch.setattr(genai_mod, "Client", EmptyClient)
    result = gemini_provider.generate_explanation(
        safe_question="task", context_json="{}", lang="ar"
    )
    assert result.ok is False
    assert result.error_code == "empty"


def test_key_never_in_status_or_logs(fake_key, caplog):
    from api.services import gemini_provider
    from api.settings import public_gemini_settings

    snap = gemini_provider.status_snapshot()
    pub = public_gemini_settings()
    blob = json.dumps({"snap": snap, "pub": pub})
    assert fake_key not in blob
    assert snap.get("api_key") is None
    assert "api_key_configured" in snap
    with caplog.at_level(logging.WARNING):
        gemini_provider.logger.warning("gemini_call_failed code=%s", "upstream")
    assert fake_key not in caplog.text


@pytest.mark.parametrize("lang,needle", [("ar", "Egyptian-friendly Arabic"), ("en", "English")])
def test_language_instruction_in_prompt(
    fake_key, monkeypatch: pytest.MonkeyPatch, lang: str, needle: str
):
    from api.services import gemini_provider

    captured: dict = {}

    class CaptureModels:
        def generate_content(self, **kwargs):
            captured["contents"] = kwargs["contents"]
            captured["system"] = kwargs["config"].system_instruction
            return SimpleNamespace(text="ok")

    class CaptureClient:
        def __init__(self, **kwargs):
            self.models = CaptureModels()

    import google.genai as genai_mod

    monkeypatch.setattr(genai_mod, "Client", CaptureClient)

    gemini_provider.generate_explanation(
        safe_question="Summarize counts from CONTEXT_JSON.",
        context_json="{}",
        lang=lang,
    )
    assert f"lang={lang}" in captured["contents"]
    assert needle in captured["system"]
    assert "SAFE_TASK" in captured["contents"]
    assert "USER_QUESTION" not in captured["contents"]
