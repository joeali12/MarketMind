"""FastAPI entrypoint for MarketMind demo analytics + upload review."""

from __future__ import annotations

import io
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.settings import (  # noqa: E402
    CURRENCY_CODE,
    CURRENCY_SYMBOL,
    DEMO_BADGE_AR,
    DEMO_BADGE_EN,
    DEMO_PROVENANCE,
    MAX_PREVIEW_ROWS,
    MAX_UPLOAD_BYTES,
    UPLOAD_TTL_SECONDS,
)
from api.services import demo_data  # noqa: E402
from api.services import cleaning_proposals as clean_svc  # noqa: E402
from api.services import upload_analytics  # noqa: E402
from api.services import upload_assistant  # noqa: E402
from api.services import upload_profile  # noqa: E402
from api.services import upload_store  # noqa: E402
from api.services import gap_fill as gap_fill_svc  # noqa: E402
from api.services import canonical_upload  # noqa: E402
from api.services import column_mapping as cmap_svc  # noqa: E402
from marketmind.data.cleaning import eligible_positive_spend_mask  # noqa: E402
from marketmind.inference import predict_customer  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("marketmind.api")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    upload_store.ensure_tmp_root()
    removed = upload_store.cleanup_expired()
    logger.info("startup upload_cleanup removed=%s", removed)
    yield


app = FastAPI(title="MarketMind API", version="0.1.0", lifespan=_lifespan)
def _cors_origins() -> list[str]:
    """Local defaults plus comma-separated ALLOWED_ORIGINS (Vercel / custom domains)."""
    import os

    base = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
        "http://127.0.0.1:8501",
        "http://localhost:8501",
        "http://127.0.0.1:8502",
        "http://localhost:8502",
        "http://127.0.0.1:8503",
        "http://localhost:8503",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]
    extra = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    # Dedupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for o in base + extra:
        if o not in seen:
            seen.add(o)
            out.append(o)
    return out


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STITCH_DIR = ROOT / "static" / "stitch"


@app.get("/")
def product_home() -> RedirectResponse:
    """Public product face: exact Stitch upload screen, backed by this API."""
    return RedirectResponse(url="/stitch/welcome_upload_pipeline.html")


if STITCH_DIR.is_dir():
    app.mount("/stitch", StaticFiles(directory=str(STITCH_DIR), html=False), name="stitch")


