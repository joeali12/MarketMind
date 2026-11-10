"""Load saved artifacts and run validated inference (no silent retrain)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from marketmind.config import ARTIFACTS_DIR, REGRESSION_FEATURE_COLS, SEGMENTATION_FEATURE_COLS


class ArtifactError(RuntimeError):
    """Missing or incompatible model artifacts."""


@dataclass
class InferenceResult:
    customer_id: Any
    recency: float
    frequency: float
    monetary: float
    cluster_id: int | None
    segment_label: str | None
    predicted_spend_90d: float
    suggested_action: str | None
    metadata: dict[str, Any]


def default_artifact_paths(artifacts_dir: Path | None = None) -> dict[str, Path]:
    root = Path(artifacts_dir) if artifacts_dir is not None else ARTIFACTS_DIR
    return {
        "segmentation": root / "segmentation_pipeline.joblib",
        "regression": root / "regression_pipeline.joblib",
        "metadata": root / "model_metadata.json",
    }


def load_artifacts(artifacts_dir: Path | None = None) -> dict[str, Any]:
    paths = default_artifact_paths(artifacts_dir)
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        raise ArtifactError(
            "Required artifacts missing: "
            + ", ".join(f"{k} ({paths[k]})" for k in missing)
            + ". Train and save models before running the app (see README)."
        )
    try:
        segmentation = joblib.load(paths["segmentation"])
        regression = joblib.load(paths["regression"])
        metadata = json.loads(paths["metadata"].read_text())
    except Exception as exc:  # noqa: BLE001 — surface as setup error
        raise ArtifactError(
            f"Failed to load artifacts (incompatible or corrupt): {exc}"
        ) from exc
    return {
        "segmentation": segmentation,
        "regression": regression,
        "metadata": metadata,
        "paths": {k: str(v) for k, v in paths.items()},
    }


def validate_customer_features(row: pd.Series | dict[str, Any]) -> pd.DataFrame:
    data = dict(row) if not isinstance(row, dict) else row
    missing = [c for c in SEGMENTATION_FEATURE_COLS if c not in data]
    if missing:
        raise ValueError(f"Missing required feature(s): {missing}")
    frame = pd.DataFrame([{c: data[c] for c in SEGMENTATION_FEATURE_COLS}])
    for c in SEGMENTATION_FEATURE_COLS:
        val = float(frame.at[0, c])
        if not pd.notna(val):
            raise ValueError(f"Feature {c} is missing/NaN")
        if val < 0:
            raise ValueError(f"Feature {c} must be nonnegative, got {val}")
        frame.at[0, c] = val
    return frame


def predict_customer(
    features: pd.Series | dict[str, Any],
    artifacts: dict[str, Any] | None = None,
    *,
    artifacts_dir: Path | None = None,
) -> InferenceResult:
    """Assign segment and predict 90-day spend from saved pipelines."""
    arts = artifacts if artifacts is not None else load_artifacts(artifacts_dir)
    X = validate_customer_features(features)
    meta = arts["metadata"]
    cluster_id = int(arts["segmentation"].predict(X)[0])
    label_map = meta.get("segment_label_map", {}) or {}
    segment_label = label_map.get(str(cluster_id), label_map.get(cluster_id))
    action_map = meta.get("segment_action_map", {}) or {}
    action = action_map.get(str(cluster_id), action_map.get(segment_label))
    # Mark actions as heuristics if present
    if action is not None and not meta.get("actions_approved", False):
        action = f"[Heuristic — pending approval] {action}"

    yhat = float(arts["regression"].predict(X.loc[:, list(REGRESSION_FEATURE_COLS)])[0])
    cid = features.get("customer_id") if hasattr(features, "get") else None
    if cid is None and isinstance(features, dict):
        cid = features.get("customer_id")

    return InferenceResult(
        customer_id=cid,
        recency=float(X.at[0, "recency"]),
        frequency=float(X.at[0, "frequency"]),
        monetary=float(X.at[0, "monetary"]),
        cluster_id=cluster_id,
        segment_label=segment_label,
        predicted_spend_90d=yhat,
        suggested_action=action,
        metadata={
            "cutoff": meta.get("test_cutoff") or meta.get("train_cutoffs"),
            "target_window_days": meta.get("target_window_days", 90),
            "currency_label": meta.get("currency_label"),
            "model_name": meta.get("selected_regression_model"),
            "actions_approved": meta.get("actions_approved", False),
        },
    )
