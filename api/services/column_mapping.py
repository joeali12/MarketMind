"""POS / retail header detection, session mapping, and canonical framing.

Academic UCI training still uses marketmind.data.schema.to_canonical with exact
Online Retail II headers. Upload sessions use this module instead.

Capabilities (minimum data):
- sales_totals / product_rankings: product id or name + (line_amount OR qty×unit_price)
- date_trends: usable invoice_date + monetary measure
- order_counts: invoice/order id (else unavailable — do not treat each row as an order)
- customer_groups / returning: usable customer_id
- category_analysis: explicitly mapped category
- country / customer_id are optional for store-level sales
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

# Canonical fields used by upload analytics / cleaning / assistant.
CANONICAL_FIELDS: tuple[str, ...] = (
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "line_amount",
    "customer_id",
    "country",
    "category",
    "row_currency",
)

# Optional for store sales; required for specific capabilities.
OPTIONAL_FOR_SALES: frozenset[str] = frozenset(
    {"invoice", "customer_id", "country", "category", "row_currency", "stock_code"}
)

AUTO_APPLY_MIN_CONF = 0.85
SUGGEST_MIN_CONF = 0.70

# Normalized header key → (canonical, confidence, note)
# Never map bare "amount"/"total" to unit_price — those are ambiguous.
_ALIAS_TABLE: list[tuple[str, str, float, str]] = [
    # invoice / order
    ("invoice", "invoice", 1.0, "exact"),
    ("invoiceno", "invoice", 0.95, "alias"),
    ("invoice_no", "invoice", 0.95, "alias"),
    ("invoice number", "invoice", 0.95, "alias"),
    ("order id", "invoice", 0.9, "alias"),
    ("order_id", "invoice", 0.9, "alias"),
    ("orderno", "invoice", 0.9, "alias"),
    ("order number", "invoice", 0.9, "alias"),
    ("order no", "invoice", 0.9, "alias"),
    ("transaction id", "invoice", 0.9, "alias"),
    ("transaction_id", "invoice", 0.9, "alias"),
    ("txn id", "invoice", 0.88, "alias"),
    ("txnid", "invoice", 0.88, "alias"),
    ("txn_id", "invoice", 0.88, "alias"),
    ("txnid", "invoice", 0.88, "alias"),
    ("bill no", "invoice", 0.85, "alias"),
    ("receipt no", "invoice", 0.85, "alias"),
    ("رقم الفاتورة", "invoice", 0.95, "ar"),
    ("رقم الطلب", "invoice", 0.9, "ar"),
    ("رقم الإيصال", "invoice", 0.85, "ar"),
    # dates
    ("invoicedate", "invoice_date", 1.0, "exact"),
    ("invoice date", "invoice_date", 1.0, "exact"),
    ("order date", "invoice_date", 0.95, "alias"),
    ("order_date", "invoice_date", 0.95, "alias"),
    ("sale date", "invoice_date", 0.9, "alias"),
    ("sales date", "invoice_date", 0.9, "alias"),
    ("transaction date", "invoice_date", 0.95, "alias"),
    ("txn date", "invoice_date", 0.9, "alias"),
    ("date", "invoice_date", 0.72, "generic_date"),
    ("تاريخ الفاتورة", "invoice_date", 0.95, "ar"),
    ("تاريخ البيع", "invoice_date", 0.9, "ar"),
    ("التاريخ", "invoice_date", 0.75, "ar"),
    # customer
    ("customer id", "customer_id", 1.0, "exact"),
    ("customerid", "customer_id", 1.0, "exact"),
    ("customer", "customer_id", 0.78, "generic_customer"),
    ("client id", "customer_id", 0.9, "alias"),
    ("clientid", "customer_id", 0.9, "alias"),
    ("buyer id", "customer_id", 0.85, "alias"),
    ("رقم الزبون", "customer_id", 0.95, "ar"),
    ("كود الزبون", "customer_id", 0.9, "ar"),
    ("العميل", "customer_id", 0.78, "ar"),
    # product code
    ("stockcode", "stock_code", 1.0, "exact"),
    ("stock code", "stock_code", 1.0, "exact"),
    ("sku", "stock_code", 0.95, "alias"),
    ("item code", "stock_code", 0.9, "alias"),
    ("item_code", "stock_code", 0.9, "alias"),
    ("product code", "stock_code", 0.9, "alias"),
    ("product_code", "stock_code", 0.9, "alias"),
    ("كود المنتج", "stock_code", 0.95, "ar"),
    ("رمز الصنف", "stock_code", 0.9, "ar"),
    # description / name
    ("description", "description", 1.0, "exact"),
    ("item", "description", 0.88, "alias"),
    ("item name", "description", 0.95, "alias"),
    ("item_name", "description", 0.95, "alias"),
    ("product", "description", 0.85, "alias"),
    ("product name", "description", 0.95, "alias"),
    ("product_name", "description", 0.95, "alias"),
    ("product description", "description", 0.95, "alias"),
    ("اسم المنتج", "description", 0.95, "ar"),
    ("وصف المنتج", "description", 0.95, "ar"),
    ("الصنف", "description", 0.88, "ar"),
    # quantity
    ("quantity", "quantity", 1.0, "exact"),
    ("qty", "quantity", 0.95, "alias"),
    ("units", "quantity", 0.85, "alias"),
    ("units sold", "quantity", 0.9, "alias"),
    ("qty sold", "quantity", 0.9, "alias"),
    ("الكمية", "quantity", 0.95, "ar"),
    ("كمية", "quantity", 0.9, "ar"),
    # unit price (explicit only)
    ("price", "unit_price", 0.92, "uci_price"),
    ("unitprice", "unit_price", 1.0, "exact"),
    ("unit price", "unit_price", 1.0, "exact"),
    ("unit_price", "unit_price", 1.0, "exact"),
    ("unit selling price", "unit_price", 0.95, "alias"),
    ("selling price", "unit_price", 0.88, "alias"),
    ("سعر الوحدة", "unit_price", 0.95, "ar"),
    ("سعر البيع", "unit_price", 0.85, "ar"),
    # line total / revenue (NOT unit price)
    ("line total", "line_amount", 0.95, "alias"),
    ("line_total", "line_amount", 0.95, "alias"),
    ("line amount", "line_amount", 0.95, "alias"),
    ("line_amount", "line_amount", 0.95, "alias"),
    ("sales amount", "line_amount", 0.9, "alias"),
    ("sales_amount", "line_amount", 0.9, "alias"),
    ("revenue", "line_amount", 0.85, "alias"),
    ("net sales", "line_amount", 0.85, "alias"),
    ("extended price", "line_amount", 0.9, "alias"),
    ("إجمالي السطر", "line_amount", 0.95, "ar"),
    ("قيمة السطر", "line_amount", 0.9, "ar"),
    ("المبلغ", "line_amount", 0.72, "ar_ambiguous"),
    # category
    ("category", "category", 1.0, "exact"),
    ("product category", "category", 0.95, "alias"),
    ("product_category", "category", 0.95, "alias"),
    ("product group", "category", 0.9, "alias"),
    ("dept", "category", 0.8, "alias"),
    ("department", "category", 0.85, "alias"),
    ("التصنيف", "category", 0.95, "ar"),
    ("الفئة", "category", 0.9, "ar"),
    # country
    ("country", "country", 1.0, "exact"),
    ("الدولة", "country", 0.9, "ar"),
    # currency column
    ("currency", "row_currency", 1.0, "exact"),
    ("curr", "row_currency", 0.85, "alias"),
    ("العملة", "row_currency", 0.95, "ar"),
]

# Headers that must never auto-map; user chooses unit_price vs line_amount vs ignore.
_AMBIGUOUS_AMOUNT_KEYS = frozenset(
    {
        "amount",
        "total",
        "totals",
        "value",
        "net",
        "gross",
        "sum",
        "المبلغ الإجمالي",
        "الإجمالي",
    }
)

# Cost / tax / discount — never map to selling measures automatically.
_BLOCKED_KEYS = frozenset(
    {
        "cost",
        "unit cost",
        "unit_cost",
        "tax",
        "vat",
        "discount",
        "disc",
        "تكلفة",
        "ضريبة",
        "خصم",
    }
)

_PUNCT_RE = re.compile(r"[^\w\s\u0600-\u06ff]+", re.UNICODE)


def normalize_header(name: object) -> str:
    """Lowercase, strip, collapse whitespace/underscores/punctuation for matching."""
    s = str(name or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = _PUNCT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _alias_lookup() -> dict[str, tuple[str, float, str]]:
    out: dict[str, tuple[str, float, str]] = {}
    for key, canon, conf, note in _ALIAS_TABLE:
        nk = normalize_header(key)
        compact = nk.replace(" ", "")
        out[nk] = (canon, conf, note)
        out[compact] = (canon, conf, note)
    return out


_LOOKUP = _alias_lookup()


def suggest_mappings(columns: list[str]) -> dict[str, Any]:
    """Score source headers → canonical fields. Amount/Total stay ambiguous."""
    mappings: list[dict[str, Any]] = []
    claimed: dict[str, str] = {}  # canon -> source already auto-claimed

    for col in columns:
        norm = normalize_header(col)
        compact = norm.replace(" ", "")
        blocked = norm in _BLOCKED_KEYS or compact in {normalize_header(b).replace(" ", "") for b in _BLOCKED_KEYS}
        if blocked:
            mappings.append(
                {
                    "source_column": col,
                    "target": None,
                    "confidence": 0.0,
                    "auto_apply": False,
                    "needs_user_confirm": True,
                    "ambiguous": False,
                    "blocked": True,
                    "candidates": [],
                    "note_en": "Looks like cost/tax/discount — not mapped to selling measures.",
                    "note_ar": "يبدو تكلفة/ضريبة/خصم — مش بيتربط بمقاييس البيع تلقائيًا.",
                }
            )
            continue

        if norm in _AMBIGUOUS_AMOUNT_KEYS or compact in {"amount", "total", "value", "net", "gross"}:
            mappings.append(
                {
                    "source_column": col,
                    "target": None,
                    "confidence": 0.0,
                    "auto_apply": False,
                    "needs_user_confirm": True,
                    "ambiguous": True,
                    "blocked": False,
                    "candidates": ["unit_price", "line_amount", "ignore"],
                    "note_en": (
                        "Ambiguous Amount/Total — confirm whether this is unit selling price, "
                        "line amount, or neither. Never auto-mapped to unit_price."
                    ),
                    "note_ar": (
                        "عمود Amount/Total غامض — أكّد هل هو سعر وحدة ولا إجمالي سطر ولا حاجة تانية. "
                        "مش بيتربط بسعر الوحدة تلقائيًا."
                    ),
                }
            )
            continue

        hit = _LOOKUP.get(norm) or _LOOKUP.get(compact)
        if not hit:
            mappings.append(
                {
                    "source_column": col,
                    "target": None,
                    "confidence": 0.0,
                    "auto_apply": False,
                    "needs_user_confirm": False,
                    "ambiguous": False,
                    "blocked": False,
                    "candidates": [],
                    "note_en": "Unrecognized header — map manually if needed.",
                    "note_ar": "عنوان مش معروف — اربطه يدوي لو محتاج.",
                }
            )
            continue

        target, conf, note = hit
        conflict = target in claimed
        auto = conf >= AUTO_APPLY_MIN_CONF and not conflict and target != "category"
        # Category can auto-suggest but still optional
        if target == "category":
            auto = conf >= AUTO_APPLY_MIN_CONF and not conflict
        needs = conf < AUTO_APPLY_MIN_CONF or conflict or note in {"generic_date", "generic_customer", "ar_ambiguous"}
        if auto:
            claimed[target] = col
        mappings.append(
            {
                "source_column": col,
                "target": target,
                "confidence": conf,
                "auto_apply": auto,
                "needs_user_confirm": needs and not auto,
                "ambiguous": False,
                "blocked": False,
                "candidates": [target] if target else [],
                "note_en": (
                    "Conflict: another column already maps here"
                    if conflict
                    else ("Low confidence — confirm before using" if needs else "Recognized header")
                ),
                "note_ar": (
                    "تعارض: عمود تاني مربوط بنفس الحقل"
                    if conflict
                    else ("ثقة ضعيفة — أكّد قبل الاستخدام" if needs else "عنوان معروف")
                ),
            }
        )

    auto_map = {
        m["target"]: m["source_column"]
        for m in mappings
        if m.get("auto_apply") and m.get("target")
    }
    return {
        "mappings": mappings,
        "auto_mapping": auto_map,
        "needs_confirmation": any(m.get("needs_user_confirm") for m in mappings),
        "ambiguous_columns": [m["source_column"] for m in mappings if m.get("ambiguous")],
        "auto_apply_min_confidence": AUTO_APPLY_MIN_CONF,
        "canonical_fields": list(CANONICAL_FIELDS),
        "note_en": (
            "High-confidence non-conflicting headers apply automatically. "
            "Ambiguous Amount/Total and low-confidence headers need your confirmation."
        ),
        "note_ar": (
            "العناوين عالية الثقة وغير المتعارضة بتتطبّق تلقائي. "
            "Amount/Total الغامض والعناوين ضعيفة الثقة محتاجين تأكيدك."
        ),
    }


def merge_user_mapping(
    suggestions: dict[str, Any],
    user_mapping: dict[str, str] | None,
) -> dict[str, str]:
    """Build canon→source map from auto suggestions + explicit user choices.

    user_mapping keys are canonical field names; values are source column names
    or "" / "ignore" to leave unmapped.
    """
    merged = dict(suggestions.get("auto_mapping") or {})
    if user_mapping:
        for canon, source in user_mapping.items():
            if canon not in CANONICAL_FIELDS:
                continue
            if source in (None, "", "ignore"):
                merged.pop(canon, None)
                continue
            # Drop other canons pointing at same source
            for k, v in list(merged.items()):
                if v == source and k != canon:
                    del merged[k]
            merged[canon] = str(source)
    return merged


def assess_capabilities(mapping: dict[str, str]) -> dict[str, Any]:
    """Capability flags from a confirmed/auto mapping (canon→source)."""
    has = set(mapping.keys())
    has_product = "stock_code" in has or "description" in has
    has_money = "line_amount" in has or ("quantity" in has and "unit_price" in has)
    has_qty_price = "quantity" in has and "unit_price" in has
    caps = {
        "sales_totals": has_product and has_money,
        "product_rankings": has_product and has_money,
        "date_trends": "invoice_date" in has and has_money,
        "order_counts": "invoice" in has,
        "customer_groups": "customer_id" in has,
        "returning_customers": "customer_id" in has and "invoice" in has,
        "category_analysis": "category" in has,
        "row_currency_column": "row_currency" in has,
    }
    blockers: list[dict[str, str]] = []
    if not has_product:
        blockers.append(
            {
                "en": "Map a product code or product name/description column.",
                "ar": "اربط عمود كود منتج أو اسم/وصف المنتج.",
            }
        )
    if not has_money:
        blockers.append(
            {
                "en": "Map either line amount/revenue, or both quantity and unit selling price.",
                "ar": "اربط إجمالي السطر/المبيعات، أو الكمية وسعر الوحدة معًا.",
            }
        )
    ready = caps["sales_totals"]
    return {
        "capabilities": caps,
        "analysis_ready_minimum": ready,
        "has_product": has_product,
        "has_money": has_money,
        "has_qty_and_unit_price": has_qty_price,
        "has_line_amount": "line_amount" in has,
        "blockers": blockers,
        "message_en": (
            "File can support store/product sales analysis."
            if ready
            else "Not enough mapped fields for sales analysis yet."
        ),
        "message_ar": (
            "الملف يقدر يدعم تحليل مبيعات المتجر/المنتجات."
            if ready
            else "لسه مفيش ربط كافي لتحليل المبيعات."
        ),
    }


def apply_mapping_to_frame(
    raw: pd.DataFrame,
    mapping: dict[str, str],
) -> pd.DataFrame:
    """Project source columns into a canonical frame (missing → NA columns)."""
    out: dict[str, Any] = {}
    for canon in CANONICAL_FIELDS:
        src = mapping.get(canon)
        if src and src in raw.columns:
            out[canon] = raw[src]
        else:
            out[canon] = pd.Series([pd.NA] * len(raw), index=raw.index)
    return pd.DataFrame(out, index=raw.index)


def parse_canonical_types(
    canonical: pd.DataFrame,
    *,
    date_format: str | None = None,
) -> pd.DataFrame:
    """Type-parse a canonical upload frame and compute line_amount without double-counting."""
    from marketmind.data.cleaning import is_cancellation_invoice

    out = canonical.copy()
    n = len(out)

    def _as_str(col: str) -> pd.Series:
        if col not in out.columns:
            return pd.Series([pd.NA] * n, dtype="string")
        return out[col].astype("string")

    out["invoice"] = _as_str("invoice").fillna("").astype(str).str.strip()
    # Synthetic row invoice when missing — used only for cancellation pattern; order counts gated separately
    missing_inv = out["invoice"].isin({"", "nan", "None", "<NA>"})
    if missing_inv.any():
        out.loc[missing_inv, "invoice"] = [f"ROW-{i}" for i in out.index[missing_inv]]

    out["stock_code"] = _as_str("stock_code").fillna("").astype(str).str.strip()
    out["description"] = _as_str("description")
    out["quantity"] = pd.to_numeric(out.get("quantity"), errors="coerce")
    out["unit_price"] = pd.to_numeric(out.get("unit_price"), errors="coerce")
    mapped_line = pd.to_numeric(out.get("line_amount"), errors="coerce") if "line_amount" in out.columns else None
    # customer_id: keep as string-capable numeric where possible
    cid_raw = out.get("customer_id")
    if cid_raw is not None:
        as_num = pd.to_numeric(cid_raw, errors="coerce")
        # If mostly non-numeric IDs, keep string codes in a parallel-friendly float NaN + string store
        if as_num.notna().sum() >= max(1, int(0.5 * cid_raw.notna().sum())):
            out["customer_id"] = as_num
        else:
            # Hash-free: store categorical codes as nullable string; analytics use dropna nunique on string
            out["customer_id"] = cid_raw.astype("string")
    else:
        out["customer_id"] = pd.Series([pd.NA] * n)
    out["country"] = _as_str("country")
    if "category" in out.columns:
        out["category"] = _as_str("category")
    if "row_currency" in out.columns:
        out["row_currency"] = _as_str("row_currency").str.upper()

    raw_dates = out.get("invoice_date")
    if raw_dates is None:
        out["invoice_date"] = pd.Series([pd.NaT] * n)
    elif date_format == "dayfirst":
        out["invoice_date"] = pd.to_datetime(raw_dates, errors="coerce", format="mixed", dayfirst=True)
    elif date_format == "monthfirst":
        out["invoice_date"] = pd.to_datetime(raw_dates, errors="coerce", format="mixed", dayfirst=False)
    elif date_format == "iso":
        out["invoice_date"] = pd.to_datetime(raw_dates, errors="coerce", format="ISO8601")
        still = out["invoice_date"].isna() & pd.Series(raw_dates).notna()
        if still.any():
            out.loc[still, "invoice_date"] = pd.to_datetime(
                pd.Series(raw_dates)[still], errors="coerce", format="%Y-%m-%d", exact=False
            )
    else:
        # Unconfirmed format: parse unambiguous ISO only. Do not guess DMY vs MDY.
        out["invoice_date"] = pd.to_datetime(raw_dates, errors="coerce", format="ISO8601")

    out["is_cancellation"] = is_cancellation_invoice(out["invoice"])

    # Monetary: prefer explicit line_amount; else qty × unit_price. Never multiply line_amount by qty.
    qty_price = out["quantity"] * out["unit_price"]
    if mapped_line is not None and mapped_line.notna().any():
        out["line_amount"] = mapped_line
        # Fill gaps with qty×price only where line amount missing
        need = out["line_amount"].isna() & qty_price.notna()
        out.loc[need, "line_amount"] = qty_price[need]
        out["money_source"] = "line_amount"
        out.loc[need, "money_source"] = "qty_x_unit_price"
    else:
        out["line_amount"] = qty_price
        out["money_source"] = "qty_x_unit_price"

    # Product display fallback
    blank_desc = out["description"].isna() | (out["description"].astype(str).str.strip() == "")
    blank_code = out["stock_code"].isin({"", "nan", "None", "<NA>"})
    out.loc[blank_desc & ~blank_code, "description"] = out.loc[blank_desc & ~blank_code, "stock_code"]
    out.loc[blank_code & out["description"].notna(), "stock_code"] = (
        out.loc[blank_code & out["description"].notna(), "description"].astype(str).str.slice(0, 40)
    )
    return out


def capability_docs() -> dict[str, Any]:
    return {
        "sales_totals": {
            "requires": ["product (stock_code|description)", "money (line_amount|(quantity&unit_price))"],
            "optional": ["invoice", "customer_id", "country", "category"],
        },
        "product_rankings": {
            "requires": ["product", "money"],
        },
        "date_trends": {"requires": ["invoice_date", "money"]},
        "order_counts": {"requires": ["invoice"]},
        "customer_groups": {"requires": ["customer_id"]},
        "category_analysis": {"requires": ["category"]},
        "notes_en": (
            "Anonymous sales (missing customer_id) stay in store totals. "
            "Missing optional fields disable only dependent metrics."
        ),
    }
