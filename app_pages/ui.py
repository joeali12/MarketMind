"""Shared page chrome and layout helpers for the MarketMind dashboard."""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any

import pandas as pd
import streamlit as st

from app_pages.i18n import LANG_KEY, get_lang, is_rtl, t, translate_segment_label

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
[data-testid="stSidebar"] {{ display: none; }}
[data-testid="stToolbar"] {{ display: none; }}
[data-testid="stDecoration"] {{ display: none; }}
header[data-testid="stHeader"] {{
  display: none;
}}
.stApp {{
  background: #f8f9ff;
}}
.block-container {{
  max-width: 1120px;
}}
[data-testid="stPageLink"] a {{
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-weight: 600;
  color: #13243a;
  text-decoration: none;
}}
[data-testid="stPageLink"] a:hover {{
  background: #e2dfff;
}}
[data-testid="stMetric"] {{
  border-radius: 16px;
}}
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


def apply_lang_query() -> None:
    lang = st.query_params.get("lang")
    if lang in ("ar", "en"):
        st.session_state[LANG_KEY] = lang


def _lang_href(path: str) -> str:
    return f"{path}?lang={get_lang()}"


def render_stitch_header(active_path: str) -> None:
    """Top bar matching the approved Stitch store screen."""
    items = [
        ("/", t("nav.home")),
        ("/products", t("nav.products")),
        ("/segments", t("nav.groups")),
        ("/data_validation", t("nav.validation")),
        ("/customer_lookup", t("nav.profile")),
    ]
    links = []
    for path, label in items:
        current = " aria-current=\"page\"" if path == active_path else ""
        links.append(
            f'<a class="mm-pill" href="{html.escape(_lang_href(path))}"{current}>'
            f"{html.escape(label)}</a>"
        )
    more = (
        f'<a class="mm-text" href="{html.escape(_lang_href("/overview"))}">'
        f"{html.escape(t('nav.overview'))}</a>"
        f'<a class="mm-text" href="{html.escape(_lang_href("/model_quality"))}">'
        f"{html.escape(t('nav.quality'))}</a>"
    )
    current = get_lang()
    en_cls = "mm-lang on" if current == "en" else "mm-lang"
    ar_cls = "mm-lang on" if current == "ar" else "mm-lang"
    langs = (
        f'<span class="mm-langs">'
        f'<a class="{en_cls}" href="?lang=en">EN</a>'
        f'<a class="{ar_cls}" href="?lang=ar">عربي</a>'
        f"</span>"
    )
    st.html(
        f"""
        <header class="mm-bar">
          <a class="mm-brand" href="{html.escape(_lang_href("/"))}">MarketMind</a>
          <nav class="mm-nav">{"".join(links)}</nav>
          <div class="mm-side">{more}{langs}</div>
        </header>
        <style>
          .mm-bar {{
            display: flex;
            align-items: center;
            gap: 16px;
            max-width: 1120px;
            margin: 0 auto 18px;
            padding: 10px 8px;
            flex-wrap: wrap;
          }}
          .mm-brand {{
            font-weight: 700;
            color: #0b1c30;
            text-decoration: none;
            letter-spacing: -0.03em;
            font-size: 18px;
          }}
          .mm-nav {{
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            background: #eff4ff;
            border-radius: 999px;
            padding: 6px;
          }}
          .mm-pill {{
            text-decoration: none;
            color: #464555;
            border-radius: 999px;
            padding: 8px 14px;
            font-size: 14px;
          }}
          .mm-pill[aria-current="page"] {{
            background: #213145;
            color: #eaf1ff;
            font-weight: 600;
          }}
          .mm-side {{
            margin-inline-start: auto;
            display: flex;
            gap: 14px;
            align-items: center;
          }}
          .mm-text {{
            color: #3525cd;
            text-decoration: none;
            font-size: 13px;
          }}
          .mm-langs {{
            display: flex;
            gap: 2px;
            background: #eff4ff;
            border-radius: 999px;
            padding: 3px;
          }}
          .mm-lang {{
            color: #464555;
            text-decoration: none;
            font-size: 12px;
            border-radius: 999px;
            padding: 4px 8px;
          }}
          .mm-lang.on {{
            background: #fff;
            color: #0b1c30;
            font-weight: 600;
          }}
        </style>
        """
    )


