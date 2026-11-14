"""Allowlisted analytics tools for the open-ended MarketMind assistant.

Gemini may request these tools; the backend executes all calculations and
sanitizes outputs. No raw rows, customer IDs, invoices, emails, or phones
are ever returned to the model.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from api.services import cleaning_proposals as clean_svc
from api.services import gap_fill, upload_analytics, upload_forecast, upload_profile
from api.services.upload_store import UploadSessionMeta, currency_label, upload_path

MAX_TOOL_RESULT_CHARS = 4500
_FORBIDDEN_KEYS = frozenset(
    {
        "customer_id",
        "customerid",
        "email",
        "phone",
        "address",
        "invoice",
        "invoice_id",
        "stock_code",
        "stockcode",
        "preview_rows",
        "raw_rows",
        # User-controlled file metadata can embed PII — never send to the model.
        "filename",
        "original_filename",
        "upload_filename",
    }
)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")


_KEY_ALLOW = frozenset({"error_code", "session_id", "tool", "currency_code"})


def assert_tool_result_safe(payload: Any, *, _depth: int = 0) -> None:
    """Fail closed on identifier keys / PII-shaped values in tool outputs."""
    if _depth > 8:
        raise ValueError("tool_result_too_deep")
    if isinstance(payload, dict):
        for k, v in payload.items():
            key = str(k).lower().replace("-", "_")
            if key in _FORBIDDEN_KEYS:
                raise ValueError(f"forbidden_tool_key:{key}")
            if key.endswith("_id") and key not in _KEY_ALLOW:
                raise ValueError(f"forbidden_tool_key:{key}")
            assert_tool_result_safe(v, _depth=_depth + 1)
    elif isinstance(payload, list):
        for item in payload[:50]:
            assert_tool_result_safe(item, _depth=_depth + 1)
    elif isinstance(payload, str):
        if _EMAIL_RE.search(payload) or _PHONE_RE.search(payload):
            raise ValueError("pii_shaped_value")


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    out = {"ok": True, **payload}
    assert_tool_result_safe(out)
    return out


def _err(code: str, *, en: str, ar: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message_en": en, "message_ar": ar, **extra}


def _trim(payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    if len(raw) <= MAX_TOOL_RESULT_CHARS:
        return payload
    # Prefer dropping large lists first
    slim = dict(payload)
    for key in ("products", "by_units", "by_revenue", "findings", "proposals", "candidates"):
        if key in slim and isinstance(slim[key], list) and len(slim[key]) > 3:
            slim[key] = slim[key][:3]
            slim[f"{key}_truncated"] = True
    raw2 = json.dumps(slim, ensure_ascii=False, default=str)
    if len(raw2) > MAX_TOOL_RESULT_CHARS:
        slim = {
            "ok": slim.get("ok", True),
            "error_code": "result_too_large",
            "message_en": "Tool result was too large; ask a narrower question.",
            "message_ar": "نتيجة الأداة كبيرة جدًا؛ اسأل سؤال أضيق.",
        }
    return slim


def _analysis_gate(meta: UploadSessionMeta) -> dict[str, Any] | None:
    try:
        upload_analytics.require_analysis_ready(meta)
        return None
    except Exception as exc:  # noqa: BLE001
        return _err(
            "analysis_not_ready",
            en=str(exc) or "Currency and date format must be confirmed first.",
            ar=" thrًد العملة وصيغة التاريخ أولًا قبل التحليل.",
        )


def tool_get_upload_profile(meta: UploadSessionMeta, _args: dict[str, Any]) -> dict[str, Any]:
    from api.services import canonical_upload

    try:
        df = canonical_upload.read_raw_source(meta, nrows=50_000)
    except Exception:  # noqa: BLE001
        path = upload_path(meta.session_id)
        df = clean_svc.read_upload_dataframe(
            path, nrows=50_000, sheet_name=meta.selected_sheet
        )
    profile = upload_profile.build_profile(df, meta, date_format=meta.date_format)
    findings = []
    for f in (profile.get("findings") or [])[:8]:
        if not isinstance(f, dict):
            continue
        findings.append(
            {
                "id": f.get("id"),
                "title_en": f.get("title_en"),
                "title_ar": f.get("title_ar"),
                "count": f.get("count"),
                "severity": f.get("severity"),
            }
        )
    structure = profile.get("structure") or {}
    return _ok(
        {
            "tool": "get_upload_profile",
            "row_count": profile.get("row_count"),
            "column_count": profile.get("column_count"),
            "unique_customers": structure.get("unique_customers"),
            "unique_products": structure.get("unique_products"),
            "unique_invoices": structure.get("unique_invoices"),
            "classification_en": (profile.get("classification") or {}).get("phrase_en"),
            "classification_ar": (profile.get("classification") or {}).get("phrase_ar"),
            "currency_code": meta.currency_code,
            "date_format": meta.date_format,
            "date_format_confirmed": meta.date_format_confirmed,
            "findings": findings,
            "definitions": {
                "row_count": "Uploaded line rows after read (preview-capped).",
                "findings": "Deterministic data-quality counts — not invented.",
            },
        }
    )


def tool_get_sales_kpis(meta: UploadSessionMeta, args: dict[str, Any]) -> dict[str, Any]:
    blocked = _analysis_gate(meta)
    if blocked:
        return blocked
    ov = upload_analytics.overview(meta)
    metrics = ov.get("metrics") or {}
    trend = list(ov.get("monthly_trend") or [])
    grain = str(args.get("grain") or "month").lower()
    if grain not in {"month", "all"}:
        grain = "month"
    compare = bool(args.get("compare_previous", True))
    comparison: dict[str, Any] | None = None
    if compare and len(trend) >= 2:
        a, b = trend[-2], trend[-1]
        spend_a, spend_b = float(a["spend"]), float(b["spend"])
        pct = ((spend_b - spend_a) / spend_a * 100.0) if spend_a else None
        comparison = {
            "previous_period": a["month"],
            "current_period": b["month"],
            "previous_spend": spend_a,
            "current_spend": spend_b,
            "previous_orders": int(a["orders"]),
            "current_orders": int(b["orders"]),
            "spend_pct_change": pct,
            "note_en": "Measured eligible spend in those calendar months — not causation.",
            "note_ar": "مصروف مؤهل مقاس في الشهور دي — مش سببية.",
        }
    return _ok(
        {
            "tool": "get_sales_kpis",
            "currency": currency_label(meta),
            "grain": grain,
            "metrics": {
                "eligible_sales": metrics.get("sales"),
                "orders": metrics.get("orders"),
                "customers": metrics.get("customers"),
                "average_order_value": metrics.get("average_order_value"),
                "returning_customer_share": metrics.get("returning_customer_share"),
                "date_min": metrics.get("date_min"),
                "date_max": metrics.get("date_max"),
            },
            "monthly_trend_tail": trend[-6:],
            "period_comparison": comparison,
            "definitions": ov.get("definitions")
            or {
                "eligible_sales": "Sum of positive eligible line spend after cleaning rules.",
            },
        }
    )


def tool_get_product_leaders(meta: UploadSessionMeta, args: dict[str, Any]) -> dict[str, Any]:
    blocked = _analysis_gate(meta)
    if blocked:
        return blocked
    measure = str(args.get("measure") or "units").lower()
    if measure not in {"units", "revenue"}:
        measure = "units"
    top_n = int(args.get("top_n") or 5)
    top_n = max(1, min(top_n, 10))
    leaders = upload_analytics.product_leaders(meta, top_n=top_n)
    if not leaders.get("available"):
        return _err(
            "products_unavailable",
            en=str(leaders.get("reason_en") or "Product ranking unavailable."),
            ar=str(leaders.get("reason_ar") or "ترتيب المنتجات غير متاح."),
        )
    key = "top_by_units" if measure == "units" else "top_by_revenue"
    list_key = "by_units" if measure == "units" else "by_revenue"
    # Strip stock codes from tool view — product_name + aggregates only
    def _clean_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "product_name": row.get("product_name") or row.get("name"),
            "quantity": row.get("quantity"),
            "spend": row.get("spend"),
            "orders": row.get("orders"),
        }

    by_list = [_clean_row(r) for r in (leaders.get(list_key) or []) if r]
    return _ok(
        {
            "tool": "get_product_leaders",
            "measure": measure,
            "currency": currency_label(meta),
            "top": _clean_row(leaders.get(key)),
            "ranked": by_list,
            "definitions": {
                "units": "Sum of eligible positive quantities by product name.",
                "revenue": "Sum of eligible line spend (qty × price) excluding cancellations.",
            },
        }
    )


def tool_get_category_performance(meta: UploadSessionMeta, _args: dict[str, Any]) -> dict[str, Any]:
    blocked = _analysis_gate(meta)
    if blocked:
        return blocked
    if not meta.has_category_mapped:
        return _err(
            "category_unmapped",
            en="No category column is mapped for this upload. Map Category to unlock category charts.",
            ar="مفيش عمود تصنيف مربوط في الرفع ده. اربط التصنيف لفتح رسوم التصنيفات.",
        )
    products = upload_analytics.products(meta, limit=50)
    cats = products.get("categories") or products.get("by_category") or []
    # Keep aggregate category rows only
    clean_cats = []
    for c in cats[:10]:
        if not isinstance(c, dict):
            continue
        clean_cats.append(
            {
                "category": c.get("category") or c.get("name"),
                "spend": c.get("spend") or c.get("eligible_spend"),
                "quantity": c.get("quantity") or c.get("units"),
                "orders": c.get("orders"),
            }
        )
    return _ok(
        {
            "tool": "get_category_performance",
            "currency": currency_label(meta),
            "categories": clean_cats,
            "available": bool(clean_cats),
        }
    )


def tool_get_customer_segments(meta: UploadSessionMeta, _args: dict[str, Any]) -> dict[str, Any]:
    blocked = _analysis_gate(meta)
    if blocked:
        return blocked
    segs = upload_analytics.segments(meta)
    rows = []
    for s in segs.get("segments") or []:
        rows.append(
            {
                "label_en": s.get("label_en"),
                "n_customers": s.get("n_customers"),
                "spend_share": s.get("spend_share"),
                "share": s.get("share"),
                "monetary_sum": s.get("monetary_sum"),
                "mean_recency": s.get("mean_recency") or s.get("recency_mean"),
                "mean_frequency": s.get("mean_frequency") or s.get("frequency_mean"),
            }
        )
    return _ok(
        {
            "tool": "get_customer_segments",
            "currency": currency_label(meta),
            "segments": rows,
            "returning_note_en": (
                "Descriptive RFM median splits for this upload only — not the UK demo model."
            ),
            "returning_note_ar": (
                "تقسيمات RFM وصفية للرفع ده فقط — مش موديل العرض البريطاني."
            ),
        }
    )


def tool_get_forecast_status(meta: UploadSessionMeta, _args: dict[str, Any]) -> dict[str, Any]:
    blocked = _analysis_gate(meta)
    if blocked:
        return blocked
    try:
        parsed = upload_analytics.load_parsed_frame(meta)
        raw = upload_forecast.evaluate_upload_forecast(parsed, meta)
        public = upload_forecast.public_forecast_payload(raw)
    except Exception as exc:  # noqa: BLE001
        return _err("forecast_error", en=str(exc), ar="تعذر تقييم التوقع.")
    return _ok(
        {
            "tool": "get_forecast_status",
            "available": bool(public.get("available")),
            "reason_en": public.get("reason_en"),
            "reason_ar": public.get("reason_ar"),
            "label_en": public.get("label_en"),
            "label_ar": public.get("label_ar"),
            "limitations_en": public.get("limitations_en"),
            "limitations_ar": public.get("limitations_ar"),
            "currency_code": public.get("currency_code") or currency_label(meta),
            "metrics": public.get("metrics"),
            "note_en": "Estimates are not guarantees.",
            "note_ar": "التقديرات مش ضمان.",
        }
    )


def tool_get_missing_and_fill_preview(meta: UploadSessionMeta, _args: dict[str, Any]) -> dict[str, Any]:
    """Preview only — never mutates. Strips identifiers from row samples."""
    from api.services import canonical_upload

    try:
        parsed = canonical_upload.load_canonical_frame(
            meta, nrows=100_000, require_mapping=False
        )
    except Exception as exc:  # noqa: BLE001
        return _err("invalid_frame", en=str(exc), ar="الملف مش صالح للتحليل.")
    preview = gap_fill.suggest_for_parsed(parsed, limit=15)
    # Sanitize: no invoice / customer_id / stock_code values to the model
    candidates = []
    safe_count = 0
    manual_count = 0
    for row in preview.get("rows") or []:
        sug = row.get("suggestions") or {}
        for field, detail in sug.items():
            if not isinstance(detail, dict):
                continue
            if detail.get("allowed") and detail.get("suggested") is not None:
                safe_count += 1
                candidates.append(
                    {
                        "field": field,
                        "suggested": detail.get("suggested"),
                        "reason_en": detail.get("reason_en"),
                        "reason_ar": detail.get("reason_ar"),
                        "evidence_stat": (detail.get("evidence") or {}).get("stat"),
                    }
                )
            else:
                manual_count += 1
    return _ok(
        {
            "tool": "get_missing_and_fill_preview",
            "unresolved_row_count_sampled": len(preview.get("rows") or []),
            "safe_fill_candidate_count": safe_count,
            "manual_only_issue_count": manual_count,
            "smart_fillable_fields": preview.get("smart_fillable_fields"),
            "manual_only_fields": preview.get("manual_only_fields"),
            "price_policy": preview.get("price_policy"),
            "candidates_sample": candidates[:12],
            "mutated": False,
            "note_en": preview.get("note_en"),
            "note_ar": preview.get("note_ar"),
        }
    )


def tool_get_cleaning_impact(meta: UploadSessionMeta, _args: dict[str, Any]) -> dict[str, Any]:
    from api.services import canonical_upload

    path = upload_path(meta.session_id)
    try:
        df = canonical_upload.read_raw_source(meta, nrows=100_000)
    except Exception:  # noqa: BLE001
        df = clean_svc.read_upload_dataframe(
            path, nrows=100_000, sheet_name=meta.selected_sheet
        )
    parsed = None
    try:
        if meta.mapping_confirmed or meta.column_mapping:
            parsed = canonical_upload.load_canonical_frame(
                meta, nrows=100_000, require_mapping=False
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
    brief = []
    for p in (proposals.get("proposals") or [])[:8]:
        brief.append(
            {
                "id": p.get("id"),
                "title_en": p.get("title_en"),
                "title_ar": p.get("title_ar"),
                "rows_affected": p.get("rows_affected"),
                "destructive": bool(p.get("destructive")),
                "default_accepted": bool(p.get("default_accepted")),
                "estimated_impact": p.get("estimated_impact"),
            }
        )
    return _ok(
        {
            "tool": "get_cleaning_impact",
            "proposals": brief,
            "unresolved_preview_count": len(proposals.get("unresolved_preview") or []),
            "baseline": {
                "rows": (proposals.get("baseline") or {}).get("rows"),
                "eligible_spend": (proposals.get("baseline") or {}).get("eligible_spend"),
            },
            "currency": currency_label(meta),
        }
    )


def tool_apply_safe_fills(meta: UploadSessionMeta, args: dict[str, Any]) -> dict[str, Any]:
    """Apply only deterministic high-confidence fills when explicitly authorized."""
    if not bool(args.get("confirm_apply")):
        return _err(
            "confirm_required",
            en="Set confirm_apply=true only after the user clearly asked to apply safe fills.",
            ar="ضع confirm_apply=true فقط بعد طلب صريح بتطبيق الملء الآمن.",
        )
    path = upload_path(meta.session_id)
    raw = clean_svc.read_upload_dataframe(
        path, nrows=None, sheet_name=meta.selected_sheet
    )
    from api.services import canonical_upload

    try:
        parsed = canonical_upload.load_canonical_frame(
            meta, nrows=None, require_mapping=False
        )
    except Exception:  # noqa: BLE001
        return _err(
            "mapping_required",
            en="Confirm column mapping before applying safe fills.",
            ar="أكّد ربط الأعمدة قبل تطبيق الملء الآمن.",
        )
    preview = gap_fill.suggest_for_parsed(parsed, limit=200)
    patches: list[dict[str, Any]] = []
    skipped_manual = 0
    skipped_insufficient = 0
    for row in preview.get("rows") or []:
        idx = row.get("row_index")
        for field, detail in (row.get("suggestions") or {}).items():
            if field in gap_fill.MANUAL_ONLY or field == "quantity":
                # Never invent IDs/dates/invoices/quantities from patterns
                skipped_manual += 1
                continue
            if not isinstance(detail, dict):
                continue
            if detail.get("allowed") and detail.get("suggested") is not None:
                patches.append(
                    {
                        "row_index": idx,
                        "field": field,
                        "value": detail["suggested"],
                        "source": "smart",
                    }
                )
            else:
                skipped_insufficient += 1

    if not patches:
        return _ok(
            {
                "tool": "apply_safe_fills",
                "mutated": False,
                "applied_count": 0,
                "fields_filled": {},
                "skipped_manual_or_unsafe": skipped_manual,
                "skipped_insufficient_evidence": skipped_insufficient,
                "price_policy": preview.get("price_policy"),
                "message_en": "No eligible safe fills to apply. Remaining blanks stay manual.",
                "message_ar": "مفيش ملء آمن قابل للتطبيق. الفراغات المتبقية تفضل يدوي.",
            }
        )
    from api.services import upload_store

    import shutil

    backup_path = gap_fill.pre_safe_fill_backup_path(path)
    try:
        # Byte-identical session backup so restore does not depend on format sniffing.
        shutil.copy2(path, backup_path)
        if not backup_path.exists() or backup_path.stat().st_size <= 0:
            raise OSError("backup_missing_or_empty")
    except Exception:  # noqa: BLE001
        return _err(
            "backup_required",
            en=(
                "Could not create a restore backup for this session; "
                "safe fills were not applied. Preview and manual review remain available."
            ),
            ar=(
                "مقدرناش نعمل نسخة استرجاع للجلسة دي؛ الملء الآمن ماتطبّقش. "
                "المعاينة والملء اليدوي لسه متاحين."
            ),
        )

    updated, applied = gap_fill.apply_patches_to_source(
        raw, patches, column_mapping=meta.column_mapping
    )
    gap_fill.write_source_dataframe(
        path, updated, sheet_name=meta.selected_sheet
    )
    meta.byte_size = path.stat().st_size
    upload_store.save_meta(meta)
    fields_filled: dict[str, int] = {}
    for a in applied:
        fields_filled[a["field"]] = fields_filled.get(a["field"], 0) + 1
    upload_store.safe_log_outcome(
        meta.session_id,
        outcome="safe_fill_applied",
        extra={"applied": len(applied), "backup": True, "fields": fields_filled},
    )
    return _ok(
        {
            "tool": "apply_safe_fills",
            "mutated": True,
            "applied_count": len(applied),
            "applied_fields": sorted(fields_filled.keys()),
            "fields_filled": fields_filled,
            "skipped_manual_or_unsafe": skipped_manual,
            "skipped_insufficient_evidence": skipped_insufficient,
            "price_policy": preview.get("price_policy"),
            "backup_available": True,
            "message_en": (
                f"Applied {len(applied)} deterministic safe fills "
                f"({fields_filled}). "
                "Customer IDs, dates, invoices, and quantities stay manual. "
                "You can undo via restore_pre_safe_fill while this session is active."
            ),
            "message_ar": (
                f"اتطبّق {len(applied)} ملء آمن محدد "
                f"({fields_filled}). "
                "أرقام الزباين والتواريخ والفواتير والكميات تفضل يدوي. "
                "تقدر ترجع بالنسخة الاحتياطية طول ما الجلسة شغالة."
            ),
            "refresh_hint": "reload_profile_cleaning_dashboard",
        }
    )


def tool_restore_pre_safe_fill(meta: UploadSessionMeta, args: dict[str, Any]) -> dict[str, Any]:
    """Restore the active upload file from the pre-safe-fill backup (session-scoped)."""
    if not bool(args.get("confirm_restore")):
        return _err(
            "confirm_required",
            en="Set confirm_restore=true only after the user clearly asked to undo safe fills.",
            ar="ضع confirm_restore=true فقط بعد طلب صريح بالتراجع عن الملء الآمن.",
        )
    import shutil

    path = upload_path(meta.session_id)
    backup_path = gap_fill.pre_safe_fill_backup_path(path)
    if not backup_path.exists():
        return _err(
            "no_backup",
            en="No pre-fill backup exists for this upload session.",
            ar="مفيش نسخة استرجاع قبل الملء للجلسة دي.",
        )
    try:
        shutil.copy2(backup_path, path)
        from api.services import upload_store

        meta.byte_size = path.stat().st_size
        upload_store.save_meta(meta)
        # Count rows for the user-facing summary after a successful byte restore.
        restored_df = clean_svc.read_upload_dataframe(path, nrows=None)
        upload_store.safe_log_outcome(
            meta.session_id,
            outcome="safe_fill_restored",
            extra={"rows": len(restored_df)},
        )
    except Exception:  # noqa: BLE001
        return _err(
            "restore_failed",
            en="Restore failed; the current session file was left unchanged.",
            ar="الاسترجاع فشل؛ ملف الجلسة الحالي اتساب زي ما هو.",
        )
    return _ok(
        {
            "tool": "restore_pre_safe_fill",
            "mutated": True,
            "restored": True,
            "row_count": len(restored_df),
            "message_en": (
                "Restored the upload file from the pre-safe-fill backup for this session. "
                "Reload profile, cleaning, and dashboard."
            ),
            "message_ar": (
                "اترجع ملف الرفع من نسخة ما قبل الملء الآمن لهذه الجلسة. "
                "حدّث الملف والتنظيف ولوحة التحليل."
            ),
            "refresh_hint": "reload_profile_cleaning_dashboard",
        }
    )


def tool_preview_data_transform(meta: UploadSessionMeta, args: dict[str, Any]) -> dict[str, Any]:
    """Preview a session-file transform / plan (aggregates only)."""
    from api.services import data_transforms

    plan = args.get("plan")
    if isinstance(plan, str):
        try:
            import json

            plan = json.loads(plan)
        except Exception:  # noqa: BLE001
            plan = None
    result = data_transforms.preview_or_apply(
        meta,
        op=str(args.get("op") or ""),
        confirm_apply=False,
        column=args.get("column"),
        new_column=args.get("new_column"),
        threshold=args.get("threshold"),
        fill_value=args.get("fill_value"),
        rename_to=args.get("rename_to"),
        plan=plan if isinstance(plan, list) else None,
    )
    result["tool"] = "preview_data_transform"
    return result


def tool_apply_data_transform(meta: UploadSessionMeta, args: dict[str, Any]) -> dict[str, Any]:
    """Apply a session-file transform / plan after explicit confirmation."""
    from api.services import data_transforms

    if not bool(args.get("confirm_apply")):
        return _err(
            "confirm_required",
            en="Set confirm_apply=true only after the user clearly asked to apply the transform.",
            ar="ضع confirm_apply=true فقط بعد طلب صريح بتطبيق التحويل.",
        )
    plan = args.get("plan")
    if isinstance(plan, str):
        try:
            import json

            plan = json.loads(plan)
        except Exception:  # noqa: BLE001
            plan = None
    result = data_transforms.preview_or_apply(
        meta,
        op=str(args.get("op") or ""),
        confirm_apply=True,
        column=args.get("column"),
        new_column=args.get("new_column"),
        threshold=args.get("threshold"),
        fill_value=args.get("fill_value"),
        rename_to=args.get("rename_to"),
        plan=plan if isinstance(plan, list) else None,
    )
    result["tool"] = "apply_data_transform"
    return result


TOOL_HANDLERS: dict[str, Callable[[UploadSessionMeta, dict[str, Any]], dict[str, Any]]] = {
    "get_upload_profile": tool_get_upload_profile,
    "get_sales_kpis": tool_get_sales_kpis,
    "get_product_leaders": tool_get_product_leaders,
    "get_category_performance": tool_get_category_performance,
    "get_customer_segments": tool_get_customer_segments,
    "get_forecast_status": tool_get_forecast_status,
    "get_missing_and_fill_preview": tool_get_missing_and_fill_preview,
    "get_cleaning_impact": tool_get_cleaning_impact,
    "apply_safe_fills": tool_apply_safe_fills,
    "restore_pre_safe_fill": tool_restore_pre_safe_fill,
    "preview_data_transform": tool_preview_data_transform,
    "apply_data_transform": tool_apply_data_transform,
}


TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "get_upload_profile",
        "description": "File profile, structure counts, and data-quality findings for the active upload.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_sales_kpis",
        "description": "Eligible sales KPIs, trend tail, and optional previous-vs-current month comparison.",
        "parameters": {
            "type": "object",
            "properties": {
                "grain": {"type": "string", "description": "month or all"},
                "compare_previous": {"type": "boolean"},
            },
            "required": [],
        },
    },
    {
        "name": "get_product_leaders",
        "description": "Top products by units or eligible revenue for the active upload.",
        "parameters": {
            "type": "object",
            "properties": {
                "measure": {"type": "string", "description": "units or revenue"},
                "top_n": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_category_performance",
        "description": "Category aggregates when a category column is mapped.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_customer_segments",
        "description": "Descriptive RFM customer group aggregates for this upload (no identities).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_forecast_status",
        "description": "Whether a store-specific forecast is available, with reasons and limitations.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_missing_and_fill_preview",
        "description": "Preview missing-value issues and safe fill candidates. Does not mutate data.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_cleaning_impact",
        "description": "Cleaning proposals and estimated impact for the active upload.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "apply_safe_fills",
        "description": (
            "Apply only deterministic high-confidence fills (price/description with same-file evidence) "
            "after the user clearly requested applying fills. Never invents IDs, dates, invoices, or quantities. "
            "Requires confirm_apply=true. Creates a session backup first; refuses to apply if backup fails."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirm_apply": {"type": "boolean"},
            },
            "required": ["confirm_apply"],
        },
    },
    {
        "name": "restore_pre_safe_fill",
        "description": (
            "Undo the last safe-fill apply by restoring the session-scoped pre-fill backup. "
            "Requires confirm_restore=true. Only works for the active temporary upload session."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirm_restore": {"type": "boolean"},
            },
            "required": ["confirm_restore"],
        },
    },
    {
        "name": "preview_data_transform",
        "description": (
            "Preview a safe mutation of THIS upload session file only (no write yet). "
            "Prefer op='plan' with a steps[] list for open-ended reshape requests. "
            "Step ops: filter, sort, assign (expr), replace, split, merge, floor_date, "
            "strip_time, fillna, cast, rename, drop, parse_currency, groupby_agg, dedupe, clip. "
            "Expressions are a constrained DSL (columns, + - * /, comparisons, "
            "abs/round/lower/year/month/to_number/…) — never arbitrary Python. "
            "Legacy shortcuts: strip_time, add_invoice_flag, drop_column, rename_column, "
            "cast_numeric, fill_constant. Returns aggregates only — never raw rows."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "description": (
                        "plan | strip_time | add_invoice_flag | drop_column | "
                        "rename_column | cast_numeric | fill_constant"
                    ),
                },
                "plan": {
                    "type": "array",
                    "description": "For op=plan: list of {op, ...} step objects",
                    "items": {"type": "object"},
                },
                "column": {"type": "string"},
                "new_column": {"type": "string"},
                "threshold": {"type": "number"},
                "fill_value": {"type": "string"},
                "rename_to": {"type": "string"},
            },
            "required": ["op"],
        },
    },
    {
        "name": "apply_data_transform",
        "description": (
            "Apply a previewed session-file plan/transform after the user clearly asked "
            "(apply / طبّق / do it). Requires confirm_apply=true. Session backup first. "
            "Scope: this temporary upload only — no demo data, shell, network, or model training."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "op": {"type": "string"},
                "confirm_apply": {"type": "boolean"},
                "plan": {"type": "array", "items": {"type": "object"}},
                "column": {"type": "string"},
                "new_column": {"type": "string"},
                "threshold": {"type": "number"},
                "fill_value": {"type": "string"},
                "rename_to": {"type": "string"},
            },
            "required": ["op", "confirm_apply"],
        },
    },
]


def execute_tool(name: str, meta: UploadSessionMeta, args: dict[str, Any] | None) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _err("unknown_tool", en=f"Unknown tool: {name}", ar=f"أداة غير معروفة: {name}")
    raw_args = args if isinstance(args, dict) else {}
    # Reject unexpected keys (defense in depth)
    allowed = set(
        (
            next(
                (d["parameters"]["properties"].keys() for d in TOOL_DECLARATIONS if d["name"] == name),
                {},
            )
        )
    )
    cleaned = {k: v for k, v in raw_args.items() if k in allowed}
    try:
        result = handler(meta, cleaned)
    except Exception:  # noqa: BLE001
        return _err("tool_failed", en="Tool execution failed safely.", ar="فشل تنفيذ الأداة بأمان.")
    try:
        assert_tool_result_safe(result)
    except Exception:  # noqa: BLE001
        return _err(
            "privacy_blocked",
            en="Tool result blocked by privacy rules.",
            ar="نتيجة الأداة اتمنعت بقواعد الخصوصية.",
        )
    return _trim(result)


def gemini_tool_schemas() -> list[Any]:
    """Build google.genai FunctionDeclaration objects."""
    from google.genai import types

    decls = []
    for d in TOOL_DECLARATIONS:
        decls.append(
            types.FunctionDeclaration(
                name=d["name"],
                description=d["description"],
                parameters=d["parameters"],
            )
        )
    return decls
