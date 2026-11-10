# MarketMind Implementation Log

Living record of phase progress. Numbers recorded only after computed by project code.

## Phase 0 — Repository and decisions audit

**Date:** 2026-11-06  
**Status:** Passed

### Found at audit start

- Only the specification markdown file present; no git repo, no code, no dataset, no venv.
- Compute: 24 CPUs, ~62 GiB RAM, ample disk.
- Tools: `uv`, `hf` (not logged in), Python 3.12.15.

### Schema confirmed from downloaded file

| Sheet | Rows |
|---|---:|
| Year 2009-2010 | 525,461 |
| Year 2010-2011 | 541,910 |
| Total | 1,067,371 |

Headers: `Invoice`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`, `Price`, `Customer ID`, `Country`.  
SHA-256: `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`  
Date span (raw): 2009-12-01 → 2011-12-09.

### Files created

`docs/implementation_log.md`, `docs/open_decisions_register.md`, `docs/data_dictionary.md`

### Commands

- `git init`
- Dataset download via classic UCI xlsx URL
- `uv venv` + package install

### Acceptance

- Existing state understood — **pass**
- Source file + schema confirmed — **pass**
- TBD register created — **pass**
- No user file overwritten — **pass**

---

## Phase 1 — Project skeleton and environment

**Status:** Passed

### Files

Repository layout under `src/marketmind/`, `tests/`, `scripts/`, `app.py`, `app_pages/`, `requirements.txt`, `pyproject.toml`, `.gitignore`, `.streamlit/config.toml`, synthetic fixture.

### Commands / outputs

- `uv pip install ...` → sklearn 1.9.1, pandas 3.1.1, streamlit 1.67.0
- Streamlit skill discovery path resolved after venv install

### Acceptance

- Fresh env documented — **pass**
- Imports work — **pass**
- No dataset/secrets committed — **pass** (raw xlsx gitignored)
- Config centralized — **pass**

---

## Phase 2 — Data acquisition, ingestion, understanding

**Status:** Passed

### Computed quality (`reports/raw_quality_summary.json`)

- n_rows: 1,067,371
- customers non-null: 5,942
- missing Customer ID: 243,007 (22.77%)
- cancellation rows: 19,494
- negative quantity: 22,950
- exact duplicates: 34,335
- countries: 43 (UK 981,330 rows)

### Acceptance

- Loads reproducibly — **pass**
- Data dictionary documented — **pass**
- Quality summary computed — **pass**

---

## Phase 3 — EDA and cleaning

**Status:** Passed (provisional D5 policy documented)

### Cleaning reconciliation

| Step | Removed | After |
|---|---:|---:|
| exact duplicates | 34,335 | 1,033,036 |
| missing customer id | 235,151 | 797,885 |

Cleaned customers: 5,942. EDA figures in `reports/figures/`; insights in `reports/eda_insights.json` (UK eligible spend share ≈ 82.8%; cancellation share ≈ 2.3%).

---

## Phase 4 — Time design, features, target

**Status:** Passed with documented D4 choice

- Lookback: full history on/before cutoff
- Train cutoff: 2010-12-11 (4,316 customers; zero-target 69.5%)
- Test cutoff: 2011-09-10 (5,283 customers; zero-target 56.7%)
- Leakage tests: **12 passed** including RFM/target tests

---

## Phase 5 — Segmentation

**Status:** Passed (k=2 is silhouette-optimal but thin for personas — flagged for user)

- K-Means k=2, silhouette 0.425
- Hierarchical ward silhouette ≈ 0.418 (n=4,316)
- PCA 2D explained variance ≈ 0.744 + 0.196 = 0.940
- Labels/actions provisional; `actions_approved=false`

---

## Phase 6 — Regression

**Status:** Passed

CV MAE: baseline 389.59 · ridge 438.15 · RF 399.72 · **GB 362.31 (selected)**  
**Test (once):** GB MAE **452.10**, RMSE **2650.95**, R² **0.347**  
Baseline test MAE 609.26, RMSE 3290.69, R² -0.006

---

## Phase 7 — Artifacts and inference

**Status:** Passed

Artifacts: `segmentation_pipeline.joblib`, `regression_pipeline.joblib`, `model_metadata.json`.  
Inference smoke: finite prediction; missing-artifact error path tested.

---

## Phase 8 — Streamlit app

**Status:** Passed locally (not publicly deployed)

Pages: Home, Data validation, Overview, Segments, Customer lookup, Model quality.  
Local smoke: HTTP 200 on `streamlit run app.py` (port 8509). No silent retrain.

---

## Phase 9 — Verification

**Status:** Passed locally (screenshot/GIF still pending)

- `pytest -q` → **12 passed**
- Notebook `notebooks/01_marketmind_analysis.ipynb` executed via `jupyter nbconvert --execute` with **0 cell errors** (output copy: `01_marketmind_analysis.executed.ipynb`, gitignored)
- App local smoke — **pass** (HTTP 200)
- Screenshot/GIF — **not captured** (needs user UI review / optional later)

---

## Phase 10 — Deployment and portfolio

**Status:** Prepared; publish blocked

- Dockerfile + `docs/deployment.md` ready
- Presentation outline + LinkedIn/CV drafts use verified metrics
- Live URL / public Space / LinkedIn publish require D1 + D8

---

## Continuation pass (2026-11-06 evening)

### Fixes verified
- Segment labels corrected from RFM profiles → `Recent high-spend` / `Lapsed low-spend` (was misleading “Loyal mid-value”)
- k=2 kept (silhouette 0.425 vs k=3 0.329); `reports/k_sensitivity.json` added
- Residual plots, demo-mode CTA, stronger units/heuristic caveats in app
- Expanded tests: **19 passed**
- Notebook re-executed: **0 errors**
- Screenshots: `docs/screenshots/{home,customer_lookup,segments,model_quality}.png`
- Docs: model card, cleaning policy, HF Space template, spec audit checklist

---

## Decision resolution pass (2026-11-06)

User resolutions applied to docs/config/metadata **without retrain**:

| ID | Resolution |
|---|---|
| D5 | Eligible positive spend: exclude `C…` cancellations and non-positive qty; **not** net revenue after refunds |
| D6 | GBP (£) confirmed; no FX; `currency_confirmed=true` |
| D7 | Actions remain provisional heuristics; `actions_approved=false` |
| D1/D8 | Prefer Streamlit Community Cloud later; **do not deploy/publish** |

Verified metrics in `artifacts/model_metadata.json` left unchanged (MAE 452.10 / RMSE 2650.95 / R² 0.347).
