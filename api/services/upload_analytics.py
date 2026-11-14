"""Descriptive analytics for an upload session — never the UK demo tables.

No store-specific regression forecast until a chronological train/val split
exists for that store. The bundled demo model is never applied here.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from api.services import cleaning_proposals as clean_svc
from api.services import canonical_upload
from api.services import upload_forecast
from api.services.upload_store import UploadSessionMeta, currency_label, load_meta, upload_path


def _provisional_upload_action(row: Any) -> dict[str, Any] | None:
    """Heuristic next step from upload segment label — never approved policy (D7)."""
    label = str(getattr(row, "segment_label", "") or "")
    raw = None
    if "high" in label.lower() or "recent" in label.lower():
        raw = (
            "Consider a thank-you / retention touch for recent higher-spend customers "
            "(heuristic from this upload only)."
        )
    elif "low" in label.lower() or "lapsed" in label.lower():
        raw = (
            "Consider cautious re-engagement; expected spend may be low "
            "(heuristic from this upload only)."
        )
    elif label:
        raw = f"Review this descriptive group ({label}) before spending budget."
    if not raw:
        return None
    return {
        "provisional": True,
        "label_en": "Provisional suggested action (not approved for operations)",
        "label_ar": "اقتراح إجراء مؤقت (مش معتمد للتشغيل)",
        "raw": raw,
        "segment_label": label or None,
    }


def _envelope(meta: UploadSessionMeta, **extra: Any) -> dict[str, Any]:
    return {
        "demo": False,
        "source": "upload",
        "session_id": meta.session_id,
        "filename": meta.filename,
        "currency_code": meta.currency_code or "UNSPECIFIED",
        "currency_label": currency_label(meta),
        "currency_selected": bool(
            meta.currency_code and meta.currency_code not in {"UNSPECIFIED", None}
        ),
        "date_format": meta.date_format,
        "date_format_confirmed": meta.date_format_confirmed,
        "has_category_mapped": meta.has_category_mapped,
        "category_column": meta.category_column,
        "mapping_confirmed": bool(meta.mapping_confirmed),
        "selected_sheet": meta.selected_sheet,
        "forecast_scope": None,
        "forecast_available": False,
        **extra,
    }


def load_parsed_frame(meta: UploadSessionMeta, *, nrows: int | None = 100_000) -> pd.DataFrame:
    return canonical_upload.load_canonical_frame(meta, nrows=nrows, require_mapping=True)


def require_analysis_ready(meta: UploadSessionMeta) -> None:
    """Block silent analysis when sheet/mapping/date/currency gates are unmet."""
    if canonical_upload.needs_sheet_selection(meta):
        raise ValueError(
            "Select which Excel worksheet contains the sales rows before analysing this file."
        )
    validation = canonical_upload.validate_for_upload(meta)
    if validation.get("needs_user_mapping") and not validation.get("mapping_confirmed"):
        raise ValueError(
            "Confirm column mapping for this file before analysing."
        )
    if not validation.get("ok"):
        raise ValueError(validation.get("message") or "Upload mapping is incomplete.")
    amb = validation.get("date_format") or {}
    if amb.get("needs_confirmation") and not meta.date_format_confirmed:
        raise ValueError(
            "Confirm the invoice date format on the Upload page before analysing this file."
        )
    if not meta.currency_code or meta.currency_code == "UNSPECIFIED":
        # Allow only when an explicit single currency column already seeded the code
        raise ValueError(
            "Select the currency for monetary amounts before analysing this file."
        )
    if validation.get("multi_currency") and not meta.analysis_currency_filter:
        codes = validation.get("discovered_currencies") or []
        raise ValueError(
            "This file has multiple currencies ("
            + ", ".join(codes)
            + "). Choose one currency for totals — no hidden FX conversion."
        )


def overview(meta: UploadSessionMeta) -> dict[str, Any]:
    require_analysis_ready(meta)
    parsed = load_parsed_frame(meta)
    eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)]
    has_invoice = bool(
        meta.column_mapping and meta.column_mapping.get("invoice")
    ) or ("invoice" in parsed.columns and not parsed["invoice"].astype(str).str.startswith("ROW-").all())
    # Detect synthetic ROW-* invoices from unmapped invoice field
    real_invoices = ~parsed["invoice"].astype(str).str.match(r"^ROW-", na=False)
    order_available = bool(real_invoices.any())
    orders = (
        int(
            eligible.loc[
                real_invoices.reindex(eligible.index).fillna(False), "invoice"
            ].nunique()
        )
        if order_available
        else None
    )
    has_customer = bool(parsed["customer_id"].notna().any())
    customers = int(eligible["customer_id"].dropna().nunique()) if has_customer else 0
    sales = float(eligible["line_amount"].fillna(0).sum())
    aov = float(sales / orders) if orders else None
    if has_customer and order_available:
        inv_per = eligible.dropna(subset=["customer_id"]).groupby("customer_id")["invoice"].nunique()
        returning_share = float((inv_per > 1).mean()) if len(inv_per) else 0.0
    else:
        returning_share = None
    date_ok = bool(eligible["invoice_date"].notna().any())
    date_min = str(eligible["invoice_date"].min()) if date_ok else None
    date_max = str(eligible["invoice_date"].max()) if date_ok else None

    trend = []
    if len(eligible) and eligible["invoice_date"].notna().any():
        month = eligible.copy()
        month["month"] = month["invoice_date"].dt.to_period("M").astype(str)
        trend_df = (
            month.groupby("month")
            .agg(spend=("line_amount", "sum"), orders=("invoice", "nunique"))
            .reset_index()
            .sort_values("month")
            .tail(24)
        )
        trend = [
            {"month": r.month, "spend": float(r.spend), "orders": int(r.orders)}
            for r in trend_df.itertuples()
        ]

    rfm = _customer_rfm(eligible) if has_customer else eligible.iloc[0:0].copy()
    segments_payload = _segment_rows(rfm) if has_customer else []
    insights = _evidence_insights(
        eligible=eligible,
        trend=trend,
        rfm=rfm,
        segments=segments_payload,
        returning_share=returning_share if returning_share is not None else 0.0,
        currency=currency_label(meta),
        has_category=bool(
            (meta.has_category_mapped or (meta.column_mapping or {}).get("category"))
            and "category" in eligible.columns
        ),
        meta=meta,
    )
    if not has_customer:
        insights.insert(
            0,
            {
                "id": "no_customer_id",
                "title_en": "Customer groups unavailable",
                "title_ar": "مجموعات الزبائن مش متاحة",
                "evidence_en": (
                    "This file has no usable customer identifier. Store and product sales "
                    "totals still include anonymous lines; customer-level analytics cannot run."
                ),
                "evidence_ar": (
                    "الملف مفيهوش رقم زبون صالح. إجماليات المبيعات والمنتجات لسه محسوبة "
                    "(بما فيها المبيعات المجهولة)، لكن تحليل الزبائن مش هيشتغل."
                ),
                "caveat_en": "Map a customer/client ID column if you need groups or returning rates.",
                "caveat_ar": "اربط عمود رقم زبون/عميل لو محتاج مجموعات أو نسبة راجعين.",
            },
        )
    exclusion = dict(parsed.attrs.get("currency_exclusion") or {})
    if int(exclusion.get("blank_or_unknown_excluded") or 0) or int(
        exclusion.get("other_currency_excluded") or 0
    ):
        insights.insert(
            0,
            {
                "id": "currency_rows_excluded",
                "title_en": "Some rows are outside this currency total",
                "title_ar": "صفوف خارج إجمالي العملة دي",
                "evidence_en": exclusion.get("reason_en"),
                "evidence_ar": exclusion.get("reason_ar"),
                "caveat_en": "No exchange-rate conversion is applied.",
                "caveat_ar": "مفيش تحويل سعر صرف.",
            },
        )
    if not date_ok:
        insights.insert(
            0,
            {
                "id": "no_dates",
                "title_en": "Trends unavailable",
                "title_ar": "الاتجاهات مش متاحة",
                "evidence_en": "No usable transaction dates are mapped, so monthly trends are disabled.",
                "evidence_ar": "مفيش تواريخ معاملات مربوطة بشكل صالح، فاتجاهات الشهور متعطّلة.",
                "caveat_en": "Map and confirm a date column to enable trends.",
                "caveat_ar": "اربط وأكّد عمود التاريخ عشان الاتجاهات تشتغل.",
            },
        )
    if not order_available:
        insights.append(
            {
                "id": "no_invoice",
                "title_en": "Order counts unavailable",
                "title_ar": "عدد الطلبات مش متاح",
                "evidence_en": "No invoice/order identifier is mapped — rows are not treated as orders.",
                "evidence_ar": "مفيش رقم فاتورة/طلب مربوط — الصفوف مش بتتحسب كطلبات.",
                "caveat_en": "Map an order/invoice column to enable order counts and AOV.",
                "caveat_ar": "اربط عمود طلب/فاتورة عشان عدد الطلبات ومتوسط قيمة الطلب.",
            }
        )
    suggestions = _provisional_steps_from_insights(
        insights,
        has_category=bool(meta.has_category_mapped or (meta.column_mapping or {}).get("category")),
        segments=segments_payload,
    )
    forecast_raw = upload_forecast.evaluate_upload_forecast(parsed, meta)
    forecast = upload_forecast.public_forecast_payload(forecast_raw)
    # Segments stay available for /groups explorers but are not forced on the store hero.
    deep_dives: list[dict[str, Any]] = []
    if has_customer and segments_payload and customers >= 5:
        biggest = max(segments_payload, key=lambda s: int(s.get("n_customers") or 0))
        deep_dives.append(
            {
                "id": "customer_groups",
                "href": "/groups",
                "forced": False,
                "title_en": "Optional deep dive: descriptive customer groups",
                "title_ar": "تحليل أعمق اختياري: مجموعات زبائن وصفية",
                "why_en": (
                    f"Largest descriptive group is “{biggest.get('label_en')}” "
                    f"({biggest.get('n_customers')} customers). Open Groups only if useful — "
                    "not required to read the dashboard."
                ),
                "why_ar": (
                    f"أكبر مجموعة وصفية «{biggest.get('label_en')}» "
                    f"({biggest.get('n_customers')} زبون). افتح المجموعات لو مفيد — "
                    "مش مطلوب عشان تقرأ اللوحة."
                ),
            }
        )

    if returning_share is not None:
        meaning = {
            "en": (
                f"About {(returning_share * 100):.0f}% of customers with IDs placed more than one order "
                f"in this file (returning-customer share). This describes history in the upload only — "
                "not a causal claim."
            ),
            "ar": (
                f"حوالي {(returning_share * 100):.0f}% من الزباين اللي ليهم رقم عملوا أكتر من طلب "
                "في الملف ده (نسبة الزباين الراجعين). ده وصف للتاريخ في الرفع فقط — مش ادعاء سببية."
            ),
        }
    elif not has_customer:
        meaning = {
            "en": (
                "Customer-level analytics are unavailable because no customer ID is mapped. "
                "Store and product totals still use every eligible sales line, including anonymous ones."
            ),
            "ar": (
                "تحليل الزبائن مش متاح لأن مفيش رقم زبون مربوط. "
                "إجماليات المتجر والمنتجات لسه بتحسب كل سطور البيع المؤهلة، بما فيها المجهولة."
            ),
        }
    else:
        meaning = {
            "en": "Sales figures come from the mapped columns in this upload only.",
            "ar": "أرقام المبيعات جاية من الأعمدة المربوطة في الرفع ده فقط.",
        }

    return _envelope(
        meta,
        metrics={
            "sales": sales,
            "orders": orders,
            "customers": customers if has_customer else None,
            "average_order_value": aov,
            "returning_customer_share": returning_share,
            "date_min": date_min,
            "date_max": date_max,
            "eligible_rows": int(len(eligible)),
            "sales_gbp": sales if meta.currency_code == "GBP" else None,
            "orders_available": order_available,
            "customers_available": has_customer,
            "trends_available": date_ok,
        },
        capabilities={
            "sales_totals": True,
            "product_rankings": True,
            "date_trends": date_ok,
            "order_counts": order_available,
            "customer_groups": has_customer,
            "category_analysis": bool(
                (meta.has_category_mapped or (meta.column_mapping or {}).get("category"))
                and "category" in eligible.columns
            ),
        },
        monthly_trend=trend if date_ok else [],
        chart_units={
            "spend": currency_label(meta),
            "orders": "orders" if order_available else "unavailable",
        },
        rfm_summary=_rfm_distribution(rfm) if has_customer else {},
        # Kept for API consumers / Groups; store UI must not treat as primary.
        segment_chart=segments_payload,
        show_segment_chart_on_store=False,
        optional_deep_dives=deep_dives,
        currency_exclusion=exclusion,
        evidence_insights=insights,
        insights=[],  # demo-style factual claims unused for uploads
        what_this_may_mean=meaning,
        suggested_next_steps=suggestions,
        actions_approved=False,
        forecast=forecast,
        forecast_available=bool(forecast.get("available")),
        caveat_en=(
            "Metrics are descriptive totals from your uploaded file only. "
            f"Amounts are in {currency_label(meta)}. No FX conversion. "
            "Not the bundled UK demo sample."
        ),
        caveat_ar=(
            "الأرقام وصفية من ملفك المرفوع فقط. "
            f"المبالغ بـ {currency_label(meta)}. مفيش تحويل عملة. "
            "مش عينة العرض البريطانية."
        ),
        definitions={
            "eligible_spend_en": (
                "Eligible positive spend excludes cancellation invoices (C#### / C-…) "
                "and non-positive quantities."
            ),
            "eligible_spend_ar": (
                "المصروف المؤهل بيستبعد فواتير الإلغاء (C#### / C-…) والكميات غير الموجبة."
            ),
            "returning_customer_en": (
                "A returning customer has more than one distinct invoice in this file."
            ),
            "returning_customer_ar": (
                "الزبون الراجع عنده أكتر من فاتورة مميزة في الملف ده."
            ),
        },
    )


def _segment_rows(rfm: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if rfm.empty:
        return rows
    total_spend = float(rfm["monetary"].sum()) or 1.0
    for label, part in rfm.groupby("segment_label"):
        rows.append(
            {
                "cluster_id": int(part["cluster_id"].iloc[0]),
                "label_en": str(label),
                "n_customers": int(len(part)),
                "share": float(len(part) / len(rfm)),
                "spend_share": float(part["monetary"].sum() / total_spend),
                "recency_mean": float(part["recency"].mean()),
                "frequency_mean": float(part["frequency"].mean()),
                "monetary_mean": float(part["monetary"].mean()),
                "monetary_median": float(part["monetary"].median()),
                "monetary_sum": float(part["monetary"].sum()),
            }
        )
    return rows


def _rfm_distribution(rfm: pd.DataFrame) -> dict[str, Any]:
    if rfm.empty:
        return {"available": False}
    return {
        "available": True,
        "n_customers": int(len(rfm)),
        "recency": {
            "median": float(rfm["recency"].median()),
            "p25": float(rfm["recency"].quantile(0.25)),
            "p75": float(rfm["recency"].quantile(0.75)),
        },
        "frequency": {
            "median": float(rfm["frequency"].median()),
            "p25": float(rfm["frequency"].quantile(0.25)),
            "p75": float(rfm["frequency"].quantile(0.75)),
        },
        "monetary": {
            "median": float(rfm["monetary"].median()),
            "p25": float(rfm["monetary"].quantile(0.25)),
            "p75": float(rfm["monetary"].quantile(0.75)),
            "top10_share": float(
                rfm.sort_values("monetary", ascending=False).head(max(1, len(rfm) // 10))[
                    "monetary"
                ].sum()
                / (float(rfm["monetary"].sum()) or 1.0)
            ),
        },
    }


def _evidence_insights(
    *,
    eligible: pd.DataFrame,
    trend: list[dict[str, Any]],
    rfm: pd.DataFrame,
    segments: list[dict[str, Any]],
    returning_share: float,
    currency: str,
    has_category: bool,
    meta: UploadSessionMeta,
) -> list[dict[str, Any]]:
    """Evidence-based insights with supporting numbers — no causal claims."""
    out: list[dict[str, Any]] = []

    # Month-over-month only when >= 3 periods
    if len(trend) >= 3:
        a, b = trend[-2], trend[-1]
        spend_a, spend_b = float(a["spend"]), float(b["spend"])
        if spend_a > 0:
            pct = (spend_b - spend_a) / spend_a * 100
            out.append(
                {
                    "id": "mom_spend",
                    "title_en": "Latest month vs previous month (eligible spend)",
                    "title_ar": "آخر شهر مقابل الشهر اللي قبله (مصروف مؤهل)",
                    "evidence_en": (
                        f"{a['month']}: {spend_a:.0f} {currency} → {b['month']}: {spend_b:.0f} {currency} "
                        f"({pct:+.1f}%). Orders {a['orders']} → {b['orders']}."
                    ),
                    "evidence_ar": (
                        f"{a['month']}: {spend_a:.0f} {currency} ← {b['month']}: {spend_b:.0f} {currency} "
                        f"({pct:+.1f}%). الطلبات {a['orders']} ← {b['orders']}."
                    ),
                    "supporting": {
                        "from_month": a["month"],
                        "to_month": b["month"],
                        "spend_from": spend_a,
                        "spend_to": spend_b,
                        "pct_change": pct,
                    },
                    "caveat_en": "Two months only — not a long-term trend claim.",
                    "caveat_ar": "شهرين بس — مش ادعاء اتجاه طويل.",
                }
            )
    elif trend:
        out.append(
            {
                "id": "trend_insufficient",
                "title_en": "Not enough monthly periods for a change comparison",
                "title_ar": "فترات شهرية مش كفاية لمقارنة التغيّر",
                "evidence_en": f"Only {len(trend)} month(s) with eligible spend in this file.",
                "evidence_ar": f"فيه {len(trend)} شهر فقط بمصروف مؤهل في الملف ده.",
                "supporting": {"months": len(trend)},
                "caveat_en": "Need at least 3 months to show month-over-month change here.",
                "caveat_ar": "محتاجين ٣ شهور على الأقل عشان نعرض تغيّر شهر عن شهر هنا.",
            }
        )

    if not rfm.empty:
        dist = _rfm_distribution(rfm)
        out.append(
            {
                "id": "returning_share",
                "title_en": "Returning-customer share",
                "title_ar": "نسبة الزباين الراجعين",
                "evidence_en": (
                    f"{returning_share:.0%} of customers with IDs have more than one invoice "
                    f"(n={dist['n_customers']})."
                ),
                "evidence_ar": (
                    f"{returning_share:.0%} من الزباين اللي ليهم رقم عندهم أكتر من فاتورة "
                    f"(n={dist['n_customers']})."
                ),
                "supporting": {"returning_share": returning_share, "n_customers": dist["n_customers"]},
                "caveat_en": "Describes this file only — not why customers return.",
                "caveat_ar": "وصف للملف ده فقط — مش تفسير ليه بيرجعوا.",
            }
        )
        top_share = dist["monetary"]["top10_share"]
        out.append(
            {
                "id": "spend_concentration",
                "title_en": "Customer spend concentration",
                "title_ar": "تركّز مصروف الزباين",
                "evidence_en": (
                    f"The top ~10% of customers by spend account for {top_share:.0%} of eligible spend "
                    f"(median customer spend {dist['monetary']['median']:.0f} {currency})."
                ),
                "evidence_ar": (
                    f"أعلى حوالي ١٠٪ من الزباين بالمصروف بيمثلوا {top_share:.0%} من المصروف المؤهل "
                    f"(وسيط مصروف الزبون {dist['monetary']['median']:.0f} {currency})."
                ),
                "supporting": {
                    "top10_spend_share": top_share,
                    "median_monetary": dist["monetary"]["median"],
                },
                "caveat_en": "Concentration statistic only — not a recommendation by itself.",
                "caveat_ar": "إحصائية تركّز فقط — مش توصية لوحدها.",
            }
        )

    if segments:
        biggest = max(segments, key=lambda s: s["n_customers"])
        out.append(
            {
                "id": "largest_group",
                "title_en": "Largest customer group in this file",
                "title_ar": "أكبر مجموعة زباين في الملف",
                "evidence_en": (
                    f"“{biggest['label_en']}” has {biggest['n_customers']} customers "
                    f"({biggest['share']:.0%} of customers, {biggest['spend_share']:.0%} of spend)."
                ),
                "evidence_ar": (
                    f"«{biggest['label_en']}» فيها {biggest['n_customers']} زبون "
                    f"({biggest['share']:.0%} من الزباين، {biggest['spend_share']:.0%} من المصروف)."
                ),
                "supporting": biggest,
                "caveat_en": "Groups are descriptive RFM median splits for this upload — not the UK demo model.",
                "caveat_ar": "المجموعات تقسيمات وصفية من متوسطات RFM للرفع ده — مش موديل العرض البريطاني.",
            }
        )

    if has_category and "category" in eligible.columns:
        cat = (
            eligible.groupby("category", dropna=False)["line_amount"]
            .sum()
            .sort_values(ascending=False)
        )
        if len(cat):
            top = cat.index[0]
            share = float(cat.iloc[0] / (float(cat.sum()) or 1.0))
            out.append(
                {
                    "id": "top_category",
                    "title_en": "Top mapped category by eligible spend",
                    "title_ar": "أعلى تصنيف مربوط بالمصروف المؤهل",
                    "evidence_en": (
                        f"“{top}” contributes {share:.0%} of eligible spend "
                        f"({float(cat.iloc[0]):.0f} {currency})."
                    ),
                    "evidence_ar": (
                        f"«{top}» بتمثل {share:.0%} من المصروف المؤهل "
                        f"({float(cat.iloc[0]):.0f} {currency})."
                    ),
                    "supporting": {"category": str(top), "spend_share": share, "spend": float(cat.iloc[0])},
                    "caveat_en": "Requires an explicitly mapped category column.",
                    "caveat_ar": "محتاج عمود تصنيف مربوط صراحة.",
                }
            )

    # Coverage caveat
    missing_cid = int(eligible["customer_id"].isna().sum()) if "customer_id" in eligible.columns else 0
    if missing_cid:
        out.append(
            {
                "id": "coverage_missing_cid",
                "title_en": "Customer coverage limitation",
                "title_ar": "محدودية تغطية الزباين",
                "evidence_en": (
                    f"{missing_cid} eligible lines lack a customer ID, so customer-level shares "
                    "exclude those lines."
                ),
                "evidence_ar": (
                    f"{missing_cid} سطر مؤهل من غير رقم زبون، فنِسب الزباين بتستبعد الأسطر دي."
                ),
                "supporting": {"eligible_lines_missing_customer_id": missing_cid},
                "caveat_en": "IDs are never invented.",
                "caveat_ar": "أرقام الزباين مش بتتولَّد.",
            }
        )

    return out


def _provisional_steps_from_insights(
    insights: list[dict[str, Any]],
    *,
    has_category: bool,
    segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Map evidence to senior-analyst decision briefs — actions_approved=false."""
    steps: list[dict[str, Any]] = []
    by_id = {i["id"]: i for i in insights}

    def _add(
        *,
        title_en: str,
        title_ar: str,
        evidence_en: str,
        evidence_ar: str,
        try_en: str,
        try_ar: str,
        uncertainty_en: str,
        uncertainty_ar: str,
    ) -> None:
        steps.append(
            {
                "rank": len(steps) + 1,
                "title_en": title_en,
                "title_ar": title_ar,
                "evidence_en": f"What we see: {evidence_en} Why it matters: {try_en}",
                "evidence_ar": f"اللي شايفينه: {evidence_ar} ليه يهم: {try_ar}",
                "uncertainty_en": uncertainty_en,
                "uncertainty_ar": uncertainty_ar,
            }
        )

    if "mom_spend" in by_id:
        _add(
            title_en="Decide whether last-month spend change needs an ops check",
            title_ar="قرّر لو تغيّر مصروف آخر شهر محتاج مراجعة تشغيل",
            evidence_en=by_id["mom_spend"]["evidence_en"],
            evidence_ar=by_id["mom_spend"]["evidence_ar"],
            try_en="Compare top products for those two months; look for stockouts or promo timing.",
            try_ar="قارن أعلى المنتجات في الشهرين؛ دور على نفاد مخزون أو توقيت عروض.",
            uncertainty_en="Two-month change only — not a proven trend; actions_approved=false.",
            uncertainty_ar="تغيّر شهرين فقط — مش اتجاه مثبت؛ actions_approved=false.",
        )
    if "returning_share" in by_id:
        share = float(by_id["returning_share"]["supporting"]["returning_share"])
        if share < 0.4:
            _add(
                title_en="Decide how to handle many one-time buyers",
                title_ar="قرّر إزاي تتعامل مع كثرة المشترين مرة واحدة",
                evidence_en=by_id["returning_share"]["evidence_en"],
                evidence_ar=by_id["returning_share"]["evidence_ar"],
                try_en="Sample a few one-time invoices on Profile; optional Groups deep dive if useful.",
                try_ar="اتطلع على كام فاتورة لمرة واحدة في الملف؛ مجموعات اختيارية لو مفيدة.",
                uncertainty_en="Provisional — not causal; actions_approved=false.",
                uncertainty_ar="مؤقت — مش سببية؛ actions_approved=false.",
            )
        else:
            _add(
                title_en="Protect repeat buyers that already drive this file",
                title_ar="حافظ على الزباين الراجعين اللي بيمشّوا الملف ده",
                evidence_en=by_id["returning_share"]["evidence_en"],
                evidence_ar=by_id["returning_share"]["evidence_ar"],
                try_en="List top returning customers by spend and check recent gaps in their orders.",
                try_ar="اعمل قائمة بأعلى الراجعين مصروفًا واتأكد من فجوات طلباتهم الأخيرة.",
                uncertainty_en="Descriptive only — not proof loyalty tactics will work.",
                uncertainty_ar="وصفي فقط — مش إثبات إن تكتيكات الولاء هتنجح.",
            )
    if "spend_concentration" in by_id:
        _add(
            title_en="Decide whether high-spend concentration is a risk or an opportunity",
            title_ar="قرّر لو تركّز المصروف فرصة ولا مخاطرة",
            evidence_en=by_id["spend_concentration"]["evidence_en"],
            evidence_ar=by_id["spend_concentration"]["evidence_ar"],
            try_en="Open Profile for the top spenders; confirm they are healthy accounts, not one-off spikes.",
            try_ar="افتح الملف لأعلى المصروف؛ اتأكد إنهم حسابات سليمة مش قفزات لمرة واحدة.",
            uncertainty_en="Concentration ≠ causation; provisional heuristic.",
            uncertainty_ar="التركّز مش سببية؛ اقتراح مؤقت.",
        )
    if "top_category" in by_id:
        _add(
            title_en="Lean inventory attention toward the top mapped category",
            title_ar="ركّز متابعة المخزون على أعلى تصنيف مربوط",
            evidence_en=by_id["top_category"]["evidence_en"],
            evidence_ar=by_id["top_category"]["evidence_ar"],
            try_en="Check stock and returns for that category on Products.",
            try_ar="راجع المخزون والمرتجعات للتصنيف ده في المنتجات.",
            uncertainty_en="Requires mapped categories; not a guarantee of margin.",
            uncertainty_ar="محتاج تصنيف مربوط؛ مش ضمان لهامش ربح.",
        )
    elif not has_category:
        _add(
            title_en="Optional: map Category later if you want category charts",
            title_ar="اختياري: اربط التصنيف لاحقًا لو عايز رسوم تصنيفات",
            evidence_en="No category mapping on this upload session.",
            evidence_ar="مفيش ربط تصنيف في جلسة الرفع دي.",
            try_en="Skip unless category views matter for your decisions — not required for the dashboard.",
            try_ar="تخطّى لو مش محتاج تصنيفات — مش مطلوب للوحة التحليل.",
            uncertainty_en="Optional; never invents category values.",
            uncertainty_ar="اختياري؛ مش هنخمّن قيم التصنيف.",
        )
    if segments and "largest_group" in by_id and len(steps) < 4:
        _add(
            title_en="Optional deep dive into descriptive customer groups",
            title_ar="تحليل أعمق اختياري لمجموعات الزباين الوصفية",
            evidence_en=by_id["largest_group"]["evidence_en"],
            evidence_ar=by_id["largest_group"]["evidence_ar"],
            try_en="Open Groups only if segment-style views help — the main dashboard does not require it.",
            try_ar="افتح المجموعات لو هتفيدك — اللوحة الأساسية مش محتاجاها.",
            uncertainty_en="Descriptive RFM splits for this file only — not the UK demo model.",
            uncertainty_ar="تقسيمات RFM وصفية للملف ده فقط — مش موديل العرض البريطاني.",
        )
    return steps


