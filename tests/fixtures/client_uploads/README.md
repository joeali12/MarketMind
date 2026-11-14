# Client upload fixtures (POS compatibility matrix)

Synthetic fixtures are **labeled synthetic** and are for schema/compatibility tests only.
They are **not** academic model-quality evidence.

The Egypt CSV/XLSX files are a **real retail sample** (committed fixtures, not symlinks) used for product upload isolation journeys. They are **not** part of the UCI academic training evidence.

See `matrix_manifest.json` for per-fixture currency, date format, mapping, and expected sales.

| File | Headers / layout | Money source | Expected sales | Auto-map? | Capabilities |
|------|------------------|--------------|----------------|-----------|--------------|
| `MarketMind_Egypt_Retail_Test.csv` / `.xlsx` | UCI-like EN + Category | qty × price | from file | high-confidence UCI | sales, products, customers, category |
| `synth_pos_en_qty_price.csv` | `order_id,order_date,item,sku,qty,unit_price,customer_id` | qty × price | **69** | yes (EN POS aliases) | sales, products, customers |
| `synth_supermarket_line_total.csv` | `InvoiceNo,SaleDate,ProductName,Qty,LineTotal,CustomerID` | **line_amount** (not Qty×LineTotal) | **81** | yes | sales, products, customers |
| `synth_arabic_headers.csv` | رقم الفاتورة، تاريخ البيع، اسم المنتج، … | qty × price | ≥0 | yes (AR aliases) | sales, products |
| `synth_no_customer_id.csv` | `order_date,item,qty,unit_price` | qty × price | **41** | yes | sales, products; **no** customer groups / order KPIs |
| `synth_uci_no_category.csv` | UCI without Category | qty × price | ≥0 | yes | sales; category analysis off |
| `synth_ambiguous_amount.csv` | `TxnID,TxnDate,Product,Qty,Amount` | qty × price **after** mapping Amount→unit_price | **67.5** | **no** — Amount stays ambiguous | needs user mapping |
| `synth_iso_dates.csv` | POS EN + ISO dates | qty × price | ≥0 | yes | ISO auto; no forced dayfirst |
| `synth_semicolon_bom.csv` | UTF-8 BOM + `;` delimiter | qty × price | ≥0 | yes | encoding/delimiter detect |
| `synth_multisheet_sales.xlsx` | sheets `Summary` / **`SalesLines`** | qty × price | **170** | after sheet pick | must select SalesLines |

## Rules verified by tests

- Ambiguous `Amount` / `Total` never auto-maps to `unit_price`.
- Line totals are not multiplied by quantity again.
- Missing optional fields disable only dependent metrics.
- Currencies are never mixed or FX-converted. A chosen analysis currency includes only rows whose currency column matches that code. Blank, empty, or unknown currency values are excluded and the count plus reason are shown. Other currencies in the same file are excluded too, not converted.
- Session mapping/sheet/currency/date drive cleaning + analytics + assistant.
