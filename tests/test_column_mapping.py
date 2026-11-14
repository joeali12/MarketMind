"""POS header aliases, ambiguous Amount, and capability gates."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api.services import column_mapping as cmap


def test_english_and_arabic_aliases():
    en = cmap.suggest_mappings(
        ["order_id", "order_date", "item", "sku", "qty", "unit_price", "customer_id"]
    )
    assert en["auto_mapping"]["invoice"] == "order_id"
    assert en["auto_mapping"]["unit_price"] == "unit_price"
    ar = cmap.suggest_mappings(
        ["رقم الفاتورة", "تاريخ البيع", "اسم المنتج", "الكمية", "سعر الوحدة"]
    )
    assert ar["auto_mapping"]["invoice"] == "رقم الفاتورة"
    assert ar["auto_mapping"]["unit_price"] == "سعر الوحدة"


def test_amount_never_auto_maps_to_unit_price():
    sug = cmap.suggest_mappings(["Product", "Qty", "Amount"])
    amount = next(m for m in sug["mappings"] if m["source_column"] == "Amount")
    assert amount["ambiguous"] is True
    assert amount["auto_apply"] is False
    assert "unit_price" not in sug["auto_mapping"].values()
    assert "Amount" not in sug["auto_mapping"].values()


def test_line_total_maps_without_qty_multiply_double_count():
    raw = pd.DataFrame(
        {
            "ProductName": ["Tea", "Coffee"],
            "Qty": [2, 1],
            "LineTotal": [20.0, 12.0],
        }
    )
    sug = cmap.suggest_mappings(list(raw.columns))
    mapping = sug["auto_mapping"]
    assert mapping.get("line_amount") == "LineTotal"
    assert "unit_price" not in mapping
    parsed = cmap.parse_canonical_types(cmap.apply_mapping_to_frame(raw, mapping))
    assert float(parsed["line_amount"].sum()) == 32.0
    # Must not be qty * line_total
    assert float(parsed["line_amount"].iloc[0]) == 20.0


def test_qty_times_unit_price():
    raw = pd.DataFrame(
        {"item": ["A", "B"], "qty": [2, 3], "unit_price": [10.0, 5.0]}
    )
    mapping = cmap.suggest_mappings(list(raw.columns))["auto_mapping"]
    parsed = cmap.parse_canonical_types(cmap.apply_mapping_to_frame(raw, mapping))
    assert float(parsed["line_amount"].sum()) == 35.0


def test_capabilities_without_customer():
    mapping = {"description": "item", "quantity": "qty", "unit_price": "unit_price"}
    caps = cmap.assess_capabilities(mapping)
    assert caps["analysis_ready_minimum"] is True
    assert caps["capabilities"]["customer_groups"] is False
    assert caps["capabilities"]["sales_totals"] is True


def test_capabilities_without_date_disables_trends_only():
    mapping = {
        "description": "item",
        "quantity": "qty",
        "unit_price": "unit_price",
        "customer_id": "customer_id",
    }
    caps = cmap.assess_capabilities(mapping)
    assert caps["capabilities"]["date_trends"] is False
    assert caps["capabilities"]["sales_totals"] is True


def test_merge_user_mapping_resolves_amount():
    sug = cmap.suggest_mappings(["TxnID", "Product", "Qty", "Amount"])
    merged = cmap.merge_user_mapping(
        sug,
        {
            "invoice": "TxnID",
            "description": "Product",
            "quantity": "Qty",
            "unit_price": "Amount",
        },
    )
    assert merged["unit_price"] == "Amount"
    assert cmap.assess_capabilities(merged)["analysis_ready_minimum"]
