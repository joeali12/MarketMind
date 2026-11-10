"""Calm home: four clear tasks for a busy shop owner."""

from __future__ import annotations

import streamlit as st

from app_pages._shared import load_metadata, try_artifacts
from app_pages.i18n import t
from app_pages.ui import learn_more, page_header, plain_language_note

page_header(
    t("home.title"),
    icon=":material/storefront:",
    subtitle=t("home.subtitle"),
    badge=t("home.badge"),
    badge_color="primary",
)
plain_language_note(t("home.note"))

st.warning(
    title=t("home.demo_warning_title"),
    body=t("home.demo_warning_body"),
    icon=":material/info:",
)

# Four primary tasks — upload, dashboard, groups, profile
with st.container(horizontal=True, gap="medium", wrap=True):
    with st.container(border=True, height="stretch"):
        st.subheader(t("home.cta_upload_title"), icon=":material/upload_file:", anchor=False)
        st.caption(t("home.cta_upload_cap"))
        if st.button(
            t("home.cta_upload_btn"),
            type="secondary",
            icon=":material/arrow_forward:",
            key="home_upload_cta",
            width="content",
        ):
            st.switch_page("app_pages/data_validation.py")

    with st.container(border=True, height="stretch"):
        st.subheader(t("home.cta_dash_title"), icon=":material/dashboard:", anchor=False)
        st.caption(t("home.cta_dash_cap"))
        if st.button(
            t("home.cta_dash_btn"),
            type="secondary",
            icon=":material/arrow_forward:",
            key="home_dash_cta",
            width="content",
        ):
            st.switch_page("app_pages/overview.py")

    with st.container(border=True, height="stretch"):
        st.subheader(t("home.cta_groups_title"), icon=":material/groups:", anchor=False)
        st.caption(t("home.cta_groups_cap"))
        if st.button(
            t("home.cta_groups_btn"),
            type="primary",
            icon=":material/arrow_forward:",
            key="home_groups_cta",
            width="content",
        ):
            st.switch_page("app_pages/segments.py")

    with st.container(border=True, height="stretch"):
        st.subheader(t("home.cta_profile_title"), icon=":material/person_search:", anchor=False)
        st.caption(t("home.cta_profile_cap"))
        if st.button(
            t("home.cta_profile_btn"),
            type="primary",
            icon=":material/arrow_forward:",
            key="home_profile_cta",
            width="content",
        ):
            st.session_state["demo_mode"] = True
            st.switch_page("app_pages/customer_lookup.py")

with st.container(border=True):
    st.subheader(t("home.what_title"), icon=":material/query_stats:", anchor=False)
    st.caption(t("home.what_not"))

with learn_more():
    st.markdown(t("home.what_body"))
    meta = load_metadata()
    if meta:
        st.markdown(
            t(
                "home.about_period",
                start=str(meta["data"]["date_min"])[:10],
                end=str(meta["data"]["date_max"])[:10],
                currency=meta.get("currency_label", "GBP (£)"),
                days=meta.get("target_window_days", 90),
            )
        )
    st.page_link(
        "app_pages/model_quality.py",
        label=t("home.link_quality"),
        icon=":material/arrow_forward:",
    )

if try_artifacts() is None:
    st.error(
        title=t("home.artifacts_error_title"),
        body=t("home.artifacts_error_body"),
        icon=":material/error:",
    )
