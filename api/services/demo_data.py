"""Cached loaders for bundled demo tables (UK retail, GBP)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import pandas as pd

from marketmind.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, REPORTS_DIR
from marketmind.data.cleaning import eligible_positive_spend_mask
from marketmind.inference import load_artifacts


@lru_cache(maxsize=1)
def metadata() -> dict[str, Any]:
    path = ARTIFACTS_DIR / "model_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def artifacts() -> dict[str, Any]:
    return load_artifacts(ARTIFACTS_DIR)


@lru_cache(maxsize=1)
def customer_train() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DATA_DIR / "customer_train.parquet")


@lru_cache(maxsize=1)
def customer_test() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DATA_DIR / "customer_test.parquet")


@lru_cache(maxsize=1)
def customers_combined() -> pd.DataFrame:
    """Prefer test customers for lookup (aligned with demo cutoff); append train ids."""
    test = customer_test().copy()
    train = customer_train().copy()
    test["source_split"] = "test"
    train["source_split"] = "train"
    # Prefer test row when customer appears in both
    combined = pd.concat([test, train], ignore_index=True)
    combined = combined.drop_duplicates(subset=["customer_id"], keep="first")
    return combined


@lru_cache(maxsize=1)
def customers_with_segments() -> pd.DataFrame:
    arts = artifacts()
    df = customers_combined().copy()
    X = df[["recency", "frequency", "monetary"]]
    df["cluster_id"] = arts["segmentation"].predict(X).astype(int)
    label_map = (arts["metadata"].get("segment_label_map") or {})
    df["segment_label"] = df["cluster_id"].map(lambda c: label_map.get(str(c), label_map.get(c)))
    return df


@lru_cache(maxsize=1)
def segment_profiles() -> pd.DataFrame:
    return pd.read_csv(REPORTS_DIR / "segment_profiles_train.csv")


@lru_cache(maxsize=1)
def transactions_cleaned() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DATA_DIR / "transactions_cleaned.parquet")


@lru_cache(maxsize=1)
def eda_insights() -> dict[str, Any]:
    path = REPORTS_DIR / "eda_insights.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def quality_summary() -> dict[str, Any]:
    path = REPORTS_DIR / "raw_quality_summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def reconciliation() -> pd.DataFrame | None:
    path = REPORTS_DIR / "cleaning_reconciliation.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


@lru_cache(maxsize=1)
def test_metrics() -> dict[str, Any]:
    path = REPORTS_DIR / "test_metrics.json"
    if not path.exists():
        return metadata().get("test_metrics") or {}
    return json.loads(path.read_text())


def eligible_tx() -> pd.DataFrame:
    tx = transactions_cleaned()
    return tx.loc[eligible_positive_spend_mask(tx)].copy()
