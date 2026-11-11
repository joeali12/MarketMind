# Open Decisions Register

Status values: `TBD`, `Proposed (pending approval)`, `Resolved`, `Blocked`.

| ID | Decision | Status | Resolution / notes | Needs user now? |
|---|---|---|---|---|
| D1 | Deployment host | **Resolved (approved)** | PDF public app host: **Streamlit Community Cloud**. Repository `joeali12/MarketMind`, branch `main`, entrypoint `app.py`. Approved 2026-11-11. The local Next.js app is not this Cloud app. **No live URL yet.** | No |
| D2 | User input path | **Resolved (MVP)** | Demo customer tables + schema upload validation + manual RFM form. | No |
| D3 | Full data vs sample | **Resolved (evidence)** | Full workbook used (1,067,371 rows). No sampling. | No |
| D4 | Lookback / cutoffs | **Resolved (evidence)** | Full-history lookback; train 2010-12-11; test 2011-09-10. | No |
| D5 | Returns/cancellations in target | **Resolved (user)** | Eligible spend excludes cancellation invoices starting with `C` and non-positive quantities. Target is **eligible positive spend**, not net revenue after refunds. Cancellations remain tagged in the cleaned store for EDA. | No |
| D6 | Currency label | **Resolved (user)** | Display **GBP (£)** per UCI dataset description. No currency conversion. `currency_confirmed=true`. | No |
| D7 | Segment action mapping | **Resolved (user constraint)** | Keep marketing actions as **provisional heuristics** only. `actions_approved` stays **false**. Do not present as approved business policy. | No |
| D8 | Publish publicly / LinkedIn | **Resolved (Streamlit approved, not live)** | User approved public publish of the Streamlit Community Cloud app on 2026-11-11. LinkedIn and CV drafts stay unpublished. Do not write a URL until a real `*.streamlit.app` address is opened and its pages are checked. | No |

## Segmentation k (reviewed)

**Kept k=2.** Train silhouette 0.425 vs k=3 at 0.329; profiles: *Recent high-spend* / *Lapsed low-spend*. k=3 is sensitivity only (`reports/k_sensitivity.json`).

## Remaining external blockers (not local TBD)

- Streamlit Community Cloud app is approved and not created yet (no live URL).
- LinkedIn / CV posting and live README URL (assets drafted; publication not approved).