def _demo_envelope(**extra: Any) -> dict[str, Any]:
    return {
        "demo": True,
        "provenance": DEMO_PROVENANCE,
        "currency": CURRENCY_CODE,
        "currency_symbol": CURRENCY_SYMBOL,
        "badge_en": DEMO_BADGE_EN,
        "badge_ar": DEMO_BADGE_AR,
        "has_category_field": False,
        "forecast_scope": "demo_only",
        **extra,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    from api.settings import public_gemini_settings

    md = demo_data.metadata()
    return _demo_envelope(
        actions_approved=bool(md.get("actions_approved", False)),
        train_cutoffs=md.get("train_cutoffs"),
        test_cutoff=md.get("test_cutoff"),
        target_window_days=md.get("target_window_days", 90),
        currency_label=md.get("currency_label", "GBP (£)"),
        currency_confirmed=bool(md.get("currency_confirmed", True)),
        segment_label_map=md.get("segment_label_map") or {},
        selected_regression_model=md.get("selected_regression_model"),
        test_metrics=md.get("test_metrics") or {},
        assistant=public_gemini_settings(),
        upload_policy={
            "allowed_extensions": [".csv", ".xlsx"],
            "max_bytes": MAX_UPLOAD_BYTES,
            "max_preview_rows": MAX_PREVIEW_ROWS,
            "ttl_seconds": UPLOAD_TTL_SECONDS,
            "temp_root": "data/uploads/tmp/<session_id>/",
            "logs_file_contents": False,
            "logs_pii": False,
        },
    )


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    eda = demo_data.eda_insights()
    snap = demo_data.store_snapshot()
    metrics = dict(snap.get("metrics") or {})

    if not metrics:
        try:
            tx = demo_data.transactions_cleaned()
        except demo_data.DemoDataUnavailable as exc:
            demo_data.raise_demo_unavailable(exc)
        eligible = tx.loc[eligible_positive_spend_mask(tx)]
        orders = int(eligible["invoice"].nunique())
        customers = int(eligible["customer_id"].nunique())
        sales = float(eligible["line_amount"].sum())
        aov = float(sales / orders) if orders else 0.0
        inv_per = eligible.groupby("customer_id")["invoice"].nunique()
        returning_share = float((inv_per > 1).mean()) if len(inv_per) else 0.0
        metrics = {
            "sales_gbp": sales,
            "orders": orders,
            "customers": customers,
            "average_order_value_gbp": aov,
            "returning_customer_share": returning_share,
            "date_min": eda.get("date_min") or str(eligible["invoice_date"].min()),
            "date_max": eda.get("date_max") or str(eligible["invoice_date"].max()),
            "eligible_rows": int(len(eligible)),
        }
    else:
        # Keep EDA date bounds authoritative when present
        if eda.get("date_min"):
            metrics["date_min"] = eda["date_min"]
        if eda.get("date_max"):
            metrics["date_max"] = eda["date_max"]

    # Arabic claims are curated mirrors for the known demo insight IDs (not machine-translated invent).
    claim_ar_by_id = {
        1: "حجم المعاملات المؤهلة بيتغيّر بشكل واضح من شهر لشهر بين ٢٠٠٩–٢٠١١.",
        2: "مصروف السطر منحرف لليمين؛ جزء صغير من السطور بيمثل جزء كبير من القيمة.",
        3: "المملكة المتحدة تمثل غالبية المصروف المؤهل في العينة دي.",
        4: "صفوف الإلغاء أقلية مستمرة ولازم تتعامل معاها بصراحة في أهداف المصروف.",
        5: "الكمية وسعر الوحدة فيهم قيم متطرفة؛ مجموع الـ monetary في RFM حساس للذيل.",
    }
    insights = [
        {
            "id": i.get("id"),
            "claim_en": i.get("claim"),
            "claim_ar": claim_ar_by_id.get(i.get("id"), i.get("claim")),
            "type": i.get("type"),
        }
        for i in (eda.get("insights") or [])[:5]
    ]

    return _demo_envelope(
        metrics=metrics,
        insights=insights,
        caveat_en=eda.get("caveat")
        or "Insights describe this historical UK sample in GBP, not your live shop.",
        caveat_ar=(
            "الملحوظات وصفية من العينة البريطانية التاريخية بالجنيه الإسترليني، مش متجرك الحقيقي."
        ),
    )


@app.get("/api/segments")
def segments() -> dict[str, Any]:
    profiles = demo_data.segment_profiles()
    md = demo_data.metadata()
    label_map = md.get("segment_label_map") or {}
    rows = []
    for _, r in profiles.iterrows():
        cid = int(r["cluster_id"])
        rows.append(
            {
                "cluster_id": cid,
                "label_en": label_map.get(str(cid), f"Group {cid}"),
                "n_customers": int(r["n_customers"]),
                "share": float(r["share"]),
                "recency_mean": float(r["recency_mean"]),
                "recency_median": float(r["recency_median"]),
                "frequency_mean": float(r["frequency_mean"]),
                "frequency_median": float(r["frequency_median"]),
                "monetary_mean_gbp": float(r["monetary_mean"]),
                "monetary_median_gbp": float(r["monetary_median"]),
            }
        )
    return _demo_envelope(segments=rows)


@app.get("/api/segments/{cluster_id}/customers")
def segment_customers(cluster_id: int, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    df = demo_data.customers_with_segments()
    subset = df[df["cluster_id"] == cluster_id].sort_values("monetary", ascending=False)
    total = int(len(subset))
    page = subset.iloc[offset : offset + limit]
    customers = [
        {
            "customer_id": int(r.customer_id) if pd.notna(r.customer_id) else None,
            "recency": float(r.recency),
            "frequency": float(r.frequency),
            "monetary_gbp": float(r.monetary),
            "segment_label": r.segment_label,
            "source_split": r.source_split,
        }
        for r in page.itertuples()
    ]
    return _demo_envelope(
        cluster_id=cluster_id,
        total=total,
        offset=offset,
        limit=limit,
        customers=customers,
    )


@app.get("/api/customers")
def list_customers(limit: int = 100, q: str | None = None) -> dict[str, Any]:
    df = demo_data.customers_with_segments()
    if q:
        try:
            qid = float(q)
            df = df[df["customer_id"] == qid]
        except ValueError:
            df = df.iloc[0:0]
    df = df.sort_values("monetary", ascending=False).head(limit)
    return _demo_envelope(
        customers=[
            {
                "customer_id": int(r.customer_id),
                "recency": float(r.recency),
                "frequency": float(r.frequency),
                "monetary_gbp": float(r.monetary),
                "cluster_id": int(r.cluster_id),
                "segment_label": r.segment_label,
            }
            for r in df.itertuples()
        ]
    )


@app.get("/api/customers/{customer_id}")
def customer_profile(customer_id: int) -> dict[str, Any]:
    df = demo_data.customers_with_segments()
    match = df[df["customer_id"] == float(customer_id)]
    if match.empty:
        raise HTTPException(status_code=404, detail="Customer not found in demo tables")
    row = match.iloc[0]
    md = demo_data.metadata()
    cutoff = pd.Timestamp(md.get("test_cutoff") or "2011-09-10")
    try:
        tx = demo_data.eligible_tx()
    except demo_data.DemoDataUnavailable as exc:
        demo_data.raise_demo_unavailable(exc)
    cust_tx = tx[tx["customer_id"] == float(customer_id)].sort_values("invoice_date")
    # Features / history available at prediction time: on or before cutoff
    hist_at_cutoff = cust_tx[cust_tx["invoice_date"] <= cutoff]
    # Later actual spend is retrospective comparison only (never mixed into at-cutoff history)
    after_cutoff = cust_tx[cust_tx["invoice_date"] > cutoff]
    products = (
        hist_at_cutoff.groupby(["stock_code", "description"], dropna=False)
        .agg(quantity=("quantity", "sum"), spend_gbp=("line_amount", "sum"), lines=("invoice", "nunique"))
        .reset_index()
        .sort_values("spend_gbp", ascending=False)
        .head(15)
    )
    arts = demo_data.artifacts()
    pred = predict_customer(
        {
            "customer_id": customer_id,
            "recency": float(row.recency),
            "frequency": float(row.frequency),
            "monetary": float(row.monetary),
        },
        artifacts=arts,
    )
    actions_approved = bool(
        pred.metadata.get("actions_approved", md.get("actions_approved", False))
    )
    suggested = pred.suggested_action
    if not actions_approved and suggested:
        suggested = {
            "provisional": True,
            "label_en": "Provisional suggested action (not approved for operations)",
            "label_ar": "اقتراح إجراء مؤقت (مش معتمد للتشغيل)",
            "raw": suggested,
        }
    actual = (
        float(row.target_spend_90d)
        if "target_spend_90d" in row and pd.notna(row.target_spend_90d)
        else None
    )
    return _demo_envelope(
        customer={
            "customer_id": customer_id,
            "recency": float(row.recency),
            "frequency": float(row.frequency),
            "monetary_gbp": float(row.monetary),
            "cluster_id": int(row.cluster_id),
            "segment_label": row.segment_label,
            "source_split": row.source_split,
            "prediction_cutoff": str(cutoff.date()),
        },
        purchase_history=[
            {
                "invoice": str(r.invoice),
                "invoice_date": str(r.invoice_date),
                "stock_code": str(r.stock_code),
                "description": None if pd.isna(r.description) else str(r.description),
                "quantity": float(r.quantity),
                "line_amount_gbp": float(r.line_amount),
                "available_at_prediction": True,
            }
            for r in hist_at_cutoff.tail(40).itertuples()
        ],
        retrospective_actual={
            "label_en": (
                "Actual eligible spend after the prediction cutoff (retrospective comparison only). "
                "Not available at prediction time."
            ),
            "label_ar": (
                "المصروف المؤهل الفعلي بعد حد التوقع (مقارنة لاحقة فقط). "
                "مش كان متاح وقت التوقع."
            ),
            "target_spend_90d_actual_gbp": actual,
            "post_cutoff_lines": [
                {
                    "invoice": str(r.invoice),
                    "invoice_date": str(r.invoice_date),
                    "stock_code": str(r.stock_code),
                    "line_amount_gbp": float(r.line_amount),
                    "available_at_prediction": False,
                }
                for r in after_cutoff.head(20).itertuples()
            ],
        },
        products_bought=[
            {
                "stock_code": str(r.stock_code),
                "description": None if pd.isna(r.description) else str(r.description),
                "quantity": float(r.quantity),
                "spend_gbp": float(r.spend_gbp),
                "lines": int(r.lines),
                "historical_only": True,
                "as_of_cutoff": str(cutoff.date()),
            }
            for r in products.itertuples()
        ],
        estimate={
            "predicted_spend_90d_gbp": float(pred.predicted_spend_90d),
            "forecast_scope": "demo_only",
            "label_en": "Demo estimate (model trained on sample UK data) — not a guarantee",
            "label_ar": "تقدير تجريبي (الموديل متدرب على بيانات بريطانية تجريبية) — مش ضمان",
            "suggested_action": suggested,
            "actions_approved": actions_approved,
            "prediction_cutoff": str(cutoff.date()),
        },
    )


class PredictBody(BaseModel):
    customer_id: int | None = None
    recency: float = Field(ge=0)
    frequency: float = Field(ge=0)
    monetary: float = Field(ge=0)


@app.post("/api/predict")
def predict(body: PredictBody) -> dict[str, Any]:
    """Demo-only RFM inference. Never marks upload-store forecasts as validated."""
    arts = demo_data.artifacts()
    result = predict_customer(
        {
            "customer_id": body.customer_id,
            "recency": body.recency,
            "frequency": body.frequency,
            "monetary": body.monetary,
        },
        artifacts=arts,
    )
    return _demo_envelope(
        prediction={
            "customer_id": body.customer_id,
            "cluster_id": result.cluster_id,
            "segment_label": result.segment_label,
            "predicted_spend_90d_gbp": result.predicted_spend_90d,
            "suggested_action": result.suggested_action,
            "forecast_scope": "demo_only",
            "label_en": "Demo estimate (model trained on sample UK data) — not a guarantee",
        }
    )


@app.get("/api/products")
def products(limit: int = 30) -> dict[str, Any]:
    snap = demo_data.store_snapshot()
    product_rows: list[dict[str, Any]] = []
    trend_rows: list[dict[str, Any]] = []

    # Prefer committed full-store snapshot so clones match published demo numbers
    # without requiring the full cleaned parquet.
    if snap.get("products") and not demo_data.has_full_transactions():
        for p in (snap.get("products") or [])[:limit]:
            product_rows.append(
                {
                    "stock_code": str(p.get("stock_code")),
                    "description": p.get("description"),
                    "quantity": float(p.get("quantity") or 0),
                    "spend_gbp": float(p.get("spend_gbp") or 0),
                    "orders": int(p.get("orders") or 0),
                    "note_en": "Historical sales only — not a prediction of future need",
                }
            )
        trend_rows = list(snap.get("monthly_trend") or [])[-24:]
    else:
        try:
            tx = demo_data.eligible_tx()
        except demo_data.DemoDataUnavailable as exc:
            if snap.get("products"):
                for p in (snap.get("products") or [])[:limit]:
                    product_rows.append(
                        {
                            "stock_code": str(p.get("stock_code")),
                            "description": p.get("description"),
                            "quantity": float(p.get("quantity") or 0),
                            "spend_gbp": float(p.get("spend_gbp") or 0),
                            "orders": int(p.get("orders") or 0),
                            "note_en": "Historical sales only — not a prediction of future need",
                        }
                    )
                trend_rows = list(snap.get("monthly_trend") or [])[-24:]
            else:
                demo_data.raise_demo_unavailable(exc)
        else:
            by_product = (
                tx.groupby(["stock_code", "description"], dropna=False)
                .agg(
                    quantity=("quantity", "sum"),
                    spend_gbp=("line_amount", "sum"),
                    orders=("invoice", "nunique"),
                )
                .reset_index()
                .sort_values("spend_gbp", ascending=False)
                .head(limit)
            )
            month = tx.copy()
            month["month"] = month["invoice_date"].dt.to_period("M").astype(str)
            trend = (
                month.groupby("month")
                .agg(spend_gbp=("line_amount", "sum"), orders=("invoice", "nunique"))
                .reset_index()
                .sort_values("month")
                .tail(24)
            )
            product_rows = [
                {
                    "stock_code": str(r.stock_code),
                    "description": None if pd.isna(r.description) else str(r.description),
                    "quantity": float(r.quantity),
                    "spend_gbp": float(r.spend_gbp),
                    "orders": int(r.orders),
                    "note_en": "Historical sales only — not a prediction of future need",
                }
                for r in by_product.itertuples()
            ]
            trend_rows = [
                {"month": r.month, "spend_gbp": float(r.spend_gbp), "orders": int(r.orders)}
                for r in trend.itertuples()
            ]

    return _demo_envelope(
        category_available=False,
        category_omitted_reason_en=(
            "Bundled demo transactions have no product-category field. "
            "Category charts appear only when an uploaded file includes a mapped category column."
        ),
        category_omitted_reason_ar=(
            "بيانات العرض التجريبية مفيهاش عمود تصنيف للمنتجات. "
            "رسوم التصنيف بتظهر بس لو الملف المرفوع فيه عمود تصنيف مربوط."
        ),
        products=product_rows,
        monthly_trend=trend_rows,
        categories=[],
    )


@app.get("/api/project")
def project_details() -> dict[str, Any]:
    md = demo_data.metadata()
    recon = demo_data.reconciliation()
    return _demo_envelope(
        model={
            "selected_regression_model": md.get("selected_regression_model"),
            "test_metrics": md.get("test_metrics"),
            "baseline_test_metrics": md.get("baseline_test_metrics"),
            "train_cutoffs": md.get("train_cutoffs"),
            "test_cutoff": md.get("test_cutoff"),
            "eligible_spend_policy": md.get("eligible_spend_policy"),
            "actions_approved": md.get("actions_approved", False),
        },
        quality=demo_data.quality_summary(),
        cleaning_reconciliation=recon.to_dict(orient="records") if recon is not None else [],
        definitions={
            "currency_en": "All demo money values are GBP (£). No FX conversion.",
            "currency_ar": "كل مبالغ العرض بالجنيه الإسترليني (£). مفيش تحويل عملة.",
            "eligible_spend_en": (
                "Eligible positive spend excludes cancellation invoices (C…) "
                "and non-positive quantities (D5)."
            ),
            "eligible_spend_ar": (
                "المصروف المؤهل بيستبعد فواتير الإلغاء (C…) والكميات غير الموجبة (D5)."
            ),
            "forecast_en": (
                "90-day spend model is trained on this UK demo sample only. "
                "Not validated for uploaded stores."
            ),
            "forecast_ar": (
                "موديل مصروف ٩٠ يوم متدرب على العينة البريطانية التجريبية فقط. "
                "مش متحقق منه لمتاجر مرفوعة."
            ),
        },
    )


# ----- Upload -----


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    """Stream the upload to disk; abort as soon as the byte limit is exceeded."""
    try:
        meta = await upload_store.create_session_from_upload_file(
            file.filename or "upload.bin",
            file.read,
            max_bytes=MAX_UPLOAD_BYTES,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    path = upload_store.upload_path(meta.session_id)
    try:
        meta = canonical_upload.ensure_workbook_meta(meta)
        df = canonical_upload.read_raw_source(meta, nrows=MAX_PREVIEW_ROWS + 1)
    except Exception as exc:  # noqa: BLE001
        upload_store.discard_session(meta.session_id)
        upload_store.safe_log_outcome(meta.session_id, outcome="read_fail")
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc

    truncated = len(df) > MAX_PREVIEW_ROWS
    if truncated:
        df = df.iloc[:MAX_PREVIEW_ROWS]
    meta.row_count = int(len(df))
    # Seed high-confidence auto mapping only when the sales sheet is known.
    # Multi-sheet workbooks must not lock mapping to the first sheet silently.
    resolved: dict[str, Any] = {
        "needs_user_mapping": True,
        "mapping_confirmed": False,
        "effective_mapping": {},
    }
    if not canonical_upload.needs_sheet_selection(meta):
        resolved = canonical_upload.resolve_mapping(meta, [str(c) for c in df.columns])
        if resolved.get("mapping_confirmed") and not meta.mapping_confirmed:
            meta.column_mapping = resolved["effective_mapping"]
            meta.mapping_confirmed = True
            if meta.column_mapping.get("category"):
                meta.has_category_mapped = True
                meta.category_column = meta.column_mapping["category"]
    upload_store.save_meta(meta)
    date_info = canonical_upload.validate_for_upload(meta).get("date_format")
    upload_store.safe_log_outcome(
        meta.session_id, outcome="stored", row_count=meta.row_count
    )
    return {
        "session_id": meta.session_id,
        "filename": meta.filename,
        "byte_size": meta.byte_size,
        "row_count_preview": meta.row_count,
        "preview_truncated": truncated,
        "max_preview_rows": MAX_PREVIEW_ROWS,
        "ttl_seconds": UPLOAD_TTL_SECONDS,
        "currency_code": meta.currency_code,
        "date_format": meta.date_format,
        "date_format_info": date_info,
        "workbook_sheets": meta.workbook_sheets or [],
        "selected_sheet": meta.selected_sheet,
        "needs_sheet_selection": canonical_upload.needs_sheet_selection(meta),
        "mapping_confirmed": meta.mapping_confirmed,
        "needs_user_mapping": bool(resolved.get("needs_user_mapping"))
        and not meta.mapping_confirmed,
        "note_en": (
            "File stored temporarily for review only. Contents are not logged. "
            "Session files are deleted on discard, export, or after 2 hours. "
            "Confirm column mapping, currency, and date format before analysis. "
            "Amounts are not labelled with a currency unless you choose one."
        ),
        "note_ar": (
            "الملف متخزن مؤقتًا للمراجعة بس. المحتوى مش بيتسجل في اللوجات. "
            "بيتيمسح عند الإلغاء أو التصدير أو بعد ساعتين. "
            "أكّد ربط الأعمدة والعملة وصيغة التاريخ قبل التحليل. "
            "المبالغ مش هتتوسم بعملة إلا لو اخترت عملة."
        ),
    }


class UploadSettingsBody(BaseModel):
    session_id: str
    currency_code: str | None = None
    date_format: str | None = None
    confirm_date_format: bool = False
    analysis_currency_filter: str | None = None
    selected_sheet: str | None = None


@app.post("/api/upload/settings")
def upload_settings(body: UploadSettingsBody) -> dict[str, Any]:
    try:
        meta = upload_store.load_meta(body.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if body.currency_code is not None:
        code = body.currency_code.strip().upper() or "UNSPECIFIED"
        if code not in upload_store.KNOWN_CURRENCY_CODES:
            raise HTTPException(
                status_code=400,
                detail=f"currency_code must be one of {sorted(upload_store.KNOWN_CURRENCY_CODES)}",
            )
        meta.currency_code = code

    if body.date_format is not None:
        fmt = body.date_format.strip().lower()
        if fmt not in {"dayfirst", "monthfirst", "iso", ""}:
            raise HTTPException(
                status_code=400,
                detail="date_format must be dayfirst, monthfirst, or iso",
            )
        meta.date_format = fmt or None
        if body.confirm_date_format and meta.date_format:
            meta.date_format_confirmed = True
        elif not meta.date_format:
            meta.date_format_confirmed = False

    if body.confirm_date_format and meta.date_format:
        meta.date_format_confirmed = True

    if body.analysis_currency_filter is not None:
        filt = body.analysis_currency_filter.strip().upper() or None
        meta.analysis_currency_filter = filt

    if body.selected_sheet is not None:
        meta = canonical_upload.ensure_workbook_meta(meta)
        sheet = body.selected_sheet.strip()
        sheets = meta.workbook_sheets or []
        if sheet and sheet not in sheets:
            raise HTTPException(
                status_code=400,
                detail=f"Worksheet not found. Available: {sheets}",
            )
        previous_sheet = meta.selected_sheet
        meta.selected_sheet = sheet or None
        # Changing worksheet invalidates prior column mapping for that sheet.
        if previous_sheet != meta.selected_sheet:
            meta.column_mapping = None
            meta.mapping_confirmed = False
            meta.has_category_mapped = False
            meta.category_column = None

    upload_store.save_meta(meta)
    upload_store.safe_log_outcome(
        meta.session_id,
        outcome="settings",
        extra={"currency": meta.currency_code, "date_format": meta.date_format},
    )
    return {
        "session_id": meta.session_id,
        "currency_code": meta.currency_code,
        "currency_label": upload_store.currency_label(meta),
        "date_format": meta.date_format,
        "date_format_confirmed": meta.date_format_confirmed,
        "has_category_mapped": meta.has_category_mapped,
        "category_column": meta.category_column,
        "analysis_currency_filter": meta.analysis_currency_filter,
        "selected_sheet": meta.selected_sheet,
        "workbook_sheets": meta.workbook_sheets or [],
        "mapping_confirmed": meta.mapping_confirmed,
    }


class ColumnMappingBody(BaseModel):
    session_id: str
    mapping: dict[str, str] = Field(default_factory=dict)
    confirm: bool = True


@app.post("/api/upload/mapping")
def upload_column_mapping(body: ColumnMappingBody) -> dict[str, Any]:
    """Persist user-confirmed source→canonical column mapping for this session."""
    meta = _upload_meta(body.session_id)
    if canonical_upload.needs_sheet_selection(meta):
        raise HTTPException(
            status_code=400,
            detail="Select an Excel worksheet before confirming column mapping",
        )
    raw = canonical_upload.read_raw_source(meta, nrows=MAX_PREVIEW_ROWS)
    columns = [str(c) for c in raw.columns]
    suggestions = cmap_svc.suggest_mappings(columns)
    merged = cmap_svc.merge_user_mapping(suggestions, body.mapping)
    # Validate sources exist
    for canon, src in merged.items():
        if src not in columns:
            raise HTTPException(
                status_code=400,
                detail=f"Source column {src!r} for {canon} not in file",
            )
    caps = cmap_svc.assess_capabilities(merged)
    if body.confirm and not caps["analysis_ready_minimum"]:
        raise HTTPException(
            status_code=400,
            detail=caps.get("message_en")
            or "Map product and monetary columns before confirming",
        )
    meta.column_mapping = merged
    meta.mapping_confirmed = bool(body.confirm and caps["analysis_ready_minimum"])
    if merged.get("category"):
        meta.has_category_mapped = True
        meta.category_column = merged["category"]
    else:
        meta.has_category_mapped = False
        meta.category_column = None
    upload_store.save_meta(meta)
    upload_store.safe_log_outcome(
        meta.session_id,
        outcome="mapping_confirmed" if meta.mapping_confirmed else "mapping_saved",
        extra={"fields": sorted(merged.keys())},
    )
    return {
        "session_id": meta.session_id,
        "column_mapping": merged,
        "mapping_confirmed": meta.mapping_confirmed,
        "capabilities": caps,
        "suggestions": suggestions,
    }


@app.get("/api/upload/{session_id}/profile")
def upload_file_profile(session_id: str) -> dict[str, Any]:
    """Factual summary of an upload before / during cleaning review."""
    meta = _upload_meta(session_id)
    meta = canonical_upload.ensure_workbook_meta(meta)
    upload_store.save_meta(meta)
    try:
        df = canonical_upload.read_raw_source(meta, nrows=MAX_PREVIEW_ROWS)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    body = upload_profile.build_profile(df, meta, date_format=meta.date_format)
    upload_store.safe_log_outcome(
        session_id,
        outcome="profile",
        row_count=body.get("row_count"),
        extra={"code": "ok" if body.get("ok") else "invalid"},
    )
    return body


class AssistantHistoryTurn(BaseModel):
    role: str
    text: str = Field(max_length=500)


class AssistantBody(BaseModel):
    session_id: str
    question: str = Field(min_length=1, max_length=2000)
    lang: str = "en"
    history: list[AssistantHistoryTurn] | None = None


@app.post("/api/upload/assistant")
def upload_assistant_chat(body: AssistantBody) -> dict[str, Any]:
    """Open-ended grounded Q&A over the current upload — no raw rows sent externally."""
    meta = _upload_meta(body.session_id)
    df = canonical_upload.read_raw_source(meta, nrows=MAX_PREVIEW_ROWS)
    profile = upload_profile.build_profile(df, meta, date_format=meta.date_format)
    parsed = None
    try:
        if meta.mapping_confirmed or meta.column_mapping:
            parsed = canonical_upload.load_canonical_frame(
                meta, nrows=MAX_PREVIEW_ROWS, require_mapping=False
            )
    except Exception:  # noqa: BLE001
        parsed = None
    proposals = clean_svc.build_proposals(
        df,
        date_format=meta.date_format,
        currency_code=meta.currency_code,
        category_column=meta.category_column if meta.has_category_mapped else None,
        column_mapping=meta.column_mapping,
        parsed_override=parsed,
    )
    analytics: dict[str, Any] | None = None
    try:
        if meta.date_format_confirmed or not (profile.get("date_format") or {}).get(
            "needs_confirmation"
        ):
            if meta.currency_code and meta.currency_code != "UNSPECIFIED":
                analytics = {
                    "segments": upload_analytics.segments(meta).get("segments"),
                    "product_leaders": upload_analytics.product_leaders(meta),
                }
    except Exception:  # noqa: BLE001
        analytics = None
    profile = {
        **profile,
        "profile_confirmed": bool(meta.profile_confirmed),
        "gap_fill_preference": meta.gap_fill_preference,
        "session_id": meta.session_id,
    }
    history = (
        [{"role": t.role, "text": t.text} for t in (body.history or [])]
        if body.history
        else None
    )
    result = upload_assistant.answer(
        body.question,
        profile=profile,
        proposals=proposals,
        analytics=analytics,
        lang=body.lang if body.lang in {"ar", "en"} else "en",
        meta=meta,
        history=history,
    )
    # Apply confirm / gap-preference actions server-side when present
    for action in result.get("actions") or []:
        if action.get("type") == "confirm_profile":
            meta.profile_confirmed = bool(action.get("confirmed"))
            upload_store.save_meta(meta)
        elif action.get("type") == "set_gap_fill_preference":
            pref = action.get("preference")
            if pref in {"manual", "smart", None}:
                meta.gap_fill_preference = pref
                upload_store.save_meta(meta)
    upload_store.safe_log_outcome(
        body.session_id,
        outcome="assistant",
        extra={"code": "unsupported" if result.get("unsupported") else "ok"},
    )
    return result


@app.get("/api/upload/assistant/status")
def upload_assistant_status() -> dict[str, Any]:
    return upload_assistant.provider_status()


@app.post("/api/upload/validate")
def upload_validate(session_id: str, category_column: str | None = None) -> dict[str, Any]:
    try:
        meta = upload_store.load_meta(session_id)
        upload_store.upload_path(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    meta = canonical_upload.ensure_workbook_meta(meta)
    if category_column is not None:
        if canonical_upload.needs_sheet_selection(meta):
            raise HTTPException(status_code=400, detail="Select a worksheet first")
        raw = canonical_upload.read_raw_source(meta, nrows=MAX_PREVIEW_ROWS)
        mapping = dict(meta.column_mapping or {})
        if category_column == "":
            meta.has_category_mapped = False
            meta.category_column = None
            mapping.pop("category", None)
        else:
            if category_column not in raw.columns:
                raise HTTPException(status_code=400, detail="category_column not in file")
            meta.has_category_mapped = True
            meta.category_column = category_column
            mapping["category"] = category_column
        meta.column_mapping = mapping or None
    result = canonical_upload.validate_for_upload(meta)
    # Persist ISO auto-confirm side effects from validate_for_upload
    upload_store.save_meta(meta)
    result["mappable_columns"] = result.get("columns") or []
    upload_store.safe_log_outcome(
        session_id,
        outcome="validated",
        row_count=result.get("row_count"),
        extra={
            "code": "ok" if result.get("ok") else "mapping_incomplete",
            "missing_columns": result.get("missing_columns"),
        },
    )
    try:
        df = canonical_upload.read_raw_source(meta, nrows=15)
        preview = df.head(15).where(pd.notna(df.head(15)), None).to_dict(orient="records")
    except Exception:  # noqa: BLE001
        preview = []
    return {
        "session_id": session_id,
        "validation": result,
        "preview_rows": preview,
        "has_category_mapped": meta.has_category_mapped,
        "category_column": meta.category_column,
        "mapping_confirmed": meta.mapping_confirmed,
        "selected_sheet": meta.selected_sheet,
        "workbook_sheets": meta.workbook_sheets or [],
        "column_mapping": meta.column_mapping or {},
    }


@app.post("/api/upload/cleaning-proposals")
def upload_proposals(session_id: str) -> dict[str, Any]:
    try:
        meta = upload_store.load_meta(session_id)
        upload_store.upload_path(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    df = canonical_upload.read_raw_source(meta, nrows=MAX_PREVIEW_ROWS)
    parsed = None
    try:
        if meta.mapping_confirmed or (meta.column_mapping and cmap_svc.assess_capabilities(meta.column_mapping).get("analysis_ready_minimum")):
            parsed = canonical_upload.load_canonical_frame(
                meta, nrows=MAX_PREVIEW_ROWS, require_mapping=False
            )
    except Exception:  # noqa: BLE001
        parsed = None
    payload = clean_svc.build_proposals(
        df,
        date_format=meta.date_format,
        currency_code=meta.currency_code,
        category_column=meta.category_column if meta.has_category_mapped else None,
        column_mapping=meta.column_mapping,
        parsed_override=parsed,
    )
    upload_store.safe_log_outcome(
        session_id,
        outcome="proposals",
        row_count=payload.get("baseline", {}).get("rows"),
        extra={"proposals": len(payload.get("proposals") or [])},
    )
    return {
        "session_id": session_id,
        "currency_code": meta.currency_code,
        "date_format": meta.date_format,
        "date_format_confirmed": meta.date_format_confirmed,
        **payload,
    }


class ConfirmProfileBody(BaseModel):
    session_id: str
    confirmed: bool = True


@app.post("/api/upload/confirm-profile")
def upload_confirm_profile(body: ConfirmProfileBody) -> dict[str, Any]:
    try:
        meta = upload_store.load_meta(body.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    meta.profile_confirmed = bool(body.confirmed)
    upload_store.save_meta(meta)
    upload_store.safe_log_outcome(
        body.session_id,
        outcome="profile_confirmed",
        extra={"confirmed": meta.profile_confirmed},
    )
    return {
        "session_id": body.session_id,
        "profile_confirmed": meta.profile_confirmed,
        "gap_fill_preference": meta.gap_fill_preference,
    }


class GapFillPreferenceBody(BaseModel):
    session_id: str
    preference: str  # manual | smart


@app.post("/api/upload/gap-fill-preference")
def upload_gap_fill_preference(body: GapFillPreferenceBody) -> dict[str, Any]:
    try:
        meta = upload_store.load_meta(body.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pref = body.preference.strip().lower()
    if pref not in {"manual", "smart"}:
        raise HTTPException(status_code=400, detail="preference must be manual or smart")
    if not meta.profile_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirm the file summary first before choosing gap-fill mode",
        )
    meta.gap_fill_preference = pref
    upload_store.save_meta(meta)
    return {
        "session_id": body.session_id,
        "profile_confirmed": meta.profile_confirmed,
        "gap_fill_preference": meta.gap_fill_preference,
    }


class GapPatch(BaseModel):
    row_index: int
    field: str
    value: Any
    source: str = "manual"  # manual | smart


class GapFillBody(BaseModel):
    session_id: str
    patches: list[GapPatch] = Field(default_factory=list)
    apply_all_smart: bool = False


class RestoreSafeFillBody(BaseModel):
    session_id: str
    confirm_restore: bool = False


@app.get("/api/upload/{session_id}/safe-fill-backup")
def upload_safe_fill_backup_status(session_id: str) -> dict[str, Any]:
    """Whether a session-scoped pre-safe-fill backup exists for undo."""
    try:
        path = upload_store.upload_path(session_id)
        upload_store.load_meta(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    backup = gap_fill_svc.pre_safe_fill_backup_path(path)
    return {
        "session_id": session_id,
        "backup_available": backup.exists() and backup.stat().st_size > 0,
    }


@app.post("/api/upload/restore-safe-fill")
def upload_restore_safe_fill(body: RestoreSafeFillBody) -> dict[str, Any]:
    """Restore the active upload file from the pre-safe-fill backup (session only)."""
    if not body.confirm_restore:
        raise HTTPException(status_code=400, detail="confirm_restore must be true")
    try:
        meta = upload_store.load_meta(body.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from api.services import assistant_tools

    result = assistant_tools.execute_tool(
        "restore_pre_safe_fill", meta, {"confirm_restore": True}
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message_en") or result.get("error_code") or "restore_failed",
        )
    path = upload_store.upload_path(body.session_id)
    restored_df = clean_svc.read_upload_dataframe(
        path, nrows=None, sheet_name=meta.selected_sheet
    )
    refreshed = clean_svc.build_proposals(
        restored_df,
        date_format=meta.date_format,
        currency_code=meta.currency_code,
        category_column=meta.category_column if meta.has_category_mapped else None,
        column_mapping=meta.column_mapping,
    )
    profile = upload_profile.build_profile(
        restored_df, meta, date_format=meta.date_format
    )
    return {
        "session_id": body.session_id,
        "restored": True,
        "profile": profile,
        "unresolved_preview": refreshed.get("unresolved_preview") or [],
        "gap_fill": refreshed.get("gap_fill") or {},
        "note_en": result.get("message_en"),
        "note_ar": result.get("message_ar"),
    }


@app.post("/api/upload/gap-fill")
def upload_gap_fill(body: GapFillBody) -> dict[str, Any]:
    """Apply user-approved manual or evidence-based smart fills; rewrite session file."""
    try:
        path = upload_store.upload_path(body.session_id)
        meta = upload_store.load_meta(body.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not meta.profile_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirm the file summary before filling gaps",
        )

    raw = clean_svc.read_upload_dataframe(
        path, nrows=None, sheet_name=meta.selected_sheet
    )
    proposals = clean_svc.build_proposals(
        raw,
        date_format=meta.date_format,
        currency_code=meta.currency_code,
        category_column=meta.category_column if meta.has_category_mapped else None,
        column_mapping=meta.column_mapping,
    )
    patches: list[dict[str, Any]] = [p.model_dump() for p in body.patches]

    if body.apply_all_smart:
        if meta.gap_fill_preference != "smart" and not body.patches:
            # Allow explicit apply_all_smart after user chose smart in UI
            pass
        for row in proposals.get("unresolved_preview") or []:
            suggestions = row.get("suggestions") or {}
            for field, sug in suggestions.items():
                if not sug.get("allowed") or sug.get("suggested") is None:
                    continue
                patches.append(
                    {
                        "row_index": row["row_index"],
                        "field": field,
                        "value": sug["suggested"],
                        "source": "smart",
                    }
                )

    if not patches:
        raise HTTPException(status_code=400, detail="No patches to apply")

    updated, applied = gap_fill_svc.apply_patches_to_source(
        raw, patches, column_mapping=meta.column_mapping
    )
    gap_fill_svc.write_source_dataframe(
        path, updated, sheet_name=meta.selected_sheet
    )
    meta.byte_size = path.stat().st_size
    upload_store.save_meta(meta)

    refreshed = clean_svc.build_proposals(
        updated,
        date_format=meta.date_format,
        currency_code=meta.currency_code,
        category_column=meta.category_column if meta.has_category_mapped else None,
        column_mapping=meta.column_mapping,
    )
    upload_store.safe_log_outcome(
        body.session_id,
        outcome="gap_fill",
        row_count=len(updated),
        extra={"applied": len(applied), "smart": sum(1 for a in applied if a["source"] == "smart")},
    )
    return {
        "session_id": body.session_id,
        "applied": applied,
        "applied_count": len(applied),
        "unresolved_preview": refreshed.get("unresolved_preview") or [],
        "gap_fill": refreshed.get("gap_fill") or {},
        "saved_to_session_file": True,
        "note_en": "Patches saved into the temporary upload session file (not published).",
        "note_ar": "التعديلات اتحفظت في ملف جلسة الرفع المؤقت (مش منشور).",
    }


class ApplyBody(BaseModel):
    session_id: str
    accepted_ids: list[str] = Field(default_factory=list)
    keep_session: bool = False
    discard_session: bool = True


@app.post("/api/upload/accept-cleaning")
def upload_accept_cleaning(body: ApplyBody) -> dict[str, Any]:
    """Persist accepted cleaning proposal ids without discarding the session."""
    try:
        meta = upload_store.load_meta(body.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    meta.accepted_cleaning_ids = list(body.accepted_ids)
    upload_store.save_meta(meta)
    upload_store.safe_log_outcome(
        body.session_id,
        outcome="accept_cleaning",
        row_count=meta.row_count,
        extra={"accepted": body.accepted_ids},
    )
    return {
        "session_id": body.session_id,
        "accepted_cleaning_ids": meta.accepted_cleaning_ids,
        "saved": True,
        "note_en": "Accepted cleaning choices saved for this upload session.",
        "note_ar": "اختيارات التنظيف المقبولة اتحفظت لجلسة الرفع دي.",
    }


@app.post("/api/upload/apply")
def upload_apply(body: ApplyBody) -> Response:
    """Apply accepted cleaning ops and return a cleaned CSV export.

    By default the session is discarded after export (download-and-done).
    Pass keep_session=true (or discard_session=false) to keep analyzing.
    """
    try:
        path = upload_store.upload_path(body.session_id)
        meta = upload_store.load_meta(body.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    df = clean_svc.read_upload_dataframe(path, nrows=None)
    try:
        applied = clean_svc.apply_proposals(
            df,
            body.accepted_ids,
            date_format=meta.date_format,
            category_column=meta.category_column if meta.has_category_mapped else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    out_df: pd.DataFrame = applied["dataframe"]
    buf = io.StringIO()
    out_df.to_csv(buf, index=False)
    data = buf.getvalue().encode("utf-8")
    upload_store.write_export(body.session_id, data, "cleaned.csv")
    meta.accepted_cleaning_ids = list(body.accepted_ids)
    upload_store.save_meta(meta)
    upload_store.safe_log_outcome(
        body.session_id,
        outcome="applied_export",
        row_count=applied["rows_after"],
        extra={"accepted": body.accepted_ids, "currency": meta.currency_code},
    )
    currency = meta.currency_code or "UNSPECIFIED"
    keep = bool(body.keep_session) or (not body.discard_session)
    if not keep:
        upload_store.discard_session(body.session_id)

    return Response(
        content=data,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=marketmind_cleaned.csv",
            "X-Rows-Before": str(applied["rows_before"]),
            "X-Rows-After": str(applied["rows_after"]),
            "X-Eligible-Spend": str(applied["eligible_spend_after"]),
            "X-Currency-Code": currency,
            "X-Session-Kept": "1" if keep else "0",
        },
    )


def _upload_meta(session_id: str):
    try:
        return upload_store.load_meta(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/upload/{session_id}/overview")
def upload_overview(session_id: str) -> dict[str, Any]:
    meta = _upload_meta(session_id)
    try:
        return upload_analytics.overview(meta)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/upload/{session_id}/segments")
def upload_segments(session_id: str) -> dict[str, Any]:
    meta = _upload_meta(session_id)
    try:
        return upload_analytics.segments(meta)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/upload/{session_id}/segments/{cluster_id}/customers")
def upload_segment_customers(
    session_id: str, cluster_id: int, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    meta = _upload_meta(session_id)
    try:
        return upload_analytics.segment_customers(
            meta, cluster_id, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/upload/{session_id}/customers")
def upload_customers(session_id: str, limit: int = 100, q: str | None = None) -> dict[str, Any]:
    meta = _upload_meta(session_id)
    try:
        return upload_analytics.list_customers(meta, limit=limit, q=q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/upload/{session_id}/customers/{customer_id}")
def upload_customer_profile(session_id: str, customer_id: str) -> dict[str, Any]:
    meta = _upload_meta(session_id)
    try:
        # Keep alphanumeric IDs; coerce pure integers when possible.
        cid: int | str = customer_id
        try:
            if customer_id.strip().lstrip("-").isdigit():
                cid = int(customer_id)
        except ValueError:
            cid = customer_id
        return upload_analytics.customer_profile(meta, cid)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/upload/{session_id}/products")
def upload_products(session_id: str, limit: int = 30) -> dict[str, Any]:
    """Product/category aggregates for an upload session (never demo tables)."""
    meta = _upload_meta(session_id)
    try:
        body = upload_analytics.products(meta, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    upload_store.safe_log_outcome(
        session_id,
        outcome="upload_products",
        row_count=len(body.get("products") or []),
        extra={"code": "category_on" if body.get("category_available") else "category_off"},
    )
    return body


@app.delete("/api/upload/session")
def upload_discard(session_id: str) -> dict[str, str]:
    upload_store.discard_session(session_id)
    return {"status": "discarded", "session_id": session_id}


@app.get("/api/upload/policy")
def upload_policy() -> dict[str, Any]:
    return {
        "allowed_extensions": [".csv", ".xlsx"],
        "max_bytes": MAX_UPLOAD_BYTES,
        "max_preview_rows": MAX_PREVIEW_ROWS,
        "ttl_seconds": UPLOAD_TTL_SECONDS,
        "temp_storage": "data/uploads/tmp/<session_id>/",
        "logging": {
            "file_contents": False,
            "pii": False,
            "allowed_fields": [
                "timestamp",
                "session_id_hash",
                "byte_size",
                "extension",
                "outcome_codes",
                "row_count",
            ],
        },
        "retention": [
            "discard endpoint",
            "after successful export download",
            "TTL 2 hours",
            "startup cleanup",
        ],
        "multi_tenant": False,
        "encryption_at_rest_claimed": False,
    }
