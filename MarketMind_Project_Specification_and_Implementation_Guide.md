# MarketMind
## Project Specification and Implementation Guide

**Purpose:** This document is the implementation contract for an AI coding agent (Cursor) and the developer. Follow it in order. Do not invent project requirements, fabricate results, silently resolve TBD decisions, or claim functionality that has not been implemented and verified.

**Product:** Customer Lifetime Value and Segmentation Engine  
**Course context:** NextGen Institute, Machine Learning Final Project  
**Primary audience:** Small and medium-sized businesses (SMEs), especially online retailers  
**Developer context:** Individual student; intermediate Python/Pandas and introductory ML; VS Code/Jupyter Notebook  
**Dataset:** Online Retail II, UCI Machine Learning Repository  
**Application framework:** Streamlit (working choice carried forward from project planning)  
**Schedule:** No deadline is specified in this document.

---

## 1. Instructions to the implementation agent

1. Read this entire specification before creating or changing files.
2. First inspect the repository, available data, environment, and existing work. Preserve useful work and user data. Do not overwrite files or remove data without explicit approval.
3. Build the project in small, reviewable stages following the roadmap in Section 13. Keep the notebook and production code consistent; avoid duplicating business logic.
4. Keep requirements, recommendations, and TBD items distinct. PDF requirements are mandatory unless the instructor approves a change. Project decisions in this document are the agreed product direction. Recommendations are implementation guidance and may be adjusted with a written rationale. A TBD is unresolved: do not choose a value silently. Ask the user when it blocks implementation, or implement a clearly isolated configuration placeholder and mark dependent functionality incomplete.
5. Never invent dataset counts, segment profiles, model scores, charts, app links, screenshots, business impact, or CV/LinkedIn claims. Generate every reported number from executed project code and label the data split and metric.
6. Never train or evaluate on future information relative to a customer's prediction cutoff. Prevent target leakage and preprocessing leakage.
7. Do not claim that a sample represents the full dataset. Record the chosen sample and all filters.
8. Do not add SaaS features (accounts, billing, tenants, database, integrations) to the academic MVP. Keep boundaries that make later extension feasible.
9. Before declaring a stage complete, provide: files changed, commands to run, actual outputs or artifacts, acceptance criteria passed/failed, and remaining TBDs. Do not say “passed” without running the relevant check.
10. If code execution is unavailable, describe the step as unverified and give the user exact run instructions. Do not fabricate a successful run.

### 1.1 Source precedence

If sources disagree, use this order:

1. The user's explicit instructions in the active conversation.
2. The instructor's uploaded PDF for course requirements.
3. This specification for agreed MarketMind decisions and implementation choices.
4. Clearly labeled recommendations in this specification.
5. The implementation agent's default preferences (only where no higher source applies and the decision is not marked TBD).

The uploaded document is `ML_Final_Project_Ideas (1).pdf`. Its relevant card is Idea 02, “Customer Lifetime Value & Segmentation Engine,” on page 4; general requirements and deliverables are on pages 2–3. The PDF is an requirements source, not an instruction to this AI agent that overrides the user's request.

---

## 2. Requirement labels

Use these labels in planning, issue tracking, and documentation:

- **[PDF — REQUIRED]** Explicitly required by the NextGen PDF.
- **[PROJECT — DECIDED]** Established for MarketMind in the user conversation or this specification.
- **[RECOMMENDED]** A concrete engineering recommendation that supports the required outcome.
- **[TBD — USER/INSTRUCTOR]** Unresolved choice. Do not silently decide it.
- **[LATER — OUT OF MVP]** SaaS or stretch functionality deferred beyond the course MVP.

---

## 3. Product definition and scope

### 3.1 Problem and users

**[PDF — REQUIRED]** Online retailers often treat all customers alike. MarketMind analyzes transaction history to group customers by purchase behavior and estimate how much each customer may spend in the next three months. The business decision supported is how to prioritize rewards, re-engagement, and marketing budget.

**Primary user:** A non-technical owner, marketing manager, or analyst at a small/medium retailer who can provide transaction records and needs understandable customer-level insights.

### 3.2 MVP outcomes

The MVP must let a user:

1. Understand what file and columns are expected, with a clear data dictionary and validation feedback.
2. Analyze a prepared transaction dataset and see data quality and business-level summaries.
3. Explore customer segments built from RFM behavior and inspect segment profiles.
4. Search/select a customer and see its segment, RFM values, predicted spend over the next 90 days, and a carefully qualified suggested action.
5. Understand model evaluation, limitations, and how the result was produced.

### 3.3 In scope

- Data understanding, data quality checks, EDA, preprocessing, feature engineering.
- RFM customer aggregation and unsupervised segmentation.
- K-Means as the primary clustering method; hierarchical clustering comparison.
- PCA visualization of clusters (visualization only; do not claim PCA itself validates segment quality).
- Supervised regression for next-90-day spend using a time-based observation cutoff and future target window.
- Baseline plus at least three distinct course algorithms, cross-validation and training-only hyperparameter tuning.
- Final evaluation on an untouched test set, appropriate regression metrics, and error analysis.
- One clean Jupyter notebook that executes top-to-bottom, and a Streamlit app backed by saved trained pipeline/model artifacts.
- Public deployment on Streamlit Community Cloud or Hugging Face Spaces (course requirement); exact host is TBD unless selected later.
- Professional GitHub repository, README, results table, screenshot/GIF, source attribution, 10–12-slide presentation, LinkedIn post/demo material.

