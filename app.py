"""MarketMind Streamlit entrypoint — loads saved artifacts; does not retrain."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

st.set_page_config(
    page_title="MarketMind",
    page_icon=":material/storefront:",
    layout="wide",
    initial_sidebar_state="auto",
)

from app_pages.i18n import render_language_switcher, t  # noqa: E402
from app_pages.ui import inject_direction_and_motion  # noqa: E402

render_language_switcher()
inject_direction_and_motion()

home = st.Page("app_pages/home.py", title=t("nav.home"), icon=":material/home:", default=True)
upload = st.Page(
    "app_pages/data_validation.py",
    title=t("nav.validation"),
    icon=":material/upload_file:",
)
dashboard = st.Page(
    "app_pages/overview.py",
    title=t("nav.overview"),
    icon=":material/dashboard:",
)
groups = st.Page(
    "app_pages/segments.py",
    title=t("nav.groups"),
    icon=":material/groups:",
)
profile = st.Page(
    "app_pages/customer_lookup.py",
    title=t("nav.profile"),
    icon=":material/person_search:",
)
quality = st.Page(
    "app_pages/model_quality.py",
    title=t("nav.quality"),
    icon=":material/monitoring:",
)

page = st.navigation(
    {
        t("nav.section_main"): [home, upload, dashboard, groups, profile],
        t("nav.section_project"): [quality],
    }
)
page.run()
