"""Upload-store 90-day forecast: target-window purge and leakage-safe evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api.services import upload_forecast
from api.services.upload_store import UploadSessionMeta
from api.settings import (
    UPLOAD_FORECAST_MIN_HOLDOUT_ROWS,
    UPLOAD_FORECAST_MIN_SPAN_DAYS,
    UPLOAD_FORECAST_MIN_TRAIN_ROWS,
    UPLOAD_FORECAST_WINDOW_DAYS,
)


def _meta(**kwargs) -> UploadSessionMeta:
    base = dict(
        session_id="test-forecast",
        created_at=0.0,
        filename="shop.csv",
        extension=".csv",
        byte_size=1,
        currency_code="EGP",
        date_format="dayfirst",
        date_format_confirmed=True,
    )
    base.update(kwargs)
    return UploadSessionMeta(**base)


def _synthetic_frame(*, days: int, n_customers: int = 30, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-01-01")
    rows = []
    for d in range(days):
        day = start + pd.Timedelta(days=d)
        for _ in range(3):
            cid = int(rng.integers(1, n_customers + 1))
            qty = float(rng.integers(1, 5))
            price = float(rng.uniform(10, 80))
            rows.append(
                {
                    "invoice": f"INV-{d}-{cid}-{len(rows)}",
                    "invoice_date": day,
                    "customer_id": float(cid),
                    "stock_code": f"SKU{cid % 7}",
                    "description": "item",
                    "quantity": qty,
                    "unit_price": price,
                    "line_amount": qty * price,
                    "is_cancellation": False,
                    "country": "Egypt",
                }
            )
    return pd.DataFrame(rows)


def test_eligibility_config_documents_purge_rule():
    cfg = upload_forecast.eligibility_config()
    assert cfg["window_days"] == UPLOAD_FORECAST_WINDOW_DAYS
    assert cfg["min_span_days"] == UPLOAD_FORECAST_MIN_SPAN_DAYS
    assert cfg["min_train_rows"] == UPLOAD_FORECAST_MIN_TRAIN_ROWS
    assert cfg["min_holdout_rows"] == UPLOAD_FORECAST_MIN_HOLDOUT_ROWS
    assert cfg["require_beat_baseline"] is True
    assert "target_window_end" in cfg["train_purge_rule"]
    assert cfg["target_definition"] == "(cutoff, cutoff + window_days]"
    assert "UK demo" in cfg["note_en"]


def test_purge_helper_drops_overlapping_windows():
    holdout = pd.Timestamp("2025-10-02")
    rows = pd.DataFrame(
        {
            "cutoff": pd.to_datetime(
                ["2025-04-01", "2025-07-30", "2025-08-29", "2025-09-28"]
            ),
            "target_spend_90d": [1.0, 2.0, 3.0, 4.0],
        }
    )
    purged = upload_forecast.purge_overlapping_train(rows, holdout)
    # 2025-04-01 + 90d = 2025-06-30 <= holdout → keep
    # 2025-07-30 + 90d = 2025-10-28 > holdout → drop
    # 2025-08-29 + 90d and 2025-09-28 + 90d → drop
    assert list(purged["cutoff"].dt.strftime("%Y-%m-%d")) == ["2025-04-01"]
    assert upload_forecast.target_window_end(pd.Timestamp("2025-07-30")) > holdout


def test_short_history_unavailable():
    frame = _synthetic_frame(days=60, n_customers=20)
    result = upload_forecast.evaluate_upload_forecast(frame, _meta())
    assert result["available"] is False
    assert result["uses_uk_demo_model"] is False
    assert result["forecast_scope"] is None
    assert str(UPLOAD_FORECAST_MIN_SPAN_DAYS) in result["reason_en"]
    public = upload_forecast.public_forecast_payload(result)
    assert not any(str(k).startswith("_") for k in public)


def test_successful_eval_has_no_train_target_overlap():
    """Regression: every kept train target_window_end must be <= holdout_cutoff."""
    frame = _synthetic_frame(days=500, n_customers=50, seed=3)
    result = upload_forecast.evaluate_upload_forecast(frame, _meta())
    assert "train_rows_before_purge" in result
    holdout_cutoff = pd.Timestamp(result["holdout_cutoff"])
    latest_train_end = pd.Timestamp(result["latest_train_target_window_end"])
    assert latest_train_end <= holdout_cutoff
    assert pd.Timestamp(result["latest_train_cutoff"]) < holdout_cutoff
    assert result["holdout_rows"] >= UPLOAD_FORECAST_MIN_HOLDOUT_ROWS
    assert result["train_rows"] == result["train_rows_before_purge"] - result["purged_overlap_rows"]
    # With 30-day cutoff steps and a 90-day window, near-holdout cutoffs purge.
    assert result["purged_overlap_rows"] > 0
    assert result["metrics"]["evaluation_fit"] == "purged_train_only"
    if result["available"]:
        assert result["train_rows"] >= UPLOAD_FORECAST_MIN_TRAIN_ROWS
        assert result["metrics"]["serving_fit"] == "all_observed_snapshots_after_holdout_gate"
        assert result["metrics"]["beats_baseline"] is True
        assert result["metrics"]["candidate_mae"] < result["metrics"]["baseline_mae"]
    else:
        assert result["metrics"]["serving_fit"] is None
        assert result.get("_model") is None


def test_holdout_is_final_cutoff_only_and_train_earlier():
    frame = _synthetic_frame(days=500, n_customers=50, seed=11)
    # Rebuild internals via evaluate path fields
    result = upload_forecast.evaluate_upload_forecast(frame, _meta())
    if not result.get("holdout_cutoff"):
        pytest.skip("no holdout formed")
    holdout_cutoff = pd.Timestamp(result["holdout_cutoff"])
    if result.get("latest_train_cutoff"):
        assert pd.Timestamp(result["latest_train_cutoff"]) < holdout_cutoff
    assert result["holdout_target_window_end"] == str(
        upload_forecast.target_window_end(holdout_cutoff).date()
    )


def test_purge_reduces_reported_train_count():
    """Fixture where overlapping snapshots exist; train_rows reflects purged set."""
    # Long enough for multiple cutoffs within 90d of the final holdout
    frame = _synthetic_frame(days=400, n_customers=40, seed=7)
    result = upload_forecast.evaluate_upload_forecast(frame, _meta())
    assert "train_rows_before_purge" in result or result["available"] is False
    if "train_rows_before_purge" not in result:
        pytest.skip("split never reached purge stage")
    assert result["train_rows_before_purge"] > result["train_rows"]
    assert result["purged_overlap_rows"] == (
        result["train_rows_before_purge"] - result["train_rows"]
    )
    if result["available"]:
        assert result["latest_train_target_window_end"] <= result["holdout_cutoff"]


def test_after_purge_insufficient_train_marks_unavailable(monkeypatch):
    """Raise min train rows so post-purge count fails the gate."""
    import api.services.upload_forecast as uf

    monkeypatch.setattr(uf, "UPLOAD_FORECAST_MIN_TRAIN_ROWS", 10_000)
    frame = _synthetic_frame(days=400, n_customers=25, seed=2)
    result = uf.evaluate_upload_forecast(frame, _meta())
    assert result["available"] is False
    assert "purging" in result["reason_en"].lower()
    assert result["train_rows"] < 10_000
    assert result["train_rows_before_purge"] >= result["train_rows"]


def test_candidate_must_beat_baseline_before_serving(monkeypatch):
    """If candidate loses on holdout, no estimate / no serving model."""
    import api.services.upload_forecast as uf

    real_mae = uf.mean_absolute_error
    calls = {"n": 0}

    def flip_candidate_worse(y_true, y_pred):
        calls["n"] += 1
        mae = float(real_mae(y_true, y_pred))
        # Call order: baseline then candidate
        if calls["n"] >= 2:
            return mae + 1e6
        return mae

    monkeypatch.setattr(uf, "mean_absolute_error", flip_candidate_worse)
    frame = _synthetic_frame(days=500, n_customers=50, seed=5)
    result = uf.evaluate_upload_forecast(frame, _meta())
    assert result["available"] is False
    assert result["metrics"]["beats_baseline"] is False
    assert result.get("_model") is None
    assert uf.predict_customers(result) == []


def test_predict_uses_serving_model_not_exposed_in_public(monkeypatch):
    """Force a win over baseline so serving refit is exercised."""
    import api.services.upload_forecast as uf

    real_mae = uf.mean_absolute_error
    calls = {"n": 0}

    def favor_candidate(y_true, y_pred):
        calls["n"] += 1
        mae = float(real_mae(y_true, y_pred))
        # Call 1 baseline, call 2 candidate — make candidate strictly better
        if calls["n"] == 1:
            return mae + 10.0
        return max(0.0, mae - 1.0)

    monkeypatch.setattr(uf, "mean_absolute_error", favor_candidate)
    frame = _synthetic_frame(days=500, n_customers=50, seed=9)
    result = uf.evaluate_upload_forecast(frame, _meta())
    assert result["available"] is True
    assert result["_model"] is not None
    assert result.get("_evaluation_model") is not None
    assert result["_model"] is not result["_evaluation_model"]
    preds = uf.predict_customers(result)
    assert preds
    # predict_customers must use _model (serving), not evaluation-only object
    assert result["metrics"]["serving_fit"] == "all_observed_snapshots_after_holdout_gate"
    public = uf.public_forecast_payload(result)
    assert "_model" not in public
    assert "_evaluation_model" not in public
    assert "_latest_rfm" not in public
    assert public["metrics"]["evaluation_fit"] == "purged_train_only"


def test_predict_empty_when_unavailable():
    result = upload_forecast._unavailable("x", "y")
    assert upload_forecast.predict_customers(result) == []
