"""General session-file mutation plans (constrained DSL — no arbitrary eval).

Natural-language intents compile to a list of typed steps that run only on the
temporary upload dataframe. Refuses shell/network/demo/retrain/exfil paths.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

import pandas as pd

# --- Unsafe / out-of-scope cues (refuse, do not plan) ---
_UNSAFE = re.compile(
    r"(?i)\b("
    r"retrain|fine[\s-]?tune|train\s+model|shell|bash|powershell|curl|wget|"
    r"http://|https://|ftp://|socket|subprocess|os\.system|rm\s+-rf|"
    r"drop\s+database|delete\s+session|wipe\s+session|exfiltrat|"
    r"send\s+(all\s+)?raw\s+rows|email\s+the\s+file|upload\s+to\s+s3|"
    r"demo\s+data|uk\s+demo|academic\s+pdf"
    r")\b|"
    r"(أعد تدريب|تدريب الموديل|شيل الجلسة|امسح الجلسة|ابعت الملف|ديمو|العينة البريطانية)"
)

PLAN_OPS = frozenset(
    {
        "filter",
        "sort",
        "assign",
        "replace",
        "split",
        "merge",
        "floor_date",
        "strip_time",
        "fillna",
        "cast",
        "rename",
        "drop",
        "parse_currency",
        "groupby_agg",
        "dedupe",
        "clip",
    }
)

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}


def is_unsafe_request(question: str) -> bool:
    return bool(_UNSAFE.search(question or ""))


def _norm(name: object) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def resolve_column(df: pd.DataFrame, requested: str | None) -> str | None:
    if not requested:
        return None
    want = _norm(requested)
    for c in df.columns:
        if _norm(c) == want or _norm(c).replace(" ", "") == want.replace(" ", ""):
            return str(c)
    for c in df.columns:
        if want and want in _norm(c):
            return str(c)
    return None


def _col_map(df: pd.DataFrame) -> dict[str, str]:
    """Map normalized / spaced / underscored names → real column."""
    out: dict[str, str] = {}
    for c in df.columns:
        s = str(c)
        out[_norm(s)] = s
        out[_norm(s).replace(" ", "")] = s
        out[_norm(s).replace(" ", "_")] = s
        # bare identifier form used in expressions
        ident = re.sub(r"[^\w]", "_", s)
        out[ident.lower()] = s
        out[ident] = s
    return out


class SafeExprError(ValueError):
    pass


def _as_numeric(val: Any) -> Any:
    if isinstance(val, pd.Series):
        if pd.api.types.is_numeric_dtype(val):
            return val
        return pd.to_numeric(val, errors="coerce")
    if isinstance(val, (int, float, bool)):
        return val
    try:
        return float(val)
    except (TypeError, ValueError):
        return val


def _numeric_pair(left: Any, right: Any) -> tuple[Any, Any]:
    return _as_numeric(left), _as_numeric(right)


def eval_expr(df: pd.DataFrame, expr: str) -> pd.Series | Any:
    """Evaluate a constrained expression against dataframe columns (no eval)."""
    text = (expr or "").strip()
    if not text or len(text) > 500:
        raise SafeExprError("Expression empty or too long")
    # Allow Excel-ish AND/OR and = for equality in simple cases
    text = re.sub(r"\bAND\b", " and ", text, flags=re.I)
    text = re.sub(r"\bOR\b", " or ", text, flags=re.I)
    text = re.sub(r"\bNOT\b", " not ", text, flags=re.I)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise SafeExprError(f"Invalid expression syntax: {exc}") from exc

    cols = _col_map(df)

    def call_fn(name: str, args: list[Any]) -> Any:
        n = name.lower()
        if n == "abs" and len(args) == 1:
            return abs(args[0]) if not isinstance(args[0], pd.Series) else args[0].abs()
        if n == "round" and 1 <= len(args) <= 2:
            nd = int(args[1]) if len(args) == 2 else 0
            return args[0].round(nd) if isinstance(args[0], pd.Series) else round(args[0], nd)
        if n in {"lower", "upper", "strip"} and len(args) == 1:
            s = args[0].astype(str) if isinstance(args[0], pd.Series) else str(args[0])
            if n == "lower":
                return s.str.lower() if isinstance(s, pd.Series) else s.lower()
            if n == "upper":
                return s.str.upper() if isinstance(s, pd.Series) else s.upper()
            return s.str.strip() if isinstance(s, pd.Series) else s.strip()
        if n == "isna" and len(args) == 1:
            return args[0].isna() if isinstance(args[0], pd.Series) else pd.isna(args[0])
        if n == "notna" and len(args) == 1:
            return args[0].notna() if isinstance(args[0], pd.Series) else pd.notna(args[0])
        if n == "to_number" and len(args) == 1:
            return pd.to_numeric(args[0], errors="coerce")
        if n == "to_str" and len(args) == 1:
            return args[0].astype(str) if isinstance(args[0], pd.Series) else str(args[0])
        if n in {"year", "month", "day"} and len(args) == 1:
            dt = pd.to_datetime(args[0], errors="coerce")
            return getattr(dt.dt, n)
        if n == "floor_month" and len(args) == 1:
            dt = pd.to_datetime(args[0], errors="coerce")
            return dt.dt.to_period("M").dt.to_timestamp()
        if n == "coalesce" and len(args) >= 2:
            out = args[0]
            for a in args[1:]:
                out = out.fillna(a) if isinstance(out, pd.Series) else (a if pd.isna(out) else out)
            return out
        raise SafeExprError(f"Function not allowed: {name}")

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            key = node.id
            if key in {"True", "False", "None"}:
                return {"True": True, "False": False, "None": None}[key]
            # column lookup
            real = cols.get(key) or cols.get(key.lower()) or cols.get(_norm(key))
            if real is None:
                raise SafeExprError(f"Unknown column or name: {key}")
            return df[real]
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            val = visit(node.operand)
            if isinstance(node.op, ast.Not):
                return ~val if isinstance(val, pd.Series) else (not val)
            return _UNARY[type(node.op)](val)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = visit(node.left), visit(node.right)
            if type(node.op) in {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow}:
                left, right = _numeric_pair(left, right)
            return _BINOPS[type(node.op)](left, right)
        if isinstance(node, ast.BoolOp):
            values = [visit(v) for v in node.values]
            out = values[0]
            for v in values[1:]:
                if isinstance(node.op, ast.And):
                    out = out & v
                else:
                    out = out | v
            return out
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            result = None
            for op, comp in zip(node.ops, node.comparators, strict=True):
                right = visit(comp)
                if type(op) not in _CMPOPS:
                    raise SafeExprError("Comparison not allowed")
                if type(op) in {ast.Lt, ast.LtE, ast.Gt, ast.GtE}:
                    left_n, right_n = _numeric_pair(left, right)
                    # Only coerce when the other side is numeric-ish
                    if isinstance(right, (int, float)) or isinstance(left, (int, float)):
                        left, right = left_n, right_n
                    elif isinstance(left, pd.Series) and isinstance(right, pd.Series):
                        left, right = left_n, right_n
                piece = _CMPOPS[type(op)](left, right)
                result = piece if result is None else (result & piece)
                left = right
            return result
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise SafeExprError("Only simple function calls allowed")
            if node.keywords:
                raise SafeExprError("Keyword args not allowed in expressions")
            return call_fn(node.func.id, [visit(a) for a in node.args])
        if isinstance(node, ast.IfExp):
            cond = visit(node.test)
            body = visit(node.body)
            orelse = visit(node.orelse)
            if isinstance(cond, pd.Series):
                if isinstance(body, pd.Series) and isinstance(orelse, pd.Series):
                    return body.where(cond, orelse)
                return pd.Series(
                    [
                        (body.iloc[i] if isinstance(body, pd.Series) else body)
                        if bool(cond.iloc[i])
                        else (orelse.iloc[i] if isinstance(orelse, pd.Series) else orelse)
                        for i in range(len(cond))
                    ],
                    index=df.index,
                )
            return body if cond else orelse
        raise SafeExprError(f"Disallowed syntax: {type(node).__name__}")

    return visit(tree)


def execute_steps(
    df: pd.DataFrame,
    steps: list[dict[str, Any]],
    *,
    mapping: dict[str, str] | None = None,
    protected_drop: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Run a plan on a copy of df. Returns ok, dataframe, summary, impact."""
    if not steps:
        return {"ok": False, "error_code": "empty_plan", "message_en": "Empty plan."}
    if len(steps) > 12:
        return {"ok": False, "error_code": "plan_too_long", "message_en": "Max 12 steps per plan."}

    out = df.copy()
    mapping = dict(mapping or {})
    notes: list[str] = []
    rows_before = len(out)
    cols_before = list(out.columns)

    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            return {"ok": False, "error_code": "bad_step", "message_en": f"Step {i} is not an object."}
        op = str(raw.get("op") or "").strip().lower()
        if op not in PLAN_OPS:
            return {
                "ok": False,
                "error_code": "unknown_step",
                "message_en": f"Unknown step op {op!r}. Allowed: {sorted(PLAN_OPS)}",
            }
        try:
            out, note = _run_step(out, op, raw, mapping=mapping, protected_drop=protected_drop)
            notes.append(note)
        except SafeExprError as exc:
            return {
                "ok": False,
                "error_code": "expr_error",
                "message_en": str(exc),
                "message_ar": f"تعبير غير مسموح: {exc}",
                "step": i,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error_code": "step_failed",
                "message_en": f"Step {i} ({op}) failed: {exc}",
                "message_ar": f"الخطوة {i} فشلت: {exc}",
                "step": i,
            }

    rows_after = len(out)
    cols_after = list(out.columns)
    added = [c for c in cols_after if c not in cols_before]
    removed = [c for c in cols_before if c not in cols_after]
    return {
        "ok": True,
        "dataframe": out,
        "mapping": mapping,
        "notes": notes,
        "impact": {
            "rows_before": rows_before,
            "rows_after": rows_after,
            "rows_delta": rows_after - rows_before,
            "cols_added": added,
            "cols_removed": removed,
            "col_count_before": len(cols_before),
            "col_count_after": len(cols_after),
        },
        "preview_en": "; ".join(notes),
        "preview_ar": "؛ ".join(notes),
        "apply_en": "Applied: " + "; ".join(notes),
        "apply_ar": "اتطبّق: " + "؛ ".join(notes),
    }


