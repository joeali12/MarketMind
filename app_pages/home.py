"""Store overview for the bundled UK sample. Landing page of the public app."""

from __future__ import annotations

import json

import streamlit as st

from app_pages._shared import load_store_snapshot
from app_pages.i18n import t
from app_pages.ui import render_stitch_dashboard
from marketmind.config import REPORTS_DIR

snap = load_store_snapshot()
metrics = snap.get("metrics") or {}

st.title(t("home.title"))
st.caption(t("home.subtitle"))

if not metrics:
    st.error(
        title="Store snapshot missing",
        body="reports/demo_store_snapshot.json is not in this deployment.",
        icon=":material/error:",
    )
    st.stop()

eda_path = REPORTS_DIR / "eda_insights.json"
eda = json.loads(eda_path.read_text()) if eda_path.exists() else {}
render_stitch_dashboard(snap, eda)
