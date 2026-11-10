"""Artifact load and inference contract tests."""

from __future__ import annotations

import pytest

from marketmind.config import ARTIFACTS_DIR
from marketmind.inference import ArtifactError, load_artifacts, predict_customer, validate_customer_features


@pytest.mark.skipif(
    not (ARTIFACTS_DIR / "regression_pipeline.joblib").exists(),
    reason="Artifacts not trained yet",
)
def test_artifact_roundtrip_predicts_finite():
    arts = load_artifacts()
    result = predict_customer(
        {"recency": 10, "frequency": 3, "monetary": 250.0},
        artifacts=arts,
    )
    assert result.cluster_id is not None
    assert result.predicted_spend_90d == result.predicted_spend_90d  # not NaN
    assert isinstance(result.predicted_spend_90d, float)


def test_validate_rejects_negative():
    with pytest.raises(ValueError, match="nonnegative"):
        validate_customer_features({"recency": -1, "frequency": 1, "monetary": 1})


def test_missing_artifacts_message(tmp_path):
    with pytest.raises(ArtifactError, match="missing"):
        load_artifacts(tmp_path)