def render_stitch_dashboard(snapshot: dict, eda: dict) -> None:
    """Store dashboard cards. Figures come from the UK sample snapshot, not the Stitch mock."""
    kpis = snapshot.get("metrics") or {}
    monthly = snapshot.get("monthly_trend") or []
    products = (snapshot.get("products") or [])[:5]
    uk = float(eda.get("uk_spend_share") or 0)
    cancel = float(eda.get("cancellation_row_share") or 0)
    date_min = str(kpis.get("date_min") or "")[:10]
    date_max = str(kpis.get("date_max") or "")[:10]

    def money(value: float) -> str:
        return f"GBP {value:,.0f}"

    values = [float(row.get("spend_gbp") or 0) for row in monthly]
    peak = max(values) if values else 1
    width, height = 640, 180
    if len(values) >= 2:
        step = width / (len(values) - 1)
        coords = [
            (index * step, height - (value / peak) * (height - 16) - 8)
            for index, value in enumerate(values)
        ]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        area = f"0,{height} " + line + f" {width},{height}"
    else:
        line, area = "", ""

    product_rows = []
    for row in products:
        product_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('description') or ''))}</td>"
            f"<td>{money(float(row.get('spend_gbp') or 0))}</td>"
            f"<td>{int(row.get('quantity') or 0):,}</td>"
            "</tr>"
        )
    chart = ""
    if line:
        chart = f"""
        <svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(t('store.chart'))}">
          <polygon points="{area}" fill="#4f46e5" opacity="0.16"></polygon>
          <polyline points="{line}" fill="none" stroke="#4f46e5" stroke-width="3"></polyline>
        </svg>
        """
    st.html(
        f"""
        <section class="mm-dash">
          <p class="mm-kicker">{html.escape(t("home.badge"))}</p>
          <div class="mm-kpis">
            <article><span>{html.escape(t("store.sales"))}</span><strong>{money(float(kpis.get("sales_gbp") or 0))}</strong></article>
            <article><span>{html.escape(t("store.orders"))}</span><strong>{int(kpis.get("orders") or 0):,}</strong></article>
            <article><span>{html.escape(t("store.customers"))}</span><strong>{int(kpis.get("customers") or 0):,}</strong></article>
            <article><span>{html.escape(t("store.aov"))}</span><strong>{money(float(kpis.get("average_order_value_gbp") or 0))}</strong></article>
            <article><span>{html.escape(t("store.returning"))}</span><strong>{float(kpis.get("returning_customer_share") or 0):.1%}</strong></article>
          </div>
          <div class="mm-grid">
            <article class="mm-card">
              <h2>{html.escape(t("store.chart"))}</h2>
              <p>{html.escape(date_min)} — {html.escape(date_max)}</p>
              {chart}
            </article>
            <article class="mm-card">
              <h2>{html.escape(t("store.insights"))}</h2>
              <ul>
                <li>{html.escape(t("store.insight_1"))}</li>
                <li>{html.escape(t("store.insight_2"))}</li>
                <li>{html.escape(t("store.insight_3"))}</li>
              </ul>
              <p>{html.escape(t("store.evidence_numbers", uk=f"{uk:.1%}", cancel=f"{cancel:.1%}"))}</p>
            </article>
          </div>
          <article class="mm-card">
            <h2>{html.escape(t("store.top_products"))}</h2>
            <table>
              <tbody>{"".join(product_rows)}</tbody>
            </table>
            <p>{html.escape(t("store.caveat"))}</p>
          </article>
        </section>
        <style>
          .mm-dash {{ max-width: 1120px; margin: 0 auto; }}
          .mm-kicker {{ color: #464555; font-size: 13px; }}
          .mm-kpis {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }}
          .mm-kpis article, .mm-card {{
            background: #fff; border: 1px solid #c7c4d8; border-radius: 22px; padding: 16px 18px;
          }}
          .mm-kpis span, .mm-card p {{ color: #464555; font-size: 13px; }}
          .mm-kpis strong {{ display: block; margin-top: 8px; font-size: 22px; color: #0b1c30; }}
          .mm-grid {{ display: grid; grid-template-columns: 1.4fr 0.8fr; gap: 12px; margin-top: 12px; }}
          .mm-card {{ margin-top: 12px; }}
          .mm-card h2 {{ margin: 0 0 8px; font-size: 18px; color: #0b1c30; }}
          .mm-card svg {{ width: 100%; height: auto; }}
          .mm-card table {{ width: 100%; border-collapse: collapse; }}
          .mm-card td {{ padding: 8px 0; border-bottom: 1px solid #e7e5f2; color: #0b1c30; }}
          .mm-card td:last-child, .mm-card td:nth-child(2) {{ text-align: end; }}
          @media (max-width: 800px) {{
            .mm-kpis, .mm-grid {{ grid-template-columns: 1fr; }}
          }}
        </style>
        """
    )
