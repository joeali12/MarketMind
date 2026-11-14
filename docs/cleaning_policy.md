# Cleaning and eligible-spend policy

Status: **Resolved (D5, user 2026-11-06)**. Documented from UCI Online Retail II semantics and observed data.

## Rules applied in `clean_transactions`

| Step | Rule | Rationale |
|---|---|---|
| parse_types | Coerce types; flag `is_cancellation` with conservative pattern `C####` or `C-…` (not every code starting with letter `C`, so `CAI-…` stays a sale); academic UCI path uses `line_amount = quantity * unit_price` | Matches `is_cancellation_invoice` / `_CANCEL_RE` in code |
| drop_unparseable_dates | Remove rows with unparseable InvoiceDate | Customer-level time features require valid dates |
| drop_non_finite_qty_price | Remove NaN quantity/price after coerce | Invalid numeric lines |
| drop_exact_duplicates | Drop exact duplicates on business columns | Observed 34,335 exact duplicates in source |
| drop_missing_customer_id | Remove rows without Customer ID | Customer-level RFM/modeling requires an ID |

Cancellations are **kept** in the cleaned store (tagged) so EDA can quantify them.

## Eligible positive spend (`eligible_positive_spend_mask`) — D5 resolved

Rows counted toward RFM monetary/frequency and the 90-day **target**:

- not a cancellation invoice (conservative `C####` / `C-…` pattern — see `is_cancellation_invoice`)
- `quantity > 0` (when quantity is present)
- `unit_price >= 0` (when unit price is present; upload line-total files may use mapped `line_amount` instead)

## Product uploads (Next.js / FastAPI)

Upload sessions use the confirmed column mapping and session `date_format` / `currency_code`. Monetary totals use mapped `line_amount` **or** `quantity × unit_price` — never both multiplied together. Ambiguous `Amount`/`Total` is never auto-mapped to unit price. Missing customer ID / date / category disables only dependent metrics.

**Important:** The modeling target is **eligible positive spend**, not net revenue after refunds/returns. Negative-quantity return lines and cancellation invoices are excluded from the target sum rather than netted against positive purchases.

Customers with no eligible future purchase receive target **0** (not dropped).

## Currency — D6 resolved

UCI dataset description states unit price in sterling (£). Display label: **GBP (£)**. No FX conversion.