def _run_step(
    df: pd.DataFrame,
    op: str,
    step: dict[str, Any],
    *,
    mapping: dict[str, str],
    protected_drop: frozenset[str] | None,
) -> tuple[pd.DataFrame, str]:
    if op == "filter":
        mask = eval_expr(df, str(step.get("expr") or ""))
        if not isinstance(mask, pd.Series):
            raise SafeExprError("filter expr must yield a boolean series")
        kept = df[mask.fillna(False)].copy()
        return kept, f"filter kept {len(kept)}/{len(df)} rows"

    if op == "sort":
        by = step.get("by") or step.get("columns") or []
        if isinstance(by, str):
            by = [by]
        cols = [resolve_column(df, c) for c in by]
        if not cols or any(c is None for c in cols):
            raise SafeExprError("sort: name existing columns")
        asc = step.get("ascending", True)
        if isinstance(asc, list):
            ascending = [bool(x) for x in asc]
        else:
            ascending = bool(asc)
        return df.sort_values(cols, ascending=ascending).reset_index(drop=True), f"sorted by {cols}"

    if op == "assign":
        name = str(step.get("column") or step.get("new_column") or "").strip()
        expr = str(step.get("expr") or "")
        if not name or not expr:
            raise SafeExprError("assign needs column + expr")
        val = eval_expr(df, expr)
        out = df.copy()
        if isinstance(val, pd.Series) and val.dtype == bool:
            out[name] = val.fillna(False).map(lambda v: "true" if bool(v) else "false")
        else:
            out[name] = val
        return out, f"assign {name} = {expr}"

    if op == "replace":
        col = resolve_column(df, step.get("column"))
        if not col:
            raise SafeExprError("replace: column not found")
        out = df.copy()
        old, new = step.get("old"), step.get("new")
        out[col] = out[col].replace(old, new)
        return out, f"replace in {col}: {old!r}→{new!r}"

    if op == "split":
        col = resolve_column(df, step.get("column"))
        into = step.get("into") or []
        sep = str(step.get("sep") if step.get("sep") is not None else ",")
        if not col or not into or len(into) < 2:
            raise SafeExprError("split needs column + into[>=2]")
        parts = df[col].astype(str).str.split(sep, n=len(into) - 1, expand=True)
        out = df.copy()
        for i, name in enumerate(into):
            out[str(name)] = parts[i] if i in parts.columns else ""
        return out, f"split {col} → {list(into)}"

    if op == "merge":
        cols_in = step.get("columns") or []
        into = str(step.get("into") or step.get("column") or "").strip()
        sep = str(step.get("sep") if step.get("sep") is not None else " ")
        resolved = [resolve_column(df, c) for c in cols_in]
        if not into or not resolved or any(c is None for c in resolved):
            raise SafeExprError("merge needs columns + into")
        out = df.copy()
        series = [out[c].astype(str) for c in resolved]
        merged = series[0]
        for s in series[1:]:
            merged = merged + sep + s
        out[into] = merged
        return out, f"merge {resolved} → {into}"

    if op == "floor_date":
        col = resolve_column(df, step.get("column"))
        to = str(step.get("to") or "month").lower()
        if not col:
            raise SafeExprError("floor_date: column not found")
        dt = pd.to_datetime(df[col], errors="coerce")
        out = df.copy()
        if to == "year":
            out[col] = dt.dt.to_period("Y").dt.to_timestamp().dt.strftime("%Y-%m-%d")
        elif to == "day":
            out[col] = dt.dt.strftime("%Y-%m-%d")
        else:
            out[col] = dt.dt.to_period("M").dt.to_timestamp().dt.strftime("%Y-%m-%d")
        return out, f"floor_date {col} to {to}"

    if op == "strip_time":
        col = resolve_column(df, step.get("column"))
        if not col:
            # best-effort first date-like
            for c in df.columns:
                if any(k in _norm(c) for k in ("date", "time", "تاريخ")):
                    col = str(c)
                    break
        if not col:
            raise SafeExprError("strip_time: no date column")
        out = df.copy()
        # Persist YYYY-MM-DD strings so UI never re-shows midnight ``00:00:00``.
        parsed = pd.to_datetime(out[col], errors="coerce", format="mixed")
        date_only = parsed.dt.strftime("%Y-%m-%d")
        unparsed = parsed.isna() & out[col].notna()
        if unparsed.any():
            stripped = (
                out.loc[unparsed, col]
                .map(lambda v: "" if pd.isna(v) else str(v))
                .str.replace(r"\d{1,2}:\d{2}(:\d{2})?(\.\d+)?", "", regex=True)
                .str.strip()
            )
            date_only = date_only.astype("string")
            date_only.loc[unparsed] = stripped
        out[col] = date_only.where(date_only.notna() & (date_only != ""), out[col])
        return out, f"strip_time on {col}"

    if op == "fillna":
        col = resolve_column(df, step.get("column"))
        if not col:
            raise SafeExprError("fillna: column not found")
        # Refuse inventing IDs
        if any(k in _norm(col) for k in ("customer", "invoice", "email", "phone", "زبون", "فاتور")):
            if step.get("value") not in (None, "", 0, "0"):
                raise SafeExprError("Cannot invent values for identity-like columns")
        out = df.copy()
        method = str(step.get("method") or "").lower()
        if method == "ffill":
            out[col] = out[col].ffill()
        elif method == "bfill":
            out[col] = out[col].bfill()
        else:
            out[col] = out[col].fillna(step.get("value"))
        return out, f"fillna {col}"

    if op == "cast":
        col = resolve_column(df, step.get("column"))
        to = str(step.get("to") or "number").lower()
        if not col:
            raise SafeExprError("cast: column not found")
        out = df.copy()
        if to in {"number", "numeric", "float", "int"}:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        elif to in {"str", "string", "text"}:
            out[col] = out[col].astype(str)
        else:
            raise SafeExprError(f"cast to {to} not allowed")
        return out, f"cast {col} to {to}"

    if op == "rename":
        col = resolve_column(df, step.get("column"))
        new = str(step.get("rename_to") or step.get("to") or "").strip()
        if not col or not new:
            raise SafeExprError("rename needs column + rename_to")
        if new in df.columns:
            raise SafeExprError(f"Column {new} already exists")
        out = df.rename(columns={col: new})
        for canon, src in list(mapping.items()):
            if src == col:
                mapping[canon] = new
        return out, f"rename {col} → {new}"

    if op == "drop":
        col = resolve_column(df, step.get("column"))
        if not col:
            raise SafeExprError("drop: column not found")
        key = re.sub(r"[\s_]+", "", _norm(col))
        prot = protected_drop or frozenset()
        if key in prot or col in mapping.values():
            raise SafeExprError(f"Refusing to drop protected/mapped column {col}")
        if len(df.columns) <= 2:
            raise SafeExprError("Refusing to drop when fewer than 3 columns remain")
        return df.drop(columns=[col]), f"drop {col}"

    if op == "parse_currency":
        col = resolve_column(df, step.get("column"))
        if not col:
            raise SafeExprError("parse_currency: column not found")
        out = df.copy()
        cleaned = (
            out[col]
            .astype(str)
            .str.replace(r"[^\d.\-]", "", regex=True)
        )
        out[col] = pd.to_numeric(cleaned, errors="coerce")
        return out, f"parse_currency {col}"

    if op == "groupby_agg":
        # Add a column = aggregation of value_col grouped by group_col (transform).
        group = resolve_column(df, step.get("group_by") or step.get("group"))
        value = resolve_column(df, step.get("value") or step.get("column"))
        how = str(step.get("agg") or "sum").lower()
        into = str(step.get("into") or step.get("new_column") or f"{value}_{how}_by_{group}")
        if not group or not value:
            raise SafeExprError("groupby_agg needs group_by + value")
        if how not in {"sum", "mean", "count", "min", "max"}:
            raise SafeExprError("groupby_agg agg must be sum|mean|count|min|max")
        out = df.copy()
        num = pd.to_numeric(out[value], errors="coerce")
        out[into] = num.groupby(out[group]).transform(how)
        return out, f"groupby_agg {how}({value}) by {group} → {into}"

    if op == "dedupe":
        subset = step.get("subset") or step.get("columns")
        if subset:
            if isinstance(subset, str):
                subset = [subset]
            cols = [resolve_column(df, c) for c in subset]
            if any(c is None for c in cols):
                raise SafeExprError("dedupe: column not found")
            kept = df.drop_duplicates(subset=cols, keep=str(step.get("keep") or "first"))
        else:
            kept = df.drop_duplicates(keep=str(step.get("keep") or "first"))
        return kept.reset_index(drop=True), f"dedupe → {len(kept)} rows"

    if op == "clip":
        col = resolve_column(df, step.get("column"))
        if not col:
            raise SafeExprError("clip: column not found")
        lo = step.get("min")
        hi = step.get("max")
        out = df.copy()
        out[col] = pd.to_numeric(out[col], errors="coerce").clip(lower=lo, upper=hi)
        return out, f"clip {col} to [{lo}, {hi}]"

    raise SafeExprError(f"Unhandled op {op}")


