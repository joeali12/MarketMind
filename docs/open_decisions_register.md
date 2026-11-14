# Open decisions register

Status values: `TBD`, `Proposed (pending approval)`, `Resolved`, `Blocked`.

| ID | Decision | Status | Resolution / notes | Needs user now? |
|---|---|---|---|---|
| D1 | Deployment host | **Resolved (PDF)** | Academic PDF app host: **Streamlit Community Cloud** (`app.py`). Local product UI is Next.js + FastAPI and is not the Community Cloud entrypoint. Hugging Face Spaces Docker remains a fallback template. **No live URL yet.** | No |
| D2 | User input path | **Resolved (product)** | Next.js upload journey: file → optional sheet → column mapping → currency/date confirm → cleaning/gaps → upload dashboard. Demo uses UK tables. Manual RFM form remains available in Streamlit classic mode. | No |
| D3 | Full data vs sample | **Resolved (evidence)** | Full workbook used for training (1,067,371 rows). No sampling for model evidence. Runtime demo after clone may use committed sample + `demo_store_snapshot.json`. | No |
| D4 | Lookback / cutoffs | **Resolved (evidence)** | Full-history lookback; train 2010-12-11; test 2011-09-10. Mirrored in `artifacts/model_metadata.json` and `src/marketmind/config.py`. | No |
| D5 | Returns/cancellations in target | **Resolved (user)** | Eligible spend excludes cancellation invoices matching conservative `C####` / `C-…` (`is_cancellation_invoice`) and non-positive quantities. Target is **eligible positive spend**, not net revenue after refunds. Cancellations remain tagged in the cleaned store for EDA. | No |
| D6 | Currency label | **Resolved (user)** | Display **GBP (£)** per UCI dataset description. No currency conversion. `currency_confirmed=true`. | No |
| D7 | Segment action mapping | **Resolved (user constraint)** | Keep marketing actions as **provisional heuristics** only. `actions_approved` stays **false**. Do not present as approved business policy. | No |
| D8 | Publish publicly / LinkedIn | **Resolved (not live)** | Streamlit public publish is required by the course PDF but **not executed yet** — `public_publish_approved` stays **false** until a real `*.streamlit.app` URL is created and checked. LinkedIn / CV drafts stay unpublished. | No — create Cloud app when ready |

## Segmentation k (reviewed)

k=2 from training diagnostics; labels *Recent high-spend* / *Lapsed low-spend*.

## Remaining external blockers (not local TBD)

- Streamlit Community Cloud app not created yet (no live URL) — required for PDF “deployed web app” points.
- LinkedIn / CV posting and live README URL (assets drafted; publication not approved until URL exists).
