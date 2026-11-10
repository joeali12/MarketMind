# Open Decisions Register

Status values: `TBD`, `Proposed (pending approval)`, `Resolved`, `Blocked`.

| ID | Decision | Status | Resolution / notes | Needs user now? |
|---|---|---|---|---|
| D1 | Deployment host | **Resolved (preference only)** | Preferred future host: **Streamlit Community Cloud**. HF Spaces Docker remains a fallback template only. **No deployment executed.** | No — wait for explicit publish approval |
| D2 | User input path | **Resolved (MVP)** | Demo customer tables + schema upload validation + manual RFM form. | No |
| D3 | Full data vs sample | **Resolved (evidence)** | Full workbook used (1,067,371 rows). No sampling. | No |
| D4 | Lookback / cutoffs | **Resolved (evidence)** | Full-history lookback; train 2010-12-11; test 2011-09-10. | No |
| D5 | Returns/cancellations in target | **Resolved (user)** | Eligible spend excludes cancellation invoices starting with `C` and non-positive quantities. Target is **eligible positive spend**, not net revenue after refunds. Cancellations remain tagged in the cleaned store for EDA. | No |
| D6 | Currency label | **Resolved (user)** | Display **GBP (£)** per UCI dataset description. No currency conversion. `currency_confirmed=true`. | No |
| D7 | Segment action mapping | **Resolved (user constraint)** | Keep marketing actions as **provisional heuristics** only. `actions_approved` stays **false**. Do not present as approved business policy. | No |
| D8 | Publish publicly / LinkedIn | **Resolved (not approved)** | Do **not** deploy or publish externally. Drafts stay local/unpublished until a future explicit approval. | No — blocked on future approval |

## Segmentation k (reviewed)

**Kept k=2.** Train silhouette 0.425 vs k=3 at 0.329; profiles: *Recent high-spend* / *Lapsed low-spend*. k=3 is sensitivity only (`reports/k_sensitivity.json`).

## Remaining external blockers (not local TBD)

- Public Streamlit Community Cloud deploy (preferred host chosen; publish not approved).
- LinkedIn / CV posting and live README URL (assets drafted; publication not approved).
