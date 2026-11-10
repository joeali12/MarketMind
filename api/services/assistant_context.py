"""Allowlisted aggregate context for Gemini — fail closed on privacy violations.

Security boundary is the allowlist + validation, not recursive scrubbing alone.
Never log rejected context contents or user data.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("marketmind.assistant_context")


class ContextPrivacyError(ValueError):
    """Raised when aggregate context fails privacy validation (safe reason code only)."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


# Top-level keys permitted in Gemini context
_ALLOWED_TOP_KEYS = frozenset(
    {
        "source",
        "lang",
        "disclaimer_en",
        "disclaimer_ar",
        "safe_intent",
        "safe_question",
        "privacy_cleared_user_ask",
        "file",
        "structure",
        "findings",
        "cleaning_proposals",
        "baseline",
        "gap_fill_policy",
        "segments",
        "product_leaders",
    }
)

_ALLOWED_FILE_KEYS = frozenset(
    {
        "row_count",
        "column_count",
        "classification_en",
        "classification_ar",
        "classification_confidence",
        "currency_code",
        "currency_selected",
        "date_format_confirmed",
        "profile_confirmed",
        "gap_fill_preference",
        "category_mapped",
    }
)

_ALLOWED_STRUCTURE_KEYS = frozenset(
    {
        "unique_customers",
        "unique_products",
        "unique_invoices",
        "eligible_rows",
        "eligible_spend",
        "cancellation_rows",
    }
)

_ALLOWED_FINDING_KEYS = frozenset(
    {"id", "title_en", "title_ar", "count", "severity"}
)

_ALLOWED_PROPOSAL_KEYS = frozenset(
    {
        "id",
        "title_en",
        "title_ar",
        "rows_affected",
        "destructive",
        "default_accepted",
        "eligible_spend_delta",
    }
)

_ALLOWED_BASELINE_KEYS = frozenset({"rows", "eligible_spend", "currency_code"})

_ALLOWED_GAP_KEYS = frozenset(
    {
        "smart_fillable_count",
        "manual_only_count",
        "unresolved_row_count",
        "note_en",
        "note_ar",
    }
)

_ALLOWED_SEGMENT_KEYS = frozenset(
    {
        "label_en",
        "n_customers",
        "share",
        "spend_share",
        "monetary_mean",
        "recency_mean",
        "frequency_mean",
    }
)

_ALLOWED_PRODUCT_LEADER_KEYS = frozenset(
    {
        "available",
        "currency_code",
        "measure_note_en",
        "measure_note_ar",
        "top_by_units",
        "top_by_revenue",
        "by_units",
        "by_revenue",
    }
)

_ALLOWED_PRODUCT_ROW_KEYS = frozenset({"product_name", "quantity", "spend", "orders"})

_FORBIDDEN_KEY_NAMES = frozenset(
    {
        "invoice",
        "customer_id",
        "stock_code",
        "description",
        "email",
        "phone",
        "address",
        "name",
        "preview_rows",
        "purchase_history",
        "unresolved_preview",
        "products_bought",
        "phone_number",
        "email_address",
    }
)

# Values that look like direct identifiers / contact data
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s\-()]{7,}\d)")
_INVOICE_RE = re.compile(r"\bINV[-_]?\d+", re.I)
_CUSTOMER_ID_RE = re.compile(r"\b(?:CUST|C)[-_]?\d{2,}\b", re.I)

# Lower-priority sections omitted first when bounding size
_BOUND_OMIT_ORDER = (
    "segments",
    "cleaning_proposals",
    "findings",
    "gap_fill_policy",
    "disclaimer_ar",
    "disclaimer_en",
)


def _pick(src: dict[str, Any] | None, allowed: frozenset[str]) -> dict[str, Any]:
    src = src or {}
    return {k: src[k] for k in allowed if k in src}