_STRIP_TIME_PHRASES = (
    "شيل الساعة",
    "شيل الساعات",
    "شيل الوقت",
    "امسح الساعة",
    "امسح الساعات",
    "امسح الوقت",
    "من غير وقت",
    "من غير الساعة",
    "بدون وقت",
    "بدون الساعة",
    "الوقت بالساعات",
    "بالساعات",
    "تاريخ فقط",
    "00:00:00",
    "00:00",
    "strip time",
    "strip hours",
    "strip the time",
    "strip the hours",
    "remove time",
    "remove hours",
    "remove the time",
    "remove the hours",
    "without time",
    "without the time",
    "date only",
    "dates only",
    "time of day",
)


def _wants_strip_time(q: str, q_low: str) -> bool:
    if any(p in q or p in q_low for p in _STRIP_TIME_PHRASES):
        return True
    # Loose EN: "strip/remove … time/hours" with words in between.
    if re.search(
        r"(?i)\b(strip|remove|drop|clear)\b.{0,24}\b(time|hours?|timestamp)\b",
        q_low,
    ):
        return True
    # Loose AR: شيل/امسح … وقت/ساعة
    if re.search(r"(شيل|امسح|احذف).{0,20}(وقت|ساعة|الساعات)", q):
        return True
    return False


def _strip_time_is_imperative(q: str, q_low: str) -> bool:
    """Imperative strip-time commands apply immediately (no extra «طبّق»)."""
    if any(
        p in q or p in q_low
        for p in (
            "شيل الساعة",
            "شيل الساعات",
            "شيل الوقت",
            "امسح الساعة",
            "امسح الساعات",
            "امسح الوقت",
            "strip time",
            "strip hours",
            "strip the time",
            "remove time",
            "remove hours",
            "remove the time",
            "00:00:00",
            "00:00",
        )
    ):
        return True
    if re.search(
        r"(?i)\b(strip|remove)\b.{0,24}\b(time|hours?|00:00)\b",
        q_low,
    ):
        return True
    if re.search(r"(شيل|امسح).{0,24}(وقت|ساعة|الساعات|00:00)", q):
        return True
    return False