def _customer_rfm(eligible: pd.DataFrame) -> pd.DataFrame:
    if eligible.empty or eligible["customer_id"].dropna().empty:
        return pd.DataFrame(
            columns=["customer_id", "recency", "frequency", "monetary", "segment_label"]
        )
    anchor = eligible["invoice_date"].max()
    grouped = (
        eligible.dropna(subset=["customer_id"])
        .groupby("customer_id", as_index=False)
        .agg(
            last_purchase=("invoice_date", "max"),
            frequency=("invoice", "nunique"),
            monetary=("line_amount", "sum"),
        )
    )
    grouped["recency"] = (anchor - grouped["last_purchase"]).dt.days.astype(float)
    # Descriptive groups from this file only (medians) — not the demo k-means model
    r_med = float(grouped["recency"].median()) if len(grouped) else 0.0
    m_med = float(grouped["monetary"].median()) if len(grouped) else 0.0
    f_med = float(grouped["frequency"].median()) if len(grouped) else 0.0

    def _label(row: pd.Series) -> str:
        recent = row["recency"] <= r_med
        high_m = row["monetary"] >= m_med
        high_f = row["frequency"] >= f_med
        if recent and high_m:
            return "Recent higher-spend (upload)"
        if (not recent) and (not high_m):
            return "Quieter lower-spend (upload)"
        if high_f:
            return "More frequent (upload)"
        return "Other (upload)"

    grouped["segment_label"] = grouped.apply(_label, axis=1)
    grouped["cluster_id"] = grouped["segment_label"].astype("category").cat.codes.astype(int)
    return grouped


