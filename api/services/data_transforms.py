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


def _has_time_component(series: pd.Series) -> tuple[bool, int]:
    """Return (any_time_present, count_with_time)."""
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    valid = parsed.dropna()
    if valid.empty:
        # string clock patterns
        as_str = series.astype(str)
        hit = as_str.str.contains(r"\d{1,2}:\d{2}", regex=True, na=False)
        return bool(hit.any()), int(hit.sum())
    with_time = (valid.dt.hour != 0) | (valid.dt.minute != 0) | (valid.dt.second != 0)
    # also count string times even when midnight
    as_str = series.astype(str)
    clock = as_str.str.contains(r"\d{1,2}:\d{2}", regex=True, na=False)
    count = int(with_time.sum()) + int((clock & parsed.isna()).sum())
    # If strings contain clock, count those too even when time is 00:00
    count = max(count, int(clock.sum()))
    return count > 0, count


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

    mapping = meta.column_mapping or {}
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
        # Stash resolved args so a bare «طبّق» can finish the job.
        from api.services import upload_store

        meta.pending_transform = {
            "op": op,
            "column": result.get("column") or column,
            "new_column": result.get("new_column") or new_column,
            "threshold": result.get("threshold", threshold),
            "fill_value": fill_value,
            "rename_to": result.get("rename_to") or rename_to,
        }
        upload_store.save_meta(meta)
        return result

    # Apply
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

    meta.pending_transform = None
    upload_store.save_meta(meta)
    out = {k: v for k, v in applied.items() if k != "dataframe"}
    out["ok"] = True
    out["mutated"] = True
    out["preview_only"] = False
    out["message_en"] = applied.get("apply_en") or "Transform applied to the session file."
    out["message_ar"] = applied.get("apply_ar") or "التحويل اتطبّق على ملف الجلسة."
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
        target = best
    if not target or target not in df.columns:
        return {
            "ok": False,
            "error_code": "no_datetime_column",
            "message_en": "No datetime column with a time-of-day component was found.",
            "message_ar": "مفيش عمود تاريخ فيه جزء وقت/ساعة.",
        }

    has, count = _has_time_component(df[target])
    if not has:
        return {
            "ok": False,
            "error_code": "no_time_component",
            "message_en": f"Column {target!r} already looks date-only.",
            "message_ar": f"العمود {target} أصلاً تاريخ من غير وقت.",
            "column": target,
        }

    out = df.copy()
    date_fmt = getattr(meta, "date_format", None)
    parsed = _parse_datetimes(out[target], date_fmt)
    # Confirmed format → ISO date. Unconfirmed → strip clock text only (preserve day/month order).
    if (date_fmt or "").strip().lower() in {"dayfirst", "monthfirst", "iso"}:
        date_only = parsed.dt.strftime("%Y-%m-%d")
        unparsed = parsed.isna() & out[target].notna()
        if unparsed.any():
            stripped = (
                out.loc[unparsed, target]
                .astype(str)
                .str.replace(r"\s+\d{1,2}:\d{2}(:\d{2})?(\.\d+)?", "", regex=True)
            )
            date_only = date_only.astype("string")
            date_only.loc[unparsed] = stripped
        out[target] = date_only.where(date_only.notna(), out[target])
    else:
        out[target] = (
            out[target]
            .astype(str)
            .str.replace(r"\s+\d{1,2}:\d{2}(:\d{2})?(\.\d+)?", "", regex=True)
        )

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


_BARE_CONFIRM = frozenset(
    {
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
)


def _threshold_from_question(q: str, *, default: float = 1000.0) -> float:
    """Prefer a number near comparison words; else default (avoid years/counts)."""
    compact = q.replace(",", "")
    near = re.search(
        r"(?:[><≥≤]|أكبر من|اكبر من|أكبر|اكبر|فوق|أكثر من|اكثر من|"
        r"above|greater than|over|more than|at least|>=|>)\s*"
        r"(\d+(?:\.\d+)?)",
        compact,
        re.I,
    )
    if near:
        return float(near.group(1))
    trailing = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:جنيه|جنية|EGP|GBP|USD|EUR|SAR|AED)?\s*$",
        compact,
        re.I,
    )
    if trailing:
        return float(trailing.group(1))
    # Explicit thousand words without digits
    if any(k in q for k in ("ألف", "الف", "thousand")):
        return 1000.0
    return default