def build_aggregate_context(
    *,
    profile: dict[str, Any],
    proposals: dict[str, Any] | None,
    analytics: dict[str, Any] | None,
    lang: str,
    safe_intent: str | None = None,
    safe_question: str | None = None,
    privacy_cleared_user_ask: str | None = None,
) -> dict[str, Any]:
    """Build context from explicit allowlists of server-computed aggregates only."""
    structure = profile.get("structure") or {}
    findings = profile.get("findings") or []
    currency = profile.get("currency") or {}
    cls = profile.get("classification") or {}
    proposals_list = (proposals or {}).get("proposals") or []
    baseline = (proposals or {}).get("baseline") or {}
    gap = (proposals or {}).get("gap_fill") or {}
    leaders_src = (analytics or {}).get("product_leaders") if analytics else None

    findings_safe = []
    for f in findings[:20]:
        if not isinstance(f, dict):
            continue
        item = {
            "id": f.get("id"),
            "title_en": f.get("title_en"),
            "title_ar": f.get("title_ar"),
            "count": f.get("count"),
            "severity": f.get("severity"),
        }
        findings_safe.append(_pick(item, _ALLOWED_FINDING_KEYS))

    proposals_safe = []
    for p in proposals_list[:15]:
        if not isinstance(p, dict):
            continue
        item = {
            "id": p.get("id"),
            "title_en": p.get("title_en"),
            "title_ar": p.get("title_ar"),
            "rows_affected": p.get("rows_affected"),
            "destructive": p.get("destructive"),
            "default_accepted": p.get("default_accepted"),
            "eligible_spend_delta": (p.get("estimated_impact") or {}).get(
                "eligible_spend_delta"
            ),
        }
        proposals_safe.append(_pick(item, _ALLOWED_PROPOSAL_KEYS))

    segments: list[dict[str, Any]] = []
    if analytics and isinstance(analytics.get("segments"), list):
        for s in analytics["segments"][:12]:
            if not isinstance(s, dict):
                continue
            item = {
                "label_en": s.get("label_en"),
                "n_customers": s.get("n_customers"),
                "share": s.get("share"),
                "spend_share": s.get("spend_share"),
                "monetary_mean": s.get("monetary_mean"),
                "recency_mean": s.get("recency_mean"),
                "frequency_mean": s.get("frequency_mean"),
            }
            segments.append(_pick(item, _ALLOWED_SEGMENT_KEYS))

    product_leaders: dict[str, Any] | None = None
    if isinstance(leaders_src, dict):

        def _prod_rows(rows: Any) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            if not isinstance(rows, list):
                return out
            for row in rows[:5]:
                if isinstance(row, dict):
                    out.append(_pick(row, _ALLOWED_PRODUCT_ROW_KEYS))
            return out

        top_u = leaders_src.get("top_by_units")
        top_r = leaders_src.get("top_by_revenue")
        product_leaders = _pick(
            {
                "available": leaders_src.get("available"),
                "currency_code": leaders_src.get("currency_code"),
                "measure_note_en": leaders_src.get("measure_note_en"),
                "measure_note_ar": leaders_src.get("measure_note_ar"),
                "top_by_units": _pick(top_u, _ALLOWED_PRODUCT_ROW_KEYS)
                if isinstance(top_u, dict)
                else None,
                "top_by_revenue": _pick(top_r, _ALLOWED_PRODUCT_ROW_KEYS)
                if isinstance(top_r, dict)
                else None,
                "by_units": _prod_rows(leaders_src.get("by_units")),
                "by_revenue": _prod_rows(leaders_src.get("by_revenue")),
            },
            _ALLOWED_PRODUCT_LEADER_KEYS,
        )

    smart_fields = gap.get("smart_fillable_fields") or []
    manual_fields = gap.get("manual_only_fields") or []

    ctx: dict[str, Any] = {
        "source": "upload_session_aggregates",
        "lang": lang if lang in {"ar", "en"} else "en",
        "disclaimer_en": (
            "Numbers below are server-computed. Do not invent additional figures. "
            "Estimates are not guarantees. Correlation is not causation."
        ),
        "disclaimer_ar": (
            "الأرقام دي محسوبة من السيرفر. متخترعش أرقام زيادة. "
            "التقديرات مش ضمان. الارتباط مش سببية."
        ),
        "file": _pick(
            {
                "row_count": profile.get("row_count"),
                "column_count": profile.get("column_count"),
                "classification_en": cls.get("phrase_en"),
                "classification_ar": cls.get("phrase_ar"),
                "classification_confidence": cls.get("confidence"),
                "currency_code": currency.get("code"),
                "currency_selected": currency.get("selected"),
                "date_format_confirmed": profile.get("date_format_confirmed"),
                "profile_confirmed": profile.get("profile_confirmed"),
                "gap_fill_preference": profile.get("gap_fill_preference"),
                "category_mapped": profile.get("category_mapped"),
            },
            _ALLOWED_FILE_KEYS,
        ),
        "structure": _pick(
            {
                "unique_customers": structure.get("unique_customers"),
                "unique_products": structure.get("unique_products"),
                "unique_invoices": structure.get("unique_invoices"),
                "eligible_rows": structure.get("eligible_rows"),
                "eligible_spend": structure.get("eligible_spend"),
                "cancellation_rows": structure.get("cancellation_rows"),
            },
            _ALLOWED_STRUCTURE_KEYS,
        ),
        "findings": findings_safe,
        "cleaning_proposals": proposals_safe,
        "baseline": _pick(
            {
                "rows": baseline.get("rows"),
                "eligible_spend": baseline.get("eligible_spend"),
                "currency_code": baseline.get("currency_code"),
            },
            _ALLOWED_BASELINE_KEYS,
        ),
        "gap_fill_policy": _pick(
            {
                "smart_fillable_count": len(smart_fields)
                if isinstance(smart_fields, list)
                else 0,
                "manual_only_count": len(manual_fields)
                if isinstance(manual_fields, list)
                else 0,
                "unresolved_row_count": len(
                    (proposals or {}).get("unresolved_preview") or []
                ),
                "note_en": gap.get("note_en"),
                "note_ar": gap.get("note_ar"),
            },
            _ALLOWED_GAP_KEYS,
        ),
        "segments": segments,
    }
    if product_leaders is not None:
        ctx["product_leaders"] = product_leaders
    if safe_intent:
        ctx["safe_intent"] = str(safe_intent)
    if safe_question:
        ctx["safe_question"] = str(safe_question)
    if privacy_cleared_user_ask:
        # Bound length; never include if privacy gate failed (caller responsibility)
        ctx["privacy_cleared_user_ask"] = str(privacy_cleared_user_ask).strip()[:400]
    return ctx


