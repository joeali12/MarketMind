"""Single canonical load path for upload sessions (profile/clean/analytics/tools)."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import pandas as pd

from api.services import cleaning_proposals as clean_svc
from api.services import column_mapping as cmap
from api.services import pos_ingest
from api.services.upload_store import UploadSessionMeta, save_meta, upload_path
from marketmind.config import SOURCE_COLUMN_MAP
from marketmind.data.cleaning import eligible_positive_spend_mask


def read_raw_source(meta: UploadSessionMeta, *, nrows: int | None = None) -> pd.DataFrame:
    path = upload_path(meta.session_id)
    return pos_ingest.read_upload_source(
        path, sheet_name=meta.selected_sheet, nrows=nrows
    )


def ensure_workbook_meta(meta: UploadSessionMeta) -> UploadSessionMeta:
    """Populate workbook sheet list; clear invalid selection."""
    path = upload_path(meta.session_id)
    info = pos_ingest.workbook_info(path)
    if not info["is_workbook"]:
        meta.workbook_sheets = []
        meta.selected_sheet = None
        return meta
    sheets = list(info["sheets"])
    meta.workbook_sheets = sheets
    if len(sheets) == 1:
        meta.selected_sheet = sheets[0]
    elif meta.selected_sheet and meta.selected_sheet not in sheets:
        meta.selected_sheet = None
    return meta


def needs_sheet_selection(meta: UploadSessionMeta) -> bool:
    sheets = meta.workbook_sheets or []
    return len(sheets) > 1 and not meta.selected_sheet


def default_uci_mapping_if_exact(columns: list[str]) -> dict[str, str] | None:
    """If headers exactly match UCI Online Retail II, return the known map."""
    present = set(map(str, columns))
    required = set(SOURCE_COLUMN_MAP.values())
    if required.issubset(present):
        return {canon: src for canon, src in SOURCE_COLUMN_MAP.items()}
    return None


def resolve_mapping(meta: UploadSessionMeta, columns: list[str]) -> dict[str, Any]:
    """Return suggestion payload + effective mapping for this session."""
    suggestions = cmap.suggest_mappings(columns)
    uci = default_uci_mapping_if_exact(columns)
    if meta.column_mapping:
        effective = dict(meta.column_mapping)
    elif uci:
        effective = uci
    else:
        effective = dict(suggestions.get("auto_mapping") or {})
    # Category convenience
    if meta.category_column and "category" not in effective:
        if meta.category_column in columns:
            effective["category"] = meta.category_column
    caps = cmap.assess_capabilities(effective)
    mapping_complete = bool(meta.mapping_confirmed) or (
        uci is not None and caps["analysis_ready_minimum"] and not suggestions.get("ambiguous_columns")
    )
    # Auto-confirm when UCI exact or all required high-confidence with no ambiguity
    auto_ok = (
        not suggestions.get("needs_confirmation")
        and caps["analysis_ready_minimum"]
        and not suggestions.get("ambiguous_columns")
        and not needs_sheet_selection(meta)
    )
    if auto_ok and not meta.mapping_confirmed and effective:
        mapping_complete = True
    return {
        "suggestions": suggestions,
        "effective_mapping": effective,
        "capabilities": caps,
        "mapping_confirmed": bool(meta.mapping_confirmed) or mapping_complete,
        "needs_user_mapping": (not mapping_complete)
        or bool(suggestions.get("ambiguous_columns"))
        or (not caps["analysis_ready_minimum"]),
    }


_UNKNOWN_CURRENCY = {
    "",
    "NAN",
    "<NA>",
    "NONE",
    "NULL",
    "N/A",
    "NA",
    "UNKNOWN",
    "UNSPECIFIED",
    "?",
    "-",
}


def currency_exclusion_payload(
    *,
    selected: str | None,
    included: int,
    blank_or_unknown: int,
    other_currency: int,
) -> dict[str, Any]:
    """Explain rows left out of a single-currency total. Never implies FX."""
    reason_en = (
        f"{blank_or_unknown} row(s) excluded because currency is blank or unknown. "
        f"Totals include only {selected or 'the selected currency'}. No FX conversion."
    )
    reason_ar = (
        f"اتستبعد {blank_or_unknown} صف لأن العملة فاضية أو غير معروفة. "
        f"الإجمالي يشمل {selected or 'العملة المختارة'} فقط. مفيش تحويل عملات."
    )
    if other_currency:
        reason_en += f" {other_currency} row(s) in a different currency were also excluded."
        reason_ar += f" واتستبعد كمان {other_currency} صف بعملة مختلفة."
    return {
        "selected_currency": selected,
        "included_rows": included,
        "blank_or_unknown_excluded": blank_or_unknown,
        "other_currency_excluded": other_currency,
        "fx_conversion": False,
        "reason_en": reason_en,
        "reason_ar": reason_ar,
    }


def apply_currency_policy(parsed: pd.DataFrame, meta: UploadSessionMeta) -> pd.DataFrame:
    """Keep only the chosen currency. Blank/unknown rows never join that total."""
    empty = currency_exclusion_payload(
        selected=None, included=int(len(parsed)), blank_or_unknown=0, other_currency=0
    )
    if "row_currency" not in parsed.columns:
        parsed.attrs["currency_exclusion"] = empty
        return parsed

    norm = parsed["row_currency"].astype("string").str.strip().str.upper()
    known = norm.notna() & ~norm.isin(_UNKNOWN_CURRENCY)
    codes = sorted({str(v) for v in norm[known].tolist() if str(v)})
    blank_n = int((~known).sum())
    mapped_currency = bool((meta.column_mapping or {}).get("row_currency"))
    # Canonical frames always have a currency column; ignore it unless the user
    # mapped one or the file actually contains currency codes.
    if not mapped_currency and not codes:
        parsed.attrs["currency_exclusion"] = empty
        return parsed

    if len(codes) > 1 and not (meta.analysis_currency_filter or "").strip():
        raise ValueError(
            "This file has multiple currencies: "
            + ", ".join(codes)
            + ". Select one currency for monetary totals (no hidden FX conversion). "
            + (
                f"{blank_n} row(s) also have a blank or unknown currency and will stay out of any total."
                if blank_n
                else ""
            )
        )

    selected: str | None = None
    if (meta.analysis_currency_filter or "").strip():
        selected = meta.analysis_currency_filter.strip().upper()
    elif len(codes) == 1:
        selected = codes[0]
        if not meta.currency_code or meta.currency_code == "UNSPECIFIED":
            meta.currency_code = selected

    if not selected:
        parsed.attrs["currency_exclusion"] = currency_exclusion_payload(
            selected=None,
            included=int(known.sum()),
            blank_or_unknown=blank_n,
            other_currency=0,
        )
        if blank_n:
            parsed = parsed.loc[known].copy()
            parsed.attrs["currency_exclusion"] = currency_exclusion_payload(
                selected=None,
                included=int(len(parsed)),
                blank_or_unknown=blank_n,
                other_currency=0,
            )
        return parsed

    match = known & (norm == selected)
    other_n = int((known & ~match).sum())
    kept = parsed.loc[match].copy()
    kept.attrs["currency_exclusion"] = currency_exclusion_payload(
        selected=selected,
        included=int(len(kept)),
        blank_or_unknown=blank_n,
        other_currency=other_n,
    )
    return kept


_FRAME_CACHE: OrderedDict[tuple, pd.DataFrame] = OrderedDict()
_FRAME_CACHE_MAX = 6


def _frame_cache_key(meta: UploadSessionMeta, nrows: int | None) -> tuple:
    path = upload_path(meta.session_id)
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    mapping = tuple(sorted((meta.column_mapping or {}).items()))
    return (
        meta.session_id,
        meta.selected_sheet,
        mapping,
        meta.date_format if meta.date_format_confirmed else None,
        (meta.analysis_currency_filter or "").upper(),
        nrows,
        mtime,
        path.stat().st_size if path.exists() else 0,
    )


def _cached_frame_copy(frame: pd.DataFrame) -> pd.DataFrame:
    copied = frame.copy()
    copied.attrs["currency_exclusion"] = dict(frame.attrs.get("currency_exclusion") or {})
    return copied


def load_canonical_frame(
    meta: UploadSessionMeta,
    *,
    nrows: int | None = 100_000,
    require_mapping: bool = True,
) -> pd.DataFrame:
    """Load source → apply session mapping → typed canonical frame."""
    if needs_sheet_selection(meta):
        raise ValueError(
            "This Excel workbook has multiple worksheets. Select the sales sheet before analysis."
        )
    cache_key = None
    if require_mapping:
        try:
            cache_key = _frame_cache_key(meta, nrows)
        except OSError:
            cache_key = None
        if cache_key is not None and cache_key in _FRAME_CACHE:
            _FRAME_CACHE.move_to_end(cache_key)
            return _cached_frame_copy(_FRAME_CACHE[cache_key])
    raw = read_raw_source(meta, nrows=nrows)
    resolved = resolve_mapping(meta, [str(c) for c in raw.columns])
    mapping = resolved["effective_mapping"]
    if require_mapping and not resolved["capabilities"]["analysis_ready_minimum"]:
        blockers = resolved["capabilities"].get("blockers") or []
        detail = "; ".join(b.get("en", "") for b in blockers) or "Map required sales columns."
        raise ValueError(detail)
    if require_mapping and not resolved["mapping_confirmed"] and resolved["needs_user_mapping"]:
        raise ValueError(
            "Confirm column mapping for ambiguous or unrecognized headers before analysis."
        )
    canonical = cmap.apply_mapping_to_frame(raw, mapping)
    # Ambiguous day/month order is not applied until the user confirms it.
    effective_date_format = meta.date_format if meta.date_format_confirmed else None
    parsed = cmap.parse_canonical_types(canonical, date_format=effective_date_format)
    parsed = apply_currency_policy(parsed, meta)
    if cache_key is not None:
        _FRAME_CACHE[cache_key] = _cached_frame_copy(parsed)
        _FRAME_CACHE.move_to_end(cache_key)
        while len(_FRAME_CACHE) > _FRAME_CACHE_MAX:
            _FRAME_CACHE.popitem(last=False)
    return parsed


def validate_for_upload(meta: UploadSessionMeta, *, sample_nrows: int = 500) -> dict[str, Any]:
    """Upload-oriented validation (not UCI-strict)."""
    meta = ensure_workbook_meta(meta)
    if needs_sheet_selection(meta):
        return {
            "ok": False,
            "message": "Select which Excel worksheet contains the sales rows.",
            "message_ar": "اختار ورقة الإكسل اللي فيها صفوف المبيعات.",
            "needs_sheet_selection": True,
            "sheets": meta.workbook_sheets or [],
            "missing_columns": [],
            "extra_columns": [],
            "columns": [],
            "row_count": 0,
            "date_format": {
                "needs_confirmation": False,
                "suggested": None,
                "options": ["dayfirst", "monthfirst", "iso"],
            },
            "detected_category_column": None,
            "category_available": False,
        }

    raw = read_raw_source(meta, nrows=sample_nrows)
    columns = [str(c) for c in raw.columns]
    resolved = resolve_mapping(meta, columns)
    mapping = resolved["effective_mapping"]
    caps = resolved["capabilities"]

    date_ambiguity: dict[str, Any] = {
        "needs_confirmation": False,
        "suggested": None,
        "ambiguous_sample_count": 0,
        "slash_like_count": 0,
        "options": ["dayfirst", "monthfirst", "iso"],
        "examples": [],
    }
    date_src = mapping.get("invoice_date")
    if date_src and date_src in raw.columns:
        date_ambiguity = clean_svc.detect_date_format_ambiguity(raw[date_src])
        # Surface a few raw examples for the UI
        examples = (
            raw[date_src]
            .dropna()
            .astype(str)
            .head(5)
            .tolist()
        )
        date_ambiguity["examples"] = examples
        # Unambiguous ISO → no question
        if date_ambiguity.get("suggested") == "iso" and not date_ambiguity.get(
            "needs_confirmation"
        ):
            if not meta.date_format:
                meta.date_format = "iso"
                meta.date_format_confirmed = True

    cat = mapping.get("category") or clean_svc.detect_category_column(columns)
    currencies: list[str] = []
    cur_src = mapping.get("row_currency")
    if cur_src and cur_src in raw.columns:
        # Discover across analyzed rows, not only the validation sample head.
        currency_series = raw[cur_src]
        if sample_nrows is not None:
            try:
                full_cur = read_raw_source(meta, nrows=None)
                if cur_src in full_cur.columns:
                    currency_series = full_cur[cur_src]
            except Exception:  # noqa: BLE001
                pass
        currencies = sorted(
            {
                str(v).strip().upper()
                for v in currency_series.dropna().unique().tolist()
                if str(v).strip() and str(v).strip().upper() not in {"", "NAN", "NONE", "<NA>"}
            }
        )

    ok = caps["analysis_ready_minimum"] and (
        resolved["mapping_confirmed"] or not resolved["needs_user_mapping"]
    )
    message = (
        "Schema mapping ready for sales analysis."
        if ok
        else (
            caps.get("message_en")
            or "Map product and monetary columns to continue."
        )
    )
    return {
        "ok": ok,
        "message": message,
        "message_ar": caps.get("message_ar"),
        "missing_columns": [
            f for f in ("description", "stock_code", "quantity", "unit_price", "line_amount")
            if f not in mapping
            and not (
                (f == "stock_code" and "description" in mapping)
                or (f == "description" and "stock_code" in mapping)
                or (f == "line_amount" and "quantity" in mapping and "unit_price" in mapping)
                or (f in {"quantity", "unit_price"} and "line_amount" in mapping)
            )
        ],
        "extra_columns": [c for c in columns if c not in mapping.values()],
        "detected_category_column": cat,
        "category_available": bool(cat),
        "columns": columns,
        "row_count": int(len(raw)),
        "required_columns": ["product (code|name)", "money (line_amount|(qty&unit_price))"],
        "date_format": date_ambiguity,
        "needs_sheet_selection": False,
        "sheets": meta.workbook_sheets or [],
        "column_mapping": resolved,
        "capabilities": caps,
        "discovered_currencies": currencies,
        "multi_currency": len(currencies) > 1,
        "mapping_confirmed": resolved["mapping_confirmed"],
        "needs_user_mapping": resolved["needs_user_mapping"],
    }


def eligible_for_upload(parsed: pd.DataFrame) -> pd.Series:
    """Eligible positive spend; works when unit_price is absent but line_amount exists."""
    cancel = parsed["is_cancellation"] if "is_cancellation" in parsed.columns else False
    qty_ok = parsed["quantity"].isna() | (parsed["quantity"] > 0)
    # Prefer shared cleaner when both qty and unit_price present
    if parsed["unit_price"].notna().any() and parsed["quantity"].notna().any():
        try:
            return eligible_positive_spend_mask(parsed)
        except Exception:  # noqa: BLE001
            pass
    money_ok = parsed["line_amount"].fillna(0) > 0
    return (~cancel) & qty_ok & money_ok
