"""Upload assistant: deterministic setup intents + optional Gemini explanations.

Currency, date-format, cleaning, and gap-fill choices are always deterministic.
Open explanatory questions may call Gemini 2.5 Flash with sanitized aggregates.
Gemini never invents facts; failures fall back to grounded answers with honest labels.
"""

from __future__ import annotations

import re
from typing import Any

import logging

from api.services import assistant_context, gemini_intents, gemini_provider
from api.services.assistant_context import ContextPrivacyError
from api.services.upload_store import UploadSessionMeta
from api.settings import GEMINI_MAX_CONTEXT_CHARS, GEMINI_MODEL, gemini_key_configured

logger = logging.getLogger("marketmind.upload_assistant")

# Legacy flag kept for older tests; the real adapter is gemini_provider.
_LLM_ADAPTER_IMPLEMENTED = True

CURRENCY_ALIASES: dict[str, str] = {
    "egp": "EGP",
    "جنيه": "EGP",
    "جنية": "EGP",
    "مصري": "EGP",
    "egypt": "EGP",
    "gbp": "GBP",
    "sterling": "GBP",
    "pound": "GBP",
    "جنيه استرليني": "GBP",
    "usd": "USD",
    "dollar": "USD",
    "دولار": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "يورو": "EUR",
    "sar": "SAR",
    "ريال": "SAR",
    "aed": "AED",
    "درهم": "AED",
    "cad": "CAD",
    "aud": "AUD",
    "other": "OTHER",
    "اخرى": "OTHER",
    "أخرى": "OTHER",
}

DATE_ALIASES: dict[str, str] = {
    "dayfirst": "dayfirst",
    "day first": "dayfirst",
    "dd/mm": "dayfirst",
    "d/m": "dayfirst",
    "يوم اول": "dayfirst",
    "يوم أولا": "dayfirst",
    "يوم أولاً": "dayfirst",
    "يوم/شهر": "dayfirst",
    "يوم شهر": "dayfirst",
    "monthfirst": "monthfirst",
    "month first": "monthfirst",
    "mm/dd": "monthfirst",
    "m/d": "monthfirst",
    "شهر اول": "monthfirst",
    "شهر أولا": "monthfirst",
    "شهر أولاً": "monthfirst",
    "شهر/يوم": "monthfirst",
    "iso": "iso",
    "yyyy-mm-dd": "iso",
}


def provider_status() -> dict[str, Any]:
    """Honest capability status — never claims Gemini unless key is configured.

    Live/Gemini labeling of an answer happens only after a successful provider call.
    """
    snap = gemini_provider.status_snapshot()
    return {
        **snap,
        "configured": bool(snap.get("api_key_configured")),
        "env_api_key_present": bool(snap.get("api_key_configured")),
        "env_provider_name_present": True,  # provider name is always Gemini when used
        "gemini_model": GEMINI_MODEL,
    }


_SETUP_ACTION_TYPES = frozenset(
    {
        "set_currency",
        "set_date_format",
        "confirm_profile",
        "set_gap_fill_preference",
        "set_proposal",
    }
)
_SETUP_AWAIT_FIELDS = frozenset(
    {"currency", "date_format", "profile_confirm", "gap_fill_preference"}
)


def _should_try_gemini(result: dict[str, Any], *, user_question: str) -> tuple[bool, str | None]:
    """Return (ok, skip_reason_code). Never forwards raw user text."""
    # Privacy gate first: identifier-like / pasted-row user text never triggers Gemini
    block = gemini_intents.user_text_blocks_provider(user_question)
    if block:
        return False, block
    if result.get("unsupported"):
        return False, "unsupported"
    actions = result.get("actions") or []
    if any(a.get("type") in _SETUP_ACTION_TYPES for a in actions):
        return False, "setup_action"
    awaits = {a.get("field") for a in actions if a.get("type") == "await"}
    if awaits & _SETUP_AWAIT_FIELDS:
        return False, "await_setup"
    if not result.get("gemini_safe_intent"):
        return False, "no_safe_intent"
    if not gemini_key_configured():
        return False, "missing_key"
    return True, None


def _mark_grounded_skip(result: dict[str, Any], *, reason: str | None) -> dict[str, Any]:
    result.setdefault("adapter_invoked", False)
    result.setdefault("mode", "grounded_facts")
    result["raw_rows_sent_externally"] = False
    result["raw_user_question_sent_externally"] = False
    if reason:
        result["gemini_skip_reason"] = reason
    return result


def _enrich_with_gemini(
    result: dict[str, Any],
    *,
    question: str,
    profile: dict[str, Any],
    proposals: dict[str, Any] | None,
    analytics: dict[str, Any] | None,
    lang: str,
) -> dict[str, Any]:
    """Optionally replace prose with Gemini using a fixed safe template only."""
    ok, skip_reason = _should_try_gemini(result, user_question=question)
    if not ok:
        return _mark_grounded_skip(result, reason=skip_reason)

    intent = gemini_intents.resolve_safe_intent(
        result.get("gemini_safe_intent"), lang=lang
    )
    if intent is None:
        return _mark_grounded_skip(result, reason="unknown_intent")

    safe_question = gemini_intents.template_for(intent, lang=lang)
    # Privacy gate already passed: include a short cleared ask so Gemini
    # explains THIS question using computed facts (never when blocked).
    cleared_ask = (question or "").strip()[:400]
    try:
        ctx = assistant_context.build_aggregate_context(
            profile=profile,
            proposals=proposals,
            analytics=analytics,
            lang=lang,
            safe_intent=intent.id,
            safe_question=safe_question,
            privacy_cleared_user_ask=cleared_ask,
        )
        ctx_json = assistant_context.context_as_json(
            ctx, max_chars=GEMINI_MAX_CONTEXT_CHARS
        )
    except ContextPrivacyError as exc:
        logger.warning("gemini_context_rejected code=%s", exc.reason_code)
        return _mark_grounded_skip(result, reason=exc.reason_code)

    # Defense: never ship key material in context
    from api.settings import GEMINI_API_KEY

    if GEMINI_API_KEY and GEMINI_API_KEY in ctx_json:
        logger.warning("gemini_context_rejected code=key_material")
        return _mark_grounded_skip(result, reason="key_material")

    gem = gemini_provider.generate_explanation(
        safe_question=safe_question,
        context_json=ctx_json,
        lang=lang,
        privacy_cleared_user_ask=cleared_ask,
    )
    if gem.ok and gem.text:
        result["mode"] = "gemini"
        result["adapter_invoked"] = True
        result["provider"] = "gemini"
        result["gemini_model"] = gem.model or GEMINI_MODEL
        result["gemini_safe_intent"] = intent.id
        result["answer"] = gem.text
        result["answer_en"] = gem.text if lang != "ar" else result.get("answer_en", gem.text)
        result["answer_ar"] = gem.text if lang == "ar" else result.get("answer_ar", gem.text)
        result["provider_label_en"] = (
            "MarketMind assistant (AI-assisted) — explains server-computed facts only."
        )
        result["provider_label_ar"] = (
            "مساعد MarketMind (بمساعدة ذكاء اصطناعي) — بيشرح حقائق محسوبة من السيرفر فقط."
        )
        result["fallback_used"] = False
        result["raw_rows_sent_externally"] = False
        # Cleared ask may be included; identifiers/pasted rows never are
        result["raw_user_question_sent_externally"] = False
        result["privacy_cleared_ask_sent"] = True
        result["context_keys"] = sorted(ctx.keys())
        return result

    # Honest fallback — keep grounded answer already computed
    result["mode"] = "grounded_facts"
    result["adapter_invoked"] = False
    result["provider"] = None
    result["fallback_used"] = True
    result["fallback_reason_en"] = gem.error_en
    result["fallback_reason_ar"] = gem.error_ar
    result["fallback_code"] = gem.error_code
    result["raw_user_question_sent_externally"] = False
    status = provider_status()
    result["provider_label_en"] = (
        f"Grounded facts fallback. {gem.error_en or status['label_en']}"
    )
    result["provider_label_ar"] = (
        f"حقائق محسوبة (بديل). {gem.error_ar or status['label_ar']}"
    )
    result["raw_rows_sent_externally"] = False
    return result