def _value_looks_like_identifier(value: str) -> str | None:
    if _EMAIL_RE.search(value):
        return "identifier_like_email"
    if _PHONE_RE.search(value):
        return "identifier_like_phone"
    if _INVOICE_RE.search(value):
        return "identifier_like_invoice"
    if _CUSTOMER_ID_RE.search(value):
        return "identifier_like_customer_id"
    return None


def _walk_validate(obj: Any, *, path: str) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _FORBIDDEN_KEY_NAMES:
                raise ContextPrivacyError("forbidden_key")
            if lk.endswith("_id") and lk not in {"cluster_id"}:
                raise ContextPrivacyError("forbidden_id_key")
            child = f"{path}.{k}" if path else str(k)
            _walk_validate(v, path=child)
        return
    if isinstance(obj, list):
        if len(obj) > 40:
            raise ContextPrivacyError("list_too_long")
        for i, item in enumerate(obj):
            _walk_validate(item, path=f"{path}[{i}]")
        return
    if isinstance(obj, str):
        code = _value_looks_like_identifier(obj)
        if code:
            raise ContextPrivacyError(code)
        if len(obj) > 500:
            raise ContextPrivacyError("string_too_long")
        return
    if isinstance(obj, (int, float, bool)) or obj is None:
        return
    raise ContextPrivacyError("unsupported_value_type")


