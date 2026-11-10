"""Leakage-safe 90-day spend target construction."""

from __future__ import annotations

import pandas as pd

from marketmind.config import TARGET_WINDOW_DAYS
from marketmind.data.cleaning import eligible_positive_spend_mask
from marketmind.features.rfm import build_rfm


def assert_full_target_window(
    max_date_in_source: pd.Timestamp,
    cutoff: pd.Timestamp | str,
    window_days: int = TARGET_WINDOW_DAYS,
) -> None:
    """Raise if the source does not fully observe the target window after cutoff."""
    cutoff = pd.Timestamp(cutoff)
    needed = cutoff + pd.Timedelta(days=int(window_days))
    if pd.Timestamp(max_date_in_source) < needed:
        raise ValueError(
            f"Incomplete target window for cutoff {cutoff.date()}: "
            f"need data through {needed.date()}, source max is "
            f"{pd.Timestamp(max_date_in_source).date()}"
        )


def build_target_spend(
    transactions: pd.DataFrame,
    *,
    cutoff: pd.Timestamp | str,
    customer_ids: pd.Series | list | None = None,
    window_days: int = TARGET_WINDOW_DAYS,
) -> pd.DataFrame:
    """Sum eligible spend in (cutoff, cutoff + window_days] per customer.

    Customers with no future purchase receive target 0 (not dropped).
    Only eligible positive-spend rows count (D5: not net revenue after refunds).
    """
    cutoff = pd.Timestamp(cutoff)
    end = cutoff + pd.Timedelta(days=int(window_days))

    future = transactions[
        (transactions["invoice_date"] > cutoff)
        & (transactions["invoice_date"] <= end)
    ].copy()
    future = future[eligible_positive_spend_mask(future)]

    if customer_ids is None:
        # Default universe: customers with any transaction on/before cutoff
        customer_ids = transactions.loc[
            transactions["invoice_date"] <= cutoff, "customer_id"
        ].dropna().unique()

    base = pd.DataFrame({"customer_id": pd.Series(customer_ids).unique()})
    if future.empty:
        base["target_spend_90d"] = 0.0
    else:
        spend = (
            future.groupby("customer_id")["line_amount"]
            .sum()
            .rename("target_spend_90d")
            .reset_index()
        )
        base = base.merge(spend, on="customer_id", how="left")
        base["target_spend_90d"] = base["target_spend_90d"].fillna(0.0)

    base["cutoff"] = cutoff
    base["target_window_end"] = end
    return base.sort_values("customer_id").reset_index(drop=True)


def build_customer_modeling_table(
    transactions: pd.DataFrame,
    *,
    cutoff: pd.Timestamp | str,
    lookback_days: int | None = None,
    window_days: int = TARGET_WINDOW_DAYS,
    require_observation_purchase: bool = True,
) -> pd.DataFrame:
    """Join RFM features (pre-cutoff) with 90-day target (post-cutoff).

    Leakage controls:
    - Features use invoice_date <= cutoff only.
    - Target uses cutoff < invoice_date <= cutoff + window_days only.
    """
    cutoff = pd.Timestamp(cutoff)
    max_date = pd.Timestamp(transactions["invoice_date"].max())
    assert_full_target_window(max_date, cutoff, window_days=window_days)

    rfm = build_rfm(transactions, cutoff=cutoff, lookback_days=lookback_days)
    if require_observation_purchase:
        customers = rfm["customer_id"]
    else:
        customers = transactions.loc[
            transactions["invoice_date"] <= cutoff, "customer_id"
        ].dropna().unique()

    target = build_target_spend(
        transactions,
        cutoff=cutoff,
        customer_ids=customers,
        window_days=window_days,
    )
    table = rfm.merge(target, on=["customer_id", "cutoff"], how="inner")
    # Leakage assertions
    assert table["customer_id"].is_unique or not table.duplicated(
        ["customer_id", "cutoff"]
    ).any()
    return table
