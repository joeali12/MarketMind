"""Factual upload profiling — never invents values or demo facts."""

from __future__ import annotations

from typing import Any

import pandas as pd

from api.services import cleaning_proposals as clean_svc
from api.services.upload_store import UploadSessionMeta, currency_label
from marketmind.config import REQUIRED_SOURCE_COLUMNS, SOURCE_COLUMN_MAP
from marketmind.data.cleaning import eligible_positive_spend_mask, is_cancellation_invoice

# Explicit POS header aliases → canonical (confidence 1.0 exact / 0.85 alias)
_ALIAS_MAP: dict[str, tuple[str, float]] = {
    "invoice": ("invoice", 1.0),
    "invoiceno": ("invoice", 0.85),
    "invoice_no": ("invoice", 0.85),
    "invoice number": ("invoice", 0.85),
    "bill no": ("invoice", 0.8),
    "stockcode": ("stock_code", 1.0),
    "stock code": ("stock_code", 1.0),
    "sku": ("stock_code", 0.85),
    "item code": ("stock_code", 0.85),
    "product code": ("stock_code", 0.8),
    "description": ("description", 1.0),
    "item name": ("description", 0.85),
    "product name": ("description", 0.85),
    "quantity": ("quantity", 1.0),
    "qty": ("quantity", 0.9),
    "invoicedate": ("invoice_date", 1.0),
    "invoice date": ("invoice_date", 1.0),
    "date": ("invoice_date", 0.7),  # low — require confirmation
    "price": ("unit_price", 1.0),
    "unitprice": ("unit_price", 1.0),
    "unit price": ("unit_price", 1.0),
    "amount": ("unit_price", 0.65),  # low
    "customer id": ("customer_id", 1.0),
    "customerid": ("customer_id", 1.0),
    "customer": ("customer_id", 0.7),
    "country": ("country", 1.0),
    "category": ("category", 1.0),
    "product category": ("category", 0.9),
    "cat": ("category", 0.75),
}

_LOW_CONFIDENCE = 0.75


def suggest_column_mappings(columns: list[str]) -> dict[str, Any]:
    """Map source headers to canonical fields with confidence scores."""
    mappings = []
    used_targets: set[str] = set()
    for col in columns:
        key = str(col).strip().lower().replace("_", " ")
        key_compact = key.replace(" ", "")
        hit = _ALIAS_MAP.get(key) or _ALIAS_MAP.get(key_compact)
        # Also try SOURCE_COLUMN_MAP reverse (display names)
        if not hit:
            for canon, src in SOURCE_COLUMN_MAP.items():
                if src.lower().replace("_", " ") == key or src.lower().replace(" ", "") == key_compact:
                    hit = (canon, 1.0)
                    break
        if not hit:
            mappings.append(
                {
                    "source_column": col,
                    "target": None,
                    "confidence": 0.0,
                    "auto_apply": False,
                    "needs_user_confirm": False,
                    "note_en": "Unmapped extra column",
                }
            )
            continue
        target, conf = hit
        auto = conf >= _LOW_CONFIDENCE and target not in used_targets
        if auto and target != "category":
            used_targets.add(target)
        mappings.append(
            {
                "source_column": col,
                "target": target,
                "confidence": conf,
                "auto_apply": auto and conf >= _LOW_CONFIDENCE,
                "needs_user_confirm": conf < _LOW_CONFIDENCE,
                "note_en": (
                    "Low confidence — confirm before using"
                    if conf < _LOW_CONFIDENCE
                    else "Recognized header"
                ),
            }
        )
    return {
        "mappings": mappings,
        "required_targets": list(REQUIRED_SOURCE_COLUMNS),
        "low_confidence_threshold": _LOW_CONFIDENCE,
        "note_en": "Low-confidence mappings are never applied silently.",
        "note_ar": "الربط ضعيف الثقة مش بيتطبّق لوحده من غير تأكيدك.",
    }