def assert_context_has_no_identifiers(ctx: dict[str, Any]) -> None:
    """Fail closed: raise ContextPrivacyError with a safe reason code only."""
    if not isinstance(ctx, dict):
        raise ContextPrivacyError("context_not_object")
    unknown = set(ctx.keys()) - _ALLOWED_TOP_KEYS
    if unknown:
        raise ContextPrivacyError("unknown_top_key")

    section_allow = {
        "file": _ALLOWED_FILE_KEYS,
        "structure": _ALLOWED_STRUCTURE_KEYS,
        "baseline": _ALLOWED_BASELINE_KEYS,
        "gap_fill_policy": _ALLOWED_GAP_KEYS,
    }
    for section, allowed in section_allow.items():
        block = ctx.get(section)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise ContextPrivacyError("section_not_object")
        if set(block.keys()) - allowed:
            raise ContextPrivacyError("unknown_section_key")

    for list_key, item_allowed in (
        ("findings", _ALLOWED_FINDING_KEYS),
        ("cleaning_proposals", _ALLOWED_PROPOSAL_KEYS),
        ("segments", _ALLOWED_SEGMENT_KEYS),
    ):
        items = ctx.get(list_key)
        if items is None:
            continue
        if not isinstance(items, list):
            raise ContextPrivacyError("section_not_list")
        for item in items:
            if not isinstance(item, dict):
                raise ContextPrivacyError("list_item_not_object")
            if set(item.keys()) - item_allowed:
                raise ContextPrivacyError("unknown_list_item_key")

    leaders = ctx.get("product_leaders")
    if leaders is not None:
        if not isinstance(leaders, dict):
            raise ContextPrivacyError("section_not_object")
        if set(leaders.keys()) - _ALLOWED_PRODUCT_LEADER_KEYS:
            raise ContextPrivacyError("unknown_section_key")
        for row_key in ("by_units", "by_revenue"):
            rows = leaders.get(row_key)
            if rows is None:
                continue
            if not isinstance(rows, list):
                raise ContextPrivacyError("section_not_list")
            for item in rows:
                if not isinstance(item, dict):
                    raise ContextPrivacyError("list_item_not_object")
                if set(item.keys()) - _ALLOWED_PRODUCT_ROW_KEYS:
                    raise ContextPrivacyError("unknown_list_item_key")
        for single in ("top_by_units", "top_by_revenue"):
            row = leaders.get(single)
            if row is None:
                continue
            if not isinstance(row, dict):
                raise ContextPrivacyError("list_item_not_object")
            if set(row.keys()) - _ALLOWED_PRODUCT_ROW_KEYS:
                raise ContextPrivacyError("unknown_list_item_key")

    _walk_validate(ctx, path="")

    # Serialized checks for residual dumps
    serialized = json.dumps(ctx, ensure_ascii=False)
    for banned in ("preview_rows", "purchase_history", "unresolved_preview"):
        if banned in serialized:
            raise ContextPrivacyError("forbidden_serialized_token")


def context_as_json(ctx: dict[str, Any], *, max_chars: int) -> str:
    """Serialize allowlisted context; omit lower-priority fields to stay in budget.

    Always returns valid JSON, or raises ContextPrivacyError if even the minimal
    core cannot fit.
    """
    if max_chars < 64:
        raise ContextPrivacyError("max_chars_too_small")

    working = dict(ctx)
    assert_context_has_no_identifiers(working)

    def dumps(obj: dict[str, Any]) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    text = dumps(working)
    if len(text) <= max_chars:
        return text

    for key in _BOUND_OMIT_ORDER:
        if key not in working:
            continue
        if key in {"findings", "cleaning_proposals", "segments"}:
            working[key] = []
        else:
            working.pop(key, None)
        working["_omitted_for_size"] = True
        # _omitted_for_size is not in allowlist — strip before validate by using
        # a size marker inside source note instead
        working.pop("_omitted_for_size", None)
        working["source"] = "upload_session_aggregates_bounded"
        assert_context_has_no_identifiers(working)
        text = dumps(working)
        if len(text) <= max_chars:
            return text

    # Last resort: core scalars only
    core = {
        "source": "upload_session_aggregates_minimal",
        "lang": working.get("lang", "en"),
        "safe_intent": working.get("safe_intent"),
        "safe_question": working.get("safe_question"),
        "file": working.get("file") or {},
        "structure": working.get("structure") or {},
        "baseline": working.get("baseline") or {},
        "findings": [],
        "cleaning_proposals": [],
        "segments": [],
        "gap_fill_policy": {},
    }
    # Drop None optional keys
    core = {k: v for k, v in core.items() if v is not None}
    assert_context_has_no_identifiers(core)
    text = dumps(core)
    if len(text) <= max_chars:
        return text
    raise ContextPrivacyError("context_exceeds_budget")
