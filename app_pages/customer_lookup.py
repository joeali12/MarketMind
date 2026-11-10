"""Customer profile page (bilingual, plain language)."""

from __future__ import annotations

import streamlit as st

from app_pages._shared import load_customer_tables, load_metadata, try_artifacts
from app_pages.i18n import format_model_name, t, translate_action, translate_segment_label
from app_pages.ui import metric_row, page_header, plain_language_note, primary_next_step
from marketmind.inference import predict_customer

page_header(
    t("profile.title"),
    icon=":material/person_search:",
    subtitle=t("profile.subtitle"),
    badge=t("profile.badge"),
)
plain_language_note(t("profile.note"))

if st.session_state.get("demo_mode"):
    st.success(
        title=t("profile.demo_mode_title"),
        body=t("profile.demo_mode_body"),
        icon=":material/play_circle:",
    )

arts = try_artifacts()
if arts is None:
    st.stop()

meta = load_metadata()
train_df, test_df = load_customer_tables()
if train_df is None and test_df is None:
    st.error(
        title=t("profile.tables_missing_title"),
        body=t("profile.tables_missing_body"),
        icon=":material/error:",
    )
    st.stop()

with st.container(border=True):
    st.subheader(t("profile.select_title"), icon=":material/search:", anchor=False)
    # Stable codes so language switches do not reset the selected period
    source = st.segmented_control(
        t("profile.table_label"),
        options=["train", "test"],
        format_func=lambda code: t("profile.table_train") if code == "train" else t("profile.table_test"),
        default="test",
        help=t("profile.table_help"),
        key="profile_period_code",
    )
    table = train_df if source == "train" else test_df
    if table is None:
        st.error(
            title=t("profile.tables_missing_title"),
            body=t("profile.table_unavailable"),
            icon=":material/error:",
        )
        st.stop()

    cutoff_val = str(table["cutoff"].iloc[0])
    currency = (meta or {}).get("currency_label", "GBP (£)")
    window = (meta or {}).get("target_window_days", 90)
    st.caption(
        t(
            "profile.cutoff_caption",
            cutoff=cutoff_val,
            days=window,
            currency=currency,
        )
    )

    ids = table["customer_id"].astype(int).sort_values().astype(str).tolist()
    # Keep selected customer stable across language switches when possible
    prev = st.session_state.get("profile_customer_id")
    index = ids.index(prev) if prev in ids else 0
    choice = st.selectbox(
        t("profile.customer_id"),
        options=ids,
        index=index,
        help=t("profile.customer_help"),
        key="profile_customer_select",
    )
    st.session_state["profile_customer_id"] = choice

row = table.loc[table["customer_id"].astype(int) == int(choice)].iloc[0]
features = {
    "customer_id": int(choice),
    "recency": float(row["recency"]),
    "frequency": float(row["frequency"]),
    "monetary": float(row["monetary"]),
}

try:
    result = predict_customer(features, artifacts=arts)
except Exception as exc:  # noqa: BLE001
    st.error(title=t("profile.inference_failed"), body=str(exc), icon=":material/error:")
    st.stop()

with st.container(border=True):
    st.subheader(t("profile.past_title"), icon=":material/fingerprint:", anchor=False)
    metric_row(
        [
            {
                "label": t("profile.recency"),
                "value": f"{result.recency:.0f}",
                "help": t("profile.recency_help"),
                "icon": ":material/schedule:",
            },
            {
                "label": t("profile.frequency"),
                "value": f"{result.frequency:.0f}",
                "help": t("profile.frequency_help"),
                "icon": ":material/receipt_long:",
            },
            {
                "label": t("profile.monetary", currency=currency),
                "value": f"{result.monetary:,.2f}",
                "help": t("profile.monetary_help"),
                "icon": ":material/payments:",
            },
        ]
    )

with st.container(border=True):
    st.subheader(t("profile.outlook_title"), icon=":material/query_stats:", anchor=False)
    metric_row(
        [
            {
                "label": t("profile.group"),
                "value": translate_segment_label(result.segment_label)
                if result.segment_label
                else f"cluster {result.cluster_id}",
                "help": t("profile.group_help"),
                "icon": ":material/group:",
            },
            {
                "label": t("profile.pred"),
                "value": f"{result.predicted_spend_90d:,.2f} {currency}",
                "help": t("profile.pred_help"),
                "icon": ":material/trending_up:",
            },
        ]
    )
    st.caption(t("profile.pred_explain"))
    if "target_spend_90d" in row.index:
        st.caption(
            t(
                "profile.actual_compare",
                value=f"{float(row['target_spend_90d']):,.2f}",
                currency=currency,
            )
        )
        st.caption(t("profile.actual_note"))

with st.container(border=True):
    st.subheader(t("profile.action_title"), icon=":material/campaign:", anchor=False)
    actions_approved = bool((meta or {}).get("actions_approved", False))
    if not actions_approved:
        st.warning(
            title=t("profile.action_warn_title"),
            body=t("profile.action_warn_body"),
            icon=":material/warning:",
        )
    if result.suggested_action:
        st.info(translate_action(result.suggested_action), icon=":material/lightbulb:")
    else:
        st.write(t("profile.action_none"))

with st.container(border=True):
    st.subheader(t("profile.context_title"), icon=":material/info:", anchor=False)
    st.markdown(t("profile.context_body", cutoff=cutoff_val))
    st.caption(format_model_name((meta or {}).get("selected_regression_model")))

with st.expander(t("profile.manual_expander"), icon=":material/science:"):
    st.caption(t("profile.manual_cap"))
    with st.form("manual_rfm"):
        r = st.number_input(t("profile.recency"), min_value=0.0, value=30.0)
        f = st.number_input(t("profile.frequency"), min_value=0.0, value=2.0)
        m = st.number_input(t("profile.monetary", currency=currency), min_value=0.0, value=100.0)
        submitted = st.form_submit_button(t("profile.manual_predict"), type="primary")
    if submitted:
        try:
            manual = predict_customer(
                {"recency": r, "frequency": f, "monetary": m},
                artifacts=arts,
            )
            st.write(
                {
                    t("profile.group"): translate_segment_label(manual.segment_label),
                    t("profile.pred"): f"{manual.predicted_spend_90d:,.2f} {currency}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            st.error(title=t("profile.invalid_input"), body=str(exc), icon=":material/error:")

primary_next_step(
    t("profile.next_quality"),
    "app_pages/model_quality.py",
    icon=":material/monitoring:",
)
