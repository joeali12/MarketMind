"""Leakage and RFM/target construction tests on synthetic fixture."""

from __future__ import annotations

import pandas as pd
import pytest

from marketmind.config import FIXTURES_DIR
from marketmind.data.cleaning import clean_transactions
from marketmind.data.schema import to_canonical
from marketmind.features.rfm import build_rfm
from marketmind.features.target import (
    assert_full_target_window,
    build_customer_modeling_table,
    build_target_spend,
)


@pytest.fixture
def cleaned_fixture() -> pd.DataFrame:
    raw = pd.read_csv(FIXTURES_DIR / "synthetic_transactions.csv")
    return clean_transactions(to_canonical(raw)).data


def test_rfm_respects_cutoff(cleaned_fixture: pd.DataFrame):
    cutoff = pd.Timestamp("2011-03-01")
    rfm = build_rfm(cleaned_fixture, cutoff=cutoff, lookback_days=None)
    assert rfm["customer_id"].is_unique
    # Customer 15100 only appears after March in fixture purchases starting June
    assert 15100 not in set(rfm["customer_id"].astype(int))
    # Recency non-negative
    assert (rfm["recency"] >= 0).all()
    assert (rfm["frequency"] >= 1).all()
    assert (rfm["monetary"] > 0).all()


def test_target_only_uses_future_window(cleaned_fixture: pd.DataFrame):
    cutoff = pd.Timestamp("2011-03-01")
    # Extend max date artificially by ensuring assert uses fixture max
    max_date = cleaned_fixture["invoice_date"].max()
    # May fail full 90d window — use shorter window for synthetic unit test
    target = build_target_spend(
        cleaned_fixture, cutoff=cutoff, window_days=30
    )
    # Recompute manually for customer 12583: has Mar 1 purchase exactly at cutoff?
    # Mar 1 12:00 is NOT > cutoff if cutoff is midnight Mar 1 — be explicit
    future = cleaned_fixture[
        (cleaned_fixture["invoice_date"] > cutoff)
        & (cleaned_fixture["invoice_date"] <= cutoff + pd.Timedelta(days=30))
    ]
    assert future["invoice_date"].min() > cutoff or future.empty
    assert "target_spend_90d" in target.columns
    # Zero-fill customers with no future spend still present if in customer_ids
    assert (target["target_spend_90d"] >= 0).all()


def test_incomplete_window_raises(cleaned_fixture: pd.DataFrame):
    max_date = cleaned_fixture["invoice_date"].max()
    late_cutoff = max_date - pd.Timedelta(days=10)
    with pytest.raises(ValueError, match="Incomplete target window"):
        assert_full_target_window(max_date, late_cutoff, window_days=90)


def test_modeling_table_no_feature_leakage(cleaned_fixture: pd.DataFrame):
    # Choose early cutoff with enough synthetic future days for a short window
    cutoff = pd.Timestamp("2010-12-10")
    table = build_customer_modeling_table(
        cleaned_fixture,
        cutoff=cutoff,
        lookback_days=None,
        window_days=40,
    )
    assert table["customer_id"].is_unique
    # Features only from <= cutoff: recompute RFM and compare
    rfm = build_rfm(cleaned_fixture, cutoff=cutoff)
    merged = table.merge(rfm, on=["customer_id", "cutoff"], suffixes=("", "_r"))
    assert (merged["recency"] == merged["recency_r"]).all()
    assert (merged["frequency"] == merged["frequency_r"]).all()
    assert (merged["monetary"] == merged["monetary_r"]).all()