### 3.4 Explicitly out of MVP

**[LATER — OUT OF MVP]** Authentication, organizations/tenancy, database-backed customer accounts, subscription/payment processing, automated integrations, production-grade multi-tenant privacy controls, churn prediction, advanced generative AI recommendations, automated campaign execution, and guarantees of commercial-grade CLV accuracy. Keep these out unless the user or instructor changes scope.

---

## 4. Source requirements versus product choices

| Topic | Classification | Requirement / decision |
|---|---|---|
| Project idea | [PROJECT — DECIDED] + [PDF — REQUIRED] | Idea 02: Customer Lifetime Value & Segmentation Engine. |
| Business audience | [PROJECT — DECIDED] | SMEs generally, especially online retail/marketing teams. |
| Dataset | [PROJECT — DECIDED] + PDF card | Online Retail II from UCI (about 1M transactions; exact usable rows must be computed after loading/filtering). |
| Segmentation input | [PDF — REQUIRED] | RFM features. |
| Clustering | [PDF — REQUIRED] | Compare K-Means with hierarchical clustering. |
| Visualization | [PDF — REQUIRED] | PCA visualization. |
| Regression target | [PDF — REQUIRED] | Spend over the next 90 days, made using a time cutoff. |
| App flow | [PDF — REQUIRED] | Segment dashboard and customer search/details including segment, predicted 90-day spend, recommended action. |
| Framework | [PROJECT — DECIDED for planning] | Streamlit. Gradio remains an allowed PDF alternative if user later changes choice. |
| Model serialization | [PDF — REQUIRED] | Save the final preprocessing/model pipeline with joblib for app inference. |
| Deployment host | [TBD — USER] | Streamlit Community Cloud or Hugging Face Spaces. Do not publish until credentials/settings and user intent are available. |
| Dataset sampling | [TBD — USER/IMPLEMENTATION] | Dataset card says use a well-chosen sample for very large data. Measure hardware/runtime and select a reproducible, justified strategy; document it. Do not silently choose an arbitrary sample. |
| Cutoff dates and split windows | [TBD — DATA-DEPENDENT] | Derive valid windows from actual date coverage and data volume; record rationale and ensure all are chronological. |
| Segment count and names | [TBD — DATA-DEPENDENT] | Select segment count using training data diagnostics and interpretability; derive names only from observed profiles. |
| Recommended actions | [TBD — BUSINESS POLICY] | Draft as transparent heuristic mapping based on observed segment profiles; label as suggestions, not learned causal recommendations. Get user/instructor agreement before presenting as definitive policy. |

---

## 5. Dataset and data contract

### 5.1 Dataset source

**[PDF — REQUIRED for Idea 02]** Online Retail II, UCI Machine Learning Repository: https://archive.ics.uci.edu/dataset/502

The dataset card describes approximately one million retail transactions from 2009–2011. These are approximate source-card figures, not project results. The project must read the data dictionary and cite UCI in the notebook, README, app, and presentation.

### 5.2 Expected source fields

The commonly documented transaction fields include invoice number, stock code, description, quantity, invoice date, unit price, customer ID, and country. Confirm exact column names, types, and workbook sheets from the downloaded file; do not assume the file matches a remembered schema. Create an explicit mapping/configuration if source headers differ.

### 5.3 Ingestion requirements

- Support the source workbook format used by UCI and, if useful, an explicitly documented prepared CSV/parquet format.
- Keep raw input immutable. Store derived/cleaned data separately and never commit the large raw dataset to GitHub.
- Validate required columns, parse dates, numeric types, nulls, duplicate records, and file readability.
- Report actual source row count, date range, distinct customers, missing IDs, returns/cancellations indicators, and invalid values before filtering.
- Fail with actionable messages when required fields are missing or incompatible.
- Avoid silently dropping rows. Emit a row-count reconciliation table at each cleaning step with reason and count.

### 5.4 Cleaning policy

The source card explicitly calls out returns, cancellations, and missing IDs as challenges. It does not dictate every cleaning rule. Treat the following as a **[RECOMMENDED] policy requiring explicit documentation**:

- Preserve the raw data and record all transformation rules.
- Identify cancellations and returns from invoice identifiers/quantity patterns only after inspecting the actual dataset and source documentation. Do not infer all negative quantities are errors.
- Exclude cancellation/return transactions from positive-spend targets unless an explicitly approved business definition says otherwise. Separately quantify them and state the limitation.
- Customer-level modeling requires a valid customer identifier. Exclude or segregate rows with missing IDs for customer-level RFM/modeling, and report how much data this removes.
- Resolve duplicate rows only when the source semantics justify it; never blanket-deduplicate without recording the key and impact.
- Validate quantity and unit price. Flag impossible/invalid records and document any exclusion rule. Do not clip or winsorize without fitting thresholds on training data only and recording the rationale.
- Calculate line amount consistently as quantity × unit price after confirming currency/units in source metadata. Do not invent a currency conversion.
- Keep country for descriptive context only unless its use is supported, available at inference, and deliberately approved.

