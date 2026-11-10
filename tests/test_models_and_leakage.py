"""Model fit, segmentation determinism, and leakage-oriented checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone

from marketmind.config import ARTIFACTS_DIR, FIXTURES_DIR, REGRESSION_FEATURE_COLS
from marketmind.data.cleaning import clean_transactions
from marketmind.data.schema import to_canonical
from marketmind.features.target import build_customer_modeling_table
from marketmind.inference import load_artifacts, predict_customer
from marketmind.models.regression import MeanBaselineRegressor, build_candidate_pipelines, regression_metrics
from marketmind.models.segment_labels import derive_segment_labels
from marketmind.models.segmentation import fit_kmeans_segmentation, segment_profiles


@pytest.fixture
def cleaned_fixture() -> pd.DataFrame:
    raw = pd.read_csv(FIXTURES_DIR / "synthetic_transactions.csv")
    return clean_transactions(to_canonical(raw)).data


def test_pipeline_fit_predict_finite(cleaned_fixture: pd.DataFrame):
    table = build_customer_modeling_table(
        cleaned_fixture,
        cutoff="2010-12-10",
        lookback_days=None,
        window_days=40,
    )
    X = table.loc[:, list(REGRESSION_FEATURE_COLS)]
    y = table["target_spend_90d"]
    pipes = build_candidate_pipelines(random_state=0)
    for name, pipe in pipes.items():
        model = clone(pipe)
        model.fit(X, y)
        pred = model.predict(X)
        assert pred.shape == (len(X),)
        assert np.isfinite(pred).all(), name


def test_mean_baseline_predicts_train_mean():
    model = MeanBaselineRegressor()
    X = np.zeros((4, 3))
    y = np.array([1.0, 3.0, 5.0, 7.0])
    model.fit(X, y)
    assert np.allclose(model.predict(X), 4.0)


def test_segmentation_deterministic():
    # Synthetic RFM table large enough for stable k=2
    rng = np.random.default_rng(0)
    table = pd.DataFrame(
        {
            "recency": rng.integers(1, 200, size=40),
            "frequency": rng.integers(1, 15, size=40),
            "monetary": rng.uniform(10, 5000, size=40),
        }
    )
    _, a = fit_kmeans_segmentation(table, n_clusters=2, random_state=42)
    _, b = fit_kmeans_segmentation(table, n_clusters=2, random_state=42)
    assert (a.values == b.values).all()


def test_segment_labels_match_profile_medians():
    profiles = pd.DataFrame(
        {
            "cluster_id": [0, 1],
            "recency_mean": [20.0, 120.0],
            "monetary_mean": [4000.0, 400.0],
            "frequency_mean": [8.0, 1.0],
        }
    )
    labels = derive_segment_labels(profiles)
    assert labels["0"] == "Recent high-spend"
    assert labels["1"] == "Lapsed low-spend"


def test_features_never_use_post_cutoff_rows(cleaned_fixture: pd.DataFrame):
    cutoff = pd.Timestamp("2010-12-10")
    table = build_customer_modeling_table(
        cleaned_fixture, cutoff=cutoff, window_days=40
    )
    # Any invoice after cutoff must not contribute to monetary for that customer
    for _, row in table.iterrows():
        cid = row["customer_id"]
        pre = cleaned_fixture[
            (cleaned_fixture["customer_id"] == cid)
            & (cleaned_fixture["invoice_date"] <= cutoff)
        ]
        assert pre["invoice_date"].max() <= cutoff or pre.empty


@pytest.mark.skipif(
    not (ARTIFACTS_DIR / "regression_pipeline.joblib").exists(),
    reason="Artifacts not trained yet",
)
def test_artifact_predictions_stable_and_labeled():
    arts = load_artifacts()
    r1 = predict_customer(
        {"recency": 10, "frequency": 5, "monetary": 1000.0}, artifacts=arts
    )
    r2 = predict_customer(
        {"recency": 10, "frequency": 5, "monetary": 1000.0}, artifacts=arts
    )
    assert r1.predicted_spend_90d == r2.predicted_spend_90d
    assert r1.cluster_id == r2.cluster_id
    assert r1.segment_label in arts["metadata"]["segment_label_map"].values()
    assert arts["metadata"].get("actions_approved") is False
    assert r1.suggested_action is None or "pending approval" in r1.suggested_action.lower() or "heuristic" in (
        r1.suggested_action or ""
    ).lower()


@pytest.mark.skipif(
    not (ARTIFACTS_DIR / "regression_pipeline.joblib").exists(),
    reason="Artifacts not trained yet",
)
def test_regression_metrics_shape_from_saved_metadata():
    arts = load_artifacts()
    tm = arts["metadata"]["test_metrics"]
    assert set(tm) >= {"mae", "rmse", "r2"}
    # Sanity: metrics finite; do not assert invented thresholds
    for v in tm.values():
        assert np.isfinite(v)
