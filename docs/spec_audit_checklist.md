# Spec audit checklist (verified against implementation)

Status codes: **PASS** (verified by code/run), **PARTIAL**, **BLOCKED** (external/user), **FAIL**.

## PDF / MVP outcomes

| Requirement | Status | Evidence |
|---|---|---|
| Data dictionary + validation feedback | PASS | `docs/data_dictionary.md`, Data validation page |
| Data quality + business summaries | PASS | `reports/raw_quality_summary.json`, Overview |
| RFM segments + profiles | PASS | train profiles CSV; Segments page; k=2 justified |
| Customer search: segment, RFM, 90d spend, action | PASS | Customer lookup; actions provisional |
| Model evaluation + limitations | PASS | Model quality page + model card |
| Notebook Restart & Run All | PASS | `nbconvert --execute` 0 errors (2026-11-06) |
| joblib artifacts for inference | PASS | artifacts/; app loads; no silent retrain |
| Public deploy | PARTIAL | D1/D8 approved 2026-11-11 for Streamlit Community Cloud; no live URL yet |
| README with results + credit | PASS | README table from metadata; live URL pending |
| Presentation 10–12 slides | PASS | `docs/presentation_outline.md` draft |
| LinkedIn/CV | PASS | drafts only; unpublished |

## ML lifecycle

| Item | Status | Notes |
|---|---|---|
| Cleaning + reconciliation | PASS | `reports/cleaning_reconciliation.csv` |
| EDA + 3–5 insights | PASS | figures + `eda_insights.json` + notebook |
| Leakage-safe 90d target | PASS | features ≤T; target (T,T+90]; tests |
| K-Means + hierarchical | PASS | artifacts + reports |
| PCA visualization | PASS | labeled viz-only |
| Baseline + ≥3 algorithms | PASS | mean, ridge, RF, GB |
| Train-only CV/tuning | PASS | TimeSeriesSplit; selection JSON |
| Untouched test MAE/RMSE/R² | PASS | metadata test_metrics |
| Error analysis | PASS | bands + residual PNG |
| k=2 vs k=3 sensitivity | PASS | kept k=2; `k_sensitivity.json` |

## App UX

| Item | Status | Notes |
|---|---|---|
| Demo mode | PASS | Home button → customer lookup |
| Upload validation | PASS | schema errors without crash |
| Dates/units/limitations | PASS | captions; GBP (£) confirmed (D6); eligible positive spend (D5) |
| Missing artifacts error | PASS | `ArtifactError` + home warning |
| Heuristics not as policy | PASS | `actions_approved=false` + warnings |

## Tests

| Item | Status | Notes |
|---|---|---|
| Schema/cleaning/RFM/target | PASS | pytest |
| Leakage / model / artifacts | PASS | `test_models_and_leakage.py` |
| Streamlit start smoke | PASS | HTTP 200 local |
| Screenshot materials | PASS | `docs/screenshots/*.png` captured from local app 2026-11-06 |