def _num(n: Any) -> str:
    try:
        f = float(n)
        if abs(f - round(f)) < 1e-9:
            return f"{int(round(f)):,}"
        return f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(n)


def _detect_currency(q: str) -> str | None:
    q_low = q.lower().strip()
    # Exact code
    for code in ("EGP", "GBP", "USD", "EUR", "SAR", "AED", "CAD", "AUD", "OTHER"):
        if re.search(rf"\b{code.lower()}\b", q_low):
            return code
    for alias, code in CURRENCY_ALIASES.items():
        if alias in q_low:
            return code
    return None


def _detect_date_format(q: str) -> str | None:
    q_low = q.lower().strip()
    # Prefer longer aliases first
    for alias, fmt in sorted(DATE_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in q_low:
            return fmt
    return None


def _currency_selected(profile: dict[str, Any]) -> bool:
    cur = profile.get("currency") or {}
    code = cur.get("code")
    return bool(cur.get("selected")) and code not in (None, "", "UNSPECIFIED")


def _date_ready(profile: dict[str, Any]) -> bool:
    dfmt = profile.get("date_format") or {}
    if dfmt.get("needs_confirmation") and not profile.get("date_format_confirmed"):
        return False
    return True


def _proposal_brief(p: dict[str, Any], *, ar: bool) -> str:
    title = p.get("title_ar") if ar else p.get("title_en")
    reason = p.get("reason_ar") if ar else p.get("reason_en")
    impact = p.get("estimated_impact") or {}
    delta = impact.get("eligible_spend_delta")
    line = f"• {title} — {p.get('rows_affected')} rows"
    if delta is not None:
        line += f" (Δ spend {_num(delta)})"
    if reason:
        line += f". {reason}"
    if p.get("destructive"):
        line += " [destructive — off by default]" if not ar else " [حذف — افتراضيًا مقفول]"
    return line


def _file_brief(profile: dict[str, Any], *, ar: bool) -> str:
    """One-line grounded brief from this upload's profile (not a generic script)."""
    structure = profile.get("structure") or {}
    cls = profile.get("classification") or {}
    findings = profile.get("findings") or []
    rows = _num(profile.get("row_count"))
    customers = _num(structure.get("unique_customers"))
    products = _num(structure.get("unique_products"))
    phrase = (cls.get("phrase_ar") if ar else cls.get("phrase_en")) or ""
    top_findings = []
    for f in findings[:3]:
        if not isinstance(f, dict):
            continue
        title = f.get("title_ar") if ar else f.get("title_en")
        count = f.get("count")
        if title:
            top_findings.append(f"{title} ({_num(count)})" if count is not None else str(title))
    findings_bit = "; ".join(top_findings)
    if ar:
        base = f"الملف ده: ~{rows} صف، {customers} زبون، {products} منتج."
        if phrase:
            base += f" {phrase}"
        if findings_bit:
            base += f" أبرز الملاحظات: {findings_bit}."
        return base
    base = f"This file: ~{rows} rows, {customers} customers, {products} products."
    if phrase:
        base += f" {phrase}"
    if findings_bit:
        base += f" Top findings: {findings_bit}."
    return base


def guide_opening(profile: dict[str, Any], proposals: dict[str, Any] | None, lang: str) -> dict[str, Any]:
    """First assistant turn after upload — ask for the next missing setup step."""
    ar = lang == "ar"
    status = provider_status()
    citations: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    quick: list[str] = []
    brief = _file_brief(profile, ar=ar)
    unresolved_n = len((proposals or {}).get("unresolved_preview") or [])
    plist = (proposals or {}).get("proposals") or []

    if not _currency_selected(profile):
        answer_en = (
            f"{_file_brief(profile, ar=False)}\n\n"
            "I’m your data analyst for this upload. Before totals mean anything: "
            "what currency are the amounts in? Reply EGP, GBP, USD… "
            "(I never guess currency from the numbers)."
        )
        answer_ar = (
            f"{brief}\n\n"
            "أنا محلّل البيانات للملف ده. قبل أي أرقام: المبالغ بعملة إيه؟ "
            "ردّ بـ EGP أو GBP أو USD… (مش بهزر العملة من الأرقام)."
        )
        quick = ["EGP", "GBP", "USD", "EUR", "SAR", "AED"]
        actions.append({"type": "await", "field": "currency"})
    elif not _date_ready(profile):
        answer_en = (
            f"{_file_brief(profile, ar=False)}\n\n"
            "Currency is set. Some invoice dates in THIS file could be day/month or month/day. "
            "Should I read them as day-first (DD/MM), month-first (MM/DD), or ISO (YYYY-MM-DD)?"
        )
        answer_ar = (
            f"{brief}\n\n"
            "العملة اتظبطت. بعض تواريخ الفواتير في الملف ده ممكن تتقري يوم/شهر أو شهر/يوم. "
            "تحب أقراها يوم أول (DD/MM) ولا شهر أول (MM/DD) ولا ISO؟"
        )
        quick = ["dayfirst", "monthfirst", "iso"]
        actions.append({"type": "await", "field": "date_format"})
    elif not profile.get("profile_confirmed"):
        answer_en = (
            f"{_file_brief(profile, ar=False)}\n\n"
            "Does this reading of your business file look right? "
            "Say yes if the row / customer / product picture matches what you expect."
        )
        answer_ar = (
            f"{brief}\n\n"
            "قراءتي لملف شغلك صح؟ قول «صح كده» لو عدد الصفوف/الزباين/المنتجات قريب من اللي متوقعه."
        )
        quick = ["yes correct" if not ar else "صح كده", "not correct" if not ar else "مش صح"]
        actions.append({"type": "await", "field": "profile_confirm"})
    elif not profile.get("gap_fill_preference"):
        if unresolved_n == 0:
            answer_en = (
                "No critical blanks need a client decision right now. "
                "Next I’ll walk cleaning suggestions (safe defaults stay on; destructive stays off). "
                "Or open the dashboard when currency/dates are ready."
            )
            answer_ar = (
                "مفيش فراغات حرجة محتاجة قرار منك دلوقتي. "
                "بعدين هعرض اقتراحات التنظيف (الآمن مفتوح؛ الحذف مقفول). "
                "أو افتح لوحة التحليل لما العملة/التاريخ يكونوا جاهزين."
            )
            quick = [
                "show cleaning" if not ar else "ورّيني التنظيف",
                "accept all safe" if not ar else "اقبل الآمن",
            ]
            actions.append({"type": "await", "field": "cleaning"})
        else:
            answer_en = (
                f"There are {unresolved_n} unresolved rows with critical blanks. "
                "Values only you know (customer IDs, invoice dates, prices with no clear pattern) "
                "must be filled manually — I won’t invent them. "
                "For patterned gaps I can propose smart fills from THIS file only "
                "(median price/qty or common description for the same stock). "
                "Smart fill or manual fill?"
            )
            answer_ar = (
                f"فيه {unresolved_n} صف ناقص بقيم حرجة. "
                "أي قيمة محسومة عندك بس (رقم زبون، تاريخ فاتورة، سعر من غير نمط واضح) "
                "املأها يدوي — مش هتخمّنها. "
                "للفراغات اللي ليها نمط في الملف ده أقدر أقترح ملء ذكي "
                "(وسيط السعر أو أشهر وصف لنفس المنتج — الكمية تفضل يدوي). "
                "ملء ذكي ولا ملء يدوي؟"
            )
            quick = [
                "smart fill" if not ar else "ملء ذكي",
                "manual fill" if not ar else "ملء يدوي",
            ]
            actions.append({"type": "await", "field": "gap_fill_preference"})
    else:
        mode = profile.get("gap_fill_preference")
        manual = str(mode).lower() in {"manual", "manual fill", "ملء يدوي"}
        if plist:
            briefs = "\n".join(_proposal_brief(p, ar=ar) for p in plist[:8])
            if manual:
                answer_en = (
                    "You chose manual fill for client-owned blanks — use the unresolved table "
                    f"({unresolved_n} rows). Cleaning suggestions (review, don’t auto-apply destructive):\n"
                    f"{briefs}\n"
                    "Say “accept all safe” when ready, then open your dashboard."
                )
                answer_ar = (
                    "اختارت ملء يدوي للفراغات المحسومة عندك — استخدم جدول الناقص "
                    f"({unresolved_n} صف). اقتراحات التنظيف (راجعها؛ الحذف مش بيتطبّق لوحده):\n"
                    f"{briefs}\n"
                    "قول «اقبل الآمن» لما تخلص، بعدين افتح لوحة التحليل."
                )
            else:
                answer_en = (
                    f"Gap-fill mode: {mode}. Cleaning suggestions:\n{briefs}\n"
                    f"Unresolved rows still needing attention: {unresolved_n}. "
                    "Client-owned blanks stay manual. Use the table or say “accept all safe”."
                )
                answer_ar = (
                    f"وضع الملء: {mode}. اقتراحات التنظيف:\n{briefs}\n"
                    f"صفوف لسه محتاجة تصرف: {unresolved_n}. "
                    "الفراغات المحسومة عندك تفضل يدوي. استخدم الجدول أو قول «اقبل الآمن»."
                )
            quick = [
                "accept all safe" if not ar else "اقبل الآمن",
                "reject destructive" if not ar else "ارفض الحذف",
            ]
            actions.append({"type": "await", "field": "cleaning"})
        else:
            answer_en = (
                f"Gap-fill mode is {mode}. No bulk cleaning proposals. "
                f"{unresolved_n} unresolved rows — fill those manually in the table, "
                "then open your analysis dashboard."
            )
            answer_ar = (
                f"وضع الملء {mode}. مفيش اقتراحات تنظيف جماعية. "
                f"{unresolved_n} صف ناقص — املأهم يدوي من الجدول، بعدين افتح لوحة التحليل."
            )
            if unresolved_n:
                quick = ["manual fill" if not ar else "ملء يدوي"]

    citations.append({"label": "row_count", "value": profile.get("row_count")})
    return {
        "mode": "grounded_facts",
        "adapter_invoked": False,
        "provider_label_en": status["label_en"],
        "provider_label_ar": status["label_ar"],
        "question": "",
        "answer_en": answer_en,
        "answer_ar": answer_ar,
        "answer": answer_ar if ar else answer_en,
        "citations": citations,
        "actions": actions,
        "quick_replies": quick,
        "unsupported": False,
        "session_id": profile.get("session_id"),
        "demo": False,
        "raw_rows_sent_externally": False,
    }


def _scrub_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Keep a short privacy-safe conversation tail for follow-ups."""
    out: list[dict[str, str]] = []
    for turn in history or []:
        role = turn.get("role")
        text = (turn.get("text") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        if gemini_intents.user_text_blocks_provider(text):
            continue
        out.append({"role": role, "text": text[:400]})
    return out[-6:]


def _analytics_only_grounded(
    question: str,
    *,
    lang: str,
    profile: dict[str, Any],
    analytics: dict[str, Any] | None,
) -> dict[str, Any]:
    """No-meta path: answer from precomputed analytics + profile (tests / offline)."""
    q_low = (question or "").lower()
    structure = profile.get("structure") or {}
    leaders = (analytics or {}).get("product_leaders") or {}
    if re.search(
        r"أعلى منتج|اعلى منتج|best.?sell|top.?product|most.?sold|اتباع|"
        r"highest.?revenue|top product by",
        q_low,
    ):
        wants_revenue = bool(re.search(r"revenue|إيراد|ايراد|spend|مصروف", q_low))
        top = leaders.get("top_by_revenue" if wants_revenue else "top_by_units") or {}
        pname = str(top.get("product_name") or "—")
        cur = leaders.get("currency_code") or "EGP"
        if wants_revenue:
            answer_en = (
                f"Top product by eligible revenue: {pname} "
                f"({_num(top.get('spend'))} {cur}; {_num(top.get('quantity'))} units)."
            )
            answer_ar = (
                f"أعلى منتج بالإيراد المؤهل: {pname} "
                f"({_num(top.get('spend'))} {cur}؛ {_num(top.get('quantity'))} وحدة)."
            )
            intent = "explain_top_product_revenue"
        else:
            answer_en = (
                f"Best-selling product by units: {pname} "
                f"({_num(top.get('quantity'))} units sold; eligible spend "
                f"{_num(top.get('spend'))} {cur})."
            )
            answer_ar = (
                f"أعلى منتج بالكمية المباعة: {pname} "
                f"({_num(top.get('quantity'))} وحدة؛ مصروف مؤهل "
                f"{_num(top.get('spend'))} {cur})."
            )
            intent = "explain_top_product_units"
        return {
            "answer_en": answer_en,
            "answer_ar": answer_ar,
            "mode": "grounded_facts",
            "adapter_invoked": False,
            "tools_called": ["get_product_leaders"],
            "gemini_safe_intent": intent,
            "citations": [],
            "data_mutated": False,
            "quick_replies": [],
        }
    if re.search(r"how many|عدد|كام|rows|customers|products|منتجات|زبون", q_low):
        answer_en = (
            f"Rows: {_num(profile.get('row_count'))}. "
            f"Unique customers (non-null IDs): {_num(structure.get('unique_customers'))}. "
            f"Unique products: {_num(structure.get('unique_products'))}."
        )
        answer_ar = (
            f"الصفوف: {_num(profile.get('row_count'))}. "
            f"زبائن: {_num(structure.get('unique_customers'))}. "
            f"منتجات: {_num(structure.get('unique_products'))}."
        )
        return {
            "answer_en": answer_en,
            "answer_ar": answer_ar,
            "mode": "grounded_facts",
            "adapter_invoked": False,
            "tools_called": ["get_upload_profile"],
            "gemini_safe_intent": "explain_counts",
            "citations": [],
            "data_mutated": False,
            "quick_replies": [],
        }
    return {
        "answer_en": f"File has {_num(profile.get('row_count'))} rows.",
        "answer_ar": f"الملف فيه {_num(profile.get('row_count'))} صف.",
        "mode": "grounded_facts",
        "adapter_invoked": False,
        "tools_called": [],
        "citations": [],
        "data_mutated": False,
        "quick_replies": [],
    }


def _is_session_transform_turn(question: str, meta: UploadSessionMeta | None) -> bool:
    if meta is None:
        return False
    from api.services import data_transforms as _dx
    from api.services import plan_intent, session_mutate

    if getattr(meta, "pending_transform", None) and (question or "").strip().lower() in {
        "apply",
        "do it",
        "confirm",
        "yes",
        "ok",
        "طبّق",
        "طبق",
        "نفّذ",
        "نفذ",
        "موافق",
        "أيوه",
        "ايوه",
        "تمام",
    }:
        return True
    # Soft bilingual reshape cues → route to LLM/tool transform path (not analytics Q&A).
    if plan_intent.soft_reshape_cue(question) or session_mutate.looks_like_mutation(question):
        return True
    parsed = _dx.parse_transform_intent(
        question,
        pending=getattr(meta, "pending_transform", None),
        meta=meta,
        allow_llm=False,
    )
    # Refuse messages still count as a transform turn (do not fall through to cleaning).
    return bool(parsed)


def _transform_turn_result(
    *,
    question: str,
    lang: str,
    meta: UploadSessionMeta | None,
    history: list[dict[str, str]] | None,
    profile: dict[str, Any],
    analytics: dict[str, Any] | None,
    status: dict[str, Any],
    citations: list[dict[str, Any]],
    ar: bool,
) -> dict[str, Any]:
    """Run a session transform via the open-ended path and return a full answer payload."""
    open_result = _open_ended_analytics_turn(
        question=question,
        lang=lang,
        meta=meta,
        history=history,
        profile=profile,
        analytics=analytics,
    )
    answer_en = open_result["answer_en"]
    answer_ar = open_result["answer_ar"]
    citations = list(citations) + list(open_result.get("citations") or [])
    result = {
        "mode": open_result.get("mode", "grounded_facts"),
        "adapter_invoked": bool(open_result.get("adapter_invoked")),
        "provider_label_en": open_result.get("provider_label_en") or status["label_en"],
        "provider_label_ar": open_result.get("provider_label_ar") or status["label_ar"],
        "question": question,
        "answer_en": answer_en,
        "answer_ar": answer_ar,
        "answer": answer_ar if ar else answer_en,
        "citations": citations,
        "actions": open_result.get("actions") or [],
        "quick_replies": list(open_result.get("quick_replies") or []),
        "unsupported": False,
        "gemini_safe_intent": open_result.get("gemini_safe_intent"),
        "tools_called": open_result.get("tools_called") or [],
        "data_mutated": bool(open_result.get("data_mutated")),
        "session_id": profile.get("session_id") or (meta.session_id if meta else None),
        "demo": False,
        "raw_rows_sent_externally": False,
        "raw_user_question_sent_externally": bool(
            open_result.get("raw_user_question_sent_externally")
        ),
        "fallback_used": bool(open_result.get("fallback_used")),
        "privacy_disclosure_en": (
            "When AI assist is on, your question may be sent to Google’s Gemini API "
            "with server-computed aggregates only — never raw transaction rows or personal IDs."
        ),
        "privacy_disclosure_ar": (
            "لما المساعدة الذكية تكون شغالة، سؤالك ممكن يتبعت لـ Gemini من Google "
            "مع مجاميع محسوبة من السيرفر فقط — من غير صفوف خام أو أرقام شخصية."
        ),
    }
    if open_result.get("fallback_reason_en"):
        result["fallback_reason_en"] = open_result["fallback_reason_en"]
        result["fallback_reason_ar"] = open_result.get("fallback_reason_ar")
    if open_result.get("fallback_code"):
        result["fallback_code"] = open_result["fallback_code"]
    if open_result.get("gemini_skip_reason"):
        result["gemini_skip_reason"] = open_result["gemini_skip_reason"]
    return result


def _open_ended_analytics_turn(
    *,
    question: str,
    lang: str,
    meta: UploadSessionMeta | None,
    history: list[dict[str, str]] | None,
    profile: dict[str, Any],
    analytics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tool-assisted open-ended answer with grounded fallback."""
    from api.services import gemini_tool_loop

    status = provider_status()
    ar = lang == "ar"
    safe_history = _scrub_history(history)
    block = gemini_intents.user_text_blocks_provider(question)
    if block:
        # Still honor safe transform commands locally (no Gemini / no raw rows out).
        from api.services import data_transforms as _dx

        parsed = (
            _dx.parse_transform_intent(
                question,
                pending=getattr(meta, "pending_transform", None),
                meta=meta,
                lang=lang,
                allow_llm=False,
            )
            if meta is not None
            else None
        )
        if parsed:
            grounded = gemini_tool_loop.grounded_tool_answer(
                question=question,
                lang=lang,
                meta=meta,
                parsed_intent=parsed,
                allow_llm=False,
            )
            answer = grounded.get("answer") or ""
            return {
                "answer_en": answer,
                "answer_ar": answer,
                "mode": "grounded_facts",
                "adapter_invoked": False,
                "fallback_used": True,
                "fallback_code": block,
                "gemini_skip_reason": block,
                "tools_called": grounded.get("tools_called") or [],
                "data_mutated": bool(grounded.get("mutated")),
                "quick_replies": [
                    "طبّق" if ar else "apply",
                    "قارن الشهر ده باللي قبله" if ar else "compare this month to last",
                ],
                "provider_label_en": status["label_en"],
                "provider_label_ar": status["label_ar"],
                "citations": [],
                "actions": (
                    [{"type": "refresh_after_mutation"}]
                    if grounded.get("mutated")
                    else []
                ),
                "raw_user_question_sent_externally": False,
            }
        msg_en = (
            "I can’t send that question to AI assist because it looks like it may include "
            "identifiers or pasted rows. Rephrase without IDs/emails/phones, or ask about aggregates."
        )
        msg_ar = (
            "مش هقدر أبعت السؤال للمساعدة الذكية لأنه ممكن يحتوي أرقام/صفوف. "
            "صيغه من غير أرقام شخصية أو صفوف ملصوقة، أو اسأل عن مجاميع."
        )
        return {
            "answer_en": msg_en,
            "answer_ar": msg_ar,
            "mode": "grounded_facts",
            "adapter_invoked": False,
            "fallback_used": True,
            "fallback_code": block,
            "gemini_skip_reason": block,
            "tools_called": [],
            "quick_replies": [
                "قارن الشهر ده باللي قبله" if ar else "compare this month to last",
                "إيه أعلى منتج اتباع؟" if ar else "top product by units",
            ],
            "provider_label_en": status["label_en"],
            "provider_label_ar": status["label_ar"],
            "citations": [],
            "data_mutated": False,
            "raw_user_question_sent_externally": False,
        }

    if meta is None:
        grounded = _analytics_only_grounded(
            question, lang=lang, profile=profile, analytics=analytics
        )
        grounded["raw_user_question_sent_externally"] = False
        return grounded

    # Session transforms take priority over open Q&A so reshape asks never
    # fall through to generic upload stats. Compile once, then execute.
    from api.services import data_transforms as _dx

    parsed = (
        _dx.parse_transform_intent(
            question,
            pending=getattr(meta, "pending_transform", None),
            meta=meta,
            lang=lang,
            allow_llm=True,
        )
        if meta is not None
        else None
    )
    if parsed:
        grounded = gemini_tool_loop.grounded_tool_answer(
            question=question,
            lang=lang,
            meta=meta,
            parsed_intent=parsed,
            allow_llm=False,
        )
        answer = grounded.get("answer") or ""
        sent_externally = bool(parsed.get("compiled_via_llm"))
        return {
            "answer_en": answer,
            "answer_ar": answer,
            "mode": "grounded_facts",
            "adapter_invoked": False,
            "fallback_used": False,
            "tools_called": grounded.get("tools_called") or [],
            "data_mutated": bool(grounded.get("mutated")),
            "quick_replies": [
                "طبّق" if ar else "apply",
                "شيل الساعة من التاريخ" if ar else "strip time from dates",
                "رتب حسب InvoiceDate" if ar else "sort by InvoiceDate",
                "ضيف عمود high = Quantity * Price > 500"
                if ar
                else "add column high = Quantity * Price > 500",
            ],
            "provider_label_en": "MarketMind (session transforms)",
            "provider_label_ar": "مساعد MarketMind (تحويلات الجلسة)",
            "citations": [],
            "actions": (
                [{"type": "refresh_after_mutation"}]
                if grounded.get("mutated")
                else []
            ),
            "raw_user_question_sent_externally": sent_externally,
        }

    loop = gemini_tool_loop.run_tool_assisted_turn(
        question=question,
        lang=lang,
        meta=meta,
        history=safe_history,
    )
    if loop.ok and loop.text:
        text = loop.text
        return {
            "answer_en": text if lang != "ar" else text,
            "answer_ar": text if lang == "ar" else text,
            "mode": "gemini",
            "adapter_invoked": True,
            "fallback_used": False,
            "tools_called": loop.tools_called,
            "data_mutated": loop.mutated,
            "quick_replies": [
                "قارن الشهر ده باللي قبله" if ar else "compare this month to last",
                "ورّيني ملء آمن" if ar else "preview safe fills",
                "ليه التوقع مش متاح؟" if ar else "why is forecast unavailable?",
            ],
            "provider_label_en": "MarketMind assistant (AI-assisted)",
            "provider_label_ar": "مساعد MarketMind (بمساعدة ذكاء اصطناعي)",
            "citations": [{"label": "tools_called", "value": loop.tools_called}],
            "actions": (
                [{"type": "refresh_after_mutation"}] if loop.mutated else []
            ),
            "raw_user_question_sent_externally": True,
        }

    # Tool loop already tried Gemini with the user question when a key is set;
    # do not compile again via LLM on the grounded fallback.
    grounded = gemini_tool_loop.grounded_tool_answer(
        question=question, lang=lang, meta=meta, allow_llm=False
    )
    answer = grounded.get("answer") or (
        "I couldn’t complete AI assist; here are computed facts from your upload."
        if not ar
        else "المساعدة الذكية متاحتش؛ دي حقائق محسوبة من ملفك."
    )
    sent_externally = loop.error_code not in {
        "missing_key",
        "sdk_missing",
    } or bool(grounded.get("compiled_via_llm"))
    return {
        "answer_en": answer if not ar else answer,
        "answer_ar": answer if ar else answer,
        "mode": "grounded_facts",
        "adapter_invoked": False,
        "fallback_used": True,
        "fallback_code": loop.error_code,
        "fallback_reason_en": loop.error_en,
        "fallback_reason_ar": loop.error_ar,
        "tools_called": grounded.get("tools_called") or [],
        "data_mutated": bool(grounded.get("mutated")),
        "quick_replies": [
            "قارن الشهر ده باللي قبله" if ar else "compare this month to last",
            "إيه أعلى منتج اتباع؟" if ar else "top product by units",
        ],
        "provider_label_en": (
            f"MarketMind (computed facts). {loop.error_en or status['label_en']}"
        ),
        "provider_label_ar": (
            f"مساعد MarketMind (حقائق محسوبة). {loop.error_ar or status['label_ar']}"
        ),
        "citations": [],
        "actions": (
            [{"type": "refresh_after_mutation"}] if grounded.get("mutated") else []
        ),
        "raw_user_question_sent_externally": bool(sent_externally),
    }


def answer(
    question: str,
    *,
    profile: dict[str, Any],
    proposals: dict[str, Any] | None = None,
    analytics: dict[str, Any] | None = None,
    lang: str = "en",
    meta: UploadSessionMeta | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Answer from upload artifacts; open-ended analytics via validated tools."""
    status = provider_status()
    q = (question or "").strip()
    q_low = q.lower()
    ar = lang == "ar"
    proposals_list = (proposals or {}).get("proposals") or []

    if profile.get("demo") or profile.get("source") == "demo":
        return {
            "mode": "grounded_facts",
            "adapter_invoked": False,
            "provider_label_en": status["label_en"],
            "provider_label_ar": status["label_ar"],
            "answer_en": "I only answer about the selected upload here, not the UK demo sample.",
            "answer_ar": "بجاوب هنا عن الملف المرفوع المختار، مش عن عينة العرض البريطانية.",
            "citations": [],
            "actions": [],
            "quick_replies": [],
            "unsupported": False,
            "demo": True,
            "raw_rows_sent_externally": False,
        }

    structure = profile.get("structure") or {}
    findings = profile.get("findings") or []
    currency = (profile.get("currency") or {}).get("code") or "UNSPECIFIED"
    citations: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    quick: list[str] = []
    answer_en = ""
    answer_ar = ""
    unsupported = False
    gemini_safe_intent: str | None = None

    def cite(label: str, value: Any) -> None:
        citations.append({"label": label, "value": value})

    # --- Guided setup: currency ---
    detected_cur = _detect_currency(q)
    currency_codes = {c.lower() for c in ("EGP", "GBP", "USD", "EUR", "SAR", "AED", "CAD", "AUD", "OTHER")}
    if detected_cur and (
        not _currency_selected(profile)
        or re.search(r"currency|عملة|currenc|غيّر العملة|غير العملة", q_low)
        or q_low.strip() in currency_codes
    ):
        actions.append({"type": "set_currency", "currency_code": detected_cur})
        answer_en = (
            f"Got it — amounts in this file are treated as {detected_cur}. "
            "I never convert FX. "
        )
        answer_ar = f"تمام — هعتبر المبالغ في الملف {detected_cur}. مفيش تحويل عملة. "
        cite("currency_code", detected_cur)
        if not _date_ready(profile):
            answer_en += (
                "Next: should invoice dates be day-first (DD/MM), month-first (MM/DD), or ISO?"
            )
            answer_ar += "بعدين: تواريخ الفواتير يوم أول (DD/MM) ولا شهر أول (MM/DD) ولا ISO؟"
            quick = ["dayfirst", "monthfirst", "iso"]
            actions.append({"type": "await", "field": "date_format"})
        else:
            answer_en += "Ask me about cleaning gaps, or say “show cleaning”."
            answer_ar += "اسألني عن فراغات التنظيف، أو قول «ورّيني التنظيف»."
            quick = ["show cleaning" if not ar else "ورّيني التنظيف"]

    # --- Guided setup: date format ---
    elif (detected_fmt := _detect_date_format(q)) and (
        not _date_ready(profile)
        or re.search(r"date|تاريخ|dayfirst|monthfirst|\biso\b", q_low)
    ):
        actions.append(
            {"type": "set_date_format", "date_format": detected_fmt, "confirm": True}
        )
        answer_en = f"Confirmed date format: {detected_fmt}. "
        answer_ar = f"اتأكدت صيغة التاريخ: {detected_fmt}. "
        cite("date_format", detected_fmt)
        answer_en += (
            "Please confirm: does my reading of this file look correct "
            "(row counts / products / customers)?"
        )
        answer_ar += "أكّدلي: قراءتي للملف صح؟ (عدد الصفوف / المنتجات / الزباين)؟"
        quick = ["yes correct" if not ar else "صح كده", "not correct" if not ar else "مش صح"]
        actions.append({"type": "await", "field": "profile_confirm"})

    # --- Confirm file summary ---
    elif re.search(
        r"\byes\b|correct|صح|أيوه|ايوه|تمام كده|صح كده|yes correct|looks good|موافق",
        q_low,
    ) and not profile.get("profile_confirmed"):
        actions.append({"type": "confirm_profile", "confirmed": True})
        unresolved_n = len((proposals or {}).get("unresolved_preview") or [])
        if unresolved_n == 0:
            answer_en = (
                "Thanks — summary marked correct. No critical blanks need a client decision. "
                "Say “show cleaning” to review safe proposals, then open your analysis dashboard."
            )
            answer_ar = (
                "شكرًا — الملخص اتعلم إنه صح. مفيش فراغات حرجة محتاجة قرار منك. "
                "قول «ورّيني التنظيف» لمراجعة الاقتراحات الآمنة، بعدين افتح لوحة التحليل."
            )
            quick = [
                "show cleaning" if not ar else "ورّيني التنظيف",
                "accept all safe" if not ar else "اقبل الآمن",
            ]
            actions.append({"type": "await", "field": "cleaning"})
        else:
            answer_en = (
                f"Thanks — summary marked correct. {unresolved_n} unresolved rows need attention. "
                "Anything only you know (customer IDs, dates, unclear prices) → fill manually. "
                "Patterned gaps can use smart fill from this file only. Smart fill or manual fill?"
            )
            answer_ar = (
                f"شكرًا — الملخص اتعلم إنه صح. فيه {unresolved_n} صف ناقص محتاجين تصرف. "
                "أي قيمة محسومة عندك (رقم زبون/تاريخ/سعر غامض) → املأها يدوي. "
                "الفراغات اللي ليها نمط في الملف: ملء ذكي. ملء ذكي ولا ملء يدوي؟"
            )
            quick = ["smart fill" if not ar else "ملء ذكي", "manual fill" if not ar else "ملء يدوي"]
            actions.append({"type": "await", "field": "gap_fill_preference"})

    elif re.search(r"not correct|wrong|مش صح|غلط|لا مش", q_low) and not profile.get(
        "profile_confirmed"
    ):
        actions.append({"type": "confirm_profile", "confirmed": False})
        answer_en = (
            "OK — I won’t treat the summary as confirmed. Tell me what looks wrong "
            "(currency, dates, counts), or ask about specific findings."
        )
        answer_ar = (
            "تمام — مش هعتبر الملخص مؤكد. قولّي إيه الغلط "
            "(عملة، تواريخ، أعداد)، أو اسأل عن ملاحظة معينة."
        )

    # --- Gap fill preference ---
    elif re.search(r"smart fill|ملء ذكي|ملئ ذكي|اقتراح ذكي|ذكاء", q_low) or (
        profile.get("profile_confirmed")
        and not profile.get("gap_fill_preference")
        and re.search(r"\bsmart\b|ذكي", q_low)
    ):
        actions.append({"type": "set_gap_fill_preference", "preference": "smart"})
        answer_en = (
            "Smart-fill mode on. In the unresolved table, review suggested values "
            "(with evidence). Apply all smart suggestions or edit cells, then Save. "
            "Customer IDs and invoice dates stay manual-only."
        )
        answer_ar = (
            "وضع الملء الذكي شغال. في جدول الصفوف الناقصة راجع القيم المقترحة "
            "(مع الدليل). طبّق كل الاقتراحات الذكية أو عدّل الخلايا، بعدين احفظ. "
            "رقم الزبون وتاريخ الفاتورة يدوي فقط."
        )
        quick = ["show cleaning" if not ar else "ورّيني التنظيف"]

    elif re.search(r"manual fill|ملء يدوي|ملئ يدوي|يدوي", q_low) or (
        profile.get("profile_confirmed")
        and not profile.get("gap_fill_preference")
        and re.search(r"\bmanual\b|بنفسى|بنفسي", q_low)
    ):
        actions.append({"type": "set_gap_fill_preference", "preference": "manual"})
        answer_en = (
            "Manual-fill mode on. Type missing values in the unresolved table and Save to the session file. "
            "I still won’t invent customer IDs or dates for you."
        )
        answer_ar = (
            "وضع الملء اليدوي شغال. اكتب القيم الناقصة في الجدول واحفظها في ملف الجلسة. "
            "لسه مش هخترعلك رقم زبون أو تاريخ."
        )
        quick = ["show cleaning" if not ar else "ورّيني التنظيف"]

    # --- Session transforms (before cleaning «apply» / «طبّق») ---
    elif _is_session_transform_turn(q, meta):
        return _transform_turn_result(
            question=q,
            lang=lang,
            meta=meta,
            history=history,
            profile=profile,
            analytics=analytics,
            status=status,
            citations=citations,
            ar=ar,
        )

    # --- Show / walk cleaning ---
    elif re.search(
        r"clean|تنظيف|propos|اقتراح|gap|فراغ|show cleaning|ورّيني التنظيف|وريني التنظيف",
        q_low,
    ):
        if not proposals_list:
            answer_en = "No cleaning proposals for this session yet."
            answer_ar = "مفيش اقتراحات تنظيف للجلسة دي لسه."
        else:
            briefs = "\n".join(_proposal_brief(p, ar=ar) for p in proposals_list)
            unresolved_n = len((proposals or {}).get("unresolved_preview") or [])
            answer_en = (
                "Cleaning suggestions (fixed policy rules — critical values are never invented):\n"
                f"{briefs}\n"
                f"Unresolved rows shown below: {unresolved_n}. "
                "How do you want to handle these gaps?"
            )
            answer_ar = (
                "اقتراحات التنظيف (قواعد ثابتة — القيم الحرجة مش بتتولَّد):\n"
                f"{briefs}\n"
                f"الصفوف الناقصة معروضة تحت: {unresolved_n}. "
                "حابب تتصرف في الفراغات دي إزاي؟"
            )
            for p in proposals_list:
                cite(str(p.get("id")), p.get("rows_affected"))
            quick = [
                "accept all safe" if not ar else "اقبل الآمن",
                "reject destructive" if not ar else "ارفض الحذف",
                "keep defaults" if not ar else "سيب الافتراضي",
            ]
            actions.append({"type": "await", "field": "cleaning"})

    # --- Accept / reject cleaning ---
    elif re.search(
        r"accept|reject|اقبل|ارفض|apply|طبّق|طبق|safe|destructive|افتراضي|defaults",
        q_low,
    ):
        if not proposals_list:
            answer_en = "No proposals to adjust."
            answer_ar = "مفيش اقتراحات للتعديل."
        else:
            ids = {str(p.get("id")): p for p in proposals_list}
            changed: list[str] = []
            if re.search(r"accept all safe|اقبل الآمن|اقبل الامن", q_low):
                for pid, p in ids.items():
                    if not p.get("destructive"):
                        actions.append(
                            {"type": "set_proposal", "proposal_id": pid, "accepted": True}
                        )
                        changed.append(f"accept {pid}")
            if re.search(r"reject destructive|ارفض الحذف|ارفض الهدام", q_low):
                for pid, p in ids.items():
                    if p.get("destructive"):
                        actions.append(
                            {"type": "set_proposal", "proposal_id": pid, "accepted": False}
                        )
                        changed.append(f"reject {pid}")
            if re.search(r"keep defaults|default|افتراضي|سيب الافتراضي", q_low):
                for pid, p in ids.items():
                    actions.append(
                        {
                            "type": "set_proposal",
                            "proposal_id": pid,
                            "accepted": bool(p.get("default_accepted"))
                            and not p.get("destructive"),
                        }
                    )
                    changed.append(f"default {pid}")
            # Per-id: accept foo / reject bar
            for m in re.finditer(r"(accept|reject|اقبل|ارفض)\s+([a-zA-Z0-9_\-]+)", q_low):
                verb, pid = m.group(1), m.group(2)
                if pid in {"all", "safe", "destructive", "defaults", "الآمن", "الامن", "الحذف"}:
                    continue
                # fuzzy match proposal id
                match_id = next(
                    (k for k in ids if k.lower() == pid or pid in k.lower()), None
                )
                if match_id:
                    acc = verb in {"accept", "اقبل"}
                    actions.append(
                        {"type": "set_proposal", "proposal_id": match_id, "accepted": acc}
                    )
                    changed.append(f"{'accept' if acc else 'reject'} {match_id}")
            if not changed and actions:
                pass
            if not actions:
                answer_en = (
                    "Tell me which proposals to accept/reject. "
                    "Example: “accept all safe” or “reject drop_invalid_dates”."
                )
                answer_ar = (
                    "قولّي أنهي اقتراحات أقبل/أرفض. "
                    "مثال: «اقبل الآمن» أو «ارفض drop_invalid_dates»."
                )
                quick = ["accept all safe" if not ar else "اقبل الآمن"]
            else:
                answer_en = (
                    "Updated cleaning choices: "
                    + "; ".join(changed)
                    + ". Unresolved rows stay visible — I never invent missing IDs, prices, or dates."
                )
                answer_ar = (
                    "اتحدّثت اختيارات التنظيف: "
                    + "؛ ".join(changed)
                    + ". الصفوف الناقصة تفضل ظاهرة — مش هنتخمّن أرقام أو أسعار أو تواريخ."
                )
                cite("proposal_updates", len(actions))

    elif re.search(r"\bdemo\b|\buk\b|britain|بريطان|عرض البريطان|uk demo", q_low):
        answer_en = (
            "This assistant only uses your upload session facts. "
            "It does not mix in UK demo metrics."
        )
        answer_ar = (
            "المساعد ده بيستخدم حقائق جلسة الرفع بس. "
            "مش بيخلط معاها أرقام عينة العرض البريطانية."
        )

    elif not answer_en and (
        not _currency_selected(profile) or not _date_ready(profile)
    ) and not re.search(
        r"قارن|compare|منتج|product|توقع|forecast|ناقص|missing|ملء|fill|"
        r"مبيعات|sales|مجموعة|segment|لخّص|لخص|summary|next|بعدين",
        q_low,
    ):
        # Incomplete setup and not clearly an analytics ask — nudge setup
        if not _currency_selected(profile):
            answer_en = (
                "Before other questions: what currency is this file in? "
                "(EGP, GBP, USD…) — I won’t invent it."
            )
            answer_ar = (
                "قبل أي سؤال تاني: الملف بعملة إيه؟ "
                "(EGP، GBP، USD…) — مش هتتخمّن."
            )
            quick = ["EGP", "GBP", "USD", "EUR"]
            actions.append({"type": "await", "field": "currency"})
        else:
            answer_en = (
                "Next I need the invoice date format: day-first, month-first, or ISO?"
            )
            answer_ar = "محتاج صيغة تاريخ الفاتورة: يوم أول، شهر أول، ولا ISO؟"
            quick = ["dayfirst", "monthfirst", "iso"]
            actions.append({"type": "await", "field": "date_format"})

    elif not answer_en:
        # Open-ended analytics: tool-assisted Gemini or grounded tool fallback
        open_result = _open_ended_analytics_turn(
            question=q,
            lang=lang,
            meta=meta,
            history=history,
            profile=profile,
            analytics=analytics,
        )
        answer_en = open_result["answer_en"]
        answer_ar = open_result["answer_ar"]
        citations.extend(open_result.get("citations") or [])
        quick = list(open_result.get("quick_replies") or [])
        result = {
            "mode": open_result.get("mode", "grounded_facts"),
            "adapter_invoked": bool(open_result.get("adapter_invoked")),
            "provider_label_en": open_result.get("provider_label_en") or status["label_en"],
            "provider_label_ar": open_result.get("provider_label_ar") or status["label_ar"],
            "question": q,
            "answer_en": answer_en,
            "answer_ar": answer_ar,
            "answer": answer_ar if ar else answer_en,
            "citations": citations,
            "actions": open_result.get("actions") or [],
            "quick_replies": quick,
            "unsupported": False,
            "gemini_safe_intent": open_result.get("gemini_safe_intent"),
            "tools_called": open_result.get("tools_called") or [],
            "data_mutated": bool(open_result.get("data_mutated")),
            "session_id": profile.get("session_id") or (meta.session_id if meta else None),
            "demo": False,
            "raw_rows_sent_externally": False,
            "raw_user_question_sent_externally": False,
            "fallback_used": bool(open_result.get("fallback_used")),
            "privacy_disclosure_en": (
                "When AI assist is on, your question may be sent to Google’s Gemini API "
                "with server-computed aggregates only — never raw transaction rows or personal IDs."
            ),
            "privacy_disclosure_ar": (
                "لما المساعدة الذكية تكون شغالة، سؤالك ممكن يتبعت لـ Gemini من Google "
                "مع مجاميع محسوبة من السيرفر فقط — من غير صفوف خام أو أرقام شخصية."
            ),
        }
        if open_result.get("fallback_reason_en"):
            result["fallback_reason_en"] = open_result["fallback_reason_en"]
            result["fallback_reason_ar"] = open_result.get("fallback_reason_ar")
        if open_result.get("fallback_code"):
            result["fallback_code"] = open_result["fallback_code"]
        if open_result.get("gemini_skip_reason"):
            result["gemini_skip_reason"] = open_result["gemini_skip_reason"]
        return result

    result = {
        "mode": "grounded_facts",
        "adapter_invoked": False,
        "provider_label_en": status["label_en"],
        "provider_label_ar": status["label_ar"],
        "question": q,
        "answer_en": answer_en,
        "answer_ar": answer_ar,
        "answer": answer_ar if ar else answer_en,
        "citations": citations,
        "actions": actions,
        "quick_replies": quick,
        "unsupported": unsupported,
        "gemini_safe_intent": gemini_safe_intent,
        "session_id": profile.get("session_id"),
        "demo": False,
        "raw_rows_sent_externally": False,
        "raw_user_question_sent_externally": False,
        "fallback_used": False,
    }
    return _enrich_with_gemini(
        result,
        question=q,
        profile=profile,
        proposals=proposals,
        analytics=analytics,
        lang=lang,
    )
