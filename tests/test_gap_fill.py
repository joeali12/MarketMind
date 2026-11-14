"""Evidence-based gap fill — never invents customer IDs, dates, or quantities."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api.services import gap_fill


def test_price_policy_constants_documented():
    assert gap_fill.MIN_PRICE_PEERS == 3
    assert gap_fill.PRICE_STABILITY_MAX_CV == 0.25


def test_conflicting_prices_not_suggested():
    """Two divergent peer prices (CV > 0.25) must not auto-fill unit_price."""
    df = pd.DataFrame(
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
    sug = gap_fill.suggest_for_parsed(df)
    row = next(r for r in sug["rows"] if r["row_index"] == 2)
    # Only 2 peers — insufficient even before CV
    assert row["suggestions"]["unit_price"]["allowed"] is False
    assert row["suggestions"]["quantity"]["allowed"] is False
    assert row["suggestions"]["customer_id"]["allowed"] is False
    assert row["suggestions"]["invoice_date"]["allowed"] is False
    assert row["suggestions"]["customer_id"]["suggested"] is None


def test_stable_peer_prices_allow_unit_price():
    df = pd.DataFrame(
        {
            "invoice": ["A1", "A2", "A3", "A4"],
            "stock_code": ["S1", "S1", "S1", "S1"],
            "description": ["Tea", "Tea", "Tea", pd.NA],
            "quantity": [1.0, 1.0, 1.0, pd.NA],
            "unit_price": [10.0, 10.0, 10.0, pd.NA],
            "customer_id": [1.0, 2.0, 3.0, pd.NA],
            "invoice_date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", pd.NaT]
            ),
            "country": ["EG"] * 4,
            "is_cancellation": [False] * 4,
            "line_amount": [10.0, 10.0, 10.0, pd.NA],
        }
    )
    sug = gap_fill.suggest_for_parsed(df)
    row = next(r for r in sug["rows"] if r["row_index"] == 3)
    assert row["suggestions"]["unit_price"]["allowed"] is True
    assert row["suggestions"]["unit_price"]["suggested"] == 10.0
    assert row["suggestions"]["description"]["allowed"] is True
    assert row["suggestions"]["description"]["suggested"] == "Tea"
    assert row["suggestions"]["quantity"]["allowed"] is False
    assert row["suggestions"]["customer_id"]["allowed"] is False
    assert row["suggestions"]["invoice_date"]["allowed"] is False


def test_unstable_prices_with_enough_peers_rejected():
    df = pd.DataFrame(
        {
            "invoice": [f"A{i}" for i in range(4)],
            "stock_code": ["S1"] * 4,
            "description": ["Tea"] * 3 + [pd.NA],
            "quantity": [1.0, 1.0, 1.0, pd.NA],
            "unit_price": [5.0, 10.0, 20.0, pd.NA],
            "customer_id": [1.0, 2.0, 3.0, pd.NA],
            "invoice_date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", pd.NaT]
            ),
            "country": ["EG"] * 4,
            "is_cancellation": [False] * 4,
            "line_amount": [5.0, 10.0, 20.0, pd.NA],
        }
    )
    sug = gap_fill.suggest_for_parsed(df)
    row = next(r for r in sug["rows"] if r["row_index"] == 3)
    assert row["suggestions"]["unit_price"]["allowed"] is False
    assert (row["suggestions"]["unit_price"]["evidence"] or {}).get("rejected") == (
        "unstable_prices"
    )


def test_conflicting_descriptions_rejected():
    df = pd.DataFrame(
        {
            "invoice": ["A1", "A2", "A3"],
            "stock_code": ["S1", "S1", "S1"],
            "description": ["Tea", "Coffee", pd.NA],
            "quantity": [1.0, 1.0, 1.0],
            "unit_price": [10.0, 10.0, 10.0],
            "customer_id": [1.0, 2.0, 3.0],
            "invoice_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "country": ["EG"] * 3,
            "is_cancellation": [False] * 3,
            "line_amount": [10.0, 10.0, 10.0],
        }
    )
    sug = gap_fill.suggest_for_parsed(df)
    row = next(r for r in sug["rows"] if r["row_index"] == 2)
    assert row["suggestions"]["description"]["allowed"] is False


def test_apply_blocks_smart_customer_id_and_quantity():
    raw = pd.DataFrame(
        {
            "Invoice": ["A1", "A2"],
            "StockCode": ["S1", "S1"],
            "Description": ["Tea", "Tea"],
            "Quantity": [1, None],
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
                "source": "smart",
            },
            {
                "row_index": 1,
                "field": "quantity",
                "value": 5.0,
                "source": "smart",
            },
            {
                "row_index": 1,
                "field": "customer_id",
                "value": 7.0,
                "source": "manual",
            },
        ],
    )
    fields = {(a["field"], a["source"]) for a in applied}
    assert ("unit_price", "smart") in fields
    assert ("customer_id", "manual") in fields
    assert ("customer_id", "smart") not in fields
    assert ("quantity", "smart") not in fields
    assert float(updated.loc[1, "Customer ID"]) == 7.0
    assert float(updated.loc[1, "Price"]) == 10.0
    assert pd.isna(updated.loc[1, "Quantity"])