def classify_dataset(df: pd.DataFrame, validation: dict[str, Any]) -> dict[str, Any]:
    """Phrase classification as 'appears to be…' with supporting columns."""
    cols = [str(c) for c in df.columns]
    has_invoice = any("invoice" in c.lower() for c in cols)
    has_qty = any(c.lower() in {"quantity", "qty"} for c in cols)
    has_price = any("price" in c.lower() or c.lower() == "amount" for c in cols)
    has_date = any("date" in c.lower() for c in cols)
    has_customer = any("customer" in c.lower() for c in cols)
    has_product = any(
        x in "".join(cols).lower() for x in ("stock", "sku", "description", "product")
    )
    score = sum([has_invoice, has_qty, has_price, has_date, has_customer, has_product])
    confidence = round(score / 6.0, 2)
    evidence = []
    if has_invoice:
        evidence.append("invoice-like column")
    if has_qty:
        evidence.append("quantity column")
    if has_price:
        evidence.append("price/amount column")
    if has_date:
        evidence.append("date column")
    if has_customer:
        evidence.append("customer identifier column")
    if has_product:
        evidence.append("product/stock/description column")

    if validation.get("ok") and confidence >= 0.67:
        label_en = "Appears to be retail line-item transactions (POS-style)"
        label_ar = "يبدو إنه معاملات بيع بالسطر (نمط نقاط البيع)"
    elif confidence >= 0.5:
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
    validation = clean_svc.validate_upload_frame(df)
    mappings = suggest_column_mappings([str(c) for c in df.columns])
    classification = classify_dataset(df, validation)

    preview = df.head(8).where(pd.notna(df.head(8)), None)
    # Safe preview: truncate long strings; never log
    preview_rows = []
    for _, row in preview.iterrows():
        preview_rows.append(
            {str(k): (None if pd.isna(v) else (str(v)[:80] if not isinstance(v, (int, float)) else v)) for k, v in row.items()}
        )

    findings: list[dict[str, Any]] = []
    if not validation["ok"]:
        return {
            "ok": False,
            "validation": validation,
            "column_mappings": mappings,
            "classification": classification,
            "row_count": int(len(df)),
            "column_count": int(df.shape[1]),
            "preview_rows": preview_rows,
            "findings": [
                {
                    "id": "missing_required_columns",
                    "severity": "error",
                    "title_en": "Required columns missing",
                    "title_ar": "أعمدة مطلوبة ناقصة",
                    "count": len(validation.get("missing_columns") or []),
                    "detail_en": validation.get("message"),
                }
            ],
            "currency": {
                "code": meta.currency_code,
                "label": currency_label(meta),
                "selected": bool(meta.currency_code and meta.currency_code != "UNSPECIFIED"),
            },
            "date_format": validation.get("date_format"),
            "date_format_confirmed": meta.date_format_confirmed,
        }

    rename = {src: canon for canon, src in SOURCE_COLUMN_MAP.items()}
    working = df.rename(columns=rename)[list(SOURCE_COLUMN_MAP.keys())].copy()
    parsed = clean_svc.parse_upload_types(working, date_format=date_format or meta.date_format)
    if meta.has_category_mapped and meta.category_column and meta.category_column in df.columns:
        parsed["category"] = df[meta.category_column].astype("string").values

    eligible = parsed.loc[eligible_positive_spend_mask(parsed)]
    cancel = parsed["is_cancellation"]
    bad_dates = parsed["invoice_date"].isna()
    missing_price = parsed["unit_price"].isna()
    missing_cid = parsed["customer_id"].isna()
    missing_desc = parsed["description"].isna()
    dups = parsed.duplicated(
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

    def _examples(mask: pd.Series, cols: list[str], n: int = 3) -> list[dict[str, Any]]:
        rows = []
        for _, r in parsed.loc[mask, cols].head(n).iterrows():
            rows.append({c: (None if pd.isna(r[c]) else str(r[c])[:60]) for c in cols})
        return rows

    if int(bad_dates.sum()):
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
                "title_en": "Missing unit price",
                "title_ar": "سعر الوحدة ناقص",
                "count": int(missing_price.sum()),
                "examples": _examples(missing_price, ["invoice", "stock_code", "unit_price"]),
            }
        )
    if int(missing_cid.sum()):
        findings.append(
            {
                "id": "missing_customer_id",
                "severity": "warning",
                "title_en": "Missing customer ID",
                "title_ar": "رقم زبون ناقص",
                "count": int(missing_cid.sum()),
                "examples": _examples(missing_cid, ["invoice", "stock_code", "customer_id"]),
                "detail_en": "Customer analytics need an ID; IDs are never invented.",
            }
        )
    if int(dups.sum()):
        findings.append(
            {
                "id": "exact_duplicates",
                "severity": "warning",
                "title_en": "Exact duplicate lines",
                "title_ar": "صفوف مكررة تمامًا",
                "count": int(dups.sum()),
                "examples": _examples(dups, ["invoice", "stock_code", "quantity"]),
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
                "detail_en": (
                    "Detected with conservative patterns (C#### or C-…), not every invoice "
                    "starting with letter C (so CAI-… stays a normal sale)."
                ),
                "rule": "C#### or C-*",
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

    date_min = str(eligible["invoice_date"].min()) if len(eligible) and eligible["invoice_date"].notna().any() else None
    date_max = str(eligible["invoice_date"].max()) if len(eligible) and eligible["invoice_date"].notna().any() else None

    return {
        "ok": True,
        "validation": validation,
        "column_mappings": mappings,
        "classification": classification,
        "row_count": int(len(df)),
        "column_count": int(df.shape[1]),
        "recognized_required": [
            c for c in REQUIRED_SOURCE_COLUMNS if c in parsed.columns
        ],
        "extra_columns": validation.get("extra_columns") or [],
        "preview_rows": preview_rows,
        "findings": findings,
        "structure": {
            "has_customer_id": bool(parsed["customer_id"].notna().any()),
            "has_product_id": bool(parsed["stock_code"].notna().any()),
            "unique_customers": int(parsed["customer_id"].dropna().nunique()),
            "unique_products": int(parsed["stock_code"].dropna().nunique()),
            "unique_invoices": int(parsed["invoice"].nunique()),
            "cancellation_rows": int(cancel.sum()),
            "eligible_rows": int(len(eligible)),
            "eligible_spend": float(eligible["line_amount"].fillna(0).sum()),
            "date_min": date_min,
            "date_max": date_max,
            "appears_transactional": classification["confidence"] >= 0.67,
        },
        "currency": {
            "code": meta.currency_code,
            "label": currency_label(meta),
            "selected": bool(meta.currency_code and meta.currency_code != "UNSPECIFIED"),
            "note_en": "Currency is never inferred from amounts.",
            "note_ar": "العملة مش بتتستنتج من الأرقام.",
        },
        "date_format": validation.get("date_format"),
        "date_format_confirmed": meta.date_format_confirmed,
        "date_format_selected": meta.date_format,
        "category_mapped": meta.has_category_mapped,
        "category_column": meta.category_column,
        "source": "upload",
        "demo": False,
        "session_id": meta.session_id,
        "filename": meta.filename,
    }