def segments(meta: UploadSessionMeta) -> dict[str, Any]:
    require_analysis_ready(meta)
    parsed = load_parsed_frame(meta)
    eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)]
    rfm = _customer_rfm(eligible)
    rows = _segment_rows(rfm)
    return _envelope(
        meta,
        segments=rows,
        chart_units={"spend": currency_label(meta), "customers": "customers"},
        note_en=(
            "Groups are descriptive splits from this upload's RFM medians. "
            "Not the bundled UK demo segmentation model."
        ),
        note_ar=(
            "المجموعات تقسيمات وصفية من متوسطات RFM في ملفك. "
            "مش موديل تقسيم العرض البريطاني."
        ),
    )


def segment_customers(
    meta: UploadSessionMeta, cluster_id: int, *, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    require_analysis_ready(meta)
    parsed = load_parsed_frame(meta)
    eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)]
    rfm = _customer_rfm(eligible)
    subset = rfm[rfm["cluster_id"] == cluster_id].sort_values("monetary", ascending=False)
    total = int(len(subset))
    page = subset.iloc[offset : offset + limit]
    customers = [
        {
            "customer_id": int(r.customer_id) if pd.notna(r.customer_id) else None,
            "recency": float(r.recency),
            "frequency": float(r.frequency),
            "monetary": float(r.monetary),
            "segment_label": r.segment_label,
            "source_split": "upload",
        }
        for r in page.itertuples()
    ]
    return _envelope(
        meta,
        cluster_id=cluster_id,
        total=total,
        offset=offset,
        limit=limit,
        customers=customers,
    )


