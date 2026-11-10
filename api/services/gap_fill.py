"""Evidence-based gap-fill suggestions for unresolved upload rows.

Smart fills are never applied silently. Only fields with a clear same-file
pattern are proposed. Customer IDs and invoice dates are never invented —
those stay manual-only.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from marketmind.config import SOURCE_COLUMN_MAP

# Fields we may propose from file patterns (with explicit user approval).
# Quantity is never median-invented — transaction qty stays owner-owned.
SMART_FILLABLE = frozenset({"unit_price", "description"})
# Never invent — user must type these.
MANUAL_ONLY = frozenset({"customer_id", "invoice_date", "invoice", "quantity"})


def _issues_for_row(row: pd.Series) -> list[str]:
    issues = []
    if pd.isna(row.get("invoice_date")):
        issues.append("invoice_date")
    if pd.isna(row.get("quantity")):
        issues.append("quantity")
    if pd.isna(row.get("unit_price")):
        issues.append("unit_price")
    if pd.isna(row.get("customer_id")):
        issues.append("customer_id")
    if pd.isna(row.get("description")):
        issues.append("description")
    inv = row.get("invoice")
    if pd.isna(inv) or str(inv).strip() in {"", "nan", "None"}:
        issues.append("invoice")
    return issues


def suggest_for_parsed(parsed: pd.DataFrame, *, limit: int = 25) -> dict[str, Any]:
    """Build unresolved rows + optional smart suggestions with evidence."""
    if parsed.empty:
        return {
            "rows": [],
            "smart_fillable_fields": sorted(SMART_FILLABLE),
            "manual_only_fields": sorted(MANUAL_ONLY),
            "note_en": "No rows to review.",
            "note_ar": "مفيش صفوف للمراجعة.",
        }

    mask = (
        parsed["invoice_date"].isna()
        | parsed["quantity"].isna()
        | parsed["unit_price"].isna()
        | parsed["customer_id"].isna()
        | parsed["description"].isna()
        | parsed["invoice"].isna()
        | (parsed["invoice"].astype(str).str.strip() == "")
        | (parsed["invoice"].astype(str).str.lower() == "nan")
    )
    unresolved = parsed.loc[mask].head(limit)

    # Precompute stock-code stats from non-null peers
    price_by_stock: dict[str, float] = {}
    qty_by_stock: dict[str, float] = {}
    desc_by_stock: dict[str, str] = {}
    if "stock_code" in parsed.columns:
        for stock, part in parsed.groupby(parsed["stock_code"].astype(str), dropna=True):
            prices = part["unit_price"].dropna()
            prices = prices[prices >= 0]
            if len(prices):
                price_by_stock[str(stock)] = float(prices.median())
            qtys = part["quantity"].dropna()
            qtys = qtys[qtys > 0]
            if len(qtys):
                qty_by_stock[str(stock)] = float(qtys.median())
            descs = part["description"].dropna().astype(str)
            descs = descs[descs.str.strip() != ""]
            if len(descs):
                desc_by_stock[str(stock)] = str(descs.mode().iloc[0])

    rows: list[dict[str, Any]] = []
    for idx, row in unresolved.iterrows():
        issues = _issues_for_row(row)
        stock = None if pd.isna(row.get("stock_code")) else str(row.get("stock_code"))
        suggestions: dict[str, Any] = {}
        for field in issues:
            if field in MANUAL_ONLY:
                suggestions[field] = {
                    "suggested": None,
                    "allowed": False,
                    "reason_en": "Never invented — fill manually if you know the value.",
                    "reason_ar": "مش بيتولَّد — املأه يدوي لو تعرفه.",
                    "evidence": None,
                }
                continue
            if field == "unit_price" and stock and stock in price_by_stock:
                val = price_by_stock[stock]
                suggestions[field] = {
                    "suggested": val,
                    "allowed": True,
                    "reason_en": f"Median unit_price for stock {stock} in this file.",
                    "reason_ar": f"وسيط سعر الوحدة للمنتج {stock} في الملف ده.",
                    "evidence": {"stock_code": stock, "stat": "median", "n_peers": "file"},
                }
            elif field == "description" and stock and stock in desc_by_stock:
                val = desc_by_stock[stock]
                suggestions[field] = {
                    "suggested": val,
                    "allowed": True,
                    "reason_en": f"Most common description for stock {stock} in this file.",
                    "reason_ar": f"أشهر وصف للمنتج {stock} في الملف ده.",
                    "evidence": {"stock_code": stock, "stat": "mode"},
                }
            else:
                suggestions[field] = {
                    "suggested": None,
                    "allowed": False,
                    "reason_en": "No same-file pattern strong enough — fill manually.",
                    "reason_ar": "مفيش نمط كافي في الملف — املأه يدوي.",
                    "evidence": None,
                }

        rows.append(
            {
                "row_index": int(idx) if not isinstance(idx, tuple) else int(idx[0]),
                "invoice": None if pd.isna(row.get("invoice")) else str(row.get("invoice")),
                "stock_code": stock,
                "description": None
                if pd.isna(row.get("description"))
                else str(row.get("description")),
                "quantity": None if pd.isna(row.get("quantity")) else float(row.get("quantity")),
                "unit_price": None
                if pd.isna(row.get("unit_price"))
                else float(row.get("unit_price")),
                "customer_id": None
                if pd.isna(row.get("customer_id"))
                else float(row.get("customer_id")),
                "invoice_date": None
                if pd.isna(row.get("invoice_date"))
                else str(row.get("invoice_date")),
                "issues": issues,
                "suggestions": suggestions,
            }
        )

    return {
        "rows": rows,
        "smart_fillable_fields": sorted(SMART_FILLABLE),
        "manual_only_fields": sorted(MANUAL_ONLY),
        "note_en": (
            "Smart fill only proposes values with same-file evidence (e.g. median price "
            "for the same stock code). Customer IDs and invoice dates are never invented. "
            "Nothing is written until you approve and save."
        ),
        "note_ar": (
            "الملء الذكي بيقترح قيم ليها دليل من نفس الملف (مثل وسيط السعر لنفس كود المنتج). "
            "رقم الزبون وتاريخ الفاتورة مش بيتولَّدوا. مفيش حفظ غير بعد موافقتك."
        ),
    }


def apply_patches_to_source(
    raw_df: pd.DataFrame,
    patches: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Apply user-approved patches onto the source-column dataframe.

    Each patch: {row_index, field (canonical), value, source: manual|smart}
    """
    out = raw_df.copy()
    applied: list[dict[str, Any]] = []
    for p in patches:
        field = str(p.get("field") or "")
        if field not in SOURCE_COLUMN_MAP:
            continue
        src_col = SOURCE_COLUMN_MAP[field]
        if src_col not in out.columns:
            continue
        try:
            idx = int(p["row_index"])
        except (KeyError, TypeError, ValueError):
            continue
        if idx in out.index:
            loc = idx
        elif 0 <= idx < len(out):
            loc = out.index[idx]
        else:
            continue

        value = p.get("value")
        source = str(p.get("source") or "manual")
        if source == "smart" and field in MANUAL_ONLY:
            # Hard block inventing IDs/dates even if client sends smart
            continue
        if value is None or value == "":
            continue

        if field in {"quantity", "unit_price", "customer_id"}:
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
        else:
            value = str(value)

        out.at[loc, src_col] = value
        applied.append(
            {
                "row_index": int(idx),
                "field": field,
                "source_column": src_col,
                "value": value,
                "source": source,
            }
        )
    return out, applied


def write_source_dataframe(path, df: pd.DataFrame) -> None:
    suffix = str(path).lower()
    if suffix.endswith(".csv"):
        df.to_csv(path, index=False)
    elif suffix.endswith(".xlsx"):
        df.to_excel(path, index=False)
    else:
        raise ValueError("Unsupported file type")