def looks_like_mutation(question: str) -> bool:
    """True when the user is asking to reshape the file (not analytics Q&A)."""
    q = question or ""
    q_low = q.lower()
    # Avoid intercepting analytics ("compare this month", "أي عمود ناقص", …).
    if re.search(
        r"(?i)\b(compar|توقع|forecast|kpi|أعلى منتج|top product|قارن|مبيعات الشهر|segment)\b",
        q,
    ):
        return False
    if _wants_strip_time(q, q_low):
        return True
    cues = (
        "filter ",
        "sort by",
        "order by",
        "replace ",
        "split ",
        "merge ",
        "fillna",
        "fill na",
        "group by",
        "groupby",
        "dedupe",
        "drop duplicates",
        "clip ",
        "floor to month",
        "parse currency",
        "cast to",
        "drop column",
        "add column",
        "new column",
        "keep only",
        "delete rows",
        "رتب حسب",
        "فلتر ",
        "استبدل",
        "اقسم ",
        "ادمج ",
        "املأ الفاضي",
        "ضيف عمود",
        "أضف عمود",
        "عمود جديد",
        "أول الشهر",
        "امسح عمود",
        "احذف عمود",
        "شيل المكرر",
        "احذف التكرار",
        "حوّل لرقم",
    )
    return any(c in q_low or c in q for c in cues)