### 5.5 Privacy and data

The dataset is public and anonymized according to its source description. Do not add real customer data. Do not expose uploaded datasets in logs, public artifacts, or repository commits. The academic app should state that inputs are processed for demonstration and clarify the deployed app's actual storage behavior; do not promise non-retention unless verified.

---

## 6. ML lifecycle and methodology

### 6.1 Lifecycle overview

1. Frame the retail decision and define the prediction time.
2. Acquire and inspect the dataset; establish a data dictionary and reproducible snapshot.
3. Perform EDA and write 3–5 evidence-backed insights/hypotheses.
4. Define the time cutoff, eligible customers, feature window, and future target window.
5. Split chronologically before fitting any learned preprocessing or model.
6. Build preprocessing and model pipelines; fit on training data only.
7. Establish baselines, compare algorithms, cross-validate and tune on training data only.
8. Select models using predeclared business-relevant criteria; evaluate once on untouched test data.
9. Perform error analysis, interpret results, state limitations and business implications.
10. Save complete fitted pipeline(s), metadata, feature schema and evaluation report.
11. Load saved artifact in the Streamlit app and perform validated inference.
12. Deploy, smoke-check the public app, and create evidence-based presentation/README/LinkedIn materials.

### 6.2 Problem framing

**Segmentation:** Unsupervised grouping of customers based on purchase recency, frequency, and monetary value over a defined historical observation window. It does not directly predict a future outcome.

**Regression:** Estimate a customer's total eligible purchase spend during the 90 days immediately after an observation cutoff, using only information available on or before that cutoff.

Define a single customer prediction row per cutoff. A customer's transaction after cutoff must never affect that customer's input features for that cutoff. If repeated cutoffs are used, all split rules must prevent the same customer or overlapping future windows from leaking across train/test in a way that inflates performance; document the chosen scheme.

### 6.3 Temporal feature/target construction

For a cutoff date `T`:

- **Observation window:** transactions with invoice date on/before `T` and within the chosen lookback duration `[T - L, T]` (lookback `L` is TBD/data-dependent and must be explicitly documented).
- **Target window:** transactions in `(T, T + 90 days]`.
- **Target:** sum of eligible positive line spend per customer within the target window, with return/cancellation handling consistent with the approved cleaning policy.
- **Features:** calculated only from the observation window. At minimum provide R, F, M. Additional features are permitted only if they are available at prediction time, justified, reproducible, and added consistently to the saved inference pipeline.
- **Eligibility:** decide and document how to handle customers with zero eligible purchases in the observation window and customers absent in the target window. A customer with no future purchase normally has target spend 0; do not drop these customers simply because they did not return.
- **Censoring:** ensure every selected cutoff has a full 90-day future observation period in the source data. Exclude cutoffs that cannot be fully observed and explain the count.
- **Multiple cutoffs:** if using rolling cutoffs, choose dates based on data coverage and sample size. Record exact dates and ensure test predictions occur later than training labels. Avoid overlapping target windows across folds where that would invalidate the estimate.

Do not use a random row split for future-spend prediction. Recommended approach: use one or more historical cutoffs for training/validation and a later cutoff for final testing, with a customer-level table per cutoff. If the limited dataset requires another design, document the alternative and its limitations before coding it.

### 6.4 EDA

**[PDF — REQUIRED]** Univariate, bivariate, and multivariate EDA with clear charts, ending with 3–5 written insights or hypotheses.

Cover, as appropriate to actual fields:

- Transaction date coverage, row counts by time, countries, customers, invoices.
- Quantity, unit price, line value and customer spend distributions; skew and extreme values.
- Missingness, duplicates, cancellations/returns and their time/customer patterns.
- Customer-level RFM distributions and correlations.
- Segment plots and PCA projection after clustering.
- Regression target distribution and target by relevant feature/segment.

Every insight must point to an actual table/chart and distinguish observation from causal claim. Do not state that an association causes spend or proves a marketing action will work.

### 6.5 Preprocessing and leakage controls

**[PDF — REQUIRED]** Put preprocessing inside scikit-learn Pipeline/ColumnTransformer, split before fitting preprocessing, and avoid leakage.

- Fit imputation, scaling, encoding, feature selection, PCA-for-modeling (if any), and model steps on training folds only.
- RFM features are typically skewed. Evaluate a documented transformation (e.g., `log1p` for nonnegative features) and scaling inside the pipeline; check assumptions and support inference values. Do not transform negative values with `log1p` without handling them explicitly.
- Segmentation's scaler and clustering are fitted on the designated training/analysis dataset. Persist the fitted scaler and cluster model together as a pipeline/artifact for assigning new customers to the established clusters.
- PCA for the required visualization should be fitted on the same documented feature space; do not fit it on test data if used in evaluation. It may be a visualization transform separate from the inference model.
- Separate model-selection data from final test data. Never tune against the untouched test set.
- If using temporal CV, respect time ordering. Do not use ordinary shuffled K-fold for future prediction.

