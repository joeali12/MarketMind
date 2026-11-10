"""Customer-level RFM feature construction (observation window only)."""

from __future__ import annotations

import pandas as pd

from marketmind.data.cleaning import eligible_positive_spend_mask


def build_rfm(
    transactions: pd.DataFrame,
    *,
    cutoff: pd.Timestamp | str,
    lookback_days: int | None = None,
) -> pd.DataFrame:
    """Build one RFM row per customer using only data on/before cutoff.

    Definitions
    -----------
    - Recency: days between cutoff and most recent eligible purchase (lower = more recent).
    - Frequency: count of distinct eligible invoices in the observation window.
    - Monetary: sum of eligible line_amount in the observation window.

    Eligible rows use `eligible_positive_spend_mask` (D5: eligible positive spend).

    Parameters
    ----------
    lookback_days:
        If set, restrict observation to [cutoff - lookback_days, cutoff].
        If None, use all history on/before cutoff (documented as full-history lookback).
    """
    cutoff = pd.Timestamp(cutoff)
    required = {
        "customer_id",
        "invoice",
        "invoice_date",
        "line_amount",
        "is_cancellation",
        "quantity",
        "unit_price",
    }
    missing = required - set(transactions.columns)
    if missing:
        raise ValueError(f"build_rfm missing columns: {sorted(missing)}")

    obs = transactions[transactions["invoice_date"] <= cutoff].copy()
    if lookback_days is not None:
        start = cutoff - pd.Timedelta(days=int(lookback_days))
        obs = obs[obs["invoice_date"] >= start]

    eligible = obs[eligible_positive_spend_mask(obs)]
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "customer_id",
                "cutoff",
                "recency",
                "frequency",
                "monetary",
                "n_eligible_lines",
            ]
        )

    grouped = eligible.groupby("customer_id", as_index=False)
    last_purchase = grouped["invoice_date"].max().rename(
        columns={"invoice_date": "last_purchase_date"}
    )
    frequency = (
        eligible.groupby("customer_id")["invoice"].nunique().rename("frequency").reset_index()
    )
    monetary = (
        eligible.groupby("customer_id")["line_amount"].sum().rename("monetary").reset_index()
    )
    n_lines = (
        eligible.groupby("customer_id").size().rename("n_eligible_lines").reset_index()
    )

    rfm = last_purchase.merge(frequency, on="customer_id").merge(monetary, on="customer_id")
    rfm = rfm.merge(n_lines, on="customer_id")
    rfm["cutoff"] = cutoff
    rfm["recency"] = (cutoff - rfm["last_purchase_date"]).dt.days.astype(int)
    rfm = rfm.drop(columns=["last_purchase_date"])
    # Uniqueness assertion
    if rfm["customer_id"].duplicated().any():
        raise AssertionError("RFM table is not unique by customer_id")
    return rfm[
        ["customer_id", "cutoff", "recency", "frequency", "monetary", "n_eligible_lines"]
    ].sort_values("customer_id").reset_index(drop=True)
