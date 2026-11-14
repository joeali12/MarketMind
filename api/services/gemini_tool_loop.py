"""Bounded Gemini tool-calling loop over MarketMind analytics tools.

Credentials stay on the API server. Tool execution is always local and validated.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from api.services import assistant_tools, gemini_provider
from api.services.gemini_provider import GeminiResult, classify_provider_error, _friendly_error
from api.services.upload_store import UploadSessionMeta
from api.settings import (
    GEMINI_API_KEY,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    gemini_key_configured,
)

logger = logging.getLogger("marketmind.gemini_tools")

MAX_TOOL_ROUNDS = 3

OPEN_ASSISTANT_SYSTEM = """You are MarketMind, a senior retail data analyst for the customer's uploaded sales file.
Answer in the user's language (Egyptian-friendly Arabic if lang=ar, else concise English).

You may call approved analytics tools to fetch server-computed facts for THIS upload only.
You may also preview/apply allowlisted data transforms on the temporary upload session file:
- strip_time: remove time-of-day from date/timestamp columns (keep calendar date)
- add_invoice_flag: add a true/false column when invoice total (or row amount) exceeds a threshold
- drop_column / rename_column / cast_numeric / fill_constant (with safety limits)
Workflow: call preview_data_transform first; call apply_data_transform with confirm_apply=true
only when the user clearly asked to apply/do it (e.g. شيل الساعة، ضيف عمود، apply, do it).
Never invent numbers, product names, forecasts, or causes. Use only tool results for file-specific claims.
If a request is ambiguous, ask one short clarifying question.
If data is missing, say what is missing and suggest the next useful step.
Recommendations are provisional suggestions, not policy.
Never claim causation from correlation.
Never expose tool names, JSON payloads, debug keys, or model IDs in the customer-facing answer.
Brand yourself as MarketMind / مساعد MarketMind.
For fill requests: preview first via get_missing_and_fill_preview; only call apply_safe_fills
with confirm_apply=true when the user clearly asked to apply/fill safe values.
Never invent customer IDs, invoices, dates, or transaction quantities.
"""


@dataclass
class ToolLoopResult:
    ok: bool
    text: str = ""
    mode: str = "grounded_facts"
    tools_called: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_en: str | None = None
    error_ar: str | None = None
    mutated: bool = False
    model: str | None = None


def _extract_function_calls(response: Any) -> list[tuple[str, dict[str, Any], str | None]]:
    """Return list of (name, args, call_id)."""
    out: list[tuple[str, dict[str, Any], str | None]] = []
    candidates = getattr(response, "function_calls", None) or []
    if candidates:
        for fc in candidates:
            name = getattr(fc, "name", None) or ""
            args = dict(getattr(fc, "args", None) or {})
            cid = getattr(fc, "id", None)
            if name:
                out.append((name, args, cid))
        return out
    # Fallback: parse candidates/content parts
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if not fc:
                continue
            name = getattr(fc, "name", None) or ""
            args = dict(getattr(fc, "args", None) or {})
            if name:
                out.append((name, args, getattr(fc, "id", None)))
    return out


def run_tool_assisted_turn(
    *,
    question: str,
    lang: str,
    meta: UploadSessionMeta,
    history: list[dict[str, str]] | None = None,
) -> ToolLoopResult:
    """Run up to MAX_TOOL_ROUNDS of Gemini function calling with local tool execution."""
    if not gemini_key_configured():
        en, ar = _friendly_error("missing_key")
        return ToolLoopResult(ok=False, error_code="missing_key", error_en=en, error_ar=ar)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        en, ar = _friendly_error("sdk_missing")
        return ToolLoopResult(ok=False, error_code="sdk_missing", error_en=en, error_ar=ar)

    tools = [
        types.Tool(function_declarations=assistant_tools.gemini_tool_schemas())
    ]
    timeout_ms = int(GEMINI_TIMEOUT_SECONDS * 1000)
    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(api_version="v1beta", timeout=timeout_ms),
    )

    contents: list[Any] = []
    # Bounded privacy-safe history (already scrubbed by caller)
    for turn in (history or [])[-6:]:
        role = "user" if turn.get("role") == "user" else "model"
        text = (turn.get("text") or "").strip()[:400]
        if text:
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text)])
            )

    user_prompt = (
        f"lang={lang}\n"
        f"currency_code={meta.currency_code}\n"
        f"date_format_confirmed={bool(meta.date_format_confirmed)}\n"
        f"USER_REQUEST:\n{(question or '').strip()[:800]}\n\n"
        "Use tools if needed. Answer the request directly using tool facts only. "
        "Never mention or request the upload filename."
    )
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
    )

    tools_called: list[str] = []
    mutated = False
    config = types.GenerateContentConfig(
        system_instruction=OPEN_ASSISTANT_SYSTEM,
        temperature=0.3,
        max_output_tokens=min(GEMINI_MAX_OUTPUT_TOKENS, 1024),
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=config,
            )
            calls = _extract_function_calls(response)
            text = (getattr(response, "text", None) or "").strip()

            if not calls:
                if text:
                    if GEMINI_API_KEY and GEMINI_API_KEY in text:
                        text = text.replace(GEMINI_API_KEY, "[redacted]")
                    return ToolLoopResult(
                        ok=True,
                        text=text,
                        mode="gemini",
                        tools_called=tools_called,
                        mutated=mutated,
                        model=GEMINI_MODEL,
                    )
                en, ar = _friendly_error("empty")
                return ToolLoopResult(
                    ok=False,
                    error_code="empty",
                    error_en=en,
                    error_ar=ar,
                    tools_called=tools_called,
                )

            # Append model turn with function calls
            model_parts = []
            for cand in getattr(response, "candidates", None) or []:
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) or []
                model_parts.extend(parts)
            if model_parts:
                contents.append(types.Content(role="model", parts=model_parts))

            # Execute tools and append responses
            response_parts = []
            for name, args, call_id in calls:
                tools_called.append(name)
                result = assistant_tools.execute_tool(name, meta, args)
                if result.get("mutated"):
                    mutated = True
                payload = json.dumps(result, ensure_ascii=False, default=str)[:4500]
                fr_kwargs: dict[str, Any] = {
                    "name": name,
                    "response": {"result": payload},
                }
                if call_id:
                    fr_kwargs["id"] = call_id
                response_parts.append(
                    types.Part.from_function_response(**fr_kwargs)
                )
            contents.append(types.Content(role="user", parts=response_parts))

        # Exhausted rounds — ask for final prose without more tools
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=(
                            "Tool budget reached. Give the best final customer-facing answer "
                            "from the tool results already obtained. No more tool calls."
                        )
                    )
                ],
            )
        )
        final = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=OPEN_ASSISTANT_SYSTEM,
                temperature=0.2,
                max_output_tokens=min(GEMINI_MAX_OUTPUT_TOKENS, 1024),
            ),
        )
        text = (getattr(final, "text", None) or "").strip()
        if text:
            return ToolLoopResult(
                ok=True,
                text=text,
                mode="gemini",
                tools_called=tools_called,
                mutated=mutated,
                model=GEMINI_MODEL,
            )
        en, ar = _friendly_error("empty")
        return ToolLoopResult(ok=False, error_code="empty", error_en=en, error_ar=ar, tools_called=tools_called)
    except Exception as exc:  # noqa: BLE001
        code = classify_provider_error(exc)
        en, ar = _friendly_error(code)
        logger.warning("gemini_tool_loop_failed code=%s", code)
        return ToolLoopResult(
            ok=False,
            error_code=code,
            error_en=en,
            error_ar=ar,
            tools_called=tools_called,
            mutated=mutated,
        )


def grounded_tool_answer(
    *,
    question: str,
    lang: str,
    meta: UploadSessionMeta,
) -> dict[str, Any]:
    """Deterministic multi-tool fallback when Gemini is unavailable.

    Heuristically selects tools from the question and composes a grounded reply.
    """
    q = (question or "").lower()
    ar = lang == "ar"
    called: list[str] = []
    parts: list[str] = []

    def use(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        called.append(name)
        return assistant_tools.execute_tool(name, meta, args or {})

    if any(k in q for k in ("قارن", "compare", "شهر", "month", "مبيعات", "sales", "spend")):
        r = use("get_sales_kpis", {"compare_previous": True})
        if r.get("ok") and r.get("period_comparison"):
            c = r["period_comparison"]
            if ar:
                parts.append(
                    f"مقارنة المصروف المؤهل: {c['previous_period']} = {c['previous_spend']:.0f} "
                    f"{r.get('currency')} ← {c['current_period']} = {c['current_spend']:.0f} "
                    f"{r.get('currency')} "
                    f"({'%+.1f' % c['spend_pct_change'] + '%' if c.get('spend_pct_change') is not None else 'n/a'})."
                )
            else:
                parts.append(
                    f"Eligible spend comparison: {c['previous_period']} = {c['previous_spend']:.0f} "
                    f"{r.get('currency')} → {c['current_period']} = {c['current_spend']:.0f} "
                    f"{r.get('currency')} "
                    f"({'%+.1f' % c['spend_pct_change'] + '%' if c.get('spend_pct_change') is not None else 'n/a'})."
                )
        elif r.get("ok"):
            m = r.get("metrics") or {}
            parts.append(
                (f"إجمالي المصروف المؤهل {_fmt(m.get('eligible_sales'))} {r.get('currency')}، "
                 f"طلبات {_fmt(m.get('orders'))}، زبائن {_fmt(m.get('customers'))}.")
                if ar
                else (
                    f"Eligible sales {_fmt(m.get('eligible_sales'))} {r.get('currency')}, "
                    f"orders {_fmt(m.get('orders'))}, customers {_fmt(m.get('customers'))}."
                )
            )
        else:
            parts.append(r.get("message_ar") if ar else r.get("message_en") or "")

    if any(k in q for k in ("منتج", "product", "units", "كمية", "إيراد", "revenue", "اتباع", "يبيع")):
        measure = "revenue" if any(k in q for k in ("إيراد", "revenue", "spend", "مصروف")) else "units"
        r = use("get_product_leaders", {"measure": measure, "top_n": 5})
        top = r.get("top") if r.get("ok") else None
        if top and top.get("product_name"):
            if measure == "units":
                parts.append(
                    f"أعلى منتج بالكمية: {top['product_name']} ({_fmt(top.get('quantity'))} وحدة)."
                    if ar
                    else f"Top product by units: {top['product_name']} ({_fmt(top.get('quantity'))} units)."
                )
            else:
                parts.append(
                    f"أعلى منتج بالإيراد المؤهل: {top['product_name']} "
                    f"({_fmt(top.get('spend'))} {r.get('currency')})."
                    if ar
                    else f"Top product by eligible spend: {top['product_name']} "
                    f"({_fmt(top.get('spend'))} {r.get('currency')})."
                )
        elif r.get("ok") is False:
            parts.append(r.get("message_ar") if ar else r.get("message_en") or "")

    if any(k in q for k in ("توقع", "forecast", "prediction")):
        r = use("get_forecast_status")
        if r.get("ok"):
            if r.get("available"):
                parts.append(r.get("label_ar") if ar else r.get("label_en") or "")
            else:
                parts.append(r.get("reason_ar") if ar else r.get("reason_en") or "")

    if any(k in q for k in ("ارجع", "استرجع", "تراجع", "undo", "restore", "rollback")):
        r = use("restore_pre_safe_fill", {"confirm_restore": True})
        parts.append(
            r.get("message_ar") if ar else r.get("message_en") or r.get("message_ar") or ""
        )

    # Allowlisted session-file transforms (date strip, invoice flags, …)
    from api.services import data_transforms as _dx

    parsed = _dx.parse_transform_intent(
        question, pending=getattr(meta, "pending_transform", None)
    )
    if parsed:
        tool_name = (
            "apply_data_transform" if parsed.get("confirm_apply") else "preview_data_transform"
        )
        args = {k: v for k, v in parsed.items() if k != "confirm_apply" and v is not None}
        if parsed.get("confirm_apply"):
            args["confirm_apply"] = True
        r = use(tool_name, args)
        parts.append(
            (r.get("message_ar") if ar else r.get("message_en"))
            or (r.get("preview_ar") if ar else r.get("preview_en"))
            or ""
        )
        if r.get("ok") and r.get("needs_confirm") and ar:
            parts.append("لو موافق، اكتب: طبّق")
        elif r.get("ok") and r.get("needs_confirm"):
            parts.append("If that looks right, reply: apply")

    if any(k in q for k in ("ناقص", "missing", "فراغ", "fill", "املأ", "املئ", "ملء")):
        if any(k in q for k in ("طبّق", "طبق", "apply", "نفّذ", "نفذ", "احفظ الملء")):
            r = use("apply_safe_fills", {"confirm_apply": True})
        else:
            r = use("get_missing_and_fill_preview")
        parts.append(r.get("message_ar") or r.get("note_ar") if ar else r.get("message_en") or r.get("note_en") or "")
        if r.get("ok") and r.get("safe_fill_candidate_count") is not None and ar:
            parts.append(
                f"مرشحات ملء آمن: {r.get('safe_fill_candidate_count')}؛ "
                f"مشاكل يدوية تقريبًا: {r.get('manual_only_issue_count')}."
            )
        elif r.get("ok") and r.get("safe_fill_candidate_count") is not None:
            parts.append(
                f"Safe fill candidates: {r.get('safe_fill_candidate_count')}; "
                f"manual issues ~{r.get('manual_only_issue_count')}."
            )
        if r.get("ok") and r.get("fields_filled") is not None:
            parts.append(
                f"حقول اتملت: {r.get('fields_filled')}؛ تخطّي يدوي: {r.get('skipped_manual_or_unsafe')}؛ "
                f"دليل غير كافي: {r.get('skipped_insufficient_evidence')}."
                if ar
                else f"Fields filled: {r.get('fields_filled')}; skipped manual: {r.get('skipped_manual_or_unsafe')}; "
                f"insufficient evidence: {r.get('skipped_insufficient_evidence')}."
            )

    if any(k in q for k in ("مجموعة", "segment", "group", "inactive", "هامد", "راجع")):
        r = use("get_customer_segments")
        if r.get("ok") and r.get("segments"):
            biggest = max(r["segments"], key=lambda s: int(s.get("n_customers") or 0))
            parts.append(
                f"أكبر مجموعة وصفية: {biggest.get('label_en')} "
                f"({biggest.get('n_customers')} زبون)."
                if ar
                else f"Largest descriptive group: {biggest.get('label_en')} "
                f"({biggest.get('n_customers')} customers)."
            )

    if not parts:
        r = use("get_upload_profile")
        if r.get("ok"):
            parts.append(
                f"الرفع الحالي: حوالي {_fmt(r.get('row_count'))} صف، "
                f"{_fmt(r.get('unique_customers'))} زبون، {_fmt(r.get('unique_products'))} منتج. "
                "اسأل عن المبيعات، المنتجات، المقارنة، التنظيف، أو التوقع."
                if ar
                else f"Current upload: ~{_fmt(r.get('row_count'))} rows, "
                f"{_fmt(r.get('unique_customers'))} customers, {_fmt(r.get('unique_products'))} products. "
                "Ask about sales, products, comparisons, cleaning, or forecast."
            )
        else:
            parts.append(r.get("message_ar") if ar else r.get("message_en") or "")

    answer = "\n".join(p for p in parts if p).strip()
    mutated = (
        "apply_safe_fills" in called
        or "restore_pre_safe_fill" in called
        or "apply_data_transform" in called
    ) and (
        "Applied" in answer
        or "Added" in answer
        or "Stripped" in answer
        or "Dropped" in answer
        or "Renamed" in answer
        or "Filled" in answer
        or "Cast" in answer
        or "اتطبّق" in answer
        or "اتضاف" in answer
        or "اتشال" in answer
        or "اتمسح" in answer
        or "اتغيّر" in answer
        or "اتملت" in answer
        or "اتحوّل" in answer
        or "Restored" in answer
        or "اترجع" in answer
    )
    return {
        "ok": True,
        "answer": answer,
        "tools_called": called,
        "mode": "grounded_facts",
        "mutated": bool(mutated),
    }


def _fmt(n: Any) -> str:
    try:
        f = float(n)
        if abs(f - round(f)) < 1e-9:
            return f"{int(round(f)):,}"
        return f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(n or "—")
