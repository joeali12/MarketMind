"""Cached loaders for bundled demo tables (UK retail, GBP).

Clone-resilient strategy:
- Prefer full ``transactions_cleaned.parquet`` when present (local training artifact).
- Else use committed ``transactions_demo_sample.parquet`` for customer history.
- Overview / product rollups prefer ``reports/demo_store_snapshot.json`` so clone
  demos stay accurate without shipping the full ~800k-row cleaned store.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import pandas as pd
from fastapi import HTTPException

from marketmind.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, REPORTS_DIR
from marketmind.data.cleaning import eligible_positive_spend_mask
from marketmind.inference import load_artifacts

_TX_FULL = PROCESSED_DATA_DIR / "transactions_cleaned.parquet"
_TX_SAMPLE = PROCESSED_DATA_DIR / "transactions_demo_sample.parquet"
_SNAPSHOT = REPORTS_DIR / "demo_store_snapshot.json"

MISSING_TX_DETAIL = (
    "Demo transaction tables are missing. Run the cleaning pipeline to create "
    "data/processed/transactions_cleaned.parquet, or ensure the committed "
    "transactions_demo_sample.parquet and reports/demo_store_snapshot.json "
    "are present (see README)."
)


class DemoDataUnavailable(FileNotFoundError):
    """Raised when required demo tables cannot be loaded."""


def raise_demo_unavailable(exc: BaseException | None = None) -> None:
    """Convert missing demo data into a clear HTTP 503 for API callers."""
    detail = MISSING_TX_DETAIL
    if exc is not None and str(exc):
        detail = f"{MISSING_TX_DETAIL} ({exc})"
    raise HTTPException(status_code=503, detail=detail) from exc


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
    label_map = arts["metadata"].get("segment_label_map") or {}
    df["segment_label"] = df["cluster_id"].map(lambda c: label_map.get(str(c), label_map.get(c)))
    return df


@lru_cache(maxsize=1)
def segment_profiles() -> pd.DataFrame:
    return pd.read_csv(REPORTS_DIR / "segment_profiles_train.csv")


@lru_cache(maxsize=1)
def store_snapshot() -> dict[str, Any]:
    if not _SNAPSHOT.exists():
        return {}
    return json.loads(_SNAPSHOT.read_text())


@lru_cache(maxsize=1)
def transactions_cleaned() -> pd.DataFrame:
    """Load full cleaned transactions, else the committed demo sample."""
    if _TX_FULL.exists():
        return pd.read_parquet(_TX_FULL)
    if _TX_SAMPLE.exists():
        return pd.read_parquet(_TX_SAMPLE)
    raise DemoDataUnavailable(MISSING_TX_DETAIL)


def has_full_transactions() -> bool:
    return _TX_FULL.exists()


def has_transaction_source() -> bool:
    return _TX_FULL.exists() or _TX_SAMPLE.exists()


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
