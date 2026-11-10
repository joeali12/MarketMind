"""Evidence-based gap fill — never invents customer IDs or dates."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api.services import gap_fill


def _frame():
    return pd.DataFrame(
        {
            "invoice": ["A1", "A2", "A3"],
            "stock_code": ["S1", "S1", "S1"],
            "description": ["Tea", "Tea", pd.NA],
            "quantity": [2.0, 4.0, pd.NA],
            "unit_price": [10.0, 14.0, pd.NA],
            "customer_id": [1.0, 2.0, pd.NA],
            "invoice_date": pd.to_datetime(["2024-01-01", "2024-01-02", pd.NaT]),
            "country": ["EG", "EG", "EG"],
            "is_cancellation": [False, False, False],
            "line_amount": [20.0, 56.0, pd.NA],
        }
    )


def test_suggestions_use_stock_median_not_ids_or_dates():
    sug = gap_fill.suggest_for_parsed(_frame())
    assert sug["rows"]
    row = next(r for r in sug["rows"] if r["row_index"] == 2)
    assert row["suggestions"]["unit_price"]["allowed"] is True
    assert row["suggestions"]["unit_price"]["suggested"] == 12.0
    # Quantity stays manual — never invent transaction qty from a median pattern
    assert row["suggestions"]["quantity"]["allowed"] is False
    assert row["suggestions"]["customer_id"]["allowed"] is False
    assert row["suggestions"]["customer_id"]["suggested"] is None
    assert row["suggestions"]["invoice_date"]["allowed"] is False


def test_apply_blocks_smart_customer_id():
    raw = pd.DataFrame(
        {
            "Invoice": ["A1", "A2"],
            "StockCode": ["S1", "S1"],
            "Description": ["Tea", "Tea"],
            "Quantity": [1, 1],
            "InvoiceDate": ["2024-01-01", "2024-01-02"],
            "Price": [10.0, None],
            "Customer ID": [1.0, None],
            "Country": ["EG", "EG"],
        }
    )
    updated, applied = gap_fill.apply_patches_to_source(
        raw,
        [
            {
                "row_index": 1,
                "field": "unit_price",
                "value": 10.0,
                "source": "smart",
            },
            {
                "row_index": 1,
                "field": "customer_id",
                "value": 99.0,
                "source": "smart",  # must be blocked
            },
            {
                "row_index": 1,
                "field": "customer_id",
                "value": 7.0,
                "source": "manual",  # allowed
            },
        ],
    )
    fields = {(a["field"], a["source"]) for a in applied}
    assert ("unit_price", "smart") in fields
    assert ("customer_id", "manual") in fields
    assert ("customer_id", "smart") not in fields
    assert float(updated.loc[1, "Customer ID"]) == 7.0
    assert float(updated.loc[1, "Price"]) == 10.0
