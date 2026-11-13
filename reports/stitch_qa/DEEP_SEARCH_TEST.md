# Deep-search upload test (live site)

No skills matched for Kaggle/dataset download (`npx skills find`).

## Sources downloaded

| File | Source | Notes |
|---|---|---|
| `online_retail_databricks.csv` (43MB, 541,909 rows) | GitHub Databricks Spark Definitive Guide retail dump | Classic UCI Online Retail schema |
| `online_retail_amir.csv` (43MB) | GitHub amir-hojjati Online Retail | Same family |
| `online_retail_ibm_sample.csv` (265KB, 3,066 rows) | IBM customer_pos_analytics sample | Day-first dates |
| `OnlineRetail.xlsx` (23MB) | UCI ML archive classic Online Retail workbook | Full xlsx |

Prepared under `data/uploads/deep_search_samples/`:
- `ext_uci_online_retail_3k.csv` / `.xlsx`
- `ext_uci_online_retail_mid_5k.csv` (mid-season slice)
- `ext_pos_headers_price.csv` (Invoice / Price / Customer ID)
- `ext_line_total_schema.csv` (line_total without unit price)
- `ext_eu_semicolon.csv` (UTF-8 BOM + `;`)
- `online_retail_ibm_sample.csv`
- `OnlineRetail.xlsx`

## Live API results (`http://127.0.0.1:8000`)

**8 / 8 passed** (upload → settings → profile → cleaning proposals → overview → products)

| File | Sales | Orders | Customers | Time |
|---|---:|---:|---:|---:|
| IBM sample CSV | 58,736.61 | 134 | 94 | 1.0s |
| UCI 3k CSV | 57,329.56 | 131 | 91 | 0.9s |
| UCI mid 5k CSV | 100,699.49 | 231 | 173 | 1.0s |
| UCI 3k XLSX | 57,329.56 | 131 | 91 | 2.5s |
| POS renamed headers | 57,329.56 | 131 | 91 | 1.3s |
| line_total schema | 57,329.56 | 122 | 91 | 1.2s |
| EU semicolon | 20,788.32 | 54 | 39 | 0.6s |
| OnlineRetail.xlsx full | 1,956,643.58 | 3,658 | 1,597 | 23.8s |

Machine-readable: `reports/stitch_qa/deep_search_upload_results.json`

## Browser

Loaded mid-5k session on `/stitch/store_dashboard.html` and confirmed live panel KPIs.
