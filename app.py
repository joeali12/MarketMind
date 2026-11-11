"""MarketMind public entry. Streamlit Community Cloud runs this file, not the Next.js app."""

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
    initial_sidebar_state="collapsed",
)

from app_pages.i18n import render_language_switcher, t  # noqa: E402
from app_pages.ui import inject_direction_and_motion  # noqa: E402

inject_direction_and_motion()

store = st.Page("app_pages/home.py", title=t("nav.home"), icon=":material/dashboard:", default=True)
upload = st.Page("app_pages/data_validation.py", title=t("nav.validation"), icon=":material/upload_file:")
overview = st.Page("app_pages/overview.py", title=t("nav.overview"), icon=":material/summarize:")
products = st.Page("app_pages/products.py", title=t("nav.products"), icon=":material/inventory_2:")
groups = st.Page("app_pages/segments.py", title=t("nav.groups"), icon=":material/groups:")
profile = st.Page("app_pages/customer_lookup.py", title=t("nav.profile"), icon=":material/person_search:")
project = st.Page("app_pages/model_quality.py", title=t("nav.quality"), icon=":material/monitoring:")

page = st.navigation(
    [store, upload, overview, products, groups, profile, project],
    position="hidden",
)

brand, nav, lang = st.columns([1.3, 5.2, 1.3], vertical_alignment="center")
with brand:
    st.markdown("**MarketMind**")
with nav:
    with st.container(horizontal=True, gap="small"):
        st.page_link(store, label=t("nav.home"))
        st.page_link(upload, label=t("nav.validation"))
        st.page_link(overview, label=t("nav.overview"))
        st.page_link(products, label=t("nav.products"))
        st.page_link(groups, label=t("nav.groups"))
        st.page_link(profile, label=t("nav.profile"))
        st.page_link(project, label=t("nav.quality"))
with lang:
    render_language_switcher()

page.run()