### 6.6 RFM definition and segmentation

Compute customer-level features from the approved observation window:

- **Recency (R):** days between cutoff `T` and the customer's most recent eligible purchase. Lower is more recent.
- **Frequency (F):** number of distinct eligible invoices/orders, not raw line-item rows, unless data inspection proves invoice semantics differ. State the definition.
- **Monetary (M):** sum of eligible line spend in the observation window, using the approved return policy.

Build a clear customer-level table and validate uniqueness by customer and cutoff. Inspect distributions and correlations. Compare:

- **K-Means** over transformed/scaled RFM.
- **Hierarchical clustering** over a justified sample if needed for memory/runtime; report its linkage/distance choices and limitation.
- Cluster-count diagnostics: elbow/inertia and silhouette score where computationally feasible; also assess cluster size, stability/interpretability, and business usefulness. Metrics alone do not determine the best number.
- **PCA visualization** to project RFM to two dimensions for display, annotate explained variance, and make clear that the projection can distort distances.

Do not assume a fixed number of clusters, segment labels, or segment proportions. Choose using observed results, explain the tradeoff, and keep final names in a mapping/config file with evidence from profiles. If no defensible segmentation emerges, report that honestly.

### 6.7 Regression models and evaluation

**[PDF — REQUIRED]** Compare a simple baseline and at least three different course algorithms; cross-validation and hyperparameter tuning on training data; final scores on untouched test data; error analysis.

Recommended candidate set, subject to feasibility and course coverage:

1. Mean prediction baseline (and optionally a business rule baseline such as last-window spend, clearly labeled).
2. Linear Regression or Ridge Regression.
3. Random Forest Regressor.
4. Gradient Boosting Regressor or HistGradientBoostingRegressor.

Do not claim any algorithm is best before running it. Use explicit pipelines and reproducible random seeds where applicable. Record parameter grids/search spaces, scoring, CV strategy, runtime, and selected parameters. For temporally constructed data use time-aware validation.

Report at least **MAE, RMSE, and R²** on the untouched test set as required metric examples in the PDF; include target units and split/cutoff. If targets are highly skewed, consider a transformed target only with a correctly inverse-transformed prediction and interpretable metrics in original spend units. Also inspect:

- Error distribution and residual plots.
- Performance by actual spend bands, segment, and prediction availability groups where sample sizes permit.
- Underprediction/overprediction and impacts on marketing prioritization.
- Baseline versus candidate model table.

Do not represent R² as a percentage of accuracy. Avoid MAPE when targets can be zero. Explain limitations due to old dataset period, sample strategy, changing customer behavior, returns, and limited external features.

### 6.8 Selection, reproducibility and artifacts

Select the final regression and segmentation artifacts using documented training/validation evidence and the user-facing use case. Keep test results untouched until selection is complete. Persist:

- Fitted preprocessing + regression model pipeline (joblib).
- Fitted segmentation preprocessing + cluster assignment model/pipeline (joblib).
- Feature names/order, expected types, transformation parameters, cluster label mapping, training cutoff(s), data source/version/hash if feasible, package versions, random seeds, and evaluation metrics in a JSON/YAML metadata file.
- A model version/artifact timestamp. Never commit secrets or the full dataset.

For `joblib`, load only project-generated trusted artifacts. Explain that serialized Python objects are version-sensitive and should not be loaded from unknown sources. Ensure app dependency versions match those used to create artifacts. The app must show a clear setup error if artifacts are missing or incompatible; it must not silently retrain.

### 6.9 Inference contract

At inference, application code must:

1. Accept a prepared customer-level row or derive RFM from a user's uploaded transaction file (the MVP must define which path is implemented; customer dashboard needs customer-level data available).
2. Validate required fields, date assumptions, numeric values, and nonnegative constraints as applicable.
3. Apply exactly the saved preprocessing pipeline and model; preserve feature order through named columns.
4. Return a segment label and predicted total spend for the next 90 days, with currency/units caveat if source currency is unresolved.
5. Show model/data cutoff, concise explanation, and limitations; do not imply certainty.
6. Handle malformed files, empty data, unseen categories, missing customers, and missing/corrupt artifacts with actionable messages rather than a crash.

**TBD:** Whether users upload raw transactions or a pre-aggregated customer table in the deployed demo. Recommended MVP: provide both a sample-data/demo mode and upload of the documented transaction schema, while ensuring no sensitive files are retained. Confirm feasibility and storage behavior before implementation.

---

## 7. Realistic end-user journey

Example journey (illustrative workflow only; all displayed numbers must come from actual data/model outputs):

