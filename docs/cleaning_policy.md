# Cleaning and eligible-spend policy

Status: **Resolved (D5, user 2026-11-06)**. Documented from UCI Online Retail II semantics and observed data.

## Rules applied in `clean_transactions`

| Step | Rule | Rationale |
|---|---|---|
| parse_types | Coerce types; flag `is_cancellation` if Invoice upper starts with `C`; `line_amount = quantity * unit_price` | UCI card: codes starting with `c` are cancellations |
| drop_unparseable_dates | Remove rows with unparseable InvoiceDate | Customer-level time features require valid dates |
| drop_non_finite_qty_price | Remove NaN quantity/price after coerce | Invalid numeric lines |
| drop_exact_duplicates | Drop exact duplicates on business columns | Observed 34,335 exact duplicates in source |
| drop_missing_customer_id | Remove rows without Customer ID | Customer-level RFM/modeling requires an ID |

Cancellations are **kept** in the cleaned store (tagged) so EDA can quantify them.

## Eligible positive spend (`eligible_positive_spend_mask`) — D5 resolved

Rows counted toward RFM monetary/frequency and the 90-day **target**:

- not a cancellation invoice (Invoice code beginning with `C` / `c`)
- `quantity > 0`
- `unit_price >= 0`

**Important:** The modeling target is **eligible positive spend**, not net revenue after refunds/returns. Negative-quantity return lines and cancellation invoices are excluded from the target sum rather than netted against positive purchases.

Customers with no eligible future purchase receive target **0** (not dropped).

## Currency — D6 resolved

UCI dataset description states unit price in sterling (£). Display label: **GBP (£)**. No FX conversion.
