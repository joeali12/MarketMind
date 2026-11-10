# Data Dictionary — Online Retail II

**Source:** Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D  
**UCI page:** https://archive.ics.uci.edu/dataset/502/online+retail+ii  
**Local file:** `data/raw/online_retail_II.xlsx` (gitignored)  
**SHA-256:** `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`  
**License/usage:** Follow UCI Machine Learning Repository terms for the dataset.

## Workbook structure (confirmed from local file)

| Sheet | Rows | Columns |
|---|---:|---|
| Year 2009-2010 | 525,461 | 8 |
| Year 2010-2011 | 541,910 | 8 |
| **Total (both sheets)** | **1,067,371** | 8 |

## Source columns (exact headers)

| Source column | Internal name | Type (as loaded) | Description (UCI + project notes) |
|---|---|---|---|
| Invoice | `invoice` | object/str | Invoice number. Codes starting with `C` indicate cancellation (UCI). |
| StockCode | `stock_code` | object/str | Product code. |
| Description | `description` | object/str | Product name. |
| Quantity | `quantity` | int64 | Units per line. May be negative (returns/cancellations). |
| InvoiceDate | `invoice_date` | datetime64 | Transaction datetime. |
| Price | `unit_price` | float64 | Unit price. UCI card states sterling (£). Source header is `Price`, not `UnitPrice`. |
| Customer ID | `customer_id` | float64 (nullable) | Customer identifier. Missing for some rows. |
| Country | `country` | str | Customer country. |

## Derived fields (after cleaning)

| Field | Description |
|---|---|
| `is_cancellation` | True if `invoice` uppercased starts with `C`. |
| `line_amount` | `quantity * unit_price` in source units (no FX conversion). |
| `_source_sheet` | Sheet name the row was loaded from. |

## Notes

- UCI card names (`InvoiceNo`, `UnitPrice`, `CustomerID`) differ from the Excel headers above. MarketMind maps the **Excel** headers.
- Currency display: **GBP (£)** per UCI dataset description (`CURRENCY_CONFIRMED=true`); no FX conversion (D6).
- Modeling target uses **eligible positive spend** (D5): excludes cancellation invoices starting with `C` and non-positive quantities — not net revenue after refunds.
- Approximate card figure of ~1M transactions matches the confirmed total row count of **1,067,371** across both sheets.
