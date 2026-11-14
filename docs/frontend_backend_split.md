# Frontend / backend split

Primary product UI is **Next.js** (`web/`) talking to **FastAPI** (`api/`).  
Streamlit (`app.py`) remains for regression only.

## Run locally (no deploy)

```bash
# API — from repo root
source .venv/bin/activate
PYTHONPATH=src:. uvicorn api.main:app --reload --port 8000

# Web — separate terminal
cd web && npm run dev
```

Open http://127.0.0.1:3000 (rewrites `/api/*` to the API). If 3000 is busy, use `npm run dev -- -p 3001`.

## Key API routes

| Route | Role |
|-------|------|
| `GET /api/meta` | Demo provenance, GBP, upload policy |
| `GET /api/overview` | Demo store KPIs + bilingual insights |
| `GET /api/products` | Demo products; `category_available: false` |
| `POST /api/upload` | Stream to tmp; byte limit while reading |
| `POST /api/upload/settings` | Explicit `currency_code`, confirmed `date_format`, optional `selected_sheet`, `analysis_currency_filter` |
| `POST /api/upload/mapping` | Persist user-confirmed source→canonical column map for the session |
| `GET /api/upload/{session_id}/profile` | Factual file summary, findings, column mapping confidence |
| `POST /api/upload/assistant` | Grounded Q&A / Gemini tool-calling on the upload (no raw rows externally) |
| `GET /api/upload/assistant/status` | `gemini` when `GEMINI_API_KEY` is set; otherwise grounded-facts fallback |
| `POST /api/upload/validate` / `cleaning-proposals` / `apply` | Deterministic cleaning on the mapped sheet; optional category map; anomaly *review flags* |
| `GET /api/upload/{session_id}/overview\|segments\|customers\|products` | Upload-only analysis (never demo tables) |

### Upload journey (UI)

`/upload`: choose CSV/XLSX → pick Excel sheet when needed → confirm mapping for unknown/ambiguous headers → confirm currency (and date format only if ambiguous) → review cleaning/gaps → open `/store` for that session. Multi-currency files require an explicit analysis currency (no FX). Rows with a blank or unknown currency are left out of that total; the UI states how many were excluded and why. Ambiguous dates are not used for trends until the user confirms the format.

Cancellation rule (upload + cleaning): conservative `C####` or `C-…` (e.g. `C-RET-`). **Not** every invoice starting with letter `C` (so `CAI-…` stays a normal sale).

UI source selector: **Demo data** vs **My uploaded file**. Analysis pages must not mix sources.

## Preserve

- `src/marketmind/**`, `artifacts/*`, processed demo parquet, decision flags D5–D8
- Inference only via `predict_customer`; no retrain in the API

## Data boundaries

1. **Demo** = UCI Online Retail II, UK historical retail, **GBP only**. Never framed as a Cairo/Egyptian store. No FX conversion in this MVP.
2. **Category charts** only when an upload maps a category column. Demo has no category field — chart omitted with explanation.
3. **90-day models**
   - **Demo** uses the bundled UK-trained artifacts (`forecast_scope: "demo_only"`).
   - **Uploads** never use the UK model. Targets are eligible spend in `(cutoff, cutoff + 90 days]`. Training snapshots whose `target_window_end` exceeds the final holdout cutoff are **purged** before fitting. Holdout metrics use the purged train set only; a separate serving refit runs only after the candidate beats the baseline on the untouched holdout. Eligibility thresholds are in `api/settings.py` (`UPLOAD_FORECAST_*`) and are never lowered silently.
4. **Cleaning** = deterministic suggestions from `marketmind.data.cleaning`. Never invent IDs, names, dates, or amounts. Unresolved rows stay visible.
5. **Upload privacy** (must ship before privacy claims):

| Control | Spec |
|--------|------|
| Types | `.csv`, `.xlsx` |
| Max size | 25 MB |
| Preview rows | 100,000 |
| Temp path | `data/uploads/tmp/<session_id>/` (gitignored) |
| Retention | Discard, post-export delete, 2h TTL, startup cleanup |
| Logging | No file contents / PII — only hashes, sizes, extensions, outcome codes, row counts |
| Multi-tenant / encryption claims | Not claimed |

## UX

- No permanent sidebar; sticky top navigation
- Arabic RTL (EYENAmmon headings) / English LTR (system sans)
- Home focused; Store, Groups, Profile, Products, Upload, Project details
