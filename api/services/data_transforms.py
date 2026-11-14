"""Safe, allowlisted data transforms for the upload-session assistant.

All mutations rewrite only the temporary session file (never demo/academic
artifacts). Previews return aggregates only — no raw row dumps for the model.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from api.services import gap_fill
from api.services.upload_store import UploadSessionMeta, upload_path

ALLOWED_OPS = frozenset(
    {
        "strip_time",
        "add_invoice_flag",
        "drop_column",
        "rename_column",
        "cast_numeric",
        "fill_constant",
        "plan",  # general constrained session mutation plan
    }
)

# Normalized keys (spaces/underscores stripped) that must not be dropped.
_PROTECTED_DROP = frozenset(
    {
        "invoice",
        "invoiceno",
        "invoicenumber",
        "orderno",
        "orderid",
        "customerid",
        "customer",
        "clientid",
        "price",
        "unitprice",
        "quantity",
        "qty",
        "linetotal",
        "lineamount",
        "invoicedate",
        "date",
    }
)


def _protect_key(name: object) -> str:
    return re.sub(r"[\s_]+", "", _norm_col(name))


def transform_backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".pre_transform.bak")


def ensure_transform_backup(path: Path) -> Path:
    backup = transform_backup_path(path)
    if not backup.exists() or backup.stat().st_size == 0:
        shutil.copy2(path, backup)
    return backup


def _read_source(meta: UploadSessionMeta) -> pd.DataFrame:
    from api.services import cleaning_proposals as clean_svc

    path = upload_path(meta.session_id)
    return clean_svc.read_upload_dataframe(
        path, nrows=None, sheet_name=meta.selected_sheet
    )


def _write_source(meta: UploadSessionMeta, df: pd.DataFrame) -> None:
    from api.services import upload_store

    path = upload_path(meta.session_id)
    ensure_transform_backup(path)
    gap_fill.write_source_dataframe(path, df, sheet_name=meta.selected_sheet)
    meta.byte_size = path.stat().st_size
    meta.row_count = int(len(df))
    upload_store.save_meta(meta)


def _norm_col(name: object) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _parse_datetimes(series: pd.Series, date_format: str | None) -> pd.Series:
    """Parse with the session-confirmed date order; never guess DMY vs MDY."""
    fmt = (date_format or "").strip().lower()
    if fmt == "dayfirst":
        return pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=True)
    if fmt == "monthfirst":
        return pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=False)
    if fmt == "iso":
        parsed = pd.to_datetime(series, errors="coerce", format="ISO8601")
        still = parsed.isna() & series.notna()
        if still.any():
            parsed = parsed.copy()
            parsed.loc[still] = pd.to_datetime(
                series[still], errors="coerce", format="%Y-%m-%d", exact=False
            )
        return parsed
    # Unconfirmed: do not reinterpret slash dates — only parse unambiguous ISO-like values.
    return pd.to_datetime(series, errors="coerce", format="ISO8601")


def _resolve_column(df: pd.DataFrame, requested: str | None) -> str | None:
    if not requested:
        return None
    want = _norm_col(requested)
    for c in df.columns:
        if _norm_col(c) == want or _norm_col(c).replace(" ", "") == want.replace(" ", ""):
            return str(c)
    # substring soft match
    for c in df.columns:
        if want and want in _norm_col(c):
            return str(c)
    return None


def _datetime_candidates(df: pd.DataFrame, mapping: dict[str, str] | None) -> list[str]:
    cols: list[str] = []
    if mapping and mapping.get("invoice_date"):
        src = mapping["invoice_date"]
        if src in df.columns:
            cols.append(src)
    for c in df.columns:
        name = _norm_col(c)
        if any(k in name for k in ("date", "time", "تاريخ", "وقت")) and str(c) not in cols:
            cols.append(str(c))
    return cols


_CLOCK_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?")
_PURE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _value_str(value: object) -> str:
    """Human string form — keeps Timestamp midnight as ``… 00:00:00`` (unlike astype)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _has_time_component(series: pd.Series) -> tuple[bool, int]:
    """Return (any_time_present, count_with_time).

    Midnight ``00:00:00`` and string timestamps count as time-to-strip — the gaps
    UI shows ``str(Timestamp)`` with that clock even when pandas ``astype(str)``
    drops it.
    """
    as_str = series.map(_value_str)
    clock = as_str.str.contains(_CLOCK_RE.pattern, regex=True, na=False)
    # Datetime-like values that are not already pure YYYY-MM-DD strings.
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    pure_date = as_str.str.match(_PURE_DATE_RE.pattern, na=False)
    stripable = clock | (parsed.notna() & ~pure_date)
    count = int(stripable.sum())
    return count > 0, count


