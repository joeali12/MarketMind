"""Leakage-safe upload-store 90-day spend model (never the UK demo artifacts).

Builds chronological customer snapshots, purges training rows whose 90-day
target windows overlap the holdout cutoff, compares mean baseline vs Ridge on
the untouched final holdout, and only reports estimates when eligibility rules
pass and the candidate beats the baseline.

Target definition (must stay consistent everywhere):
  eligible spend in (cutoff, cutoff + window_days]
so target_window_end = cutoff + window_days.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from api.settings import (
    UPLOAD_FORECAST_CUTOFF_STEP_DAYS,
    UPLOAD_FORECAST_MIN_HOLDOUT_ROWS,
    UPLOAD_FORECAST_MIN_SPAN_DAYS,
    UPLOAD_FORECAST_MIN_TRAIN_ROWS,
    UPLOAD_FORECAST_REQUIRE_BEAT_BASELINE,
    UPLOAD_FORECAST_WINDOW_DAYS,
)
from api.services.upload_store import UploadSessionMeta, currency_label
from marketmind.data.cleaning import eligible_positive_spend_mask
from marketmind.features.rfm import build_rfm
from marketmind.features.target import build_customer_modeling_table

FEATS = ["recency", "frequency", "monetary"]


def eligibility_config() -> dict[str, Any]:
    return {
        "window_days": UPLOAD_FORECAST_WINDOW_DAYS,
        "min_span_days": UPLOAD_FORECAST_MIN_SPAN_DAYS,
        "min_train_rows": UPLOAD_FORECAST_MIN_TRAIN_ROWS,
        "min_holdout_rows": UPLOAD_FORECAST_MIN_HOLDOUT_ROWS,
        "cutoff_step_days": UPLOAD_FORECAST_CUTOFF_STEP_DAYS,
        "require_beat_baseline": UPLOAD_FORECAST_REQUIRE_BEAT_BASELINE,
        "features": list(FEATS),
        "baseline": "train_mean_target",
        "candidate": "StandardScaler+Ridge",
        "target_definition": "(cutoff, cutoff + window_days]",
        "train_purge_rule": (
            "cutoff < holdout_cutoff AND "
            "target_window_end (= cutoff + window_days) <= holdout_cutoff"
        ),
        "note_en": (
            "UK demo model is never used for uploads. "
            "Holdout metrics use purged training only; serving refits after the gate."
        ),
    }


def target_window_end(cutoff: pd.Timestamp, window_days: int = UPLOAD_FORECAST_WINDOW_DAYS) -> pd.Timestamp:
    """End of the closed side of (cutoff, cutoff + window_days]."""
    return pd.Timestamp(cutoff) + pd.Timedelta(days=int(window_days))


def purge_overlapping_train(
    train: pd.DataFrame,
    holdout_cutoff: pd.Timestamp,
    *,
    window_days: int = UPLOAD_FORECAST_WINDOW_DAYS,
) -> pd.DataFrame:
    """Drop training snapshots whose target window extends past the holdout cutoff.

    Required for every kept row:
      cutoff < holdout_cutoff
      target_window_end <= holdout_cutoff
    """
    if train.empty:
        return train.copy()
    holdout_cutoff = pd.Timestamp(holdout_cutoff)
    ends = train["cutoff"].map(lambda c: target_window_end(c, window_days))
    mask = (train["cutoff"] < holdout_cutoff) & (ends <= holdout_cutoff)
    return train.loc[mask].copy()


def _ridge_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=1.0, random_state=0)),
        ]
    )


def _unavailable(reason_en: str, reason_ar: str, **extra: Any) -> dict[str, Any]:
    return {
        "available": False,
        "forecast_scope": None,
        "reason_en": reason_en,
        "reason_ar": reason_ar,
        "eligibility": eligibility_config(),
        "uses_uk_demo_model": False,
        **extra,
    }


def evaluate_upload_forecast(parsed: pd.DataFrame, meta: UploadSessionMeta) -> dict[str, Any]:
    """Run chronological train/holdout evaluation with target-window purge."""
    cfg = eligibility_config()
    eligible = parsed.loc[eligible_positive_spend_mask(parsed)].copy()
    if eligible.empty or eligible["invoice_date"].isna().all():
        return _unavailable(
            "Not enough dated eligible transactions to build a 90-day forecast.",
            "مفيش معاملات مؤهلة بتاريخ كفاية لبناء توقع ٩٠ يوم.",
        )

    date_min = pd.Timestamp(eligible["invoice_date"].min())
    date_max = pd.Timestamp(eligible["invoice_date"].max())
    span_days = int((date_max - date_min).days)
    if span_days < UPLOAD_FORECAST_MIN_SPAN_DAYS:
        return _unavailable(
            (
                f"History span is {span_days} days; need at least "
                f"{UPLOAD_FORECAST_MIN_SPAN_DAYS} days for a leakage-safe "
                f"{UPLOAD_FORECAST_WINDOW_DAYS}-day train/holdout split."
            ),
            (
                f"مدى التاريخ {span_days} يوم؛ محتاج على الأقل "
                f"{UPLOAD_FORECAST_MIN_SPAN_DAYS} يوم لتقسيم تدريب/تحقق آمن من التسريب."
            ),
            history_span_days=span_days,
            date_min=str(date_min.date()),
            date_max=str(date_max.date()),
        )

    window = pd.Timedelta(days=UPLOAD_FORECAST_WINDOW_DAYS)
    step = pd.Timedelta(days=UPLOAD_FORECAST_CUTOFF_STEP_DAYS)
    first_cutoff = date_min + pd.Timedelta(days=30)
    last_cutoff = date_max - window
    if last_cutoff <= first_cutoff:
        return _unavailable(
            "Date range does not leave room for both feature history and a full 90-day target window.",
            "مدى التواريخ مش بيسيب مساحة لتاريخ الخصائص ونافذة هدف ٩٠ يوم كاملة.",
            history_span_days=span_days,
        )

    cutoffs: list[pd.Timestamp] = []
    c = first_cutoff
    while c <= last_cutoff:
        cutoffs.append(c)
        c = c + step
    if not cutoffs or cutoffs[-1] != last_cutoff:
        cutoffs.append(last_cutoff)

    tables = []
    for cutoff in cutoffs:
        try:
            table = build_customer_modeling_table(
                eligible,
                cutoff=cutoff,
                lookback_days=None,
                window_days=UPLOAD_FORECAST_WINDOW_DAYS,
            )
        except ValueError:
            continue
        if table.empty:
            continue
        table = table.copy()
        table["cutoff"] = pd.Timestamp(cutoff)
        table["target_window_end"] = target_window_end(cutoff)
        tables.append(table)

    if not tables:
        return _unavailable(
            "Could not build any leakage-safe customer snapshots for this file.",
            "مقدرناش نبني لقطات زبائن آمنة من التسريب للملف ده.",
            history_span_days=span_days,
        )

    all_rows = pd.concat(tables, ignore_index=True)
    holdout_cutoff = pd.Timestamp(all_rows["cutoff"].max())
    holdout_target_end = target_window_end(holdout_cutoff)
    holdout = all_rows[all_rows["cutoff"] == holdout_cutoff].copy()
    train_pre = all_rows[all_rows["cutoff"] < holdout_cutoff].copy()
    train_rows_before_purge = int(len(train_pre))
    train = purge_overlapping_train(train_pre, holdout_cutoff)
    purged_overlap_rows = train_rows_before_purge - int(len(train))

    if len(train) < UPLOAD_FORECAST_MIN_TRAIN_ROWS:
        return _unavailable(
            (
                f"After purging target windows that overlap the holdout cutoff, "
                f"only {len(train)} training snapshots remain "
                f"(removed {purged_overlap_rows} overlapping); need at least "
                f"{UPLOAD_FORECAST_MIN_TRAIN_ROWS}."
            ),
            (
                f"بعد استبعاد نوافذ الهدف المتداخلة مع حد التحقق، "
                f"فاضل {len(train)} لقطة تدريب فقط "
                f"(اتشال {purged_overlap_rows})؛ محتاج على الأقل "
                f"{UPLOAD_FORECAST_MIN_TRAIN_ROWS}."
            ),
            history_span_days=span_days,
            train_rows=int(len(train)),
            train_rows_before_purge=train_rows_before_purge,
            purged_overlap_rows=purged_overlap_rows,
            holdout_rows=int(len(holdout)),
            holdout_cutoff=str(holdout_cutoff.date()),
            holdout_target_window_end=str(holdout_target_end.date()),
        )
    if len(holdout) < UPLOAD_FORECAST_MIN_HOLDOUT_ROWS:
        return _unavailable(
            (
                f"Only {len(holdout)} holdout snapshots; need at least "
                f"{UPLOAD_FORECAST_MIN_HOLDOUT_ROWS}."
            ),
            (
                f"فيه {len(holdout)} لقطة تحقق فقط؛ محتاج على الأقل "
                f"{UPLOAD_FORECAST_MIN_HOLDOUT_ROWS}."
            ),
            history_span_days=span_days,
            train_rows=int(len(train)),
            train_rows_before_purge=train_rows_before_purge,
            purged_overlap_rows=purged_overlap_rows,
            holdout_rows=int(len(holdout)),
            holdout_cutoff=str(holdout_cutoff.date()),
            holdout_target_window_end=str(holdout_target_end.date()),
        )

    # Evaluation fit: purged training only. Metrics never use the serving refit.
    X_train = train[FEATS]
    y_train = train["target_spend_90d"].astype(float)
    X_hold = holdout[FEATS]
    y_hold = holdout["target_spend_90d"].astype(float)

    baseline_value = float(y_train.mean())
    baseline_pred = np.full(len(y_hold), baseline_value)
    baseline_mae = float(mean_absolute_error(y_hold, baseline_pred))
    baseline_rmse = float(np.sqrt(mean_squared_error(y_hold, baseline_pred)))

    eval_pipe = _ridge_pipeline()
    eval_pipe.fit(X_train, y_train)
    cand_pred = eval_pipe.predict(X_hold)
    cand_mae = float(mean_absolute_error(y_hold, cand_pred))
    cand_rmse = float(np.sqrt(mean_squared_error(y_hold, cand_pred)))
    cand_r2 = float(r2_score(y_hold, cand_pred)) if len(y_hold) > 1 else float("nan")

    beats = cand_mae < baseline_mae
    metrics = {
        "baseline_mae": baseline_mae,
        "baseline_rmse": baseline_rmse,
        "candidate_mae": cand_mae,
        "candidate_rmse": cand_rmse,
        "candidate_r2": cand_r2,
        "beats_baseline": beats,
        "evaluation_fit": "purged_train_only",
        "serving_fit": None,
    }
    split_meta = {
        "history_span_days": span_days,
        "date_min": str(date_min.date()),
        "date_max": str(date_max.date()),
        "train_rows": int(len(train)),
        "train_rows_before_purge": train_rows_before_purge,
        "purged_overlap_rows": purged_overlap_rows,
        "holdout_rows": int(len(holdout)),
        "holdout_cutoff": str(holdout_cutoff.date()),
        "holdout_target_window_end": str(holdout_target_end.date()),
        "latest_train_cutoff": str(pd.Timestamp(train["cutoff"].max()).date()),
        "latest_train_target_window_end": str(
            pd.Timestamp(train["target_window_end"].max()).date()
        ),
        "metrics": metrics,
    }

    if UPLOAD_FORECAST_REQUIRE_BEAT_BASELINE and not beats:
        return _unavailable(
            (
                f"Candidate MAE ({cand_mae:.2f}) did not beat baseline MAE ({baseline_mae:.2f}) "
                "on the chronological holdout after target-window purge, "
                "so no store-specific estimate is shown."
            ),
            (
                f"MAE المرشح ({cand_mae:.2f}) مغلبش خط الأساس ({baseline_mae:.2f}) "
                "على التحقق الزمني بعد استبعاد التداخل، فمش هنعرض تقدير خاص بالمتجر."
            ),
            **split_meta,
        )

    # Serving refit: all historically complete snapshots AFTER the holdout gate.
    # Distinct from eval_pipe — holdout metrics above must not be recomputed from this.
    serving_pipe = _ridge_pipeline()
    serving_pipe.fit(all_rows[FEATS], all_rows["target_spend_90d"].astype(float))
    metrics["serving_fit"] = "all_observed_snapshots_after_holdout_gate"

    latest_rfm = build_rfm(eligible, cutoff=date_max, lookback_days=None)

    return {
        "available": True,
        "forecast_scope": "upload_store_chronological",
        "uses_uk_demo_model": False,
        "currency_code": meta.currency_code or "UNSPECIFIED",
        "currency_label": currency_label(meta),
        "label_en": (
            f"Store-specific 90-day eligible-spend estimate ({currency_label(meta)}). "
            "Holdout MAE uses training snapshots whose target windows end on or before "
            "the holdout cutoff (target-window purge). Serving model is refit afterward — "
            "not a guarantee."
        ),
        "label_ar": (
            f"تقدير مصروف مؤهل ٩٠ يوم خاص بالمتجر ({currency_label(meta)}). "
            "MAE التحقق من لقطات تدريب نوافذ هدفها بتنتهي عند أو قبل حد التحقق "
            "(استبعاد التداخل). موديل العرض بيتدرّب بعد كده — مش ضمان."
        ),
        "eligibility": cfg,
        **{k: v for k, v in split_meta.items() if k != "metrics"},
        "metrics": metrics,
        "limitations_en": (
            "Features use only data on or before each cutoff. "
            f"Targets are eligible spend in (cutoff, cutoff + {UPLOAD_FORECAST_WINDOW_DAYS} days]. "
            "Training rows whose target window overlaps the holdout cutoff are purged before "
            "metric calculation. The serving model is a separate post-gate refit on all "
            "observed snapshots. This upload only; no FX conversion; UK demo model unused."
        ),
        "limitations_ar": (
            "الخصائص من بيانات عند أو قبل كل حد ملاحظة فقط. "
            f"الهدف هو المصروف المؤهل في (الحد، الحد + {UPLOAD_FORECAST_WINDOW_DAYS} يوم]. "
            "لقطات التدريب اللي نافذة هدفها بتتداخل مع حد التحقق بتتشال قبل حساب المقاييس. "
            "موديل العرض إعادة تدريب منفصلة بعد البوابة على كل اللقطات المرصودة. "
            "الملف المرفوع ده فقط؛ مفيش تحويل عملة؛ موديل العرض البريطاني مش مستخدم."
        ),
        "_model": serving_pipe,
        "_evaluation_model": eval_pipe,
        "_latest_rfm": latest_rfm,
    }


def predict_customers(forecast: dict[str, Any], customer_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """Serve estimates with the post-validation serving model only."""
    if not forecast.get("available"):
        return []
    model = forecast.get("_model")
    rfm = forecast.get("_latest_rfm")
    if model is None or rfm is None or rfm.empty:
        return []
    frame = rfm
    if customer_ids is not None:
        frame = rfm[rfm["customer_id"].isin(customer_ids)]
    if frame.empty:
        return []
    preds = model.predict(frame[FEATS])
    out = []
    for row, pred in zip(frame.itertuples(), preds):
        out.append(
            {
                "customer_id": int(row.customer_id),
                "predicted_spend_90d": float(max(0.0, pred)),
                "recency": float(row.recency),
                "frequency": float(row.frequency),
                "monetary": float(row.monetary),
            }
        )
    return out


def public_forecast_payload(forecast: dict[str, Any]) -> dict[str, Any]:
    """Strip in-memory model objects before JSON responses."""
    return {k: v for k, v in forecast.items() if not str(k).startswith("_")}
