"""Tests for schema validation and fixture loading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from marketmind.config import FIXTURES_DIR, SOURCE_COLUMN_MAP
from marketmind.data.cleaning import clean_transactions
from marketmind.data.schema import SchemaError, to_canonical, validate_source_columns

FIXTURE = FIXTURES_DIR / "synthetic_transactions.csv"


def test_validate_accepts_required_columns():
    cols = list(SOURCE_COLUMN_MAP.values())
    result = validate_source_columns(cols)
    assert result.ok
    assert result.missing_columns == ()


def test_validate_rejects_missing_columns():
    result = validate_source_columns(["Invoice", "StockCode"])
    assert not result.ok
    assert "Quantity" in result.missing_columns or "Price" in result.missing_columns


def test_fixture_loads_and_canonicalizes():
    assert FIXTURE.exists()
    raw = pd.read_csv(FIXTURE)
    result = validate_source_columns(raw.columns)
    assert result.ok, result.message
    canon = to_canonical(raw)
    assert set(SOURCE_COLUMN_MAP.keys()).issubset(canon.columns)
    assert len(canon) == len(raw)


def test_cleaning_reconciliation_and_types():
    raw = pd.read_csv(FIXTURE)
    canon = to_canonical(raw)
    cleaned = clean_transactions(canon, drop_exact_duplicates=True)
    assert cleaned.data["invoice_date"].notna().all()
    assert cleaned.data["customer_id"].notna().all()
    recon = cleaned.reconciliation_frame()
    assert "step" in recon.columns
    assert recon.iloc[0]["step"] == "start"
    # Exact duplicate row for customer 13748 should be removed
    removed = recon.set_index("step").loc["drop_exact_duplicates", "rows_removed"]
    assert int(removed) >= 1


def test_to_canonical_raises_on_bad_schema():
    bad = pd.DataFrame({"Invoice": [1], "x": [2]})
    with pytest.raises(SchemaError):
        to_canonical(bad)
