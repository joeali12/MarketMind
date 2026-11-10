"""Shared page chrome and layout helpers for the MarketMind dashboard."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd
import streamlit as st

from app_pages.i18n import get_lang, is_rtl, t, translate_segment_label

# Calm financial palette (mirrors .streamlit/config.toml)
NAVY = "#13243A"
TEAL = "#0F5B5A"
EMERALD = "#16835D"
MUTED = "#667085"
GOLD = "#C59A3B"

EN_SANS = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
)
AR_BODY = "'Noto Sans Arabic', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
AR_DISPLAY = "'EYENAmmon', 'Noto Sans Arabic', sans-serif"


def inject_direction_and_motion() -> None:
    """LTR/RTL, typography stacks, reduced-motion. Prefer semantic selectors over private DOM."""
    direction = "rtl" if is_rtl() else "ltr"
    if is_rtl():
        font_link = (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@400;500;600&display=swap" rel="stylesheet">'
        )
        # EYENAmmon is registered via theme.fontFaces; reinforce @font-face for headings.
        type_css = f"""
@font-face {{
  font-family: 'EYENAmmon';
  src: url('/app/static/fonts/EYENAmmon-Bold.ttf') format('truetype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}}
html {{ direction: {direction}; }}
body {{
  font-family: {AR_BODY};
  font-weight: 400;
  color: {NAVY};
}}
h1, h2, h3,
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {{
  font-family: {AR_DISPLAY} !important;
  font-weight: 700 !important;
  letter-spacing: 0;
  color: {NAVY};
}}
.mm-label-highlight {{
  font-family: {AR_DISPLAY} !important;
  font-weight: 700 !important;
  color: {TEAL};
}}
"""
    else:
        font_link = ""
        type_css = f"""
html {{ direction: {direction}; }}
body {{
  font-family: {EN_SANS};
  font-weight: 400;
  color: {NAVY};
}}
h1, h2, h3,
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {{
  font-family: {EN_SANS} !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em;
  color: {NAVY};
}}
.mm-label-highlight {{
  font-family: {EN_SANS} !important;
  font-weight: 600 !important;
  color: {TEAL};
}}
"""

    st.html(
        f"""
{font_link}
<style>
{type_css}
/* Calm surfaces — no gradients / neon */
[data-testid="stMetric"] {{
  background: #FFFFFF;
}}
@media (prefers-reduced-motion: reduce) {{
  html, body {{
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }}
}}
</style>
""",
        unsafe_allow_javascript=False,
    )


def page_header(
    title: str,
    *,
    icon: str,
    subtitle: str,
    badge: str | None = None,
    badge_color: str = "primary",
) -> None:
    if badge:
        st.badge(badge, icon=":material/verified:", color=badge_color)
    st.title(title, icon=icon, anchor=False)
    st.caption(subtitle)


def plain_language_note(message: str) -> None:
    st.info(
        title=t("shared.simple_terms"),
        body=message,
        icon=":material/lightbulb:",
    )


def learn_more(label: str | None = None):
    """Optional details expander — keeps the main path short."""
    return st.expander(label or t("shared.learn_more"), icon=":material/menu_book:")


def metric_row(items: Sequence[dict[str, Any]], *, gap: str = "medium") -> None:
    with st.container(horizontal=True, gap=gap, wrap=True):
        for item in items:
            st.metric(
                item["label"],
                item["value"],
                delta=item.get("delta"),
                delta_description=item.get("delta_description"),
                help=item.get("help"),
                icon=item.get("icon"),
                border=True,
                width="stretch",
            )


def primary_next_step(label: str, page: str, *, icon: str = ":material/arrow_forward:") -> None:
    if st.button(label, type="primary", icon=icon, width="content"):
        st.switch_page(page)


def currency_caption(meta: dict | None) -> str:
    currency = (meta or {}).get("currency_label", "GBP (£)")
    return t("overview.currency_cap", currency=currency)


def cutoff_banner(meta: dict) -> None:
    st.info(
        title=t("overview.cutoff_title"),
        body=t(
            "overview.cutoff_body",
            dmin=str(meta["data"]["date_min"])[:10],
            dmax=str(meta["data"]["date_max"])[:10],
            train=meta["train_cutoffs"][0],
            test=meta["test_cutoff"],
            days=meta["target_window_days"],
        ),
        icon=":material/calendar_month:",
    )


def segment_profile_card(row: pd.Series, currency: str) -> None:
    raw_name = str(row.get("segment", f"cluster {row.get('cluster_id')}"))
    name = translate_segment_label(raw_name)
    with st.container(border=True):
        st.subheader(name, icon=":material/group:", anchor=False)
        st.caption(
            t(
                "groups.share",
                share=float(row["share"]),
                n=int(row["n_customers"]),
            )
        )
        metric_row(
            [
                {
                    "label": t("groups.metric_recency"),
                    "value": f"{float(row['recency_mean']):.0f}",
                    "help": t("groups.metric_recency_help"),
                    "icon": ":material/schedule:",
                },
                {
                    "label": t("groups.metric_frequency"),
                    "value": f"{float(row['frequency_mean']):.1f}",
                    "help": t("groups.metric_frequency_help"),
                    "icon": ":material/receipt_long:",
                },
                {
                    "label": t("groups.metric_monetary", currency=currency),
                    "value": f"{float(row['monetary_mean']):,.0f}",
                    "help": t("groups.metric_monetary_help"),
                    "icon": ":material/payments:",
                },
            ]
        )


def inject_motion_preferences() -> None:
    inject_direction_and_motion()


def lang_code() -> str:
    return get_lang()
