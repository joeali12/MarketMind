"""Evidence-based gap-fill suggestions for unresolved upload rows.

Smart fills are never applied silently. Only fields with a clear same-file
pattern are proposed. Customer IDs, invoices, invoice dates, and quantities
are never invented — those stay manual-only.

Unit-price rules (documented):
- Require at least MIN_PRICE_PEERS non-null non-negative peer prices for the
  same stock_code in this file.
- Require price stability: coefficient of variation (std/mean) of peers must
  be <= PRICE_STABILITY_MAX_CV. If peers conflict, do not propose a value.

Description rules:
- Fill only when every non-empty peer description for that stock_code matches
  exactly (unambiguous same-product mapping).
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

# Documented unit-price evidence thresholds
MIN_PRICE_PEERS = 3
PRICE_STABILITY_MAX_CV = 0.25


def _stable_peer_price(prices: pd.Series) -> tuple[float | None, dict[str, Any]]:
    """Return (median, evidence) only when peer count and CV pass; else (None, evidence)."""
    clean = prices.dropna()
    clean = clean[clean >= 0]
    n = int(len(clean))
    evidence: dict[str, Any] = {
        "stat": "median",
        "n_peers": n,
        "min_peers_required": MIN_PRICE_PEERS,
        "max_cv_allowed": PRICE_STABILITY_MAX_CV,
    }
    if n < MIN_PRICE_PEERS:
        evidence["rejected"] = "insufficient_peers"
        return None, evidence
    mean = float(clean.mean())
    if mean <= 0:
        evidence["rejected"] = "non_positive_mean"
        return None, evidence
    cv = float(clean.std(ddof=0) / mean)
    evidence["cv"] = round(cv, 4)
    evidence["median"] = float(clean.median())
    if cv > PRICE_STABILITY_MAX_CV:
        evidence["rejected"] = "unstable_prices"
        return None, evidence
    return float(clean.median()), evidence


def _unambiguous_description(descs: pd.Series) -> tuple[str | None, dict[str, Any]]:
    clean = descs.dropna().astype(str).str.strip()
    clean = clean[clean != ""]
    n = int(len(clean))
    evidence: dict[str, Any] = {"stat": "exact_peer_consensus", "n_peers": n}
    if n < 1:
        evidence["rejected"] = "no_peers"
        return None, evidence
    unique = clean.unique()
    if len(unique) != 1:
        evidence["rejected"] = "conflicting_descriptions"
        evidence["n_distinct"] = int(len(unique))
        return None, evidence
    return str(unique[0]), evidence


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
            "price_policy": {
                "min_peers": MIN_PRICE_PEERS,
                "max_cv": PRICE_STABILITY_MAX_CV,
            },
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

    price_by_stock: dict[str, tuple[float | None, dict[str, Any]]] = {}
    desc_by_stock: dict[str, tuple[str | None, dict[str, Any]]] = {}
    if "stock_code" in parsed.columns:
        for stock, part in parsed.groupby(parsed["stock_code"].astype(str), dropna=True):
            price_by_stock[str(stock)] = _stable_peer_price(part["unit_price"])
            desc_by_stock[str(stock)] = _unambiguous_description(part["description"])

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
                val, evidence = price_by_stock[stock]
                if val is not None:
                    suggestions[field] = {
                        "suggested": val,
                        "allowed": True,
                        "reason_en": (
                            f"Stable same-stock unit_price median "
                            f"(n={evidence['n_peers']}, cv≤{PRICE_STABILITY_MAX_CV})."
                        ),
                        "reason_ar": (
                            f"وسيط سعر مستقر لنفس كود المنتج "
                            f"(n={evidence['n_peers']}، cv≤{PRICE_STABILITY_MAX_CV})."
                        ),
                        "evidence": {**evidence, "stock_code": stock},
                    }
                else:
                    why = evidence.get("rejected") or "insufficient_evidence"
                    suggestions[field] = {
                        "suggested": None,
                        "allowed": False,
                        "reason_en": (
                            f"No automatic unit_price ({why}). "
                            f"Need ≥{MIN_PRICE_PEERS} stable peer prices for the same stock."
                        ),
                        "reason_ar": (
                            f"مفيش سعر تلقائي ({why}). "
                            f"محتاج ≥{MIN_PRICE_PEERS} أسعار مستقرة لنفس كود المنتج."
                        ),
                        "evidence": {**evidence, "stock_code": stock},
                    }
            elif field == "description" and stock and stock in desc_by_stock:
                val, evidence = desc_by_stock[stock]
                if val is not None:
                    suggestions[field] = {
                        "suggested": val,
                        "allowed": True,
                        "reason_en": "Exact same-product description consensus in this file.",
                        "reason_ar": "وصف المنتج متطابق لكل الأقران في الملف ده.",
                        "evidence": {**evidence, "stock_code": stock},
                    }
                else:
                    suggestions[field] = {
                        "suggested": None,
                        "allowed": False,
                        "reason_en": "Description peers conflict or are missing — fill manually.",
                        "reason_ar": "أوصاف الأقران متعارضة أو ناقصة — املأه يدوي.",
                        "evidence": {**evidence, "stock_code": stock},
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
        "price_policy": {
            "min_peers": MIN_PRICE_PEERS,
            "max_cv": PRICE_STABILITY_MAX_CV,
        },
        "note_en": (
            f"Smart fill proposes unit_price only with ≥{MIN_PRICE_PEERS} peer prices "
            f"and CV≤{PRICE_STABILITY_MAX_CV} for the same stock code; descriptions only "
            "when every peer description matches. Customer IDs, invoices, dates, and "
            "quantities are never invented. Nothing is written until you approve."
        ),
        "note_ar": (
            f"الملء الذكي بيقترح السعر بس لو فيه ≥{MIN_PRICE_PEERS} أسعار أقران "
            f"وCV≤{PRICE_STABILITY_MAX_CV} لنفس كود المنتج؛ والوصف بس لو كل الأقران متطابقين. "
            "رقم الزبون والفواتير والتواريخ والكميات مش بيتولَّدوا. مفيش حفظ غير بعد موافقتك."
        ),
    }


def apply_patches_to_source(
    raw_df: pd.DataFrame,
    patches: list[dict[str, Any]],
    *,
    column_mapping: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Apply user-approved patches onto the source-column dataframe.

    Each patch: {row_index, field (canonical), value, source: manual|smart}
    """
    out = raw_df.copy()
    applied: list[dict[str, Any]] = []
    # Prefer session mapping; fall back to UCI defaults for academic-style files.
    field_to_source = dict(SOURCE_COLUMN_MAP)
    if column_mapping:
        field_to_source.update({k: v for k, v in column_mapping.items() if v})
    for p in patches:
        field = str(p.get("field") or "")
        if field not in field_to_source:
            continue
        src_col = field_to_source[field]
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
            # Hard block inventing IDs/dates/qty even if client sends smart
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


def pre_safe_fill_backup_path(path) -> Any:
    return path.with_suffix(path.suffix + ".pre_safe_fill.bak")
