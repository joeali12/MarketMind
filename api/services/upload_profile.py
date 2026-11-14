"""Factual upload profiling — never invents values or demo facts."""

from __future__ import annotations

from typing import Any

import pandas as pd

from api.services import canonical_upload
from api.services import cleaning_proposals as clean_svc
from api.services import column_mapping as cmap
from api.services.upload_store import UploadSessionMeta, currency_label
from marketmind.data.cleaning import eligible_positive_spend_mask


def suggest_column_mappings(columns: list[str]) -> dict[str, Any]:
    """Delegate to the shared POS mapping scorer."""
    return cmap.suggest_mappings(columns)


def classify_dataset(df: pd.DataFrame, validation: dict[str, Any]) -> dict[str, Any]:
    """Phrase classification as 'appears to be…' with supporting columns."""
    cols = [str(c) for c in df.columns]
    mapping = (validation.get("column_mapping") or {}).get("effective_mapping") or {}
    if not mapping:
        sug = cmap.suggest_mappings(cols)
        mapping = sug.get("auto_mapping") or {}
    has_invoice = "invoice" in mapping
    has_qty = "quantity" in mapping
    has_price = "unit_price" in mapping or "line_amount" in mapping
    has_date = "invoice_date" in mapping
    has_customer = "customer_id" in mapping
    has_product = "stock_code" in mapping or "description" in mapping
    score = sum([has_invoice, has_qty, has_price, has_date, has_customer, has_product])
    confidence = round(score / 6.0, 2)
    evidence = []
    if has_invoice:
        evidence.append("invoice/order column")
    if has_qty:
        evidence.append("quantity column")
    if has_price:
        evidence.append("price or line-amount column")
    if has_date:
        evidence.append("date column")
    if has_customer:
        evidence.append("customer identifier column")
    if has_product:
        evidence.append("product/stock/description column")

    caps = cmap.assess_capabilities(mapping)
    if caps.get("analysis_ready_minimum") and confidence >= 0.5:
        label_en = "Appears to be retail line-item transactions (POS-style)"
        label_ar = "يبدو إنه معاملات بيع بالسطر (نمط نقاط البيع)"
    elif confidence >= 0.4:
        label_en = "Appears related to retail transactions, but some expected fields are unclear"
        label_ar = "يبدو مرتبط بمعاملات بيع، بس بعض الحقول المتوقعة مش واضحة"
    else:
        label_en = "Does not clearly match a retail transaction export"
        label_ar = "مش واضح إنه ملف معاملات بيع بالتجزئة"

    return {
        "label_en": label_en,
        "label_ar": label_ar,
        "confidence": confidence,
        "evidence": evidence,
        "phrase_en": f"{label_en}. Supported by: {', '.join(evidence) or 'few matching headers'}.",
        "phrase_ar": f"{label_ar}. الأعمدة الداعمة: {', '.join(evidence) or 'قليل من العناوين المطابقة'}.",
    }