1. **Mariam**, marketing manager at a small online retailer, opens MarketMind and reads a brief explanation of the analysis and data handling.
2. She selects “Try demo data” or uploads a CSV/XLSX using the displayed schema guide.
3. MarketMind checks required columns and reports any missing fields, unreadable dates, missing customer IDs, negative quantities/returns, and excluded-row counts. Mariam can correct the file or continue only if validation permits.
4. The app displays a dataset summary and the analysis cutoff/period so she knows which history the model uses.
5. She opens the segmentation dashboard. It shows cluster sizes and profiles based on computed RFM summaries, alongside a PCA chart clearly labeled as a 2D visualization.
6. She searches for a customer ID. The profile shows recency, invoice frequency, monetary value, assigned segment, predicted eligible spend in the next 90 days, and a segment-based suggested action if that action mapping has been approved.
7. She reads a short explanation of model quality and limitations, including that predicted spend is an estimate based on historical data and not a guaranteed revenue outcome.
8. She downloads a results CSV only if that feature is implemented and tested. The app does not send campaigns or contact customers.

This is a user-flow illustration, not a claim that the example customer or results exist in the data.

---

## 8. Web application requirements

### 8.1 Required framework and deployment

- **[PROJECT — DECIDED]** Streamlit is the implementation choice carried forward from planning.
- **[PDF — REQUIRED]** Deploy publicly to Streamlit Community Cloud or Hugging Face Spaces. Host choice remains **TBD** until selected.
- App must be usable by a non-technical person and built around the Idea 02 customer dashboard.

### 8.2 Suggested pages

1. **Home / Start:** purpose, data/privacy note, demo mode, upload instructions.
2. **Data validation:** schema, detected issues, cleaning reconciliation, analysis period/cutoff.
3. **Overview:** actual customer/transaction summaries and eligible dataset counts.
4. **Segments:** sizes, RFM profiles, PCA chart, segment definitions and caveats.
5. **Customer lookup:** search/select ID; RFM; assigned segment; predicted 90-day spend; suggested action (if approved).
6. **Model quality:** baseline/model metrics, test window, error plots/tables, limitations.

Implement only pages supported by computed project outputs. Do not hard-code made-up KPI cards.

### 8.3 UX and reliability

- Clear labels, plain-language descriptions, units and date windows.
- Validate inputs before model calls; handle wrong input without crashing.
- Never display private raw row data unnecessarily.
- No fabricated “live” updates or unsupported explanations.
- Include a demo path that is reproducible and clearly marked as demo data.
- State that suggested marketing actions are heuristics, not causal experiments, unless separately validated.
- App should not retrain models at every startup or user request; use saved artifacts for inference.
- Cache safe, deterministic loading/summary operations where appropriate; avoid caching user-private data across sessions without a defined policy.

---

## 9. Repository structure

Recommended structure; adapt to existing repository rather than replacing it:

```text
marketmind/
├── app.py                       # Streamlit entry point
├── pages/                       # Optional Streamlit multipage UI
├── notebooks/
│   └── 01_marketmind_analysis.ipynb
├── src/marketmind/
│   ├── config.py
│   ├── data/                     # Loading, schema checks, cleaning
│   ├── features/                 # RFM and temporal target construction
│   ├── models/                   # Pipeline builders, training, evaluation
│   ├── inference.py              # Artifact loading and validated predictions
│   └── visualization/            # Reusable charts
├── artifacts/                   # Small fitted models/metadata only; policy TBD
├── data/
│   ├── raw/                      # Git-ignored; never commit source dataset
│   └── processed/                # Git-ignored unless tiny approved sample
├── reports/                     # Generated metrics/figures, no fabricated values
├── tests/                        # Focused unit/integration checks
├── docs/                         # Data dictionary, model card, decisions
├── requirements.txt              # Or pyproject.toml; choose one source of truth
├── .gitignore
├── README.md
└── LICENSE                       # Only if license/ownership is confirmed
```

The exact module split is a recommendation. Keep business logic reusable outside Streamlit, and keep notebook code readable and explanatory. Do not create empty folders or duplicate all code solely to match this tree.

### 9.1 Dependency guidance

Use Python, pandas, NumPy, scikit-learn, matplotlib/seaborn as needed, Streamlit, and joblib. Add Excel-reading support only if required by the chosen input format. Pin or constrain versions after verifying a working environment; do not invent compatibility claims. Keep one canonical dependency file and document setup commands.

---

## 10. Testing and quality gates

Tests are required as a project quality deliverable/recommendation; the PDF itself explicitly requires the notebook to run and app to handle wrong inputs. Test the following:

- Data loader accepts a valid fixture and rejects missing columns/bad dates with helpful errors.
- Cleaning output has expected types, documented exclusions, no impossible values under policy, and a row-count reconciliation.
- RFM aggregation counts distinct invoices, is unique per customer/cutoff, and respects the cutoff.
- Target construction includes only the following 90 days, handles no-purchase customers as specified, and excludes incomplete future windows.
- Temporal split ordering and preprocessing fit boundaries prevent leakage.
- Training pipeline fits and predictions have expected shape and finite values.
- Segmentation assignment is deterministic under fixed artifact and schema; labels are mapped consistently.
- Artifact save/load round-trip preserves predictions and schema metadata.
- Inference rejects malformed inputs clearly and handles unseen/missing values according to policy.
- Streamlit smoke check: app starts, demo works, invalid upload yields a message, and absent artifact yields a useful setup error.
- Notebook passes **Restart & Run All** with no errors.

