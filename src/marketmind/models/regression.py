"""Spending regression: baseline + candidate sklearn pipelines, CV, evaluation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from marketmind.config import RANDOM_SEED, REGRESSION_FEATURE_COLS


class MeanBaselineRegressor(BaseEstimator, RegressorMixin):
    """Predict the training-target mean for every row."""

    def __init__(self) -> None:
        self.mean_: float | None = None

    def fit(self, X, y):
        y = np.asarray(y, dtype=float)
        self.mean_ = float(np.mean(y))
        self.n_features_in_ = np.asarray(X).shape[1] if np.ndim(X) == 2 else 1
        return self

    def predict(self, X):
        if self.mean_ is None:
            raise RuntimeError("MeanBaselineRegressor is not fitted")
        n = len(X)
        return np.full(n, self.mean_, dtype=float)


def _log1p_nonneg(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    if np.any(X < 0):
        raise ValueError("log1p requires nonnegative features")
    return np.log1p(X)


def _make_feature_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            (
                "rfm",
                Pipeline(
                    steps=[
                        (
                            "log1p",
                            FunctionTransformer(_log1p_nonneg, feature_names_out="one-to-one"),
                        ),
                        ("scale", StandardScaler()),
                    ]
                ),
                list(REGRESSION_FEATURE_COLS),
            )
        ],
        remainder="drop",
    )


def build_candidate_pipelines(random_state: int = RANDOM_SEED) -> dict[str, Pipeline]:
    """Baseline + ≥3 distinct course algorithms as full pipelines."""
    pre = _make_feature_preprocessor()
    return {
        "mean_baseline": Pipeline(
            steps=[
                ("preprocess", clone(pre)),
                ("model", MeanBaselineRegressor()),
            ]
        ),
        "ridge": Pipeline(
            steps=[
                ("preprocess", clone(pre)),
                ("model", Ridge(random_state=random_state)),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                ("preprocess", clone(pre)),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=200,
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "gradient_boosting": Pipeline(
            steps=[
                ("preprocess", clone(pre)),
                (
                    "model",
                    GradientBoostingRegressor(random_state=random_state),
                ),
            ]
        ),
    }


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def cross_validate_models(
    pipelines: dict[str, Pipeline],
    X: pd.DataFrame,
    y: pd.Series,
    *,
    cv,
    scoring: tuple[str, ...] = ("neg_mean_absolute_error", "neg_root_mean_squared_error", "r2"),
) -> pd.DataFrame:
    """Training/validation CV only — do not pass the final test set here."""
    rows = []
    for name, pipe in pipelines.items():
        scores = cross_validate(
            pipe,
            X,
            y,
            cv=cv,
            scoring=list(scoring),
            n_jobs=-1,
            return_train_score=False,
        )
        row: dict[str, Any] = {"model": name}
        for key, values in scores.items():
            if key.startswith("test_"):
                metric = key.replace("test_", "")
                row[f"cv_mean_{metric}"] = float(np.mean(values))
                row[f"cv_std_{metric}"] = float(np.std(values))
        rows.append(row)
    return pd.DataFrame(rows)


DEFAULT_PARAM_GRIDS: dict[str, dict[str, list[Any]]] = {
    "ridge": {"model__alpha": [0.1, 1.0, 10.0, 100.0]},
    "random_forest": {
        "model__n_estimators": [100, 200],
        "model__max_depth": [5, 10, None],
        "model__min_samples_leaf": [1, 5],
    },
    "gradient_boosting": {
        "model__n_estimators": [100, 200],
        "model__learning_rate": [0.05, 0.1],
        "model__max_depth": [2, 3],
    },
}


def tune_model(
    pipeline: Pipeline,
    param_grid: dict[str, list[Any]],
    X: pd.DataFrame,
    y: pd.Series,
    *,
    cv,
    scoring: str = "neg_mean_absolute_error",
) -> GridSearchCV:
    search = GridSearchCV(
        pipeline,
        param_grid=param_grid,
        cv=cv,
        scoring=scoring,
        n_jobs=-1,
        refit=True,
    )
    search.fit(X, y)
    return search
