"""Prediction quality (project details, bilingual)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app_pages._shared import load_metadata
from app_pages.i18n import format_model_name, t
from app_pages.ui import metric_row, page_header, plain_language_note
from marketmind.config import FIGURES_DIR, PROCESSED_DATA_DIR, REPORTS_DIR

page_header(
    t("quality.title"),
    icon=":material/monitoring:",
    subtitle=t("quality.subtitle"),
    badge=t("quality.badge"),
)
plain_language_note(t("quality.note"))

meta = load_metadata()
if not meta:
    st.warning(t("overview.meta_missing"), icon=":material/warning:")
    st.stop()

currency = meta.get("currency_label", "GBP (£)")
st.info(
    title=t("quality.how_title"),
    body=t("quality.how_body", cutoff=meta["test_cutoff"]),
    icon=":material/science:",
)
with st.expander(t("quality.tech")):
    st.caption(
        f"cutoff {meta['test_cutoff']} · window {meta['target_window_days']}d · "
        "selection used training CV MAE only"
    )

tm = meta["test_metrics"]
bm = meta["baseline_test_metrics"]

metric_row(
    [
        {
            "label": t("quality.mae"),
            "value": f"{tm['mae']:,.2f}",
            "help": currency,
            "icon": ":material/straighten:",
        },
        {
            "label": t("quality.rmse"),
            "value": f"{tm['rmse']:,.2f}",
            "help": currency,
            "icon": ":material/functions:",
        },
        {
            "label": t("quality.r2"),
            "value": f"{tm['r2']:.3f}",
            "help": "R²",
            "icon": ":material/percent:",
        },
    ]
)

with st.container(border=True):
    st.subheader(t("quality.compare"), icon=":material/compare:", anchor=False)
    results = pd.DataFrame(
        [
            {
                "model": t("quality.baseline"),
                "mae": bm["mae"],
                "rmse": bm["rmse"],
                "r2": bm["r2"],
            },
            {
                "model": format_model_name(meta["selected_regression_model"]),
                "mae": tm["mae"],
                "rmse": tm["rmse"],
                "r2": tm["r2"],
            },
        ]
    )
    st.dataframe(results, width="stretch", alt="Baseline vs selected model test metrics")
    st.caption(currency)

band_path = REPORTS_DIR / "error_by_spend_band.csv"
if band_path.exists():
    with st.container(border=True):
        st.dataframe(
            pd.read_csv(band_path),
            width="stretch",
            alt="MAE by spend quartile on test set",
        )

pred_file = PROCESSED_DATA_DIR / "test_predictions.parquet"
if pred_file.exists():
    preds = pd.read_parquet(pred_file)
    with st.container(border=True):
        st.write(
            f"{preds['residual'].mean():.2f} · {preds['abs_error'].median():.2f} · n={len(preds):,}"
        )
        residual_png = FIGURES_DIR / "test_residuals.png"
        if residual_png.exists():
            st.image(
                str(residual_png),
                caption="Residuals",
                alt="Residual analysis charts for the held-out test set",
            )

with st.container(border=True):
    st.subheader(t("quality.limits"), icon=":material/gavel:", anchor=False)
    st.markdown(t("quality.limits_body", currency=currency))

with st.expander(t("quality.tech")):
    st.json(
        {
            "sklearn": meta.get("sklearn_version"),
            "pandas": meta.get("pandas_version"),
            "numpy": meta.get("numpy_version"),
            "created_at_utc": meta.get("created_at_utc"),
            "cv_mae_by_model": meta.get("cv_mae_by_model"),
            "selected_params": meta.get("selected_params"),
        }
    )