Do not write tests that encode invented performance thresholds. For checks involving random sampling, use fixed seeds and tolerances where appropriate. Report actual commands and results.

---

## 11. Deliverables and acceptance criteria

### 11.1 Notebook — [PDF — REQUIRED]

One clean Jupyter notebook runs top-to-bottom after “Restart & Run All,” with Markdown explanations between steps.

Acceptance:

- Includes problem framing, data source/dictionary, data quality, EDA, written 3–5 insights, preprocessing, temporal target construction, segmentation, regression baseline and ≥3 course algorithms, CV/tuning, untouched test metrics, error analysis, business insight and limitations.
- Records actual row/customer counts, exact cutoffs, filters, seeds, package versions where practical.
- No manually typed model score presented as though computed.
- Does not depend on an undocumented local path or hidden notebook state.

### 11.2 Deployed app — [PDF — REQUIRED]

Acceptance:

- Public URL opens in a private browser window, once deployment is approved and completed.
- Dashboard shows customer segment profiles; customer lookup returns segment, predicted 90-day spend, and recommended action if approved.
- Invalid input is handled without crash.
- Model artifacts are loaded for inference; app does not silently train.
- Data source, metric/test window, limitations, and privacy behavior are described accurately.
- Link is recorded in README and presentation only after verified.

### 11.3 GitHub repository and README — [PDF — REQUIRED]

README includes: one-sentence problem statement, live app link, screenshot/GIF, actual baseline-versus-best results table, setup/how-to-run instructions, data source credit, and limitations. Do not upload large datasets. If public hosting or repository creation requires a user-owned account/action, prepare files and instructions but do not claim completion until user performs or authorizes that action.

### 11.4 Presentation — [PDF — REQUIRED]

10–12 slides, about 10 minutes: problem → data → key EDA insights → models → results → recommendation. Suggested 11-slide sequence:

1. Title and one-line value proposition.
2. Problem, user, and decision.
3. Dataset/source and data limitations.
4. Cleaning and data quality.
5. EDA insights (evidence-based).
6. RFM definition and segmentation method.
7. Segment profiles/PCA visualization.
8. 90-day target and temporal split.
9. Model comparison and actual held-out results.
10. App demo and business recommendation.
11. Limitations, next steps, repository/app links.

### 11.5 LinkedIn post and CV bullet — [PDF — REQUIRED]

Prepare an evidence-based post with real problem, what was built, 1–2 measured results, one lesson/challenge, 30–60 second demo or screenshots, and links. CV bullet formula: action verb + built artifact + measured data scale + measured result + tools. Keep placeholders until actual numbers exist; do not fabricate numbers or publish without user approval.

### 11.6 Final self-check — [PDF — REQUIRED]

- [ ] App opens from a private browser window and handles wrong input without crashing.
- [ ] README has live link, screenshot and actual results table.
- [ ] Notebook runs top-to-bottom without errors.
- [ ] Every reported number comes from project code.
- [ ] Dataset is credited and linked.

---

## 12. SaaS-ready boundaries

“SaaS-ready” means the academic MVP is organized so future product work is possible. It does **not** mean commercially production-ready.

### Build now

- Separate reusable data/model/inference logic from the Streamlit UI.
- Keep configuration out of scattered literals.
- Use explicit input/output schemas and version model artifacts.
- Keep raw/processed data and secrets out of Git.
- Avoid assuming one fixed local path or one dataset instance throughout business logic.
- Make processing functions deterministic and testable.
- Document where user data enters, is processed, and may be stored.

### Defer

- Authentication/authorization and account recovery.
- Multi-tenancy, tenant isolation, roles, audit logs.
- Database and durable user workspaces.
- Billing/subscriptions/payment gateways.
- Production privacy/security/compliance review.
- Background jobs, queueing, monitoring/alerts, SLAs, backups, and scale testing.
- Connectors to Shopify, WooCommerce, POS, CRM, email platforms.
- Causal uplift measurement or automated campaign execution.

Do not describe the public course demo as safe for sensitive commercial data unless that has been independently designed and verified.

---

## 13. Detailed implementation roadmap (no deadline)

Complete phases sequentially. The user may review each phase. A later phase must not conceal an incomplete earlier prerequisite.

### Phase 0 — Repository and decisions audit

1. Inspect existing files, git status, Python environment, available compute, and whether dataset is already present.
2. Preserve existing user work. Record current state in a brief implementation log.
3. Create a decision register containing all TBDs in this document.
4. Confirm actual UCI workbook schema and license/usage information.

**Exit criteria:** Existing state understood; source file and schema confirmed or blocker reported; TBD register created; no user file overwritten.

