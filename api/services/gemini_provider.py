"""Gemini 2.5 Flash provider — explain aggregate MarketMind facts only.

Never logs or returns the API key. Callers must treat failure as fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from api.settings import (
    GEMINI_API_KEY,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    gemini_key_configured,
)

logger = logging.getLogger("marketmind.gemini")

SYSTEM_INSTRUCTION = """You are MarketMind's senior retail data analyst for any client's uploaded sales file.
Your job: help the shop owner understand THEIR data in plain language, ask clarifying questions when needed,
and suggest provisional decisions grounded only in server-computed aggregates.

Mission:
- Treat each upload as a unique client dataset (currency, dates, products, gaps differ per file).
- Explain what the numbers say, why it may matter operationally, and what they could try next.
- Prefer clear decision options over forcing product features (do not push customer segmentation,
  forecasting, or category charts unless the SAFE_TASK / context already supports them).

Hard rules:
- Answer in the user's selected language (Egyptian-friendly Arabic if lang=ar, otherwise English).
- Use ONLY the JSON context and the SAFE_TASK instruction for MarketMind-specific claims.
- SAFE_TASK is a fixed server template; there is no raw end-user free-text in this request.
- If a fact is missing from context, say you cannot determine it from the available analysis.
- Do not invent row counts, spend totals, customer IDs, invoices, phone numbers, emails, or dates.
- Distinguish historical measured totals from model estimates; never present estimates as guarantees.
- Recommendations are provisional suggestions, not approved business policy.
- Never claim correlation proves causation.
- Do not approve cleaning actions, mutate data, retrain models, or create forecasts.
- When a blank is client-owned (customer ID, invoice date, unknown price with no pattern), say to fill it manually.
- Do not ask for API keys or personal secrets.
- Keep answers concise and practical — like a senior analyst briefing a busy owner.
"""


@dataclass
class GeminiResult:
    ok: bool
    text: str = ""
    model: str | None = None
    error_code: str | None = None
    error_en: str | None = None
    error_ar: str | None = None


def _friendly_error(code: str) -> tuple[str, str]:
    mapping = {
        "missing_key": (
            "Gemini is not configured on this server (no API key). Using grounded facts instead.",
            "Gemini مش متظبط على السيرفر (مفيش مفتاح). هنستخدم الحقائق المحسوبة بدلًا منه.",
        ),
        "invalid_key": (
            "Gemini rejected the API key. Using grounded facts instead.",
            "Gemini رفض مفتاح الـ API. هنستخدم الحقائق المحسوبة بدلًا منه.",
        ),
        "quota": (
            "Gemini quota or rate limit was hit. Using grounded facts instead.",
            "حد استخدام Gemini خلص أو اتأجل الطلب. هنستخدم الحقائق المحسوبة بدلًا منه.",
        ),
        "timeout": (
            "Gemini timed out. Using grounded facts instead.",
            "Gemini اتأخر. هنستخدم الحقائق المحسوبة بدلًا منه.",
        ),
        "upstream": (
            "Gemini had an upstream error. Using grounded facts instead.",
            "حصل خطأ من خدمة Gemini. هنستخدم الحقائق المحسوبة بدلًا منه.",
        ),
        "empty": (
            "Gemini returned an empty answer. Using grounded facts instead.",
            "Gemini رجّع رد فاضي. هنستخدم الحقائق المحسوبة بدلًا منه.",
        ),
        "sdk_missing": (
            "Gemini SDK is not installed. Using grounded facts instead.",
            "مكتبة Gemini مش متثبتة. هنستخدم الحقائق المحسوبة بدلًا منه.",
        ),
    }
    return mapping.get(code, mapping["upstream"])


def classify_provider_error(exc: BaseException) -> str:
    msg = str(exc).lower()
    # Never include raw exception text with possible secrets in user-facing paths
    if "api key" in msg or "unauthorized" in msg or "401" in msg or "permission" in msg:
        return "invalid_key"
    if "429" in msg or "quota" in msg or "rate" in msg or "resource_exhausted" in msg:
        return "quota"
    if "timeout" in msg or "timed out" in msg or "deadline" in msg:
        return "timeout"
    return "upstream"


def generate_explanation(
    *,
    safe_question: str,
    context_json: str,
    lang: str = "en",
    privacy_cleared_user_ask: str | None = None,
) -> GeminiResult:
    """Call Gemini 2.5 Flash with a server template + allowlisted aggregates.

    ``safe_question`` must be a fixed backend template.
    ``privacy_cleared_user_ask`` is optional and only set after the privacy gate.
    Returns ok=False on any failure (never raises to UI).
    """
    if not gemini_key_configured():
        en, ar = _friendly_error("missing_key")
        return GeminiResult(ok=False, error_code="missing_key", error_en=en, error_ar=ar)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        en, ar = _friendly_error("sdk_missing")
        return GeminiResult(ok=False, error_code="sdk_missing", error_en=en, error_ar=ar)

    template = (safe_question or "").strip()[:1500]
    ask = (privacy_cleared_user_ask or "").strip()[:400]
    ask_block = f"PRIVACY_CLEARED_USER_ASK:\n{ask}\n\n" if ask else ""
    user_prompt = (
        f"lang={lang}\n"
        f"CONTEXT_JSON:\n{context_json}\n\n"
        f"SAFE_TASK:\n{template}\n\n"
        f"{ask_block}"
        "Reply using only CONTEXT_JSON facts. Lead with a direct answer. "
        "If unknown, say so. Do not invent product names or numbers."
    )

    try:
        # system_instruction requires v1beta; timeout is milliseconds
        timeout_ms = int(GEMINI_TIMEOUT_SECONDS * 1000)
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                api_version="v1beta",
                timeout=timeout_ms,
            ),
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.3,
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            en, ar = _friendly_error("empty")
            return GeminiResult(ok=False, error_code="empty", error_en=en, error_ar=ar)
        # Soft check: never echo key material if model somehow repeated env (paranoia)
        if GEMINI_API_KEY and GEMINI_API_KEY in text:
            text = text.replace(GEMINI_API_KEY, "[redacted]")
        return GeminiResult(ok=True, text=text, model=GEMINI_MODEL)
    except Exception as exc:  # noqa: BLE001 — map to safe fallback
        code = classify_provider_error(exc)
        en, ar = _friendly_error(code)
        logger.warning("gemini_call_failed code=%s", code)
        return GeminiResult(ok=False, error_code=code, error_en=en, error_ar=ar)


def status_snapshot() -> dict[str, Any]:
    """Public capability status — never includes secrets."""
    configured = gemini_key_configured()
    return {
        "provider": "gemini",
        "model": GEMINI_MODEL,
        "api_key_configured": configured,
        "adapter_implemented": True,
        "adapter_invoked": False,
        "mode": "gemini_ready" if configured else "grounded_facts",
        "label_en": (
            "MarketMind assistant with optional AI explanations (configured). "
            "Chat shows AI-assisted only after a successful call."
            if configured
            else (
                "MarketMind assistant (computed facts). "
                "Set the server-side Gemini API key locally to enable AI explanations."
            )
        ),
        "label_ar": (
            "مساعد MarketMind مع شرح اختياري بالذكاء الاصطناعي (متظبط). "
            "الدردشة بتظهر «بمساعدة ذكاء اصطناعي» بس بعد رد ناجح."
            if configured
            else (
                "مساعد MarketMind (حقائق محسوبة). "
                "حط مفتاح Gemini على السيرفر المحلي عشان الشرح بالذكاء الاصطناعي."
            )
        ),
    }
