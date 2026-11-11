"""Historical product ranking for the bundled UK sample."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app_pages._shared import load_store_snapshot
from app_pages.i18n import t
from app_pages.ui import page_header

page_header(
    t("products.title"),
    icon=":material/inventory_2:",
    subtitle=t("products.subtitle"),
)
st.caption(t("products.no_category"))

snap = load_store_snapshot()
products = pd.DataFrame(snap.get("products") or [])
if products.empty:
    st.error(
        title="Product table missing",
        body="reports/demo_store_snapshot.json is not in this deployment.",
        icon=":material/error:",
    )
    st.stop()

show = products.rename(
    columns={
        "stock_code": "Code",
        "description": "Product",
        "quantity": "Units",
        "orders": "Orders",
        "spend_gbp": "GBP",
    }
)
st.dataframe(
    show[["Code", "Product", "Units", "Orders", "GBP"]],
    hide_index=True,
    width="stretch",
)
