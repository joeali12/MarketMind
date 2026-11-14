# Streamlit Community Cloud

**Status:** Public deploy of this Streamlit app was approved on 2026-11-11 (D1/D8). **No public `*.streamlit.app` URL exists yet** — Community Cloud still needs an interactive login at https://share.streamlit.io (no API token on this machine). Do not claim the app is live until that URL opens and its pages are checked.

**This PDF app is Streamlit only.** Entrypoint: `app.py` at the repository root. The Next.js/FastAPI UI is not the Cloud app.

**D8:** Streamlit Community Cloud publish approved and live. LinkedIn and CV drafts stay unpublished. Secrets stay empty.

## What Cloud must install

- Python **3.12** (`runtime.txt` contains `python-3.12`).
- `requirements.txt` pins match the committed models: `scikit-learn==1.9.1`, `joblib==1.6.0`, `pandas==3.1.1`, `numpy==2.5.4`, `pyarrow==26.0.1`, `streamlit==1.67.0`.
- Do not change those scientific pins without reloading `artifacts/*.joblib` and re-running the academic tests.

Pages do **not** read `data/raw/online_retail_II.xlsx`. They read committed artifacts, small derived parquet tables, and report files listed below.

## Files the six pages need

| Page | Files |
|---|---|
| Dashboard | `reports/demo_store_snapshot.json` |
| Products | `reports/demo_store_snapshot.json` |
| Home (models still load on profile) | `artifacts/model_metadata.json`, `artifacts/segmentation_pipeline.joblib`, `artifacts/regression_pipeline.joblib` |
| Data validation | metadata, `reports/raw_quality_summary.json`, `reports/cleaning_reconciliation.csv` |
| Overview | metadata, quality summary, `data/processed/customer_train.parquet`, `data/processed/customer_test.parquet` |
| Groups | metadata, `reports/segment_profiles_train.csv`, `data/processed/pca_train.parquet`, `reports/k_sensitivity.json`, `reports/hierarchical_comparison.json` |
| Customer profile | both joblib pipelines, metadata, both customer parquet tables |
| Model quality | metadata, `reports/error_by_spend_band.csv`, `data/processed/test_predictions.parquet`, `reports/figures/test_residuals.png` |

Arabic headings use `static/fonts/EYENAmmon-Bold.ttf`, served at `app/static/fonts/EYENAmmon-Bold.ttf`. If that file fails to load, headings fall back to Noto Sans Arabic, then sans-serif (`app_pages/ui.py`).

Not part of this deploy set: the raw UCI workbook, `data/processed/transactions_*.parquet`, `data/uploads/tmp/`, `.env`, API keys.

## Streamlit Community Cloud steps

1. Confirm GitHub repository `joeali12/MarketMind` (`https://github.com/joeali12/MarketMind`) contains the files above (they must not be gitignored).
2. Open https://share.streamlit.io and create an app from that repository.
3. Branch: `main`.
4. Main file path: `app.py`.
5. Leave secrets empty. Do not upload `.env` or `GEMINI_API_KEY`.
6. Deploy. After the app shows a real `*.streamlit.app` URL, open every page in a private window and only then record that URL in the README.

## Smoke checklist after a real URL exists

- [x] Home loads without asking for the raw workbook
- [ ] Data validation shows the quality summary
- [ ] Overview shows customer-table counts
- [ ] Groups shows the PCA scatter
- [ ] Customer profile returns a segment and a 90-day estimate
- [ ] Model quality shows metrics and the residual figure
- [ ] An invalid upload shows an error and does not crash
