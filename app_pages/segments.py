"""Customer groups page (bilingual, plain language)."""

from __future__ import annotations

import json

import streamlit as st

from app_pages._shared import load_metadata, load_pca_train, load_segment_profiles, try_artifacts
from app_pages.i18n import t, translate_segment_label
from app_pages.ui import (
    learn_more,
    page_header,
    plain_language_note,
    primary_next_step,
    segment_profile_card,
)
from marketmind.config import REPORTS_DIR

page_header(
    t("groups.title"),
    icon=":material/groups:",
    subtitle=t("groups.subtitle"),
    badge=t("groups.badge"),
)
plain_language_note(t("groups.note"))

if try_artifacts() is None:
    st.stop()

meta = load_metadata()
profiles = load_segment_profiles()
pca_df = load_pca_train()
currency = (meta or {}).get("currency_label", "GBP (£)")

if meta:
    st.caption(t("groups.count_caption", n=meta.get("n_clusters")))
    rfm_def = meta.get("rfm_definitions", {})
    if rfm_def:
        with learn_more(t("groups.meaning_title")):
            st.markdown(t("groups.meaning_body"))
        with st.expander(t("groups.tech_defs")):
            st.json(rfm_def)

if profiles is not None:
    display = profiles.copy()
    label_map = (meta or {}).get("segment_label_map", {})
    if label_map:
        display["segment"] = display["cluster_id"].astype(str).map(label_map)
    else:
        display["segment"] = display["cluster_id"].map(lambda c: f"cluster {c}")

    canonical_options = display["segment"].astype(str).tolist()
    display_options = [translate_segment_label(c) for c in canonical_options]
    label_to_canonical = dict(zip(display_options, canonical_options, strict=True))

    selected_display = st.pills(
        t("groups.browse"),
        options=display_options,
        selection_mode="single",
        default=display_options[0] if display_options else None,
        help=t("groups.help_browse"),
    )
    if selected_display:
        canonical = label_to_canonical[selected_display]
        row = display.loc[display["segment"].astype(str) == canonical].iloc[0]
        segment_profile_card(row, currency)

    with st.container(border=True):
        st.subheader(t("groups.all_table"), icon=":material/table_chart:", anchor=False)
        table_view = display.copy()
        table_view["segment"] = table_view["segment"].map(translate_segment_label)
        st.dataframe(table_view, width="stretch", alt="Customer group profile table")
else:
    st.warning(
        title=t("groups.missing_title"),
        body=t("groups.missing_body"),
        icon=":material/warning:",
    )

sens_path = REPORTS_DIR / "k_sensitivity.json"
if sens_path.exists():
    with st.expander(t("groups.tech_k"), icon=":material/tune:"):
        sens = json.loads(sens_path.read_text())
        st.write(sens.get("selection_rule", ""))
        for cmp_ in sens.get("comparisons", []):
            st.markdown(
                f"**k={cmp_['k']}** · silhouette={cmp_['silhouette']:.3f} · "
                f"min size={cmp_['min_cluster_size']} · labels={cmp_.get('labels')}"
            )

if pca_df is not None:
    with st.container(border=True):
        st.subheader(t("groups.viz_title"), icon=":material/scatter_plot:", anchor=False)
        st.caption(t("groups.viz_cap"))
        chart_df = pca_df.copy()
        label_map = (meta or {}).get("segment_label_map", {})
        chart_df["segment"] = chart_df["cluster_id"].astype(str).map(
            lambda c: translate_segment_label(label_map.get(c, f"cluster {c}"))
        )
        st.scatter_chart(
            chart_df,
            x="pca_1",
            y="pca_2",
            color="segment",
            alt="Shopping-pattern map of training customers by group",
        )
        explained = meta.get("pca", {}) if meta else {}
        with st.expander(t("groups.viz_tech")):
            st.caption(
                f"Explained variance ratio: {explained.get('explained_variance_ratio')} · "
                f"sum={explained.get('explained_variance_ratio_sum')} · "
                f"{explained.get('note', '')}"
            )
else:
    st.warning(
        title=t("groups.missing_title"),
        body="PCA parquet not found.",
        icon=":material/warning:",
    )

hier_path = REPORTS_DIR / "hierarchical_comparison.json"
if hier_path.exists():
    with st.expander(t("groups.hier_tech"), icon=":material/account_tree:"):
        hier = json.loads(hier_path.read_text())
        st.write(
            f"{hier.get('algorithm')} · linkage={hier.get('linkage')} · "
            f"n={hier.get('n_rows_used')} · silhouette={hier.get('silhouette'):.3f}"
        )
        st.caption(f"Group sizes: {hier.get('cluster_sizes', {})}")

st.warning(
    title=t("groups.action_warn_title"),
    body=t("groups.action_warn_body"),
    icon=":material/warning:",
)

primary_next_step(
    t("groups.next_profile"),
    "app_pages/customer_lookup.py",
    icon=":material/person_search:",
)
