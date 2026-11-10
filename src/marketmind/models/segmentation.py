"""RFM segmentation: K-Means primary, hierarchical comparison, PCA viz helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from marketmind.config import RANDOM_SEED, SEGMENTATION_FEATURE_COLS


def _log1p_nonneg(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    if np.any(X < 0):
        raise ValueError("log1p transform requires nonnegative RFM inputs")
    return np.log1p(X)


def build_segmentation_pipeline(n_clusters: int, random_state: int = RANDOM_SEED) -> Pipeline:
    """Pipeline: log1p -> scale -> KMeans on RFM columns."""
    return Pipeline(
        steps=[
            (
                "preprocess",
                ColumnTransformer(
                    transformers=[
                        (
                            "rfm",
                            Pipeline(
                                steps=[
                                    (
                                        "log1p",
                                        FunctionTransformer(
                                            _log1p_nonneg, feature_names_out="one-to-one"
                                        ),
                                    ),
                                    ("scale", StandardScaler()),
                                ]
                            ),
                            list(SEGMENTATION_FEATURE_COLS),
                        )
                    ],
                    remainder="drop",
                ),
            ),
            (
                "kmeans",
                KMeans(
                    n_clusters=n_clusters,
                    random_state=random_state,
                    n_init=10,
                ),
            ),
        ]
    )


def evaluate_kmeans_k(
    rfm: pd.DataFrame,
    k_values: range | list[int],
    random_state: int = RANDOM_SEED,
) -> pd.DataFrame:
    """Elbow (inertia) and silhouette diagnostics for candidate k."""
    X = rfm.loc[:, list(SEGMENTATION_FEATURE_COLS)]
    rows = []
    for k in k_values:
        pipe = build_segmentation_pipeline(n_clusters=int(k), random_state=random_state)
        labels = pipe.fit_predict(X)
        pre = pipe.named_steps["preprocess"].transform(X)
        sil = float(silhouette_score(pre, labels)) if k > 1 and len(X) > k else float("nan")
        inertia = float(pipe.named_steps["kmeans"].inertia_)
        rows.append(
            {
                "k": int(k),
                "inertia": inertia,
                "silhouette": sil,
                "min_cluster_size": int(pd.Series(labels).value_counts().min()),
                "max_cluster_size": int(pd.Series(labels).value_counts().max()),
            }
        )
    return pd.DataFrame(rows)


def fit_kmeans_segmentation(
    rfm: pd.DataFrame,
    n_clusters: int,
    random_state: int = RANDOM_SEED,
) -> tuple[Pipeline, pd.Series]:
    pipe = build_segmentation_pipeline(n_clusters=n_clusters, random_state=random_state)
    labels = pipe.fit_predict(rfm.loc[:, list(SEGMENTATION_FEATURE_COLS)])
    return pipe, pd.Series(labels, index=rfm.index, name="cluster_id")


def hierarchical_comparison(
    rfm: pd.DataFrame,
    n_clusters: int,
    *,
    sample_size: int | None = 5000,
    linkage: str = "ward",
    random_state: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Fit agglomerative clustering on a documented sample for comparison."""
    X = rfm.loc[:, list(SEGMENTATION_FEATURE_COLS)].copy()
    sampled = False
    if sample_size is not None and len(X) > sample_size:
        X = X.sample(n=sample_size, random_state=random_state)
        sampled = True

    prep = Pipeline(
        steps=[
            (
                "log1p",
                FunctionTransformer(_log1p_nonneg, feature_names_out="one-to-one"),
            ),
            ("scale", StandardScaler()),
        ]
    )
    Xt = prep.fit_transform(X)
    model = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage)
    labels = model.fit_predict(Xt)
    sil = float(silhouette_score(Xt, labels)) if n_clusters > 1 else float("nan")
    return {
        "algorithm": "AgglomerativeClustering",
        "linkage": linkage,
        "n_clusters": n_clusters,
        "n_rows_used": int(len(X)),
        "sampled": sampled,
        "sample_size_cap": sample_size,
        "silhouette": sil,
        "cluster_sizes": pd.Series(labels).value_counts().sort_index().to_dict(),
    }


def pca_projection(
    rfm: pd.DataFrame,
    fitted_preprocess: ColumnTransformer | Pipeline,
) -> tuple[pd.DataFrame, PCA]:
    """Project preprocessed RFM to 2D for visualization; report explained variance."""
    X = rfm.loc[:, list(SEGMENTATION_FEATURE_COLS)]
    # Accept either full segmentation pipeline preprocess step or a prep pipeline
    if isinstance(fitted_preprocess, Pipeline) and "preprocess" in fitted_preprocess.named_steps:
        Xt = fitted_preprocess.named_steps["preprocess"].transform(X)
    else:
        Xt = fitted_preprocess.transform(X)
    pca = PCA(n_components=2, random_state=RANDOM_SEED)
    coords = pca.fit_transform(Xt)
    out = pd.DataFrame(
        {"pca_1": coords[:, 0], "pca_2": coords[:, 1]},
        index=rfm.index,
    )
    return out, pca


def segment_profiles(
    rfm: pd.DataFrame,
    labels: pd.Series,
) -> pd.DataFrame:
    """Mean/median RFM profiles in original units plus sizes."""
    frame = rfm.loc[:, list(SEGMENTATION_FEATURE_COLS)].copy()
    frame["cluster_id"] = labels.values
    agg = (
        frame.groupby("cluster_id")
        .agg(
            n_customers=("recency", "size"),
            recency_mean=("recency", "mean"),
            recency_median=("recency", "median"),
            frequency_mean=("frequency", "mean"),
            frequency_median=("frequency", "median"),
            monetary_mean=("monetary", "mean"),
            monetary_median=("monetary", "median"),
        )
        .reset_index()
    )
    agg["share"] = agg["n_customers"] / agg["n_customers"].sum()
    return agg