def list_customers(meta: UploadSessionMeta, *, limit: int = 100, q: str | None = None) -> dict[str, Any]:
    require_analysis_ready(meta)
    parsed = load_parsed_frame(meta)
    eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)]
    rfm = _customer_rfm(eligible)
    if q:
        try:
            qid = float(q)
            rfm = rfm[rfm["customer_id"] == qid]
        except ValueError:
            rfm = rfm.iloc[0:0]
    rfm = rfm.sort_values("monetary", ascending=False).head(limit)
    return _envelope(
        meta,
        customers=[
            {
                "customer_id": int(r.customer_id),
                "recency": float(r.recency),
                "frequency": float(r.frequency),
                "monetary": float(r.monetary),
                "cluster_id": int(r.cluster_id),
                "segment_label": r.segment_label,
            }
            for r in rfm.itertuples()
        ],
    )


def customer_profile(meta: UploadSessionMeta, customer_id: int) -> dict[str, Any]:
    require_analysis_ready(meta)
    parsed = load_parsed_frame(meta)
    eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)]
    rfm = _customer_rfm(eligible)
    match = rfm[rfm["customer_id"] == float(customer_id)]
    if match.empty:
        raise FileNotFoundError("Customer not found in upload session")
    row = match.iloc[0]
    hist = eligible[eligible["customer_id"] == float(customer_id)].sort_values("invoice_date")
    products = (
        hist.groupby(["stock_code", "description"], dropna=False)
        .agg(quantity=("quantity", "sum"), spend=("line_amount", "sum"), lines=("invoice", "nunique"))
        .reset_index()
        .sort_values("spend", ascending=False)
        .head(15)
    )

    span_days = 0
    if hist["invoice_date"].notna().any():
        span_days = int((hist["invoice_date"].max() - hist["invoice_date"].min()).days)
    n_orders = int(hist["invoice"].nunique())

    forecast_raw = upload_forecast.evaluate_upload_forecast(parsed, meta)
    forecast = upload_forecast.public_forecast_payload(forecast_raw)
    estimate = None
    if forecast.get("available"):
        preds = upload_forecast.predict_customers(forecast_raw, customer_ids=[customer_id])
        if preds:
            estimate = {
                "predicted_spend_90d": preds[0]["predicted_spend_90d"],
                "currency_code": forecast.get("currency_code"),
                "currency_label": forecast.get("currency_label"),
                "forecast_scope": forecast.get("forecast_scope"),
                "label_en": forecast.get("label_en"),
                "label_ar": forecast.get("label_ar"),
                "metrics": forecast.get("metrics"),
                "limitations_en": forecast.get("limitations_en"),
                "limitations_ar": forecast.get("limitations_ar"),
                "uses_uk_demo_model": False,
            }

    return _envelope(
        meta,
        customer={
            "customer_id": customer_id,
            "recency": float(row.recency),
            "frequency": float(row.frequency),
            "monetary": float(row.monetary),
            "cluster_id": int(row.cluster_id),
            "segment_label": row.segment_label,
            "source_split": "upload",
        },
        purchase_history=[
            {
                "invoice": str(r.invoice),
                "invoice_date": str(r.invoice_date),
                "stock_code": str(r.stock_code),
                "description": None if pd.isna(r.description) else str(r.description),
                "quantity": float(r.quantity),
                "line_amount": float(r.line_amount),
            }
            for r in hist.tail(40).itertuples()
        ],
        products_bought=[
            {
                "stock_code": str(r.stock_code),
                "description": None if pd.isna(r.description) else str(r.description),
                "quantity": float(r.quantity),
                "spend": float(r.spend),
                "lines": int(r.lines),
                "historical_only": True,
            }
            for r in products.itertuples()
        ],
        estimate=estimate,
        forecast={
            **forecast,
            "customer_history_span_days": span_days,
            "customer_order_count": n_orders,
        },
        suggested_action=_provisional_upload_action(row),
        actions_approved=False,
    )


