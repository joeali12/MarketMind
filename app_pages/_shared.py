"""Shared helpers for Streamlit pages."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from marketmind.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, PROJECT_ROOT, REPORTS_DIR
from marketmind.inference import ArtifactError, load_artifacts

ROOT = PROJECT_ROOT


@st.cache_resource
def get_artifacts():
    return load_artifacts(ARTIFACTS_DIR)


@st.cache_data
def load_metadata() -> dict:
    path = ARTIFACTS_DIR / "model_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@st.cache_data
def load_segment_profiles() -> pd.DataFrame | None:
    path = REPORTS_DIR / "segment_profiles_train.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


@st.cache_data
def load_pca_train() -> pd.DataFrame | None:
    path = PROCESSED_DATA_DIR / "pca_train.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


@st.cache_data
def load_customer_tables() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    train = PROCESSED_DATA_DIR / "customer_train.parquet"
    test = PROCESSED_DATA_DIR / "customer_test.parquet"
    train_df = pd.read_parquet(train) if train.exists() else None
    test_df = pd.read_parquet(test) if test.exists() else None
    return train_df, test_df


@st.cache_data
def load_quality_summary() -> dict:
    path = REPORTS_DIR / "raw_quality_summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@st.cache_data
def load_reconciliation() -> pd.DataFrame | None:
    path = REPORTS_DIR / "cleaning_reconciliation.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def show_artifact_error(exc: Exception) -> None:
    st.error(
        title="Model artifacts unavailable",
        body=(
            f"{exc}\n\n"
            "Train models first with `python scripts/train_marketmind.py`. "
            "The app never retrains silently."
        ),
    )


def try_artifacts():
    try:
        return get_artifacts()
    except ArtifactError as exc:
        show_artifact_error(exc)
        return None


@st.cache_data
def load_store_snapshot() -> dict:
    """Small demo-store figures. Does not read the raw UCI workbook."""
    path = REPORTS_DIR / "demo_store_snapshot.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())