### Phase 1 — Project skeleton and reproducible environment

1. Create/adapt repository structure.
2. Establish one dependency file and setup instructions.
3. Add `.gitignore` for virtual environments, secrets, raw/processed datasets, caches and temporary files.
4. Add config for input path, random seeds, date windows, and artifact paths without embedding secrets.
5. Add a small synthetic/fixture dataset for tests only if clearly labeled synthetic.

**Exit criteria:** Fresh environment setup documented; imports work; no dataset/secrets committed; configuration is centralized.

### Phase 2 — Data acquisition, ingestion and understanding

1. Download the official dataset manually or by a documented reproducible method; do not assume credentials.
2. Inspect workbook sheets and headers; verify source data dictionary.
3. Implement schema validation and robust loading.
4. Produce data quality summary: counts, types, dates, missingness, duplicates, cancellation/return indicators and numeric ranges.
5. Record source row counts and data provenance.

**Exit criteria:** Data loads reproducibly; schema and data dictionary are documented; quality summary contains computed values; failures are actionable.

### Phase 3 — EDA and cleaning policy

1. Create the row-count reconciliation for each cleaning rule.
2. Analyze transaction and customer distributions, temporal coverage, outliers, missing IDs, cancellation/return patterns.
3. Decide/confirm return, cancellation, missing ID and invalid-value policy based on observed data and document it.
4. Build charts for univariate, bivariate, and multivariate analysis.
5. Write 3–5 insights strictly supported by outputs.

**Exit criteria:** Cleaning policy documented; transformations reproducible; EDA conclusions refer to actual visual/table evidence; no causal overclaim.

### Phase 4 — Time design, customer features and target

1. Inspect date coverage and determine candidate observation cutoffs with full 90-day future windows.
2. Define lookback length, cutoff(s), eligible customer rules, spend definition and split scheme. Ask user/instructor if a material business choice cannot be resolved from source facts.
3. Create one customer-level feature row per cutoff with RFM and any approved extras.
4. Create 90-day spend target only from post-cutoff transactions.
5. Add assertions/tests proving no feature transaction is after cutoff and all targets use exactly the future period.
6. Inspect target distribution, zero-target fraction, and sample counts.

**Exit criteria:** Feature/target definitions and dates documented; chronological data split is valid; leakage checks pass; customer table is unique per customer/cutoff.

### Phase 5 — RFM segmentation

1. Build fitted preprocessing for RFM (transform/scale as justified).
2. Evaluate K-Means candidates with diagnostics and interpretability.
3. Compare hierarchical clustering on a documented sample if full-scale compute is impractical.
4. Create PCA visualization with explained variance.
5. Produce segment profiles in original RFM units and quantify sizes from actual outputs.
6. Choose labels only after reviewing profiles. Keep an explicit mapping; document how labels relate to clusters.
7. Draft segment actions as heuristics and mark pending approval if not yet approved.

**Exit criteria:** Reproducible segmentation pipeline/artifact; cluster count rationale; comparison and PCA; profiles and labels grounded in computed data; action policy caveats.

### Phase 6 — Spending regression

1. Implement a mean baseline.
2. Train at least three distinct course algorithms in sklearn pipelines.
3. Choose time-aware CV consistent with cutoff design.
4. Tune candidate hyperparameters on training/validation data only.
5. Select based on documented metrics and business use; freeze selection before test evaluation.
6. Evaluate once on untouched test set; report MAE/RMSE/R² and error analysis.
7. Compare by segment/spend bands if sample size supports it.

**Exit criteria:** Baseline and ≥3 algorithms; CV/tuning logs; honest held-out metrics; error analysis; no test leakage.

### Phase 7 — Artifacts and inference API

1. Package feature construction and preprocessing into reusable functions/pipelines.
2. Save fitted segmentation and regression pipeline(s) using joblib.
3. Save schema, feature order, cutoff, version, seed, metrics and mapping metadata.
4. Implement validated inference and artifact loading with clear errors.
5. Test artifact round-trip predictions and schema mismatch behavior.

**Exit criteria:** App-compatible artifacts load in a clean process/environment; predictions match pre-save behavior; metadata is sufficient to interpret the artifact.

### Phase 8 — Streamlit application

1. Implement the user journey and pages in Section 8.
2. Add reproducible demo mode and documented upload format.
3. Wire app to saved artifacts and shared inference code.
4. Add validation states, empty states, errors, data-period labels and limitations.
5. Verify charts and tables use computed outputs only.

**Exit criteria:** Demo and supported upload path work; invalid inputs/artifact failures are handled; no hidden retraining; customer lookup works.

### Phase 9 — Verification and notebook polish

1. Run unit/integration checks and fix issues.
2. Run notebook from a fresh kernel with Restart & Run All.
3. Run app smoke checks, including malformed upload and missing artifact.
4. Reconcile notebook, app, artifacts, and README metrics so they describe the same model/version/split.
5. Capture real screenshots/GIF and record verified local app behavior.

**Exit criteria:** Required checks actually run; failures documented; published claims match code outputs.

