#!/usr/bin/env python3
"""Train segmentation + regression artifacts with leakage-safe temporal design.

Writes:
  - artifacts/segmentation_pipeline.joblib
  - artifacts/regression_pipeline.joblib
  - artifacts/model_metadata.json
  - reports/*.json / csv diagnostics

Cutoffs and lookback are derived from cleaned data coverage and written into
metadata. They remain documented data-dependent choices (D4).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from marketmind.config import (  # noqa: E402
    ACTIONS_APPROVED,
    ARTIFACTS_DIR,
    CURRENCY_CONFIRMED,
    CURRENCY_LABEL,
    FIGURES_DIR,
    PREFERRED_DEPLOY_HOST,
    PROCESSED_DATA_DIR,
    RANDOM_SEED,
    REGRESSION_FEATURE_COLS,
    REPORTS_DIR,
    TARGET_WINDOW_DAYS,
)
from marketmind.features.target import build_customer_modeling_table  # noqa: E402
from marketmind.models.regression import (  # noqa: E402
    DEFAULT_PARAM_GRIDS,
    build_candidate_pipelines,
    cross_validate_models,
    regression_metrics,
    tune_model,
)
from marketmind.models.segment_labels import (  # noqa: E402
    derive_segment_labels,
    provisional_actions_for_labels,
)
from marketmind.models.segmentation import (  # noqa: E402
    evaluate_kmeans_k,
    fit_kmeans_segmentation,
    hierarchical_comparison,
    pca_projection,
    segment_profiles,
)


def choose_cutoffs(min_date: pd.Timestamp, max_date: pd.Timestamp) -> dict:
    """Derive chronological cutoffs with full 90-day future windows.

    Design (documented D4 resolution from data coverage):
    - Lookback: full history on/before each cutoff (lookback_days=None).
    - Train cutoff: earliest feasible cutoff that leaves room for a later test
      cutoff and full 90-day labels for both.
    - Test cutoff: later cutoff with full 90-day observation to max_date.
    """
    # Latest possible cutoff with full 90-day window
    latest_feasible = max_date - pd.Timedelta(days=TARGET_WINDOW_DAYS)
    if latest_feasible <= min_date + pd.Timedelta(days=180):
        raise RuntimeError("Insufficient date coverage for train/test cutoffs")

    # Place test cutoff at latest feasible; train cutoff ~9 months earlier
    test_cutoff = latest_feasible.normalize()
    train_cutoff = (test_cutoff - pd.Timedelta(days=273)).normalize()  # ~9 months
    if train_cutoff <= min_date + pd.Timedelta(days=90):
        train_cutoff = (min_date + pd.Timedelta(days=180)).normalize()
    if train_cutoff >= test_cutoff:
        raise RuntimeError("Could not place train cutoff before test cutoff")

    return {
        "lookback_days": None,
        "train_cutoffs": [str(train_cutoff.date())],
        "test_cutoff": str(test_cutoff.date()),
        "rationale": (
            "Full-history lookback; test cutoff = max_date - 90d; "
            "train cutoff ~273 days earlier so train labels end before test cutoff."
        ),
    }


def main() -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    cleaned_path = PROCESSED_DATA_DIR / "transactions_cleaned.parquet"
    if not cleaned_path.exists():
        raise FileNotFoundError(
            f"Missing {cleaned_path}. Run cleaning pipeline first."
        )
    tx = pd.read_parquet(cleaned_path)
    min_date = pd.Timestamp(tx["invoice_date"].min())
    max_date = pd.Timestamp(tx["invoice_date"].max())
    cutoffs = choose_cutoffs(min_date, max_date)
    train_cutoff = pd.Timestamp(cutoffs["train_cutoffs"][0])
    test_cutoff = pd.Timestamp(cutoffs["test_cutoff"])

    print("Date coverage:", min_date, "→", max_date)
    print("Train cutoff:", train_cutoff.date(), "Test cutoff:", test_cutoff.date())

    train_table = build_customer_modeling_table(
        tx, cutoff=train_cutoff, lookback_days=None, window_days=TARGET_WINDOW_DAYS
    )
    test_table = build_customer_modeling_table(
        tx, cutoff=test_cutoff, lookback_days=None, window_days=TARGET_WINDOW_DAYS
    )
    train_table.to_parquet(PROCESSED_DATA_DIR / "customer_train.parquet", index=False)
    test_table.to_parquet(PROCESSED_DATA_DIR / "customer_test.parquet", index=False)
    print(
        "Train customers:",
        len(train_table),
        "zero-target fraction:",
        float((train_table["target_spend_90d"] == 0).mean()),
    )
    print(
        "Test customers:",
        len(test_table),
        "zero-target fraction:",
        float((test_table["target_spend_90d"] == 0).mean()),
    )

    # --- Segmentation on train RFM only ---
    k_diag = evaluate_kmeans_k(train_table, k_values=range(2, 9), random_state=RANDOM_SEED)
    k_diag.to_csv(REPORTS_DIR / "kmeans_diagnostics.csv", index=False)
    # Prefer k with high silhouette and no tiny clusters (<2% share handled later)
    k_diag = k_diag.sort_values(["silhouette", "min_cluster_size"], ascending=False)
    n_clusters = int(k_diag.iloc[0]["k"])
    print("Selected k (train silhouette/size):", n_clusters)
    print(k_diag.to_string(index=False))

    seg_pipe, train_labels = fit_kmeans_segmentation(
        train_table, n_clusters=n_clusters, random_state=RANDOM_SEED
    )
    profiles = segment_profiles(train_table, train_labels)
    profiles.to_csv(REPORTS_DIR / "segment_profiles_train.csv", index=False)
    hier = hierarchical_comparison(
        train_table, n_clusters=n_clusters, sample_size=5000, random_state=RANDOM_SEED
    )
    (REPORTS_DIR / "hierarchical_comparison.json").write_text(json.dumps(hier, indent=2))

    pca_df, pca = pca_projection(train_table, seg_pipe)
    pca_df["cluster_id"] = train_labels.values
    pca_df.to_parquet(PROCESSED_DATA_DIR / "pca_train.parquet", index=False)
    explained = {
        "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "explained_variance_ratio_sum": float(pca.explained_variance_ratio_.sum()),
        "note": "PCA is for 2D visualization only; it does not validate cluster quality.",
    }
    (REPORTS_DIR / "pca_explained_variance.json").write_text(json.dumps(explained, indent=2))

    # Provisional labels from observed RFM profiles (not approved personas)
    provisional_names = derive_segment_labels(profiles)
    action_by_cluster = provisional_actions_for_labels(provisional_names)

    # Sensitivity: fit k=3 diagnostics/profiles without changing selected artifact
    sens_rows = []
    for k_alt in (2, 3):
        row = k_diag.loc[k_diag["k"] == k_alt]
        if row.empty:
            continue
        _, labs_alt = fit_kmeans_segmentation(
            train_table, n_clusters=int(k_alt), random_state=RANDOM_SEED
        )
        prof_alt = segment_profiles(train_table, labs_alt)
        sens_rows.append(
            {
                "k": int(k_alt),
                "silhouette": float(row.iloc[0]["silhouette"]),
                "inertia": float(row.iloc[0]["inertia"]),
                "min_cluster_size": int(row.iloc[0]["min_cluster_size"]),
                "labels": derive_segment_labels(prof_alt),
                "profiles": prof_alt.to_dict(orient="records"),
            }
        )
    sensitivity = {
        "selected_k": n_clusters,
        "selection_rule": (
            "Maximize training silhouette, then prefer larger min_cluster_size. "
            "k=2 wins on silhouette (see kmeans_diagnostics.csv). "
            "k=3 kept as sensitivity only — not forced for more personas."
        ),
        "comparisons": sens_rows,
    }
    (REPORTS_DIR / "k_sensitivity.json").write_text(json.dumps(sensitivity, indent=2))

    joblib.dump(seg_pipe, ARTIFACTS_DIR / "segmentation_pipeline.joblib")

    # --- Regression: CV/tune on train only; evaluate once on test ---
    X_train = train_table.loc[:, list(REGRESSION_FEATURE_COLS)]
    y_train = train_table["target_spend_90d"]
    X_test = test_table.loc[:, list(REGRESSION_FEATURE_COLS)]
    y_test = test_table["target_spend_90d"]

    # Order train by recency of customer history proxy: use customer_id stable order
    # TimeSeriesSplit needs ordered rows; sort by monetary as weak proxy is wrong.
    # Better: sort by a train-only available timestamp — last purchase approximated by -recency.
    order = train_table.sort_values("recency", ascending=False).index  # older first
    X_train_ord = X_train.loc[order]
    y_train_ord = y_train.loc[order]

    pipelines = build_candidate_pipelines(random_state=RANDOM_SEED)
    cv = TimeSeriesSplit(n_splits=3)
    cv_table = cross_validate_models(pipelines, X_train_ord, y_train_ord, cv=cv)
    cv_table.to_csv(REPORTS_DIR / "cv_results.csv", index=False)
    print(cv_table.to_string(index=False))

    tuned = {}
    for name in ("ridge", "random_forest", "gradient_boosting"):
        search = tune_model(
            pipelines[name],
            DEFAULT_PARAM_GRIDS[name],
            X_train_ord,
            y_train_ord,
            cv=cv,
            scoring="neg_mean_absolute_error",
        )
        tuned[name] = search
        print(name, "best_params", search.best_params_, "best_cv_MAE", -search.best_score_)

    # Select by best CV MAE among tuned + baseline CV MAE
    baseline_cv_mae = -float(
        cv_table.loc[cv_table["model"] == "mean_baseline", "cv_mean_neg_mean_absolute_error"].iloc[0]
    )
    selection = {"mean_baseline": baseline_cv_mae}
    for name, search in tuned.items():
        selection[name] = float(-search.best_score_)
    selected_name = min(selection, key=selection.get)
    print("Selected model by CV MAE:", selected_name, selection)

    if selected_name == "mean_baseline":
        final_model = build_candidate_pipelines(random_state=RANDOM_SEED)["mean_baseline"]
        final_model.fit(X_train, y_train)
        selected_params: dict = {}
    else:
        final_model = tuned[selected_name].best_estimator_
        selected_params = tuned[selected_name].best_params_

    # Freeze selection before test evaluation
    (REPORTS_DIR / "model_selection.json").write_text(
        json.dumps(
            {
                "selected_model": selected_name,
                "selection_metric": "cv_mae",
                "cv_mae_by_model": selection,
                "selected_params": selected_params,
                "test_untouched_until_here": True,
            },
            indent=2,
        )
    )

    y_pred = final_model.predict(X_test)
    test_metrics = regression_metrics(y_test, y_pred)
    print("TEST METRICS", test_metrics)

    # Error analysis
    err = test_table.copy()
    err["y_pred"] = y_pred
    err["residual"] = err["target_spend_90d"] - err["y_pred"]
    err["abs_error"] = err["residual"].abs()
    bands = pd.qcut(err["target_spend_90d"], q=4, duplicates="drop")
    by_band = (
        err.groupby(bands, observed=True)
        .agg(
            n=("customer_id", "size"),
            mae=("abs_error", "mean"),
            mean_actual=("target_spend_90d", "mean"),
            mean_pred=("y_pred", "mean"),
        )
        .reset_index()
    )
    by_band.to_csv(REPORTS_DIR / "error_by_spend_band.csv", index=False)
    err[["customer_id", "target_spend_90d", "y_pred", "residual", "abs_error"]].to_parquet(
        PROCESSED_DATA_DIR / "test_predictions.parquet", index=False
    )

    # Residual plot for model quality / notebook / README
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].scatter(err["y_pred"], err["residual"], s=8, alpha=0.35)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_xlabel("Predicted 90-day spend")
    axes[0].set_ylabel("Residual (actual − predicted)")
    axes[0].set_title("Test residuals vs prediction")
    axes[1].hist(err["residual"], bins=40)
    axes[1].set_xlabel("Residual")
    axes[1].set_title("Residual distribution (test)")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "test_residuals.png", dpi=120)
    plt.close(fig)

    # Baseline test metrics for comparison table
    baseline = build_candidate_pipelines(random_state=RANDOM_SEED)["mean_baseline"]
    baseline.fit(X_train, y_train)
    baseline_test = regression_metrics(y_test, baseline.predict(X_test))

    joblib.dump(final_model, ARTIFACTS_DIR / "regression_pipeline.joblib")

    # Package versions
    import sklearn

    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": RANDOM_SEED,
        "data": {
            "cleaned_rows": int(len(tx)),
            "date_min": str(min_date),
            "date_max": str(max_date),
            "train_customers": int(len(train_table)),
            "test_customers": int(len(test_table)),
        },
        "lookback_days": cutoffs["lookback_days"],
        "train_cutoffs": cutoffs["train_cutoffs"],
        "test_cutoff": cutoffs["test_cutoff"],
        "cutoff_rationale": cutoffs["rationale"],
        "target_window_days": TARGET_WINDOW_DAYS,
        "n_clusters": n_clusters,
        "segment_label_map": provisional_names,
        "segment_action_map": action_by_cluster,
        "actions_approved": ACTIONS_APPROVED,
        "selected_regression_model": selected_name,
        "selected_params": selected_params,
        "cv_mae_by_model": selection,
        "test_metrics": test_metrics,
        "baseline_test_metrics": baseline_test,
        "currency_label": CURRENCY_LABEL,
        "currency_confirmed": CURRENCY_CONFIRMED,
        "deployment": {
            "preferred_host": PREFERRED_DEPLOY_HOST,
            "public_publish_approved": False,
            "note": "D1 preference set; D8 publish not approved — do not deploy externally.",
        },
        "feature_order": list(REGRESSION_FEATURE_COLS),
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "hierarchical_comparison": hier,
        "pca": explained,
        "k_selection": sensitivity,
        "eligible_spend_policy": (
            "Exclude cancellation invoices (Invoice starting with C); "
            "require quantity > 0 and unit_price >= 0. "
            "Target is eligible positive spend, not net revenue after refunds. (D5 resolved)."
        ),
        "rfm_definitions": {
            "recency": "Days between cutoff and most recent eligible purchase (lower = more recent).",
            "frequency": "Count of distinct eligible invoices in the observation window.",
            "monetary": "Sum of eligible line_amount (quantity * unit_price) in the observation window.",
            "lookback": "Full history on/before cutoff (lookback_days=null).",
        },
        "notes": [
            "Segment names are descriptive labels from RFM profile medians; not approved personas.",
            "Segment actions are provisional heuristics only (D7); actions_approved=false — not approved business policy.",
            "Eligible-spend policy (D5): cancellations starting with C and non-positive quantities excluded; target is eligible positive spend, not net revenue after refunds.",
            "Currency (D6): GBP (£) per UCI dataset description; no FX conversion; currency_confirmed=true.",
            "Deployment (D1/D8): preferred host Streamlit Community Cloud; public publish not approved.",
            "Do not load these joblib files from untrusted sources.",
        ],
    }
    (ARTIFACTS_DIR / "model_metadata.json").write_text(json.dumps(metadata, indent=2))
    (REPORTS_DIR / "test_metrics.json").write_text(json.dumps(test_metrics, indent=2))
    print("Saved artifacts to", ARTIFACTS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
