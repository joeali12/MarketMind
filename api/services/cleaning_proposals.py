"""Deterministic, explainable cleaning suggestions — never invent values."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from marketmind.config import REQUIRED_SOURCE_COLUMNS, SOURCE_COLUMN_MAP
from marketmind.data.schema import validate_source_columns

_SLASH_DATE = re.compile(r"^\s*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\s*$")
_ISO_DATE = re.compile(r"^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}")


def read_upload_dataframe(path, *, nrows: int | None = None) -> pd.DataFrame:
    suffix = str(path).lower()
    if suffix.endswith(".csv"):
        return pd.read_csv(path, nrows=nrows)
    if suffix.endswith(".xlsx"):
        return pd.read_excel(path, nrows=nrows)
    raise ValueError("Unsupported file type")


def detect_category_column(columns: list[str]) -> str | None:
    """Heuristic name match only — does not invent a category field."""
    lowered = {c: str(c).strip().lower() for c in columns}
    for original, low in lowered.items():
        if low in {"category", "product_category", "product category", "cat"}:
            return original
    return None


def detect_date_format_ambiguity(series: pd.Series, *, sample: int = 200) -> dict[str, Any]:
    """Detect slash-style dates that could be DMY or MDY.

    Returns needs_confirmation=True when both dayfirst and monthfirst parse
    successfully for overlapping samples with different interpretations.
    """
    raw = series.dropna().astype(str).head(sample)
    if raw.empty:
        return {
            "needs_confirmation": False,
            "suggested": "iso",
            "ambiguous_sample_count": 0,
            "slash_like_count": 0,
            "options": ["dayfirst", "monthfirst", "iso"],
        }

    slash_like = raw[raw.map(lambda s: bool(_SLASH_DATE.match(s)) and not _ISO_DATE.match(s))]
    iso_like = int(raw.map(lambda s: bool(_ISO_DATE.match(s))).sum())

    if slash_like.empty:
        return {
            "needs_confirmation": False,
            "suggested": "iso" if iso_like else None,
            "ambiguous_sample_count": 0,
            "slash_like_count": 0,
            "options": ["dayfirst", "monthfirst", "iso"],
        }

    dayfirst = pd.to_datetime(slash_like, errors="coerce", dayfirst=True)
    monthfirst = pd.to_datetime(slash_like, errors="coerce", dayfirst=False)
    both_ok = dayfirst.notna() & monthfirst.notna()
    disagree = both_ok & (dayfirst.dt.normalize() != monthfirst.dt.normalize())
    ambiguous = int(disagree.sum())
    needs = ambiguous > 0
    return {
        "needs_confirmation": needs,
        "suggested": None if needs else "dayfirst",
        "ambiguous_sample_count": ambiguous,
        "slash_like_count": int(len(slash_like)),
        "options": ["dayfirst", "monthfirst", "iso"],
        "message_en": (
            "Some invoice dates look like day/month/year or month/day/year. "
            "Confirm the format before cleaning or analysis."
            if needs
            else None
        ),
        "message_ar": (
            "بعض تواريخ الفواتير ممكن تتقري يوم/شهر أو شهر/يوم. "
            "أكّد الصيغة قبل التنظيف أو التحليل."
            if needs
            else None
        ),
    }


def parse_upload_types(df: pd.DataFrame, *, date_format: str | None = None) -> pd.DataFrame:
    """Parse canonical columns; optional date_format avoids silent DMY/MDY guesses."""
    out = df.copy()
    out["invoice"] = out["invoice"].astype(str).str.strip()
    out["stock_code"] = out["stock_code"].astype(str).str.strip()
    out["description"] = out["description"].astype("string")
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce")
    out["unit_price"] = pd.to_numeric(out["unit_price"], errors="coerce")
    out["customer_id"] = pd.to_numeric(out["customer_id"], errors="coerce")
    out["country"] = out["country"].astype("string")

    raw_dates = out["invoice_date"]
    if date_format == "dayfirst":
        # Uploads can contain ISO dates alongside local slash dates. Let pandas
        # infer each value independently; inferring one format for the whole
        # column turns every value in the other format into NaT.
        out["invoice_date"] = pd.to_datetime(
            raw_dates, errors="coerce", format="mixed", dayfirst=True
        )
    elif date_format == "monthfirst":
        out["invoice_date"] = pd.to_datetime(
            raw_dates, errors="coerce", format="mixed", dayfirst=False
        )
    elif date_format == "iso":
        out["invoice_date"] = pd.to_datetime(raw_dates, errors="coerce", format="ISO8601")
        # Fallback for mixed ISO-ish strings pandas may still parse
        still = out["invoice_date"].isna() & raw_dates.notna()
        if still.any():
            out.loc[still, "invoice_date"] = pd.to_datetime(
                raw_dates[still], errors="coerce", format="%Y-%m-%d", exact=False
            )
    else:
        # Unconfirmed: coerce without inventing a locale preference
        out["invoice_date"] = pd.to_datetime(raw_dates, errors="coerce")

    from marketmind.data.cleaning import is_cancellation_invoice

    out["is_cancellation"] = is_cancellation_invoice(out["invoice"])
    out["line_amount"] = out["quantity"] * out["unit_price"]
    return out


def validate_upload_frame(df: pd.DataFrame) -> dict[str, Any]:
    result = validate_source_columns(df.columns)
    category_col = detect_category_column(list(map(str, df.columns)))
    date_ambiguity: dict[str, Any] = {
        "needs_confirmation": False,
        "suggested": None,
        "ambiguous_sample_count": 0,
        "slash_like_count": 0,
        "options": ["dayfirst", "monthfirst", "iso"],
    }
    if result.ok:
        rename = {src: canon for canon, src in SOURCE_COLUMN_MAP.items()}
        working = df.rename(columns=rename)
        if "invoice_date" in working.columns:
            date_ambiguity = detect_date_format_ambiguity(working["invoice_date"])
    return {
        "ok": result.ok,
        "message": result.message,
        "missing_columns": list(result.missing_columns),
        "extra_columns": list(result.extra_columns),
        "detected_category_column": category_col,
        "category_available": category_col is not None,
        "columns": [str(c) for c in df.columns],
        "row_count": int(len(df)),
        "required_columns": list(REQUIRED_SOURCE_COLUMNS),
        "date_format": date_ambiguity,
    }


def _eligible_mask(parsed: pd.DataFrame) -> pd.Series:
    return (
        (~parsed["is_cancellation"])
        & (parsed["quantity"] > 0)
        & (parsed["unit_price"] >= 0)
    )


def _estimate_impact(parsed: pd.DataFrame, drop_mask: pd.Series) -> dict[str, Any]:
    """Rows removed and eligible spend change if those rows are dropped."""
    before = float(parsed.loc[_eligible_mask(parsed), "line_amount"].fillna(0).sum())
    kept = parsed.loc[~drop_mask]
    after = float(kept.loc[_eligible_mask(kept), "line_amount"].fillna(0).sum())
    return {
        "rows_removed_estimate": int(drop_mask.sum()),
        "eligible_spend_delta": float(after - before),
        "eligible_spend_after_estimate": after,
    }


def build_proposals(
    df: pd.DataFrame,
    *,
    date_format: str | None = None,
    currency_code: str | None = None,
    category_column: str | None = None,
) -> dict[str, Any]:
    """Propose deterministic cleaning steps with impact estimates.

    Unresolved values remain visible; no IDs/names/amounts are invented.
    Destructive proposals default to not accepted.
    """
    validation = validate_upload_frame(df)
    if not validation["ok"]:
        return {
            "validation": validation,
            "proposals": [],
            "unresolved_preview": [],
            "baseline": {},
        }

    rename = {src: canon for canon, src in SOURCE_COLUMN_MAP.items()}
    working = df.rename(columns=rename)
    keep = list(SOURCE_COLUMN_MAP.keys())
    cat = category_column or validation.get("detected_category_column")
    if cat and cat in df.columns and cat not in rename:
        working["category"] = df[cat]
        keep = keep + ["category"]
    working = working[[c for c in keep if c in working.columns]].copy()

    parsed = parse_upload_types(
        working[[c for c in SOURCE_COLUMN_MAP.keys() if c in working.columns]],
        date_format=date_format,
    )
    if "category" in working.columns:
        parsed["category"] = working["category"].values

    baseline_rows = int(len(parsed))
    baseline_spend = float(
        parsed.loc[_eligible_mask(parsed), "line_amount"].fillna(0).sum()
    )
    currency_label = currency_code or "UNSPECIFIED"

    proposals: list[dict[str, Any]] = []

    bad_dates = parsed["invoice_date"].isna()
    if int(bad_dates.sum()):
        impact = _estimate_impact(parsed, bad_dates)
        proposals.append(
            {
                "id": "drop_unparseable_dates",
                "title_en": "Drop rows with unparseable invoice dates",
                "title_ar": "احذف الصفوف اللي تاريخ الفاتورة فيها مش مقروء",
                "reason_en": "invoice_date could not be parsed; values stay blank until you drop or fix the source file.",
                "reason_ar": "تاريخ الفاتورة مش مقروء؛ القيم تفضل فاضية لحد ما تمسح الصف أو تعدّل الملف.",
                "rows_affected": int(bad_dates.sum()),
                "estimated_impact": impact,
                "invents_values": False,
                "destructive": True,
                "default_accepted": False,
            }
        )

    bad_qty_price = parsed["quantity"].isna() | parsed["unit_price"].isna()
    if int(bad_qty_price.sum()):
        impact = _estimate_impact(parsed, bad_qty_price)
        proposals.append(
            {
                "id": "drop_non_finite_qty_price",
                "title_en": "Drop rows with missing quantity or unit price",
                "title_ar": "احذف الصفوف الناقص فيها الكمية أو السعر",
                "reason_en": "Non-numeric or missing quantity/price after coercion. Missing amounts are not filled in.",
                "reason_ar": "كمية أو سعر ناقص/مش رقمي بعد التحويل. مش هنخمّن المبالغ الناقصة.",
                "rows_affected": int(bad_qty_price.sum()),
                "estimated_impact": impact,
                "invents_values": False,
                "destructive": True,
                "default_accepted": False,
            }
        )

    dup_mask = parsed.duplicated(
        subset=[
            "invoice",
            "stock_code",
            "description",
            "quantity",
            "invoice_date",
            "unit_price",
            "customer_id",
            "country",
        ]
    )
    if int(dup_mask.sum()):
        impact = _estimate_impact(parsed, dup_mask)
        proposals.append(
            {
                "id": "drop_exact_duplicates",
                "title_en": "Drop exact duplicate transaction lines",
                "title_ar": "احذف صفوف المعاملات المكررة تمامًا",
                "reason_en": "Exact duplicates on invoice/stock/qty/date/price/customer/country.",
                "reason_ar": "تكرار مطابق على الفاتورة والمنتج والكمية والتاريخ والسعر والزبون والدولة.",
                "rows_affected": int(dup_mask.sum()),
                "estimated_impact": impact,
                "invents_values": False,
                "destructive": True,
                "default_accepted": False,
            }
        )

    missing_cid = parsed["customer_id"].isna()
    if int(missing_cid.sum()):
        impact = _estimate_impact(parsed, missing_cid)
        proposals.append(
            {
                "id": "drop_missing_customer_id",
                "title_en": "Exclude rows without Customer ID (for customer analytics)",
                "title_ar": "استبعد الصفوف من غير رقم زبون (لتحليل الزباين)",
                "reason_en": "Customer-level views need Customer ID. IDs are never invented; unresolved rows stay listed if you keep them.",
                "reason_ar": "تحليل الزباين محتاج رقم زبون. مش هنولّد أرقام؛ الصفوف الناقصة تفضل ظاهرة لو سيبتها.",
                "rows_affected": int(missing_cid.sum()),
                "estimated_impact": impact,
                "invents_values": False,
                "destructive": True,
                "default_accepted": False,
            }
        )

    cancel_rows = int(parsed["is_cancellation"].sum())
    if cancel_rows:
        proposals.append(
            {
                "id": "tag_cancellations_only",
                "title_en": "Keep cancellation/return candidates tagged (C#### or C-…)",
                "title_ar": "سيّب مرشحات الإلغاء/المرتجع موسومة (C#### أو C-…)",
                "reason_en": (
                    "Conservative rule: UCI-style C#### or C-RET-… codes. "
                    "Invoices like CAI-… are NOT treated as cancellations. "
                    "Eligible spend excludes tagged rows. Review before accepting."
                ),
                "reason_ar": (
                    "قاعدة حذرة: أكواد C#### أو C-RET-…. "
                    "فواتير زي CAI-… مش بتتحسب إلغاء. "
                    "المصروف المؤهل بيستبعد الصفوف الموسومة. راجع قبل الموافقة."
                ),
                "rows_affected": cancel_rows,
                "estimated_impact": {
                    "rows_removed_estimate": 0,
                    "eligible_spend_delta": 0.0,
                    "note_en": "Tagging only — eligible spend already excludes cancellations",
                },
                "invents_values": False,
                "destructive": False,
                "default_accepted": False,
            }
        )

    from api.services.anomaly_flags import flag_numeric_anomalies

    anomaly = flag_numeric_anomalies(parsed)

    from api.services.gap_fill import suggest_for_parsed

    gap = suggest_for_parsed(parsed, limit=25)
    unresolved_preview = gap["rows"]

    return {
        "validation": validation,
        "proposals": proposals,
        "unresolved_preview": unresolved_preview,
        "gap_fill": {
            "smart_fillable_fields": gap["smart_fillable_fields"],
            "manual_only_fields": gap["manual_only_fields"],
            "note_en": gap["note_en"],
            "note_ar": gap["note_ar"],
        },
        "anomaly_review": anomaly,
        "baseline": {
            "rows": baseline_rows,
            "eligible_spend": baseline_spend,
            "currency_code": currency_label,
            "currency_selected": bool(currency_code and currency_code != "UNSPECIFIED"),
            # Explicitly not GBP unless user selected GBP
            "amount_unit_en": (
                f"eligible spend ({currency_code})"
                if currency_code and currency_code != "UNSPECIFIED"
                else "eligible spend (source currency — select currency)"
            ),
        },
        "date_format": validation.get("date_format"),
        "note_en": "Suggestions are deterministic rules from the project cleaning policy. Nothing invents IDs, names, dates, or amounts. Anomaly scores are review flags only.",
        "note_ar": "الاقتراحات قواعد واضحة من سياسة التنظيف. منغير اختراع أرقام زباين أو أسماء أو تواريخ أو مبالغ. درجات الشذوذ علامات مراجعة فقط.",
    }


def apply_proposals(
    df: pd.DataFrame,
    accepted_ids: list[str],
    *,
    date_format: str | None = None,
    category_column: str | None = None,
) -> dict[str, Any]:
    """Apply only accepted deterministic ops; never invent values.

    Preserves optional mapped category column in the cleaned export.
    """
    from marketmind.data.cleaning import clean_transactions

    validation = validate_upload_frame(df)
    if not validation["ok"]:
        raise ValueError(validation["message"])

    rename = {src: canon for canon, src in SOURCE_COLUMN_MAP.items()}
    working = df.rename(columns=rename)
    working = working[list(SOURCE_COLUMN_MAP.keys())].copy()

    # Re-parse dates with confirmed format before clean_transactions' default parse
    if date_format:
        typed = parse_upload_types(working, date_format=date_format)
        working = working.copy()
        working["invoice_date"] = typed["invoice_date"]

    accepted = set(accepted_ids)
    result = clean_transactions(
        working,
        drop_missing_customer_id="drop_missing_customer_id" in accepted,
        drop_exact_duplicates="drop_exact_duplicates" in accepted,
        drop_unparseable_dates="drop_unparseable_dates" in accepted,
        drop_non_finite_qty_price="drop_non_finite_qty_price" in accepted,
        keep_cancellations=True,
    )
    out = result.data

    cat = category_column
    if cat and cat in df.columns:
        src = df.copy()
        src["_mm_cat"] = src[cat]
        src_ren = src.rename(columns=rename)
        merge_keys = [
            k
            for k in ["invoice", "stock_code", "quantity", "unit_price", "customer_id"]
            if k in out.columns and k in src_ren.columns
        ]
        if merge_keys:
            cat_map = src_ren[merge_keys + ["_mm_cat"]].drop_duplicates(
                subset=merge_keys, keep="first"
            )
            out = out.merge(cat_map, on=merge_keys, how="left")
            out = out.rename(columns={"_mm_cat": "category"})
        else:
            out["category"] = pd.NA

    eligible = out.loc[
        (~out["is_cancellation"]) & (out["quantity"] > 0) & (out["unit_price"] >= 0)
    ]
    return {
        "rows_before": int(len(working)),
        "rows_after": int(len(out)),
        "eligible_spend_after": float(eligible["line_amount"].fillna(0).sum()),
        "reconciliation": [s.__dict__ for s in result.reconciliation],
        "dataframe": out,
    }
