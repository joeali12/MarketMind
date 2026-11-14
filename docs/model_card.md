# Model card — MarketMind (academic MVP)

## Model details

- **Task:** Estimate eligible customer spend in the 90 days after an observation cutoff; assign RFM K-Means segment.
- **Algorithms:** Mean baseline, Ridge, Random Forest, Gradient Boosting (sklearn pipelines). Selected: **gradient_boosting**.
- **Segmentation:** K-Means on log1p+scaled RFM; hierarchical agglomerative comparison at same k.
- **Artifacts:** `artifacts/segmentation_pipeline.joblib`, `artifacts/regression_pipeline.joblib`, `artifacts/model_metadata.json`
- **Framework versions (training):** see metadata (`sklearn_version`, `pandas_version`, `numpy_version`).

## Data

- UCI Online Retail II (Chen, 2012), DOI https://doi.org/10.24432/C5CG6D
- Source rows: 1,067,371 · cleaned: 797,885 · customers with ID: 5,942
- Train cutoff: 2010-12-11 · Test cutoff: 2011-09-10 · lookback: full history on/before cutoff

## Metrics (untouched test)

| Model | MAE | RMSE | R² |
|---|---:|---:|---:|
| mean_baseline | 609.26 | 3290.69 | -0.006 |
| gradient_boosting | 452.10 | 2650.95 | 0.347 |

Units: **eligible positive spend** over 90 days in **GBP (£)** (UCI dataset description; no FX).  
D5: excludes cancellation invoices starting with `C` and non-positive quantities — **not** net revenue after refunds.  
R² is not accuracy %.

## Intended use

Academic demonstration for SME retail prioritization education. Not a commercial CLV guarantee.

## Out of scope / limitations

- No auth, billing, multi-tenant storage, or campaign execution
- Historical 2009–2011 behavior may not transfer
- High zero-target rates; skewed spend
- Segment actions are **provisional heuristics only** (`actions_approved=false`; D7) — not approved policy
- Streamlit Community Cloud live: https://marketmind-grad.streamlit.app/ (D8); LinkedIn unpublished
- joblib artifacts are version-sensitive; load only project-trusted files

## Ethical notes

Demo processes public anonymized UCI data. Do not upload sensitive commercial customer files to the public demo.
