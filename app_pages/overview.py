"""Data overview (project details, bilingual)."""

from __future__ import annotations

import streamlit as st

from app_pages._shared import load_customer_tables, load_metadata, load_quality_summary
from app_pages.i18n import t
from app_pages.ui import (
    currency_caption,
    cutoff_banner,
    learn_more,
    metric_row,
    page_header,
    plain_language_note,
    primary_next_step,
)

page_header(
    t("overview.title"),
    icon=":material/dashboard:",
    subtitle=t("overview.subtitle"),
    badge=t("overview.badge"),
)
plain_language_note(t("overview.note"))

meta = load_metadata()
summary = load_quality_summary()
train_df, test_df = load_customer_tables()

if not meta:
    st.warning(t("overview.meta_missing"), icon=":material/warning:")
else:
    cutoff_banner(meta)
    metric_row(
        [
            {
                "label": t("overview.cleaned"),
                "value": f"{meta['data']['cleaned_rows']:,}",
                "icon": ":material/table_rows:",
            },
            {
                "label": t("overview.train_cust"),
                "value": f"{meta['data']['train_customers']:,}",
                "icon": ":material/group:",
            },
            {
                "label": t("overview.test_cust"),
                "value": f"{meta['data']['test_customers']:,}",
                "icon": ":material/groups:",
            },
        ]
    )

    with st.container(border=True):
        st.subheader(t("overview.dates_title"), icon=":material/calendar_month:", anchor=False)
        st.markdown(
            f"**{meta['data']['date_min']} → {meta['data']['date_max']}**  \n"
            f"Train: `{meta['train_cutoffs'][0]}` · Test: `{meta['test_cutoff']}` · "
            f"{meta['target_window_days']} days"
        )
        st.caption(currency_caption(meta))
        if meta.get("cutoff_rationale"):
            with learn_more():
                st.caption(meta["cutoff_rationale"])
        if meta.get("eligible_spend_policy"):
            st.caption(meta["eligible_spend_policy"])

if summary:
    with st.container(border=True):
        st.write(
            f"{summary.get('n_distinct_customers_non_null')} · "
            f"{summary.get('n_missing_customer_id')} · "
            f"{summary.get('n_cancellation_invoices_rows')}"
        )

if train_df is not None:
    currency = (meta or {}).get("currency_label", "")
    zero_frac = float((train_df["target_spend_90d"] == 0).mean())
    with st.container(border=True):
        st.write(
            f"**{zero_frac:.1%}** · **{train_df['target_spend_90d'].mean():.2f}** {currency}"
        )
        with st.expander(t("quality.tech")):
            st.dataframe(
                train_df[["recency", "frequency", "monetary", "target_spend_90d"]].describe().T,
                width="stretch",
                alt="Training feature and target summary statistics",
            )

if test_df is not None:
    currency = (meta or {}).get("currency_label", "")
    zero_frac_t = float((test_df["target_spend_90d"] == 0).mean())
    with st.container(border=True):
        st.write(
            f"**{zero_frac_t:.1%}** · **{test_df['target_spend_90d'].mean():.2f}** {currency}"
        )

primary_next_step(t("overview.next_groups"), "app_pages/segments.py", icon=":material/groups:")
