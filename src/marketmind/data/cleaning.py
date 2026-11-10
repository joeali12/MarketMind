"""Cleaning transforms with explicit row-count reconciliation.

Policy notes (D5 resolved — eligible positive spend, not net revenue):
- Cancellations use a conservative invoice pattern (see is_cancellation_invoice).
- Negative quantities are quantified; not assumed to be data errors alone.
- Missing customer IDs are excluded from customer-level modeling paths.
- Exact duplicate rows can be dropped with a recorded key.
- Line amount = quantity * unit_price; demo currency is GBP (£); no FX (D6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# UCI Online Retail: "C536391". Returns/cancellations like "C-RET-0001".
# Do NOT treat every invoice starting with letter C as a cancel (e.g. CAI-…).
_CANCEL_RE = re.compile(r"^(C-\w+|C\d)", re.IGNORECASE)


def is_cancellation_invoice(invoice: pd.Series | str) -> pd.Series | bool:
    """Conservative cancellation detection for UCI-style and C-RET-style codes."""
    if isinstance(invoice, str):
        return bool(_CANCEL_RE.match(str(invoice).strip()))
    s = invoice.astype(str).str.strip()
    return s.str.match(_CANCEL_RE.pattern, case=False, na=False)


@dataclass
class ReconciliationStep:
    step: str
    reason: str
    rows_before: int
    rows_after: int
    rows_removed: int


@dataclass
class CleaningResult:
    data: pd.DataFrame
    reconciliation: list[ReconciliationStep] = field(default_factory=list)

    def reconciliation_frame(self) -> pd.DataFrame:
        return pd.DataFrame([s.__dict__ for s in self.reconciliation])


def _step(
    steps: list[ReconciliationStep],
    name: str,
    reason: str,
    before: int,
    after: int,
) -> None:
    steps.append(
        ReconciliationStep(
            step=name,
            reason=reason,
            rows_before=before,
            rows_after=after,
            rows_removed=before - after,
        )
    )


def parse_types(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["invoice"] = out["invoice"].astype(str).str.strip()
    out["stock_code"] = out["stock_code"].astype(str).str.strip()
    out["description"] = out["description"].astype("string")
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce")
    out["unit_price"] = pd.to_numeric(out["unit_price"], errors="coerce")
    out["invoice_date"] = pd.to_datetime(out["invoice_date"], errors="coerce")
    out["customer_id"] = pd.to_numeric(out["customer_id"], errors="coerce")
    out["country"] = out["country"].astype("string")
    out["is_cancellation"] = is_cancellation_invoice(out["invoice"])
    out["line_amount"] = out["quantity"] * out["unit_price"]
    return out


def clean_transactions(
    df: pd.DataFrame,
    *,
    drop_missing_customer_id: bool = True,
    drop_exact_duplicates: bool = True,
    drop_unparseable_dates: bool = True,
    drop_non_finite_qty_price: bool = True,
    keep_cancellations: bool = True,
) -> CleaningResult:
    """Apply documented cleaning rules and record reconciliation.

    Parameters control reversible policy switches. Default keeps cancellation
    rows in the cleaned transaction store (tagged) so EDA can quantify them;
    RFM/target builders use eligible_positive_spend_mask (D5 resolved).
    """
    steps: list[ReconciliationStep] = []
    working = df.copy()
    _step(steps, "start", "Input frame", len(working), len(working))

    before = len(working)
    working = parse_types(working)
    _step(steps, "parse_types", "Coerce dtypes; add flags/line_amount", before, len(working))

    if drop_unparseable_dates:
        before = len(working)
        working = working[working["invoice_date"].notna()]
        _step(
            steps,
            "drop_unparseable_dates",
            "invoice_date could not be parsed",
            before,
            len(working),
        )

    if drop_non_finite_qty_price:
        before = len(working)
        mask = working["quantity"].notna() & working["unit_price"].notna()
        working = working[mask]
        _step(
            steps,
            "drop_non_finite_qty_price",
            "quantity or unit_price non-numeric/NaN after coerce",
            before,
            len(working),
        )

    if drop_exact_duplicates:
        before = len(working)
        subset = [
            "invoice",
            "stock_code",
            "description",
            "quantity",
            "invoice_date",
            "unit_price",
            "customer_id",
            "country",
        ]
        working = working.drop_duplicates(subset=subset, keep="first")
        _step(
            steps,
            "drop_exact_duplicates",
            f"Exact duplicates on {subset}",
            before,
            len(working),
        )

    if drop_missing_customer_id:
        before = len(working)
        working = working[working["customer_id"].notna()]
        _step(
            steps,
            "drop_missing_customer_id",
            "Customer-level modeling requires Customer ID",
            before,
            len(working),
        )

    if not keep_cancellations:
        before = len(working)
        working = working[~working["is_cancellation"]]
        _step(
            steps,
            "drop_cancellations",
            "Invoice matches cancellation pattern (C#### or C-…)",
            before,
            len(working),
        )

    working = working.reset_index(drop=True)
    return CleaningResult(data=working, reconciliation=steps)


def eligible_positive_spend_mask(df: pd.DataFrame) -> pd.Series:
    """Rows counted toward eligible positive spend (D5 resolved).

    Excludes cancellation invoices (conservative C#### / C-… pattern) and
    non-positive quantities. Unit price must be >= 0. This defines eligible
    positive spend, not net revenue after refunds.
    """
    return (
        (~df["is_cancellation"])
        & (df["quantity"] > 0)
        & (df["unit_price"] >= 0)
    )
