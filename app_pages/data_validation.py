"""File validation (project details, bilingual)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app_pages._shared import load_metadata, load_quality_summary, load_reconciliation
from app_pages.i18n import t
from app_pages.ui import cutoff_banner, page_header, plain_language_note, primary_next_step
from marketmind.config import REQUIRED_SOURCE_COLUMNS, SOURCE_COLUMN_MAP
from marketmind.data.schema import validate_source_columns

page_header(
    t("validation.title"),
    icon=":material/fact_check:",
    subtitle=t("validation.subtitle"),
    badge=t("validation.badge"),
)
plain_language_note(t("validation.note"))

meta = load_metadata()
if meta:
    cutoff_banner(meta)

with st.container(border=True):
    st.subheader(t("validation.required"), icon=":material/table:", anchor=False)
    st.write(", ".join(SOURCE_COLUMN_MAP.values()))
    with st.expander(t("quality.tech")):
        schema_df = pd.DataFrame(
            {
                "source_column": list(SOURCE_COLUMN_MAP.values()),
                "internal_name": list(SOURCE_COLUMN_MAP.keys()),
            }
        )
        st.dataframe(schema_df, width="stretch", hide_index=True, alt="Required source columns mapping")

with st.container(border=True):
    st.subheader(t("validation.upload"), icon=":material/upload_file:", anchor=False)
    st.caption(t("validation.upload_cap"))
    uploaded = st.file_uploader(
        t("validation.file"),
        type=["csv", "xlsx"],
        accept_multiple_files=False,
    )
    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".csv"):
                raw = pd.read_csv(uploaded)
            else:
                raw = pd.read_excel(uploaded)
            result = validate_source_columns(raw.columns)
            if result.ok:
                st.success(title=t("validation.ok"), body=result.message, icon=":material/check_circle:")
                st.metric(t("validation.rows"), f"{len(raw):,}", border=True)
                if "InvoiceDate" in raw.columns:
                    parsed = pd.to_datetime(raw["InvoiceDate"], errors="coerce")
                    bad = int(parsed.isna().sum())
                    if bad:
                        st.warning(body=f"{bad:,} InvoiceDate", icon=":material/warning:")
            else:
                st.error(title=t("validation.bad"), body=result.message, icon=":material/error:")
            if result.extra_columns:
                st.caption(", ".join(result.extra_columns))
        except Exception as exc:  # noqa: BLE001
            st.error(title=t("validation.read_fail"), body=str(exc), icon=":material/error:")

with st.container(border=True):
    st.subheader(t("validation.quality"), icon=":material/analytics:", anchor=False)
    summary = load_quality_summary()
    if not summary:
        st.warning(icon=":material/warning:", body="—")
    else:
        st.write(
            f"**{summary.get('n_rows', 0):,}** · "
            f"**{summary.get('n_missing_customer_id', 0):,}** · "
            f"**{summary.get('n_cancellation_invoices_rows', 0):,}**"
        )
        with st.expander(t("quality.tech")):
            keys = [
                "n_rows",
                "date_min",
                "date_max",
                "n_distinct_customers_non_null",
                "n_missing_customer_id",
                "pct_missing_customer_id",
                "n_cancellation_invoices_rows",
                "n_negative_quantity_rows",
                "n_exact_duplicate_rows",
            ]
            st.json({k: summary[k] for k in keys if k in summary})

with st.container(border=True):
    st.subheader(t("validation.recon"), icon=":material/rule:", anchor=False)
    recon = load_reconciliation()
    if recon is None:
        st.warning(icon=":material/warning:", body="—")
    else:
        st.dataframe(recon, width="stretch", hide_index=True, alt="Cleaning reconciliation")
        with st.expander(t("quality.tech")):
            st.caption(
                "Eligible positive spend excludes cancellation invoices starting with C "
                "and non-positive quantities (D5)."
            )

st.caption(", ".join(REQUIRED_SOURCE_COLUMNS))
primary_next_step(t("validation.next"), "app_pages/overview.py", icon=":material/dashboard:")
