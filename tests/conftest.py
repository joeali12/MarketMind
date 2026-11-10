"""Shared pytest fixtures — never call the live Gemini API from automated tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_gemini_credentials(monkeypatch: pytest.MonkeyPatch):
    """Strip host .env keys so tests stay offline and do not spend quota.

    Individual tests that need a fake key re-enable it via monkeypatch.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "")
    # Settings / provider may already be imported with a real key from dotenv.
    try:
        import api.settings as settings

        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    except Exception:  # pragma: no cover
        pass
    try:
        import api.services.gemini_provider as gp

        monkeypatch.setattr(gp, "GEMINI_API_KEY", "")
    except Exception:  # pragma: no cover
        pass
    yield
