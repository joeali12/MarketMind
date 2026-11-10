#!/usr/bin/env python3
"""Generate EDA figures and evidence-backed insight notes from cleaned data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from marketmind.config import FIGURES_DIR, PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402
from marketmind.data.cleaning import eligible_positive_spend_mask  # noqa: E402

sns.set_theme(style="whitegrid", context="notebook")


def main() -> int:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DATA_DIR / "transactions_cleaned.parquet"
    tx = pd.read_parquet(path)
    eligible = tx[eligible_positive_spend_mask(tx)]

    # Univariate: monthly transactions
    monthly = (
        eligible.assign(month=eligible["invoice_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month")
        .size()
        .rename("n_lines")
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(monthly["month"], monthly["n_lines"])
    ax.set_title("Eligible line items per month")
    ax.set_xlabel("Month")
    ax.set_ylabel("Line count")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "eda_monthly_volume.png", dpi=120)
    plt.close(fig)

    # Univariate: line amount distribution (log)
    fig, ax = plt.subplots(figsize=(8, 4))
    sns.histplot(eligible["line_amount"].clip(lower=0), bins=50, log_scale=(False, True), ax=ax)
    ax.set_title("Eligible line_amount distribution (log y)")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "eda_line_amount_hist.png", dpi=120)
    plt.close(fig)

    # Bivariate: quantity vs unit_price sample
    sample = eligible.sample(n=min(5000, len(eligible)), random_state=42)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(sample["quantity"], sample["unit_price"], alpha=0.2, s=8)
    ax.set_xlabel("Quantity")
    ax.set_ylabel("Unit price")
    ax.set_title("Quantity vs unit price (sample of eligible lines)")
    ax.set_xlim(0, sample["quantity"].quantile(0.99))
    ax.set_ylim(0, sample["unit_price"].quantile(0.99))
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "eda_qty_price_scatter.png", dpi=120)
    plt.close(fig)

    # Multivariate: country spend share
    country_spend = (
        eligible.groupby("country")["line_amount"].sum().sort_values(ascending=False).head(10)
    )
    fig, ax = plt.subplots(figsize=(8, 4))
    country_spend.iloc[::-1].plot(kind="barh", ax=ax)
    ax.set_title("Top 10 countries by eligible spend")
    ax.set_xlabel("Sum of line_amount")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "eda_country_spend.png", dpi=120)
    plt.close(fig)

    # Cancellation rate over time
    monthly_all = tx.assign(month=tx["invoice_date"].dt.to_period("M").dt.to_timestamp())
    cancel_rate = monthly_all.groupby("month")["is_cancellation"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(cancel_rate["month"], cancel_rate["is_cancellation"] * 100)
    ax.set_title("Cancellation-row share by month (%)")
    ax.set_ylabel("% of rows with cancellation invoice")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "eda_cancel_rate.png", dpi=120)
    plt.close(fig)

    insights = {
        "n_cleaned_rows": int(len(tx)),
        "n_eligible_rows": int(len(eligible)),
        "n_customers": int(tx["customer_id"].nunique()),
        "date_min": str(tx["invoice_date"].min()),
        "date_max": str(tx["invoice_date"].max()),
        "uk_spend_share": float(
            eligible.loc[eligible["country"] == "United Kingdom", "line_amount"].sum()
            / eligible["line_amount"].sum()
        ),
        "cancellation_row_share": float(tx["is_cancellation"].mean()),
        "insights": [
            {
                "id": 1,
                "claim": "Eligible transaction volume varies substantially by month across 2009–2011.",
                "evidence": "figures/eda_monthly_volume.png",
                "type": "observation",
            },
            {
                "id": 2,
                "claim": "Line spend is heavily right-skewed; a small share of lines dominate monetary value.",
                "evidence": "figures/eda_line_amount_hist.png",
                "type": "observation",
            },
            {
                "id": 3,
                "claim": "United Kingdom accounts for the large majority of eligible spend in this dataset.",
                "evidence": "figures/eda_country_spend.png and uk_spend_share metric",
                "type": "observation",
            },
            {
                "id": 4,
                "claim": "Cancellation-marked rows are a persistent minority of activity and must be handled explicitly in spend targets.",
                "evidence": "figures/eda_cancel_rate.png and cancellation_row_share",
                "type": "observation",
            },
            {
                "id": 5,
                "claim": "Quantity and unit price show extreme outliers; RFM monetary sums will be sensitive to these tails.",
                "evidence": "figures/eda_qty_price_scatter.png and raw quality extremes",
                "type": "hypothesis_for_modeling",
            },
        ],
        "caveat": "Insights are descriptive associations from this historical dataset, not causal claims about marketing actions.",
    }
    (REPORTS_DIR / "eda_insights.json").write_text(json.dumps(insights, indent=2))
    print(json.dumps(insights, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