def product_leaders(meta: UploadSessionMeta, *, top_n: int = 5) -> dict[str, Any]:
    """Deterministic top products by units and by eligible spend (upload only)."""
    require_analysis_ready(meta)
    parsed = load_parsed_frame(meta)
    # Use upload eligibility so line-total files (no unit_price) still rank products.
    eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)].copy()
    if eligible.empty:
        return {
            "available": False,
            "currency_code": meta.currency_code or "UNSPECIFIED",
            "by_units": [],
            "by_revenue": [],
            "top_by_units": None,
            "top_by_revenue": None,
            "measure_note_en": "No eligible positive-spend lines after cleaning rules.",
            "measure_note_ar": "مفيش سطور مصروف مؤهل بعد قواعد التنظيف.",
        }

    by_product = (
        eligible.groupby(["stock_code", "description"], dropna=False)
        .agg(
            quantity=("quantity", "sum"),
            spend=("line_amount", "sum"),
            orders=("invoice", "nunique"),
        )
        .reset_index()
    )

    def _rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in frame.itertuples():
            name = None if pd.isna(r.description) else str(r.description).strip()
            out.append(
                {
                    "product_name": name or str(r.stock_code),
                    "quantity": float(r.quantity),
                    "spend": float(r.spend),
                    "orders": int(r.orders),
                }
            )
        return out

    by_units = _rows(by_product.sort_values("quantity", ascending=False).head(top_n))
    by_revenue = _rows(by_product.sort_values("spend", ascending=False).head(top_n))
    return {
        "available": True,
        "currency_code": meta.currency_code or "UNSPECIFIED",
        "by_units": by_units,
        "by_revenue": by_revenue,
        "top_by_units": by_units[0] if by_units else None,
        "top_by_revenue": by_revenue[0] if by_revenue else None,
        "measure_note_en": (
            "Units = sum of eligible quantity; revenue = sum of eligible line spend "
            "(mapped line total, or quantity × unit price), cancellations excluded."
        ),
        "measure_note_ar": (
            "الكمية = مجموع الكمية المؤهلة؛ الإيراد = مجموع مصروف السطر المؤهل "
            "(إجمالي سطر مربوط، أو كمية × سعر)، مع استبعاد الإلغاءات."
        ),
    }


