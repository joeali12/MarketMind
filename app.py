"""MarketMind public entry. Streamlit Community Cloud runs this file, not the Next.js app."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

st.set_page_config(
    page_title="MarketMind",
    page_icon=":material/storefront:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Exact Stitch product face (copied from the approved export). Academic Streamlit
# pages stay available with ?classic=1 for course checks.
if st.query_params.get("classic") != "1":
    screens = {
        "welcome": "welcome_upload_pipeline.html",
        "file": "file_understanding_setup.html",
        "cleaning": "data_cleaning_review.html",
        "store": "store_dashboard.html",
    }
    name = screens.get(st.query_params.get("screen", "welcome"), screens["welcome"])
    # Same Stitch HTML as /stitch on the API. For live uploads against the API,
    # open http://127.0.0.1:8000/ (or set MM_API_BASE). Streamlit serves the shell.
    href = f"/app/static/stitch/{name}"
    st.markdown(
        f"""
        <style>
          [data-testid="stHeader"],
          [data-testid="stToolbar"],
          [data-testid="stDecoration"],
          [data-testid="stSidebar"],
          #MainMenu {{ display: none !important; }}
          .block-container {{
            padding: 0 !important;
            max-width: 100% !important;
          }}
          html, body, .stApp {{
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            background: #f8f9ff !important;
          }}
        </style>
        <meta http-equiv="refresh" content="0; url={href}">
        """,
        unsafe_allow_html=True,
    )
    components.html(
        f"""
        <script>window.top.location.replace({href!r});</script>
        <p style="font-family:Inter,sans-serif;padding:24px">
          Opening MarketMind…
          <a href="{href}">Continue</a>
        </p>
        """,
        height=80,
    )
    st.stop()

from app_pages.i18n import t  # noqa: E402
from app_pages.ui import (  # noqa: E402
    apply_lang_query,
    inject_direction_and_motion,
    render_stitch_header,
)

apply_lang_query()
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
render_stitch_header("/" if page.url_path == "" else f"/{page.url_path}")
page.run()
