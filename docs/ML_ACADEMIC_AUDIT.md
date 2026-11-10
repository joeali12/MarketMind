# Academic ML pipeline audit (vs PDF / project specification)

Audit date: 2026-11-08. Sources: `MarketMind_Project_Specification_and_Implementation_Guide.md`, `artifacts/model_metadata.json`, `docs/model_card.md`, `docs/cleaning_policy.md`, training/inference code under `src/marketmind/` and `api/services/upload_forecast.py`.

**No new academic training run was executed in this Gemini integration pass.** Metrics below are from the recorded UK (UCI Online Retail II) artifacts already in the repository. The Egypt synthetic fixture is **not** used for academic model-quality claims.

## Checklist

| # | Requirement | Status | Evidence / notes |
|---|---|---|---|
| 1 | Genuine project dataset | **Met** | UCI Online Retail II (UK, GBP). Demo path uses cleaned parquet; synthetic Egypt fixture is upload/UI isolation only (`tests/test_egypt_fixture.py`). |
| 2 | Schema / cleaning | **Met** | `docs/cleaning_policy.md`, reconciliation reports; cancellations (`C` invoices), missing customer IDs, duplicates handled per policy. |
| 3 | Customer RFM + cutoff | **Met** | Full-history lookback on/before cutoff; recency/frequency/monetary defined in metadata `rfm_definitions`. Train cutoff `2010-12-11`, test `2011-09-10`. |
| 4 | 90-day spend target + time split | **Met** | Target window `(T, T+90]`; chronological holdout; incomplete futures excluded by cutoff choice. |
| 5 | Leakage prevention | **Met** (UK); **strengthened** (upload) | Sklearn pipelines fit on train only (`tests/test_models_and_leakage.py`). Upload forecast applies temporal purge so train target windows do not overlap holdout cutoff (`api/services/upload_forecast.py`). |
| 6 | Mean baseline + ≥3 algorithms + train CV | **Met** | mean_baseline, ridge, random_forest, gradient_boosting; CV MAE in metadata. |
| 7 | Untouched test MAE/RMSE/R² | **Met** | See metrics table below (from `artifacts/model_metadata.json`). |
| 8 | Error analysis / selection | **Met** | GB selected on training CV MAE; beats baseline on test (MAE 452 vs 609). |
| 9 | K-Means, hierarchical, PCA viz | **Met** | k=2 selected; hierarchical ward comparison; PCA for 2D viz only. |
| 10 | joblib save/load + missing artifacts | **Met** | `artifacts/regression_pipeline.joblib`, `segmentation_pipeline.joblib`; inference fails clearly if missing (`tests/test_inference.py`). |

## Recorded UK test metrics (not re-run this session)

| Model | MAE | RMSE | R² |
|---|---:|---:|---:|
| mean_baseline | 609.26 | 3290.69 | -0.006 |
| gradient_boosting (selected) | 452.10 | 2650.95 | 0.347 |

- Dataset: UCI Online Retail II, cleaned 797,885 rows, GBP.
- Train customers 4,316 · test 5,283 · target 90 days.
- Selection gate: GB CV MAE best among candidates; test evaluated once.

## Upload / Egypt fixture (not academic evidence)

After temporal purge of overlapping 90-day train targets, the Egypt synthetic store typically **fails** the beat-baseline gate. Forecast capability is then marked unavailable — correct behavior. Do not cite Egypt fixture metrics as academic performance.

## Gemini vs PDF models

Gemini 2.5 Flash is an explanation layer only. It does not train, evaluate, or replace Ridge/RF/GB/K-Means artifacts required by the PDF.
