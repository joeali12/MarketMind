"""API settings and upload privacy controls."""

from __future__ import annotations

import os
from pathlib import Path

from marketmind.config import PROJECT_ROOT

# Load local .env if present (never commit secrets).
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:  # pragma: no cover
    pass

# Upload privacy (implement before any privacy UI claims)
ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xlsx"})
MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MB
MAX_PREVIEW_ROWS: int = 100_000
UPLOAD_TTL_SECONDS: int = 2 * 60 * 60  # 2 hours
# On Vercel / read-only images, use /tmp (override with UPLOAD_TMP_ROOT).
UPLOAD_TMP_ROOT: Path = Path(
    os.environ.get(
        "UPLOAD_TMP_ROOT",
        "/tmp/marketmind-uploads"
        if os.environ.get("VERCEL") or os.environ.get("MARKETMIND_USE_TMP_UPLOADS") == "1"
        else str(PROJECT_ROOT / "data" / "uploads" / "tmp"),
    )
)

DEMO_BADGE_EN = "Sample UK retail dataset (GBP) — not your live shop."
DEMO_BADGE_AR = "بيانات تجريبية من متجر بريطاني تاريخي (جنيه إسترليني) — مش متجرك الحقيقي."
CURRENCY_CODE = "GBP"
CURRENCY_SYMBOL = "£"
DEMO_PROVENANCE = "UCI Online Retail II (UK historical retail)"

# Upload-store 90-day forecast eligibility (documented, configurable).
# Never apply the bundled UK demo model to uploads.
UPLOAD_FORECAST_WINDOW_DAYS: int = 90
UPLOAD_FORECAST_MIN_SPAN_DAYS: int = 180  # need history + full target window room
UPLOAD_FORECAST_MIN_TRAIN_ROWS: int = 40
UPLOAD_FORECAST_MIN_HOLDOUT_ROWS: int = 20
UPLOAD_FORECAST_CUTOFF_STEP_DAYS: int = 30
UPLOAD_FORECAST_REQUIRE_BEAT_BASELINE: bool = True

# Gemini 2.5 Flash — server-side only. Never expose the key to clients.
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
GEMINI_TIMEOUT_SECONDS: float = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "45"))
GEMINI_MAX_OUTPUT_TOKENS: int = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "1024"))
GEMINI_MAX_CONTEXT_CHARS: int = int(os.environ.get("GEMINI_MAX_CONTEXT_CHARS", "6000"))


def gemini_key_configured() -> bool:
    return bool(GEMINI_API_KEY)


def public_gemini_settings() -> dict:
    """Safe settings snapshot — never includes the API key."""
    return {
        "provider": "gemini",
        "model": GEMINI_MODEL,
        "api_key_configured": gemini_key_configured(),
        "timeout_seconds": GEMINI_TIMEOUT_SECONDS,
        "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
    }