def compile_plan(
    question: str,
    *,
    columns: list[str] | None = None,
    pending: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compile AR/EN question into a session mutation plan (or bare confirm)."""
    q = (question or "").strip()
    if not q:
        return None

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

    if is_unsafe_request(q):
        return {
            "op": "refuse",
            "confirm_apply": False,
            "error_code": "unsafe_request",
            "message_en": (
                "I can only reshape this upload session file. "
                "I won’t retrain models, touch demo data, run shell/network, or wipe the session."
            ),
            "message_ar": (
                "أقدر أعدّل ملف الجلسة المرفوع بس. "
                "مش هأعيد تدريب موديل ولا ألمس الديمو ولا أشغّل أوامر/شبكة ولا أمسح الجلسة."
            ),
        }

    q_low = q.lower()
    apply_words = ("طبّق", "طبق", "نفّذ", "نفذ", "اعمل", "اعملي", "apply", "do it", "please do")
    wants_apply = any(w in q_low or w in q for w in apply_words)
    cols = columns or []

    def col_named(*cands: str) -> str | None:
        for cand in cands:
            for c in cols:
                if _norm(c) == _norm(cand) or _norm(cand) in _norm(c):
                    return str(c)
        return None

    steps: list[dict[str, Any]] = []

    # Meta-aware legacy ops (date_format, blank-invoice pooling rules, …)
    # Match spoken AR/EN: «شيل الوقت بالساعات», «remove the time», «strip hours»…
    if _wants_strip_time(q, q_low) and (
        any(k in q or k in q_low for k in ("تاريخ", "date", "timestamp", "datetime", "عمود"))
        or "00:00" in q_low
    ):
        return {
            "op": "strip_time",
            "column": col_named("InvoiceDate", "date", "تاريخ"),
            "confirm_apply": wants_apply
            or _strip_time_is_imperative(q, q_low)
            or "00:00" in q_low,
        }

    if (
        any(k in q or k in q_low for k in ("عمود", "column", "flag", "boolean", "علم"))
        and any(
            k in q or k in q_low
            for k in ("أكبر", "اكبر", "فوق", "above", "greater", "over ", ">", "1000", "ألف", "الف")
        )
        and any(k in q or k in q_low for k in ("فاتور", "invoice", "true"))
    ):
        thr = 1000.0
        m = re.search(
            r"(?:[><]|أكبر من|اكبر من|فوق|above|over|greater than)\s*(\d+(?:\.\d+)?)",
            q.replace(",", ""),
            re.I,
        )
        if m:
            thr = float(m.group(1))
        elif re.search(r"\b1000\b|ألف|الف", q):
            thr = 1000.0
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
            "confirm_apply": wants_apply
            or any(w in q for w in ("ضيف عمود", "أضف عمود", "add column", "add a column", "add a boolean")),
        }

    # Filter rows: keep only / filter where / فلتر
    filt = re.search(
        r"(?:filter|keep only|where|فلتر|صف[ّي]*|خليه? بس)\s+(.+)$",
        q,
        re.I,
    )
    if filt and not steps:
        expr = _nl_condition_to_expr(filt.group(1), cols)
        if expr:
            steps.append({"op": "filter", "expr": expr})
            wants_apply = wants_apply or any(
                w in q for w in ("امسح", "احذف الصفوف", "delete rows", "keep only")
            )

    # Sort
    if any(k in q_low or k in q for k in ("sort", "order by", "رتب", "ترتيب")) and not steps:
        # "sort by X" / "رتب حسب X"
        m = re.search(
            r"(?:sort(?:ed)?\s+by|order\s+by|رتب حسب|ترتيب حسب|رتّب على)\s+[\"']?([^\"',\n]+)[\"']?",
            q,
            re.I,
        )
        by = m.group(1).strip() if m else None
        if not by:
            # pick a date or price column
            by = col_named("InvoiceDate", "Date", "Price", "Quantity")
        if by:
            asc = not any(k in q_low or k in q for k in ("desc", "تنازلي", "من الكبير"))
            steps.append({"op": "sort", "by": [by], "ascending": asc})

    # Floor date to month
    if any(
        k in q_low or k in q
        for k in ("floor to month", "month start", "أول الشهر", "لشهر", "to month", "شهر فقط")
    ) and any(k in q_low or k in q for k in ("date", "تاريخ", "invoice")):
        steps.append(
            {
                "op": "floor_date",
                "column": col_named("InvoiceDate", "Date", "تاريخ"),
                "to": "month",
            }
        )

    # Replace values
    rep = re.search(
        r"(?:replace|استبدل)\s+[\"']?([^\"']+)[\"']?\s+(?:with|ب|إلى|الى|→|->)\s+[\"']?([^\"']+)[\"']?",
        q,
        re.I,
    )
    if rep:
        col = None
        cm = re.search(r"(?:in|في)\s+[\"']?([^\"'\s]+)[\"']?", q, re.I)
        if cm:
            col = cm.group(1)
        steps.append(
            {
                "op": "replace",
                "column": col or (cols[0] if cols else None),
                "old": rep.group(1).strip(),
                "new": rep.group(2).strip(),
            }
        )

    # Split column
    sp = re.search(
        r"(?:split|اقسم)\s+[\"']?([^\"'\s]+)[\"']?\s+(?:on|by|على)\s+[\"']?([^\"'\s]+)[\"']?",
        q,
        re.I,
    )
    if sp:
        col, sep = sp.group(1), sp.group(2)
        steps.append(
            {
                "op": "split",
                "column": col,
                "sep": sep if sep not in {"space", "مسافة"} else " ",
                "into": [f"{col}_1", f"{col}_2"],
            }
        )

    # Merge columns
    mg = re.search(
        r"(?:merge|ادمج|وحّد)\s+[\"']?([^\"'\s]+)[\"']?\s+(?:and|و|&)\s+[\"']?([^\"'\s]+)[\"']?",
        q,
        re.I,
    )
    if mg:
        a, b = mg.group(1), mg.group(2)
        steps.append(
            {
                "op": "merge",
                "columns": [a, b],
                "sep": " ",
                "into": f"{a}_{b}",
            }
        )

    # Parse currency
    if any(k in q_low or k in q for k in ("parse currency", "شيل العلامة", "عملة من", "currency symbol")):
        col = col_named("Price", "Amount", "LineTotal", "السعر")
        m = re.search(r"(?:from|في|on)\s+[\"']?([^\"'\s]+)[\"']?", q, re.I)
        if m:
            col = m.group(1)
        steps.append({"op": "parse_currency", "column": col})

    # fillna
    if any(k in q_low or k in q for k in ("fillna", "fill na", "املأ الفاضي", "املئ الفاضي", "عبّي الفاضي")):
        m = re.search(
            r"(?:fillna|fill|املأ|املئ|عبّي)\s+[\"']?([^\"'\s]+)[\"']?\s+(?:with|ب|=)\s+[\"']?([^\"']+)[\"']?",
            q,
            re.I,
        )
        if m:
            steps.append({"op": "fillna", "column": m.group(1), "value": m.group(2).strip()})

    # Conditional / assign column with expression
    asg = re.search(
        r"(?:add column|new column|ضيف عمود|أضف عمود|عمود جديد)\s+[\"']?([A-Za-z0-9_\u0600-\u06FF]+)[\"']?\s*(?:=|مساوي|يساوي|:)?\s*(.+)$",
        q,
        re.I,
    )
    if asg and not any(s.get("op") == "assign" for s in steps):
        name, expr_nl = asg.group(1), asg.group(2).strip()
        expr = _nl_condition_to_expr(expr_nl, cols) or _soft_expr(expr_nl, cols)
        if expr:
            steps.append({"op": "assign", "column": name, "expr": expr})

    # Generic "column X = expr"
    asg2 = re.search(
        r"(?:set|خلي|اجعل)\s+[\"']?([A-Za-z0-9_\u0600-\u06FF]+)[\"']?\s*(?:=|يساوي)\s*(.+)$",
        q,
        re.I,
    )
    if asg2 and not steps:
        expr = _soft_expr(asg2.group(2).strip(), cols)
        if expr:
            steps.append({"op": "assign", "column": asg2.group(1), "expr": expr})

    # Dedupe
    if any(k in q_low or k in q for k in ("dedupe", "drop duplicates", "شيل المكرر", "احذف التكرار")):
        steps.append({"op": "dedupe"})

    # Rename with both sides
    ren = re.search(
        r"(?:rename|سمّي|سمي)\s+[\"']?([^\"'\s]+)[\"']?\s+(?:to|→|->|ل|إلى|الى)\s+[\"']?([^\"'\s]+)[\"']?",
        q,
        re.I,
    )
    if ren:
        steps.append({"op": "rename", "column": ren.group(1), "rename_to": ren.group(2)})

    # Drop column
    if any(k in q_low for k in ("drop column", "delete column", "remove column")) or any(
        k in q for k in ("امسح عمود", "احذف عمود", "شيل عمود")
    ):
        quoted = re.search(r"[\"']([^\"']+)[\"']", q)
        steps.append({"op": "drop", "column": quoted.group(1) if quoted else None})

    # Cast numeric
    if any(k in q_low or k in q for k in ("cast to number", "to numeric", "حوّل لرقم", "خليه رقم")):
        m = re.search(r"(?:cast|حوّل|حول)\s+[\"']?([^\"'\s]+)[\"']?", q, re.I)
        steps.append({"op": "cast", "column": m.group(1) if m else None, "to": "number"})

    if not steps:
        if looks_like_mutation(q):
            return {
                "op": "refuse",
                "confirm_apply": False,
                "error_code": "need_clearer_plan",
                "message_en": (
                    "I can reshape this upload (filter/sort/new columns/replace/split/merge/"
                    "dates/currency/fillna). Try a concrete command, e.g. "
                    "“filter Country == 'EG'”, “sort by InvoiceDate”, "
                    "“add column high = Quantity * Price > 500”, or “floor InvoiceDate to month”."
                ),
                "message_ar": (
                    "أقدر أعدّل ملف الجلسة (فلتر/ترتيب/عمود جديد/استبدال/تقسيم/دمج/"
                    "تواريخ/عملة/ملء). جرّب أمر أوضح مثل: "
                    "«فلتر Country == 'EG'» أو «رتب حسب InvoiceDate» أو "
                    "«ضيف عمود high = Quantity * Price > 500» أو «خلّي التاريخ لأول الشهر»."
                ),
            }
        return None

    # Drop null column placeholders
    cleaned = []
    for s in steps:
        if s.get("op") in {"drop", "cast", "fillna", "replace", "floor_date", "strip_time", "parse_currency"} and not s.get(
            "column"
        ):
            continue
        cleaned.append(s)
    if not cleaned:
        return None

    return {
        "op": "plan",
        "plan": cleaned,
        "confirm_apply": wants_apply
        or _strip_time_is_imperative(q, q_low)
        or any(
            w in q
            for w in (
                "ضيف عمود",
                "أضف عمود",
                "add column",
                "add a column",
            )
        ),
    }


def _ident(col: str) -> str:
    """Make a pandas column usable as an expression Name when possible."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", col or ""):
        return col
    # Spaces → use underscored form that _col_map understands
    return re.sub(r"[^\w]", "_", col)