def format_date_only(value: object) -> str | None:
    """Serialize a date/datetime for UI as YYYY-MM-DD (never ``… 00:00:00``)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.notna(parsed):
        return pd.Timestamp(parsed).strftime("%Y-%m-%d")
    text = _value_str(value).strip()
    if not text or text.lower() in {"nat", "none", "nan"}:
        return None
    return _CLOCK_RE.sub("", text).strip() or text


def preview_or_apply(
    meta: UploadSessionMeta,
    *,
    op: str,
    confirm_apply: bool = False,
    column: str | None = None,
    new_column: str | None = None,
    threshold: float | None = None,
    fill_value: str | None = None,
    rename_to: str | None = None,
    plan: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    op = (op or "").strip().lower()
    if op not in ALLOWED_OPS:
        return {
            "ok": False,
            "error_code": "unknown_op",
            "message_en": f"Unsupported transform: {op}",
            "message_ar": f"تحويل غير مدعوم: {op}",
            "allowed_ops": sorted(ALLOWED_OPS),
        }

    try:
        df = _read_source(meta)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error_code": "read_failed",
            "message_en": f"Could not read session file: {exc}",
            "message_ar": "مش قادر أقرأ ملف الجلسة.",
        }

    mapping = dict(meta.column_mapping or {})

    if op == "plan":
        from api.services import session_mutate

        steps = plan or []
        result = session_mutate.execute_steps(
            df, steps, mapping=mapping, protected_drop=_PROTECTED_DROP
        )
        if not result.get("ok"):
            return result
        result["op"] = "plan"
        result["plan"] = steps
        # Aggregates only — no raw row dump for model/tool logs.
        impact = result.get("impact") or {}
        result["preview_en"] = (
            f"Plan ({len(steps)} steps): {result.get('preview_en')}. "
            f"Rows {impact.get('rows_before')}→{impact.get('rows_after')} "
            f"(Δ{impact.get('rows_delta')}); "
            f"added cols {impact.get('cols_added')}; removed {impact.get('cols_removed')}."
        )
        result["preview_ar"] = (
            f"خطة ({len(steps)} خطوة): {result.get('preview_ar')}. "
            f"صفوف {impact.get('rows_before')}→{impact.get('rows_after')} "
            f"(Δ{impact.get('rows_delta')})؛ "
            f"أعمدة جديدة {impact.get('cols_added')}؛ محذوفة {impact.get('cols_removed')}."
        )
        result["apply_en"] = result["preview_en"].replace("Plan", "Applied plan", 1)
        result["apply_ar"] = "اتطبّقت " + result["preview_ar"]
        result.pop("mapping", None)
    else:
        handler = {
            "strip_time": _op_strip_time,
            "add_invoice_flag": _op_add_invoice_flag,
            "drop_column": _op_drop_column,
            "rename_column": _op_rename_column,
            "cast_numeric": _op_cast_numeric,
            "fill_constant": _op_fill_constant,
        }[op]
        result = handler(
            df,
            meta=meta,
            mapping=mapping,
            column=column,
            new_column=new_column,
            threshold=threshold,
            fill_value=fill_value,
            rename_to=rename_to,
            apply=False,
        )
        if not result.get("ok"):
            return result

    if not confirm_apply:
        result["preview_only"] = True
        result["needs_confirm"] = True
        result["message_en"] = (
            (result.get("preview_en") or "Preview ready.")
            + " Reply “apply” / «طبّق» to write it to the session file."
        )
        result["message_ar"] = (
            (result.get("preview_ar") or "المعاينة جاهزة.")
            + " رد بـ «طبّق» عشان يتكتب على ملف الجلسة."
        )
        from api.services import upload_store

        meta.pending_transform = {
            "op": op,
            "column": result.get("column") or column,
            "new_column": result.get("new_column") or new_column,
            "threshold": result.get("threshold", threshold),
            "fill_value": fill_value,
            "rename_to": result.get("rename_to") or rename_to,
            "plan": plan if op == "plan" else None,
        }
        upload_store.save_meta(meta)
        # Drop heavy frame from preview response
        result.pop("dataframe", None)
        return result

    # Apply — re-run so we have a fresh dataframe
    if op == "plan":
        from api.services import session_mutate

        applied = session_mutate.execute_steps(
            df, plan or [], mapping=mapping, protected_drop=_PROTECTED_DROP
        )
    else:
        handler = {
            "strip_time": _op_strip_time,
            "add_invoice_flag": _op_add_invoice_flag,
            "drop_column": _op_drop_column,
            "rename_column": _op_rename_column,
            "cast_numeric": _op_cast_numeric,
            "fill_constant": _op_fill_constant,
        }[op]
        applied = handler(
            df,
            meta=meta,
            mapping=mapping,
            column=column,
            new_column=new_column,
            threshold=threshold,
            fill_value=fill_value,
            rename_to=rename_to,
            apply=True,
        )
    if not applied.get("ok"):
        return applied
    try:
        _write_source(meta, applied["dataframe"])
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error_code": "write_failed",
            "message_en": f"Could not save transform: {exc}",
            "message_ar": "مش قادر أحفظ التحويل.",
        }
    from api.services import upload_store

    if applied.get("mapping") is not None:
        meta.column_mapping = applied["mapping"]
    meta.pending_transform = None
    upload_store.save_meta(meta)
    # Never return mapping (may contain *_id keys) or dataframe to tool callers.
    out = {
        k: v
        for k, v in applied.items()
        if k not in {"dataframe", "mapping"}
    }
    out["ok"] = True
    out["mutated"] = True
    out["preview_only"] = False
    out["message_en"] = (
        applied.get("apply_en")
        or result.get("apply_en")
        or "Transform applied to the session file."
    )
    out["message_ar"] = (
        applied.get("apply_ar")
        or result.get("apply_ar")
        or "التحويل اتطبّق على ملف الجلسة."
    )
    if op == "plan" and result.get("preview_en"):
        out["message_en"] = result["apply_en"]
        out["message_ar"] = result["apply_ar"]
    out["refresh_hint"] = "reload_profile_cleaning_dashboard"
    return out


def _op_strip_time(
    df: pd.DataFrame,
    *,
    meta: UploadSessionMeta,
    mapping: dict[str, str],
    column: str | None,
    apply: bool,
    **_: Any,
) -> dict[str, Any]:
    target = _resolve_column(df, column) if column else None
    if not target:
        candidates = _datetime_candidates(df, mapping)
        best = None
        best_count = 0
        for c in candidates:
            has, count = _has_time_component(df[c])
            if has and count >= best_count:
                best, best_count = c, count
        # Prefer a timed column; otherwise keep the mapped/date candidate so we
        # can say “already date-only” instead of “no datetime column”.
        target = best or (candidates[0] if candidates else None)
    if not target or target not in df.columns:
        return {
            "ok": False,
            "error_code": "no_datetime_column",
            "message_en": "No datetime column with a time-of-day component was found.",
            "message_ar": "مفيش عمود تاريخ فيه جزء وقت/ساعة.",
        }

    has, count = _has_time_component(df[target])
    if not has:
        # Never claim “no time” when any cell string still shows a clock (incl. 00:00:00).
        sample = ", ".join(
            _value_str(v) for v in df[target].dropna().head(3).tolist()
        ) or "(empty)"
        return {
            "ok": False,
            "error_code": "no_time_component",
            "message_en": (
                f"Column {target!r} already looks date-only "
                f"(no HH:MM / 00:00:00 in values; e.g. {sample})."
            ),
            "message_ar": (
                f"العمود {target} باين تاريخ بس من غير ساعة "
                f"(مفيش HH:MM أو 00:00:00 في القيم؛ مثال: {sample})."
            ),
            "column": target,
        }

    out = df.copy()
    parsed = _parse_datetimes(out[target], getattr(meta, "date_format", None))
    # Always persist calendar date strings — never leave Timestamp midnight
    # (UI would show ``2025-03-13 00:00:00`` again).
    date_only = parsed.dt.strftime("%Y-%m-%d")
    unparsed = parsed.isna() & out[target].notna()
    if unparsed.any():
        stripped = (
            out.loc[unparsed, target]
            .map(_value_str)
            .str.replace(_CLOCK_RE.pattern, "", regex=True)
            .str.strip()
        )
        date_only = date_only.astype("string")
        date_only.loc[unparsed] = stripped
    # Keep original only when both parse and strip failed.
    out[target] = date_only.where(date_only.notna() & (date_only != ""), out[target])

    preview = {
        "ok": True,
        "op": "strip_time",
        "column": target,
        "rows_with_time": count,
        "row_count": int(len(df)),
        "preview_en": (
            f"Will strip time-of-day from {count} values in column {target!r} "
            f"(keep calendar date only)."
        ),
        "preview_ar": (
            f"هشيل الساعة/الوقت من {count} قيمة في العمود {target} "
            f"(هفضل التاريخ بس)."
        ),
        "apply_en": (
            f"Stripped time-of-day from column {target!r} ({count} values). "
            "Reload the dashboard if it is open."
        ),
        "apply_ar": (
            f"اتشال الوقت من العمود {target} ({count} قيمة). "
            "حدّث لوحة التحليل لو مفتوحة."
        ),
    }
    if apply:
        preview["dataframe"] = out
    return preview


def _qty_price_series(df: pd.DataFrame, mapping: dict[str, str]) -> pd.Series | None:
    qty_c = mapping.get("quantity")
    price_c = mapping.get("unit_price")
    if qty_c and price_c and qty_c in df.columns and price_c in df.columns:
        return pd.to_numeric(df[qty_c], errors="coerce") * pd.to_numeric(
            df[price_c], errors="coerce"
        )
    qty = price = None
    for c in df.columns:
        n = _norm_col(c)
        if n in {"quantity", "qty"}:
            qty = c
        if n in {"price", "unit price", "unit_price", "unitprice"}:
            price = c
    if qty and price:
        return pd.to_numeric(df[qty], errors="coerce") * pd.to_numeric(
            df[price], errors="coerce"
        )
    return None


def _money_series(df: pd.DataFrame, mapping: dict[str, str]) -> pd.Series | None:
    """Per-row monetary amount: line_amount with qty×price fill for blanks."""
    qty_price = _qty_price_series(df, mapping)
    line = None
    if mapping.get("line_amount") and mapping["line_amount"] in df.columns:
        line = pd.to_numeric(df[mapping["line_amount"]], errors="coerce")
    else:
        for c in df.columns:
            n = _norm_col(c)
            if n in {"linetotal", "line total", "line_amount", "amount", "revenue"}:
                line = pd.to_numeric(df[c], errors="coerce")
                break
    if line is not None and qty_price is not None:
        return line.fillna(qty_price)
    if line is not None:
        return line
    return qty_price


def _invoice_series(df: pd.DataFrame, mapping: dict[str, str]) -> pd.Series | None:
    """Return invoice IDs as strings with blanks as <NA> (never group blanks together)."""
    raw = None
    if mapping.get("invoice") and mapping["invoice"] in df.columns:
        raw = df[mapping["invoice"]]
    else:
        for c in df.columns:
            n = _norm_col(c)
            if n in {
                "invoice",
                "invoiceno",
                "invoice no",
                "invoice number",
                "order id",
                "order_id",
            } or "فاتور" in n:
                raw = df[c]
                break
    if raw is None:
        return None
    as_str = raw.astype("string").str.strip()
    blank = (
        as_str.isna()
        | (as_str == "")
        | as_str.str.lower().isin(["nan", "none", "<na>"])
    )
    return as_str.where(~blank, pd.NA)


def _op_add_invoice_flag(
    df: pd.DataFrame,
    *,
    meta: UploadSessionMeta,
    mapping: dict[str, str],
    new_column: str | None,
    threshold: float | None,
    apply: bool,
    **_: Any,
) -> dict[str, Any]:
    thr = 1000.0 if threshold is None else float(threshold)
    col_name = (new_column or f"invoice_over_{int(thr)}").strip()
    if not col_name or col_name in df.columns:
        base = col_name or "invoice_flag"
        i = 2
        while f"{base}_{i}" in df.columns:
            i += 1
        col_name = base if base not in df.columns else f"{base}_{i}"

    money = _money_series(df, mapping)
    inv = _invoice_series(df, mapping)
    if money is None:
        return {
            "ok": False,
            "error_code": "no_money_column",
            "message_en": "Map quantity+unit price or line amount before adding an invoice value flag.",
            "message_ar": "اربط الكمية وسعر الوحدة أو إجمالي السطر قبل إضافة علم قيمة الفاتورة.",
        }
    if inv is None:
        flags = money > thr
        mode = "row"
    else:
        flags = pd.Series(False, index=df.index)
        valid = inv.notna()
        if valid.any():
            totals = money[valid].groupby(inv[valid]).transform("sum")
            flags.loc[valid] = (totals > thr).to_numpy()
        # Blank invoice IDs: evaluate the row amount alone (do not pool blanks).
        blank = ~valid
        if blank.any():
            flags.loc[blank] = (money[blank] > thr).fillna(False).to_numpy()
        mode = "invoice"

    true_n = int(flags.fillna(False).sum())
    out = df.copy()
    # Store as true/false strings for CSV round-trip clarity
    out[col_name] = flags.fillna(False).map(lambda v: "true" if bool(v) else "false")

    currency = (meta.currency_code or "UNSPECIFIED")
    preview = {
        "ok": True,
        "op": "add_invoice_flag",
        "new_column": col_name,
        "threshold": thr,
        "currency_code": currency,
        "aggregation": mode,
        "true_count": true_n,
        "false_count": int(len(df) - true_n),
        "row_count": int(len(df)),
        "preview_en": (
            f"Will add column {col_name!r}: true when "
            f"{'invoice total' if mode == 'invoice' else 'row amount'} > {thr:g} {currency} "
            f"({true_n} true / {len(df) - true_n} false)."
        ),
        "preview_ar": (
            f"هضيف عمود {col_name}: true لما "
            f"{'إجمالي الفاتورة' if mode == 'invoice' else 'قيمة السطر'} > {thr:g} {currency} "
            f"({true_n} true / {len(df) - true_n} false)."
        ),
        "apply_en": (
            f"Added column {col_name!r} (threshold {thr:g} {currency}; "
            f"{true_n} rows true). Session file updated."
        ),
        "apply_ar": (
            f"اتضاف العمود {col_name} (حد {thr:g} {currency}؛ "
            f"{true_n} صف true). ملف الجلسة اتحدّث."
        ),
    }
    if apply:
        preview["dataframe"] = out
    return preview


def _mapped_source_names(mapping: dict[str, str] | None) -> set[str]:
    return {str(v) for v in (mapping or {}).values() if v}


def _op_drop_column(
    df: pd.DataFrame,
    *,
    column: str | None,
    mapping: dict[str, str] | None = None,
    apply: bool,
    **_: Any,
) -> dict[str, Any]:
    target = _resolve_column(df, column)
    if not target:
        return {
            "ok": False,
            "error_code": "column_not_found",
            "message_en": "Name the column to drop.",
            "message_ar": "سمّي العمود اللي عايز تمسحه.",
        }
    mapped = _mapped_source_names(mapping)
    protected = _protect_key(target) in _PROTECTED_DROP or target in mapped
    if protected or len(df.columns) <= 2:
        return {
            "ok": False,
            "error_code": "protected_column",
            "message_en": f"Refusing to drop protected/mapped column {target!r}.",
            "message_ar": f"مش هقدر أمسح العمود الحساس/المربوط {target}.",
            "column": target,
        }
    out = df.drop(columns=[target])
    preview = {
        "ok": True,
        "op": "drop_column",
        "column": target,
        "row_count": int(len(df)),
        "preview_en": f"Will drop column {target!r} from the session file.",
        "preview_ar": f"همسح العمود {target} من ملف الجلسة.",
        "apply_en": f"Dropped column {target!r}.",
        "apply_ar": f"اتمسح العمود {target}.",
    }
    if apply:
        preview["dataframe"] = out
    return preview


def _op_rename_column(
    df: pd.DataFrame,
    *,
    meta: UploadSessionMeta | None = None,
    column: str | None,
    rename_to: str | None,
    mapping: dict[str, str] | None = None,
    apply: bool,
    **_: Any,
) -> dict[str, Any]:
    target = _resolve_column(df, column)
    new_name = (rename_to or "").strip()
    if not target or not new_name:
        return {
            "ok": False,
            "error_code": "rename_args",
            "message_en": "Provide column and rename_to.",
            "message_ar": "حدد العمود والاسم الجديد.",
        }
    if new_name in df.columns:
        return {
            "ok": False,
            "error_code": "name_exists",
            "message_en": f"Column {new_name!r} already exists.",
            "message_ar": f"العمود {new_name} موجود بالفعل.",
        }
    out = df.rename(columns={target: new_name})
    preview = {
        "ok": True,
        "op": "rename_column",
        "column": target,
        "rename_to": new_name,
        "preview_en": f"Will rename {target!r} → {new_name!r}.",
        "preview_ar": f"هغيّر اسم {target} → {new_name}.",
        "apply_en": f"Renamed {target!r} → {new_name!r}.",
        "apply_ar": f"اتغيّر الاسم {target} → {new_name}.",
    }
    if apply:
        preview["dataframe"] = out
        # Keep session mapping pointed at the new source header.
        src_map = dict(mapping or (meta.column_mapping if meta else None) or {})
        if src_map:
            updated = {
                canon: (new_name if src == target else src) for canon, src in src_map.items()
            }
            if meta is not None:
                meta.column_mapping = updated
            preview["mapping_updated"] = True
    return preview


def _op_cast_numeric(
    df: pd.DataFrame,
    *,
    column: str | None,
    apply: bool,
    **_: Any,
) -> dict[str, Any]:
    target = _resolve_column(df, column)
    if not target:
        return {
            "ok": False,
            "error_code": "column_not_found",
            "message_en": "Name the column to cast to numeric.",
            "message_ar": "سمّي العمود للتحويل لرقم.",
        }
    out = df.copy()
    numeric = pd.to_numeric(out[target], errors="coerce")
    coerced = int(out[target].notna().sum() - numeric.notna().sum())
    out[target] = numeric
    preview = {
        "ok": True,
        "op": "cast_numeric",
        "column": target,
        "non_numeric_to_null": coerced,
        "preview_en": (
            f"Will cast {target!r} to numeric ({coerced} values become empty if invalid)."
        ),
        "preview_ar": (
            f"هحوّل {target} لرقم ({coerced} قيمة هتبقى فاضية لو مش رقم)."
        ),
        "apply_en": f"Cast {target!r} to numeric.",
        "apply_ar": f"اتحوّل {target} لرقم.",
    }
    if apply:
        preview["dataframe"] = out
    return preview


def _op_fill_constant(
    df: pd.DataFrame,
    *,
    column: str | None,
    fill_value: str | None,
    apply: bool,
    **_: Any,
) -> dict[str, Any]:
    target = _resolve_column(df, column)
    if not target:
        return {
            "ok": False,
            "error_code": "column_not_found",
            "message_en": "Name the column to fill.",
            "message_ar": "سمّي العمود للملء.",
        }
    if fill_value is None or str(fill_value) == "":
        return {
            "ok": False,
            "error_code": "missing_fill_value",
            "message_en": "Provide fill_value (constant only — no invented IDs).",
            "message_ar": "حدد قيمة الملء الثابتة (من غير اختراع أرقام هوية).",
        }
    # Refuse filling customer/invoice-like columns with invented patterns
    if any(k in _norm_col(target) for k in ("customer", "invoice", "زبون", "عميل", "فاتور")):
        return {
            "ok": False,
            "error_code": "manual_only_column",
            "message_en": "Customer/invoice columns cannot be constant-filled by the assistant.",
            "message_ar": "أعمدة الزبون/الفاتورة مش بتتملأ بثابت من المساعد.",
            "column": target,
        }
    out = df.copy()
    blank = out[target].isna() | (out[target].astype(str).str.strip() == "")
    n = int(blank.sum())
    out.loc[blank, target] = str(fill_value)
    preview = {
        "ok": True,
        "op": "fill_constant",
        "column": target,
        "fill_value": str(fill_value),
        "rows_filled": n,
        "preview_en": f"Will fill {n} blank cells in {target!r} with {fill_value!r}.",
        "preview_ar": f"هاملأ {n} خلية فاضية في {target} بالقيمة {fill_value}.",
        "apply_en": f"Filled {n} blanks in {target!r}.",
        "apply_ar": f"اتملت {n} خلية في {target}.",
    }
    if apply:
        preview["dataframe"] = out
    return preview


def parse_transform_intent(
    question: str,
    *,
    pending: dict[str, Any] | None = None,
    columns: list[str] | None = None,
    meta: UploadSessionMeta | None = None,
    lang: str = "en",
    allow_llm: bool = True,
) -> dict[str, Any] | None:
    """Compile AR/EN question into a session transform (legacy op or general plan).

    Prefers Gemini → allowlisted mutate DSL when configured and the ask looks like
    a file reshape; falls back to deterministic compile_plan.
    """
    from api.services import plan_intent, session_mutate

    q = (question or "").strip()
    if not q:
        return None

    cols = list(columns or [])
    if not cols and meta is not None:
        try:
            cols = [str(c) for c in _read_source(meta).columns]
        except Exception:  # noqa: BLE001
            cols = list((meta.column_mapping or {}).values())

    # Bare «طبّق» / apply against a pending preview — no LLM needed.
    bare = {
        "apply",
        "do it",
        "confirm",
        "yes",
        "ok",
        "طبّق",
        "طبق",
        "نفّذ",
        "نفذ",
        "موافق",
        "أيوه",
        "ايوه",
        "تمام",
    }
    if pending and q.lower() in bare:
        out = dict(pending)
        out["confirm_apply"] = True
        return out

    # Prefer LLM understanding for bilingual reshape asks when configured.
    if allow_llm and plan_intent.soft_reshape_cue(q):
        llm_plan = plan_intent.llm_compile_plan(q, columns=cols, lang=lang)
        if llm_plan is not None:
            return llm_plan

    planned = session_mutate.compile_plan(q, columns=cols, pending=pending)
    if planned is None:
        return None
    if planned.get("op") == "refuse":
        return planned
    return planned
