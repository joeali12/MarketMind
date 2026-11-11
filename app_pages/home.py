"""Store overview — the public entry, not the old task menu."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app_pages._shared import load_store_snapshot
from app_pages.i18n import t
from app_pages.ui import metric_row, page_header, plain_language_note

snap = load_store_snapshot()
metrics = snap.get("metrics") or {}

page_header(
    t("home.title"),
    icon=":material/dashboard:",
    subtitle=t("home.subtitle"),
    badge=t("home.badge"),
)
plain_language_note(t("home.note"))

if not metrics:
    st.error(
        title="Store snapshot missing",
        body="reports/demo_store_snapshot.json is not in this deployment.",
        icon=":material/error:",
    )
    st.stop()

sales = float(metrics["sales_gbp"])
aov = float(metrics["average_order_value_gbp"])
returning = float(metrics.get("returning_customer_share") or 0)

metric_row(
    [
        {"label": t("store.sales"), "value": f"GBP {sales:,.0f}"},
        {"label": t("store.orders"), "value": f"{int(metrics['orders']):,}"},
        {"label": t("store.customers"), "value": f"{int(metrics['customers']):,}"},
        {"label": t("store.aov"), "value": f"GBP {aov:,.0f}"},
    ]
)
st.caption(
    t("store.returning")
    + f": {returning:.1%} · {metrics.get('date_min', '')[:10]} → {metrics.get('date_max', '')[:10]}"
)

trend = pd.DataFrame(snap.get("monthly_trend") or [])
if not trend.empty:
    st.subheader(t("store.chart"), anchor=False)
    st.bar_chart(trend, x="month", y="spend_gbp", color="#4f46e5", height=280)

products = pd.DataFrame(snap.get("products") or []).head(6)
if not products.empty:
    st.subheader(t("store.top_products"), anchor=False)
    show = products.rename(
        columns={
            "description": "Product",
            "quantity": "Units",
            "spend_gbp": "GBP",
            "orders": "Orders",
        }
    )
    st.dataframe(
        show[["Product", "Units", "Orders", "GBP"]],
        hide_index=True,
        width="stretch",
    )