def build_profile(
    df: pd.DataFrame,
    meta: UploadSessionMeta,
    *,
    date_format: str | None = None,
) -> dict[str, Any]:
    validation = canonical_upload.validate_for_upload(meta)
    # Re-read may differ from passed df if sheet selection changed — prefer session raw
    try:
        raw = canonical_upload.read_raw_source(meta, nrows=min(len(df) if len(df) else 5000, 5000))
    except Exception:  # noqa: BLE001
        raw = df
    columns = [str(c) for c in raw.columns]
    resolved = validation.get("column_mapping") or canonical_upload.resolve_mapping(meta, columns)
    mappings = resolved.get("suggestions") or cmap.suggest_mappings(columns)
    classification = classify_dataset(raw, validation)

    preview = raw.head(8).where(pd.notna(raw.head(8)), None)
    preview_rows = []
    for _, row in preview.iterrows():
        preview_rows.append(
            {
                str(k): (
                    None
                    if pd.isna(v)
                    else (str(v)[:80] if not isinstance(v, (int, float)) else v)
                )
                for k, v in row.items()
            }
        )

    findings: list[dict[str, Any]] = []
    if validation.get("needs_sheet_selection"):
        return {
            "ok": False,
            "validation": validation,
            "column_mappings": mappings,
            "classification": classification,
            "row_count": int(meta.row_count or 0),
            "column_count": 0,
            "preview_rows": [],
            "findings": [
                {
                    "id": "needs_sheet_selection",
                    "severity": "error",
                    "title_en": "Choose an Excel worksheet",
                    "title_ar": "اختار ورقة إكسل",
                    "count": len(validation.get("sheets") or []),
                    "detail_en": "This workbook has multiple sheets — select the sales sheet.",
                }
            ],
            "workbook": {
                "sheets": validation.get("sheets") or [],
                "selected_sheet": meta.selected_sheet,
                "needs_sheet_selection": True,
            },
            "currency": {
                "code": meta.currency_code,
                "label": currency_label(meta),
                "selected": bool(meta.currency_code and meta.currency_code != "UNSPECIFIED"),
            },
            "mapping": resolved,
            "capabilities": cmap.capability_docs(),
        }

    if not resolved.get("capabilities", {}).get("analysis_ready_minimum"):
        return {
            "ok": False,
            "validation": validation,
            "column_mappings": mappings,
            "classification": classification,
            "row_count": int(len(raw)),
            "column_count": int(raw.shape[1]),
            "preview_rows": preview_rows,
            "findings": [
                {
                    "id": "mapping_incomplete",
                    "severity": "error",
                    "title_en": "Map product and monetary columns",
                    "title_ar": "اربط أعمدة المنتج والمبلغ",
                    "count": len((resolved.get("capabilities") or {}).get("blockers") or []),
                    "detail_en": (resolved.get("capabilities") or {}).get("message_en"),
                    "detail_ar": (resolved.get("capabilities") or {}).get("message_ar"),
                }
            ],
            "currency": {
                "code": meta.currency_code,
                "label": currency_label(meta),
                "selected": bool(meta.currency_code and meta.currency_code != "UNSPECIFIED"),
            },
            "date_format": validation.get("date_format"),
            "date_format_confirmed": meta.date_format_confirmed,
            "mapping": resolved,
            "needs_user_mapping": True,
            "workbook": {
                "sheets": meta.workbook_sheets or [],
                "selected_sheet": meta.selected_sheet,
                "needs_sheet_selection": False,
            },
            "capabilities": cmap.capability_docs(),
            "source": "upload",
            "demo": False,
            "session_id": meta.session_id,
            "filename": meta.filename,
        }

    # Build typed frame when mapping is usable (even if user still confirming ambiguous extras)
    try:
        parsed = canonical_upload.load_canonical_frame(
            meta, nrows=min(len(raw), 100_000), require_mapping=False
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "validation": validation,
            "column_mappings": mappings,
            "classification": classification,
            "row_count": int(len(raw)),
            "column_count": int(raw.shape[1]),
            "preview_rows": preview_rows,
            "findings": [
                {
                    "id": "canonical_load_failed",
                    "severity": "error",
                    "title_en": "Could not build analysis view",
                    "title_ar": "مقدرناش نبني عرض التحليل",
                    "count": 1,
                    "detail_en": str(exc),
                }
            ],
            "mapping": resolved,
            "needs_user_mapping": bool(resolved.get("needs_user_mapping")),
            "source": "upload",
            "demo": False,
            "session_id": meta.session_id,
            "filename": meta.filename,
        }

    try:
        eligible = parsed.loc[eligible_positive_spend_mask(parsed)]
    except Exception:  # noqa: BLE001
        eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)]
    cancel = parsed["is_cancellation"]
    bad_dates = parsed["invoice_date"].isna()
    missing_price = parsed["unit_price"].isna() & parsed["line_amount"].isna()
    missing_cid = parsed["customer_id"].isna()
    missing_desc = parsed["description"].isna()

    def _examples(mask: pd.Series, cols: list[str], n: int = 3) -> list[dict[str, Any]]:
        rows = []
        use_cols = [c for c in cols if c in parsed.columns]
        for _, r in parsed.loc[mask, use_cols].head(n).iterrows():
            rows.append({c: (None if pd.isna(r[c]) else str(r[c])[:60]) for c in use_cols})
        return rows

    if int(bad_dates.sum()) and "invoice_date" in (meta.column_mapping or resolved.get("effective_mapping") or {}):
        findings.append(
            {
                "id": "invalid_dates",
                "severity": "error",
                "title_en": "Unparseable invoice dates",
                "title_ar": "تواريخ فاتورة مش مقروءة",
                "count": int(bad_dates.sum()),
                "examples": _examples(bad_dates, ["invoice", "invoice_date"]),
                "detail_en": "These dates stay blank — values are never invented.",
            }
        )
    if int(missing_price.sum()):
        findings.append(
            {
                "id": "missing_price",
                "severity": "error",
                "title_en": "Missing monetary values",
                "title_ar": "قيم مالية ناقصة",
                "count": int(missing_price.sum()),
                "examples": _examples(missing_price, ["invoice", "stock_code", "unit_price", "line_amount"]),
            }
        )
    if int(missing_cid.sum()) == len(parsed):
        findings.append(
            {
                "id": "no_customer_id_column",
                "severity": "info",
                "title_en": "No customer ID — store/product analytics still available",
                "title_ar": "مفيش رقم زبون — تحليل المتجر/المنتجات لسه متاح",
                "count": int(len(parsed)),
                "detail_en": "Customer groups and returning rates stay disabled until a customer ID is mapped.",
            }
        )
    elif int(missing_cid.sum()):
        findings.append(
            {
                "id": "missing_customer_id",
                "severity": "warning",
                "title_en": "Missing customer ID on some rows",
                "title_ar": "رقم زبون ناقص في بعض الصفوف",
                "count": int(missing_cid.sum()),
                "examples": _examples(missing_cid, ["invoice", "stock_code", "customer_id"]),
                "detail_en": "Anonymous lines stay in store totals; IDs are never invented.",
            }
        )
    if int(cancel.sum()):
        findings.append(
            {
                "id": "cancellation_candidates",
                "severity": "info",
                "title_en": "Cancellation / return candidates",
                "title_ar": "مرشحات إلغاء / مرتجع",
                "count": int(cancel.sum()),
                "examples": _examples(cancel, ["invoice", "quantity", "unit_price"]),
            }
        )
    if int(missing_desc.sum()):
        findings.append(
            {
                "id": "missing_description",
                "severity": "info",
                "title_en": "Missing product description",
                "title_ar": "وصف المنتج ناقص",
                "count": int(missing_desc.sum()),
            }
        )

    if resolved.get("needs_user_mapping") and not meta.mapping_confirmed:
        findings.insert(
            0,
            {
                "id": "confirm_mapping",
                "severity": "warning",
                "title_en": "Confirm column mapping",
                "title_ar": "أكّد ربط الأعمدة",
                "count": len(mappings.get("ambiguous_columns") or [])
                + sum(1 for m in mappings.get("mappings") or [] if m.get("needs_user_confirm")),
                "detail_en": "Some headers are ambiguous or low-confidence — confirm before analysis.",
            },
        )

    date_min = (
        str(eligible["invoice_date"].min())
        if len(eligible) and eligible["invoice_date"].notna().any()
        else None
    )
    date_max = (
        str(eligible["invoice_date"].max())
        if len(eligible) and eligible["invoice_date"].notna().any()
        else None
    )
    eff = resolved.get("effective_mapping") or {}

    return {
        "ok": bool(resolved.get("capabilities", {}).get("analysis_ready_minimum")),
        "validation": validation,
        "column_mappings": mappings,
        "classification": classification,
        "row_count": int(len(raw)),
        "column_count": int(raw.shape[1]),
        "recognized_required": list(eff.keys()),
        "extra_columns": [c for c in columns if c not in eff.values()],
        "preview_rows": preview_rows,
        "findings": findings,
        "structure": {
            "has_customer_id": bool(parsed["customer_id"].notna().any()),
            "has_product_id": bool(
                parsed["stock_code"].notna().any() or parsed["description"].notna().any()
            ),
            "unique_customers": int(parsed["customer_id"].dropna().nunique()),
            "unique_products": int(
                parsed["stock_code"].replace("", pd.NA).dropna().nunique()
                or parsed["description"].dropna().nunique()
            ),
            "unique_invoices": int(
                parsed.loc[~parsed["invoice"].astype(str).str.match(r"^ROW-", na=False), "invoice"].nunique()
            ),
            "cancellation_rows": int(cancel.sum()),
            "eligible_rows": int(len(eligible)),
            "eligible_spend": float(eligible["line_amount"].fillna(0).sum()),
            "date_min": date_min,
            "date_max": date_max,
            "appears_transactional": classification["confidence"] >= 0.5,
        },
        "currency": {
            "code": meta.currency_code,
            "label": currency_label(meta),
            "selected": bool(meta.currency_code and meta.currency_code != "UNSPECIFIED"),
            "discovered_currencies": validation.get("discovered_currencies") or [],
            "multi_currency": bool(validation.get("multi_currency")),
            "analysis_currency_filter": meta.analysis_currency_filter,
            "exclusion": dict(parsed.attrs.get("currency_exclusion") or {}),
            "note_en": "Currency is never inferred from amounts. Blank or unknown currency rows are left out of a chosen total.",
            "note_ar": "العملة مش بتتستنتج من الأرقام. صفوف العملة الفاضية أو غير المعروفة بتخرج من الإجمالي المختار.",
        },
        "date_format": validation.get("date_format"),
        "date_format_confirmed": meta.date_format_confirmed,
        "date_format_selected": meta.date_format,
        "category_mapped": bool(eff.get("category") or meta.has_category_mapped),
        "category_column": eff.get("category") or meta.category_column,
        "mapping": resolved,
        "needs_user_mapping": bool(resolved.get("needs_user_mapping")) and not meta.mapping_confirmed,
        "mapping_confirmed": bool(meta.mapping_confirmed) or bool(resolved.get("mapping_confirmed")),
        "workbook": {
            "sheets": meta.workbook_sheets or [],
            "selected_sheet": meta.selected_sheet,
            "needs_sheet_selection": False,
        },
        "capabilities": resolved.get("capabilities"),
        "capability_docs": cmap.capability_docs(),
        "source": "upload",
        "demo": False,
        "session_id": meta.session_id,
        "filename": meta.filename,
    }
