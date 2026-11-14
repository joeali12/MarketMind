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


def _serialize_customer_id(val: Any) -> int | float | str | None:
    """Serialize customer IDs without float precision loss.

    Alphanumeric and long digit / scientific-notation IDs stay strings.
    Only short integer-like values (≤15 digits) may be returned as int.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return int(val)
    if isinstance(val, float):
        # Already lost precision if huge; keep as int only when safe.
        if val.is_integer() and abs(val) < 1e15:
            return int(val)
        return repr(val) if abs(val) >= 1e15 else float(val)
    text = str(val).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    if any(ch in text.lower() for ch in ("e+", "e-", "e")) and _looks_scientific(text):
        return text
    if text.lstrip("-").isdigit():
        digits = text.lstrip("-")
        if len(digits) <= 15:
            return int(text)
        return text
    try:
        num = float(text)
    except ValueError:
        return text
    if num.is_integer() and abs(num) < 1e15 and "e" not in text.lower():
        return int(num)
    return text


def _looks_scientific(text: str) -> bool:
    t = text.lower().replace("+", "").replace("-", "")
    return "e" in t and t.replace("e", "").replace(".", "").isdigit()


def _line_amount_complete(row: pd.Series) -> bool:
    """Mapped line totals satisfy money without requiring unit_price."""
    if "money_source" in row.index and str(row.get("money_source")) == "line_amount":
        return pd.notna(row.get("line_amount"))
    return pd.notna(row.get("line_amount")) and pd.isna(row.get("unit_price"))


def _issues_for_row(row: pd.Series) -> list[str]:
    issues = []
    if pd.isna(row.get("invoice_date")):
        issues.append("invoice_date")
    if pd.isna(row.get("quantity")):
        issues.append("quantity")
    if pd.isna(row.get("unit_price")) and not _line_amount_complete(row):
        issues.append("unit_price")
    if pd.isna(row.get("line_amount")) and _line_amount_complete(row) is False:
        # Only flag line_amount when that is the monetary path and it is missing
        if "money_source" in row.index and str(row.get("money_source")) == "line_amount":
            issues.append("line_amount")
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

    unit_price_gap = parsed["unit_price"].isna()
    if "money_source" in parsed.columns:
        line_ok = parsed["money_source"].astype("string").eq("line_amount") & parsed[
            "line_amount"
        ].notna()
        unit_price_gap = unit_price_gap & ~line_ok
    elif "line_amount" in parsed.columns:
        line_ok = parsed["line_amount"].notna() & parsed["unit_price"].isna()
        # If every row with money uses line_amount only, don't treat unit_price as required
        if bool(parsed["unit_price"].isna().all()) and bool(parsed["line_amount"].notna().any()):
            unit_price_gap = parsed["line_amount"].isna()
    mask = (
        parsed["invoice_date"].isna()
        | parsed["quantity"].isna()
        | unit_price_gap
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
                "customer_id": _serialize_customer_id(row.get("customer_id")),
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

        if field in {"quantity", "unit_price"}:
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
        elif field == "customer_id":
            # Keep IDs textual — never float-cast (precision / alphanumeric).
            value = str(value).strip()
            if not value:
                continue
        else:
            value = str(value)

        # Source frames may be all-string (CSV/Excel dtype=str). Match dtype on write.
        col_dtype = out[src_col].dtype
        if pd.api.types.is_string_dtype(col_dtype) or str(col_dtype) in {
            "string",
            "object",
            "str",
        }:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            value = str(value)
        try:
            out.at[loc, src_col] = value
        except (TypeError, ValueError):
            out[src_col] = out[src_col].astype(object)
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


def write_source_dataframe(
    path,
    df: pd.DataFrame,
    *,
    sheet_name: str | None = None,
) -> None:
    """Write the session file. For multi-sheet Excel, replace only ``sheet_name``."""
    from pathlib import Path

    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        df.to_csv(p, index=False)
        return
    if suffix in {".xlsx", ".xls"}:
        target = sheet_name
        other_sheets: dict[str, pd.DataFrame] = {}
        if p.exists():
            try:
                book = pd.read_excel(p, sheet_name=None, engine="openpyxl")
            except Exception:  # noqa: BLE001
                book = {}
            if isinstance(book, dict) and book:
                if not target:
                    target = next(iter(book.keys()))
                for name, frame in book.items():
                    if name != target:
                        other_sheets[name] = frame
        if not target:
            target = "Sheet1"
        with pd.ExcelWriter(p, engine="openpyxl") as writer:
            for name, frame in other_sheets.items():
                frame.to_excel(writer, sheet_name=str(name)[:31], index=False)
            df.to_excel(writer, sheet_name=str(target)[:31], index=False)
        return
    raise ValueError("Unsupported file type")


def pre_safe_fill_backup_path(path) -> Any:
    return path.with_suffix(path.suffix + ".pre_safe_fill.bak")