def parse_transform_intent(
    question: str, *, pending: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Heuristic intent parser for grounded fallback (AR/EN)."""
    q = (question or "").strip()
    if not q:
        return None
    q_low = q.lower()

    # Bare confirm of a previous preview
    if pending and q_low in _BARE_CONFIRM:
        out = dict(pending)
        out["confirm_apply"] = True
        return out

    # Imperative apply cues (exclude op verbs that also describe the transform).
    apply_words = (
        "طبّق",
        "طبق",
        "نفّذ",
        "نفذ",
        "اعمل",
        "اعملي",
        "apply",
        "do it",
        "please do",
        "please apply",
    )
    wants_apply = any(w in q_low or w in q for w in apply_words)
    # Explicit strip/add/drop verbs imply apply when paired with a clear op below.
    imperative_mutate = any(
        w in q_low or w in q
        for w in (
            "شيل الساعة",
            "امسح الساعة",
            "إمسح الساعة",
            "strip time",
            "remove time",
            "ضيف عمود",
            "أضف عمود",
            "add a column",
            "add column",
            "add a boolean",
            "create a flag",
        )
    )
    wants_apply = wants_apply or imperative_mutate

    # Strip time from dates — require an explicit strip/remove cue + date cue.
    strip_cue = any(
        k in q_low or k in q
        for k in (
            "شيل الساعة",
            "امسح الساعة",
            "إمسح الساعة",
            "من غير وقت",
            "من غير الساعة",
            "تاريخ فقط",
            "date only",
            "strip time",
            "remove time",
            "without time",
            "time of day",
            "hour from",
            "from timestamp",
        )
    )
    date_cue = any(
        k in q_low or k in q
        for k in ("تاريخ", "date", "datetime", "timestamp", "invoice date", "تاريخ الفاتور")
    )
    if strip_cue and date_cue:
        return {"op": "strip_time", "confirm_apply": wants_apply}

    # Invoice flag / boolean column — need column/flag language + value comparison.
    col_cue = any(
        k in q_low or k in q
        for k in (
            "عمود",
            "column",
            "flag",
            "boolean",
            "true/false",
            "true false",
            "علم",
        )
    )
    value_cue = any(
        k in q_low or k in q
        for k in (
            "أكبر",
            "اكبر",
            "فوق",
            "أكثر",
            "اكثر",
            "above",
            "greater",
            "over ",
            "more than",
            ">",
            "1000",
            "ألف",
            "الف",
        )
    )
    invoice_cue = any(k in q_low or k in q for k in ("فاتور", "invoice", "order total", "إجمالي"))
    if col_cue and value_cue and (invoice_cue or "true" in q_low):
        thr = _threshold_from_question(q, default=1000.0)
        new_col = None
        named = re.search(
            r"(?:اسمه|اسمها|name(?:d)?|called)\s+[\"']?([A-Za-z0-9_\u0600-\u06FF]+)[\"']?",
            q,
            re.I,
        )
        if named:
            new_col = named.group(1)
        return {
            "op": "add_invoice_flag",
            "threshold": thr,
            "new_column": new_col,
            "confirm_apply": wants_apply,
        }

    if any(k in q_low for k in ("drop column", "delete column", "remove column")) or (
        any(k in q for k in ("امسح عمود", "احذف عمود", "شيل عمود"))
    ):
        quoted = re.search(r"[\"']([^\"']+)[\"']", q)
        return {
            "op": "drop_column",
            "column": quoted.group(1) if quoted else None,
            "confirm_apply": wants_apply,
        }

    # Rename only when both sides are present (avoid intercepting vague "rename" asks).
    rename_m = re.search(
        r"(?:rename|سمّي|سمي)\s+[\"']?([^\"'\s]+)[\"']?\s+(?:to|→|->|ل|إلى|الى)\s+[\"']?([^\"'\s]+)[\"']?",
        q,
        re.I,
    )
    if rename_m:
        return {
            "op": "rename_column",
            "column": rename_m.group(1),
            "rename_to": rename_m.group(2),
            "confirm_apply": wants_apply,
        }

    return None
