"""Data quality summaries computed from loaded frames."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _is_cancellation_invoice(invoice: pd.Series) -> pd.Series:
    from marketmind.data.cleaning import is_cancellation_invoice

    return is_cancellation_invoice(invoice)


def summarize_transactions(df: pd.DataFrame) -> dict[str, Any]:
    """Compute quality summary for a canonical transaction frame.

    Expects canonical columns: invoice, stock_code, description, quantity,
    invoice_date, unit_price, customer_id, country.
    """
    required = [
        "invoice",
        "stock_code",
        "description",
        "quantity",
        "invoice_date",
        "unit_price",
        "customer_id",
        "country",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"summarize_transactions missing columns: {missing}")

    dates = pd.to_datetime(df["invoice_date"], errors="coerce")
    cancel_mask = _is_cancellation_invoice(df["invoice"])
    neg_qty = df["quantity"] < 0
    zero_qty = df["quantity"] == 0
    neg_price = df["unit_price"] < 0
    zero_price = df["unit_price"] == 0
    missing_cid = df["customer_id"].isna()

    # Exact duplicate rows across all business columns
    biz = [
        "invoice",
        "stock_code",
        "description",
        "quantity",
        "invoice_date",
        "unit_price",
        "customer_id",
        "country",
    ]
    n_dup_rows = int(df.duplicated(subset=biz, keep="first").sum())

    summary: dict[str, Any] = {
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "date_min": None if dates.isna().all() else str(dates.min()),
        "date_max": None if dates.isna().all() else str(dates.max()),
        "n_unparseable_dates": int(dates.isna().sum()),
        "n_distinct_invoices": int(df["invoice"].nunique(dropna=True)),
        "n_distinct_customers_non_null": int(df["customer_id"].nunique(dropna=True)),
        "n_missing_customer_id": int(missing_cid.sum()),
        "pct_missing_customer_id": float(missing_cid.mean() * 100.0),
        "n_cancellation_invoices_rows": int(cancel_mask.sum()),
        "n_negative_quantity_rows": int(neg_qty.sum()),
        "n_zero_quantity_rows": int(zero_qty.sum()),
        "n_negative_unit_price_rows": int(neg_price.sum()),
        "n_zero_unit_price_rows": int(zero_price.sum()),
        "n_exact_duplicate_rows": n_dup_rows,
        "quantity_min": float(np.nanmin(df["quantity"].to_numpy(dtype=float))),
        "quantity_max": float(np.nanmax(df["quantity"].to_numpy(dtype=float))),
        "unit_price_min": float(np.nanmin(df["unit_price"].to_numpy(dtype=float))),
        "unit_price_max": float(np.nanmax(df["unit_price"].to_numpy(dtype=float))),
        "n_countries": int(df["country"].nunique(dropna=True)),
        "top_countries": (
            df["country"].value_counts(dropna=False).head(10).to_dict()
        ),
    }
    return summary


def quality_summary_to_frame(summary: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for k, v in summary.items():
        if isinstance(v, dict):
            v = str(v)
        rows.append({"metric": k, "value": v})
    return pd.DataFrame(rows)