def _soft_expr(text: str, columns: list[str]) -> str | None:
    """Light cleanup so Quantity * Price style expressions parse."""
    t = text.strip().rstrip(".")
    # Replace column display names that have spaces with identifiers
    for c in sorted(columns, key=len, reverse=True):
        if " " in c or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c):
            t = re.sub(re.escape(c), _ident(c), t, flags=re.I)
    # Arabic comparison words
    t = t.replace("أكبر من", ">").replace("اكبر من", ">")
    t = t.replace("أصغر من", "<").replace("اصغر من", "<")
    t = re.sub(r"\s+=\s+", " == ", t)
    try:
        ast.parse(t, mode="eval")
        return t
    except SyntaxError:
        return None


def _nl_condition_to_expr(fragment: str, columns: list[str]) -> str | None:
    frag = fragment.strip()
    # Already an expression?
    soft = _soft_expr(frag, columns)
    if soft:
        return soft
    # Country is EG / Country == EG
    m = re.search(
        r"[\"']?([A-Za-z0-9_ \u0600-\u06FF]+)[\"']?\s*(==|=|is|يساوي|==)\s*[\"']?([^\"']+)[\"']?",
        frag,
        re.I,
    )
    if m:
        left, _, right = m.group(1).strip(), m.group(2), m.group(3).strip()
        col = None
        for c in columns:
            if _norm(c) == _norm(left) or _norm(left) in _norm(c):
                col = c
                break
        if col:
            right_lit = right if re.fullmatch(r"-?\d+(\.\d+)?", right) else repr(right)
            return f"{_ident(col)} == {right_lit}"
    m2 = re.search(
        r"[\"']?([A-Za-z0-9_ \u0600-\u06FF]+)[\"']?\s*(>|>=|<|<=|أكبر من|اكبر من|أصغر من)\s*([0-9.]+)",
        frag,
        re.I,
    )
    if m2:
        left, op, num = m2.group(1).strip(), m2.group(2), m2.group(3)
        op = {">": ">", ">=": ">=", "<": "<", "<=": "<=", "أكبر من": ">", "اكبر من": ">", "أصغر من": "<"}.get(
            op, op
        )
        for c in columns:
            if _norm(c) == _norm(left) or _norm(left) in _norm(c):
                return f"{_ident(c)} {op} {num}"
    return None
