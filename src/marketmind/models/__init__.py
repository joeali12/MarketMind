"""Model builders for segmentation and regression."""

from marketmind.models.regression import (
    MeanBaselineRegressor,
    build_candidate_pipelines,
    cross_validate_models,
    regression_metrics,
    tune_model,
)
from marketmind.models.segment_labels import derive_segment_labels, provisional_actions_for_labels
from marketmind.models.segmentation import (
    build_segmentation_pipeline,
    evaluate_kmeans_k,
    fit_kmeans_segmentation,
    hierarchical_comparison,
    pca_projection,
    segment_profiles,
)

__all__ = [
    "MeanBaselineRegressor",
    "build_candidate_pipelines",
    "build_segmentation_pipeline",
    "cross_validate_models",
    "derive_segment_labels",
    "evaluate_kmeans_k",
    "fit_kmeans_segmentation",
    "hierarchical_comparison",
    "pca_projection",
    "provisional_actions_for_labels",
    "regression_metrics",
    "segment_profiles",
    "tune_model",
]