def products(meta: UploadSessionMeta, *, limit: int = 30) -> dict[str, Any]:
    require_analysis_ready(meta)
    parsed = load_parsed_frame(meta)
    eligible = parsed.loc[canonical_upload.eligible_for_upload(parsed)].copy()

    by_product = (
        eligible.groupby(["stock_code", "description"], dropna=False)
        .agg(
            quantity=("quantity", "sum"),
            spend=("line_amount", "sum"),
            orders=("invoice", "nunique"),
        )
        .reset_index()
        .sort_values("spend", ascending=False)
        .head(limit)
    )

    category_available = bool(
        meta.has_category_mapped and meta.category_column and "category" in eligible.columns
    )
    categories: list[dict[str, Any]] = []
    if category_available:
        cat_agg = (
            eligible.groupby("category", dropna=False)
            .agg(spend=("line_amount", "sum"), quantity=("quantity", "sum"), orders=("invoice", "nunique"))
            .reset_index()
            .sort_values("spend", ascending=False)
            .head(20)
        )
        categories = [
            {
                "category": None if pd.isna(r.category) else str(r.category),
                "spend": float(r.spend),
                "quantity": float(r.quantity),
                "orders": int(r.orders),
            }
            for r in cat_agg.itertuples()
        ]

    month = eligible.copy()
    month = month[month["invoice_date"].notna()]
    trend = []
    if not month.empty:
        month["month"] = month["invoice_date"].dt.to_period("M").astype(str)
        trend_df = (
            month.groupby("month")
            .agg(spend=("line_amount", "sum"), orders=("invoice", "nunique"))
            .reset_index()
            .sort_values("month")
            .tail(24)
        )
        trend = [
            {"month": r.month, "spend": float(r.spend), "orders": int(r.orders)}
            for r in trend_df.itertuples()
        ]

    return _envelope(
        meta,
        category_available=category_available,
        category_omitted_reason_en=None
        if category_available
        else (
            "Category chart needs a mapped category column on this upload. "
            "Map one on the Upload page, then reopen Products."
        ),
        category_omitted_reason_ar=None
        if category_available
        else (
            "رسم التصنيف محتاج عمود تصنيف مربوط في الرفع. "
            "اربط العمود من صفحة الرفع بعدين افتح المنتجات تاني."
        ),
        products=[
            {
                "stock_code": str(r.stock_code),
                "description": None if pd.isna(r.description) else str(r.description),
                "quantity": float(r.quantity),
                "spend": float(r.spend),
                "orders": int(r.orders),
                "note_en": "Historical lines from your upload only — not a future-need prediction",
            }
            for r in by_product.itertuples()
        ],
        monthly_trend=trend,
        categories=categories,
    )


def get_meta_or_404(session_id: str) -> UploadSessionMeta:
    try:
        return load_meta(session_id)
    except FileNotFoundError as exc:
        raise FileNotFoundError(str(exc)) from exc