### Phase 10 — Deployment and portfolio deliverables

1. Confirm deployment host (Streamlit Community Cloud or Hugging Face Spaces) if not yet selected.
2. Prepare deployment files and secrets-free configuration; never put credentials in source.
3. Deploy only with appropriate user account/access. Do not falsely claim public deployment before URL is verified.
4. Open URL in a private browser window; verify sample path and invalid-input behavior.
5. Finish README, 10–12 slide presentation, LinkedIn post/demo, and evidence-based CV bullet.
6. Verify source attribution and final self-check.

**Exit criteria:** Public link works and is recorded; deliverables are complete; every number is traceable to generated output; unresolved decisions are listed.

---

## 14. Open decisions register

Keep this table current. Move an item to “Resolved” only after user/instructor agreement or evidence-based implementation choice is documented.

| ID | Decision | Current status | Resolution rule |
|---|---|---|---|
| D1 | Deployment host: Streamlit Community Cloud or Hugging Face Spaces | TBD | Recommend Streamlit Community Cloud for Streamlit app simplicity; confirm account/deployment access before publishing. |
| D2 | User input path: raw transactions, prepared customer-level table, or both | TBD | Recommend demo mode plus raw transaction upload if implementation capacity permits. Clearly document actual storage behavior. |
| D3 | Full data or sample; sampling strategy | TBD/data-dependent | Measure size/runtime first; if sampling, make reproducible and representative for stated goal; report exact method and counts. |
| D4 | Observation lookback length, cutoff dates, and temporal split | TBD/data-dependent | Derive from date coverage and sufficient fully observed 90-day target windows; document before modeling. |
| D5 | Return/refund/cancellation treatment in spend target | TBD/data-dependent | Inspect dataset semantics; quantify impact; seek user/instructor agreement if materially ambiguous. |
| D6 | Display currency/units | TBD | Use source-defined units; do not convert or label currency without authoritative evidence. |
| D7 | Segment action mapping | TBD/business policy | Use transparent, reviewed heuristics; avoid causal or guaranteed language. |
| D8 | Whether to publish publicly and create LinkedIn content | TBD/user approval | Prepare drafts/assets; user controls publication. |

When any TBD blocks work, ask a focused question with the evidence and options. Continue independent work where possible. Never convert TBD to a silent assumption.

---

## 15. Final definition of done

MarketMind is complete for the academic MVP only when all PDF-required deliverables and the app behavior are verified, including:

- Problem and business metric framed clearly.
- Dataset source/size/schema/data quality documented with computed counts.
- EDA includes univariate/bivariate/multivariate analysis and 3–5 evidence-backed insights.
- Preprocessing is in sklearn pipelines and split before fitting.
- RFM K-Means and hierarchical comparison, PCA visualization, and defensible segment profiles.
- Time-aware 90-day spend target with leakage checks.
- Baseline plus at least three distinct course algorithms, training-only CV/tuning, untouched test evaluation, regression metrics, and error analysis.
- Saved joblib pipeline artifact(s) and working app inference.
- Usable Streamlit app deployed publicly to an approved host, with verified public link and error handling.
- Notebook passes Restart & Run All.
- GitHub repository/README, screenshot/GIF, results table, data link/credit.
- 10–12-slide presentation and evidence-based LinkedIn post/demo materials.
- Limitations and out-of-MVP SaaS work are explicit.
- No fabricated values, hidden assumptions, or unreported TBD decisions.

If an external dependency (dataset access, hosting account, instructor approval, or user publication decision) prevents completion, mark that criterion **blocked by dependency**, name it, and provide the exact next action. Do not label the project fully complete while a required item remains unverified.

---

## Appendix A — Plain-language glossary

- **RFM:** Recency (how recently someone bought), Frequency (how often they bought), and Monetary value (how much they spent during a defined period).
- **Segmentation / clustering:** Grouping similar customers without a predefined correct group label.
- **Regression:** Estimating a numeric value; here, eligible spend over the 90 days after a cutoff.
- **Observation cutoff:** The latest date whose information is allowed into the prediction features.
- **Target window:** The future period whose spend becomes the value the model learns to estimate.
- **Data leakage:** Accidental use of information that would not have been available when making a real prediction, leading to misleadingly optimistic results.
- **Pipeline:** A saved sequence of preprocessing and model steps applied consistently during training and prediction.
- **joblib:** A Python tool commonly used to save/load fitted scikit-learn pipelines. Its artifacts are Python objects and must be trusted and used with compatible dependencies.
- **MAE:** Average absolute difference between predicted and actual spend, in the target's units.
- **RMSE:** Square-rooted average squared prediction error; larger errors count more heavily.
- **R²:** A comparison of model fit to a mean baseline under a defined evaluation split; it is not an accuracy percentage.
- **PCA:** A dimensionality-reduction method that projects features to fewer axes for visualization; a 2D picture can distort original distances.
- **SaaS-ready boundary:** Code structure that supports future product work; it is not equivalent to a secure, scalable commercial SaaS service.

