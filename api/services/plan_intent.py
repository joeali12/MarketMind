"""LLM-assisted compile of AR/EN file-edit asks → session mutate DSL.

Heuristic ``compile_plan`` stays as a fast offline path. When Gemini is
configured, open-ended reshape requests are compiled to allowlisted JSON
plans (preview → apply), not answered as analytics Q&A.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from api.services.session_mutate import PLAN_OPS, is_unsafe_request
from api.settings import (
    GEMINI_API_KEY,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    gemini_key_configured,
)

logger = logging.getLogger("marketmind.plan_intent")

_SYSTEM = """You are MarketMind's session-file planner.
Convert a shop owner's request (Egyptian Arabic or English) into ONE JSON object
that mutates ONLY their temporary upload session file.

Return ONLY compact JSON (no markdown, no prose). Schema:
{"op":"plan","plan":[<steps>],"confirm_apply":true|false}
or a legacy shortcut:
{"op":"strip_time"|"add_invoice_flag"|"drop_column"|"rename_column"|"cast_numeric"|"fill_constant",
 "column":"...","new_column":"...","threshold":number,"rename_to":"...","fill_value":"...","confirm_apply":true|false}
or if this is NOT a file reshape (analytics / greeting / cleanup chat):
{"op":null}

Allowed step ops in plan[]: filter, sort, assign, replace, split, merge, floor_date,
strip_time, fillna, cast, rename, drop, parse_currency, groupby_agg, dedupe, clip.

Rules:
- Prefer op "strip_time" (or plan step strip_time) when they want dates without clock/time/hours
  (شيل الوقت، شيل الساعة، بالساعات، remove the time, strip hours, date only, …).
- Prefer floor_date when they want first-of-month / month floor.
- confirm_apply=true for imperative edits (شيل/امسح/احذف/خلّي/طبّق/strip/remove/do it).
- confirm_apply=false only when they clearly ask to preview / show first.
- Use ONLY column names from COLUMNS. If unsure, pick the closest date/invoice column.
- Never invent columns. Never request shell, network, retrain, demo data, or session wipe.
- Keep plans short (1–3 steps).
"""


def soft_reshape_cue(question: str) -> bool:
    """Broad bilingual cue that the user may be asking to edit the file."""
    q = question or ""
    q_low = q.lower()
    if is_unsafe_request(q):
        return True  # still route so we can refuse cleanly
    verbs = (
        "شيل",
        "امسح",
        "احذف",
        "خلّي",
        "خلي",
        "غيّر",
        "غير",
        "حوّل",
        "حول",
        "رتب",
        "فلتر",
        "ضيف",
        "أضف",
        "اضف",
        "املأ",
        "املا",
        "اقسم",
        "ادمج",
        "استبدل",
        "strip",
        "remove",
        "delete",
        "drop",
        "rename",
        "fill",
        "sort",
        "filter",
        "cast",
        "parse",
        "floor",
        "dedupe",
        "merge",
        "split",
        "replace",
        "add column",
        "new column",
    )
    objects = (
        "عمود",
        "تاريخ",
        "وقت",
        "ساعة",
        "ساعات",
        "صف",
        "column",
        "date",
        "time",
        "hour",
        "hours",
        "row",
        "invoice",
        "timestamp",
    )
    if any(v in q or v in q_low for v in verbs) and any(
        o in q or o in q_low for o in objects
    ):
        return True
    # Apply / confirm after a preview
    if q_low.strip() in {
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
    }:
        return True
    return False


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _sanitize_plan(
    data: dict[str, Any],
    *,
    columns: list[str],
) -> dict[str, Any] | None:
    op = data.get("op")
    if op is None or op == "null" or op == "":
        return None
    confirm = bool(data.get("confirm_apply"))
    cols_norm = {str(c).strip().lower(): str(c) for c in columns}

    def resolve_col(name: object) -> str | None:
        if name is None:
            return None
        s = str(name).strip()
        if not s:
            return None
        if s in columns:
            return s
        hit = cols_norm.get(s.lower())
        if hit:
            return hit
        for c in columns:
            if s.lower() in c.lower() or c.lower() in s.lower():
                return str(c)
        return None

    legacy = {
        "strip_time",
        "add_invoice_flag",
        "drop_column",
        "rename_column",
        "cast_numeric",
        "fill_constant",
    }
    if op in legacy:
        out: dict[str, Any] = {"op": op, "confirm_apply": confirm}
        col = resolve_col(data.get("column"))
        if col:
            out["column"] = col
        if data.get("new_column"):
            out["new_column"] = str(data["new_column"])[:80]
        if data.get("rename_to"):
            out["rename_to"] = str(data["rename_to"])[:80]
        if data.get("fill_value") is not None:
            out["fill_value"] = str(data["fill_value"])[:120]
        if data.get("threshold") is not None:
            try:
                out["threshold"] = float(data["threshold"])
            except (TypeError, ValueError):
                pass
        return out

    if op != "plan":
        return None

    steps_in = data.get("plan") or data.get("steps") or []
    if not isinstance(steps_in, list) or not steps_in:
        return None
    cleaned: list[dict[str, Any]] = []
    for step in steps_in[:5]:
        if not isinstance(step, dict):
            continue
        sop = str(step.get("op") or "").strip()
        if sop not in PLAN_OPS:
            continue
        item = dict(step)
        item["op"] = sop
        for key in ("column", "group_by", "value", "left", "right"):
            if key in item:
                resolved = resolve_col(item.get(key))
                if resolved:
                    item[key] = resolved
        cleaned.append(item)
    if not cleaned:
        return None
    return {"op": "plan", "plan": cleaned, "confirm_apply": confirm}


def llm_compile_plan(
    question: str,
    *,
    columns: list[str] | None = None,
    lang: str = "en",
) -> dict[str, Any] | None:
    """Ask Gemini to compile a reshape request into allowlisted DSL JSON."""
    if not gemini_key_configured():
        return None
    q = (question or "").strip()
    if not q:
        return None
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

    cols = [str(c) for c in (columns or [])][:80]
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("llm_compile_plan sdk_missing")
        return None

    user_prompt = (
        f"lang={lang}\n"
        f"COLUMNS={json.dumps(cols, ensure_ascii=False)}\n"
        f"USER_REQUEST={q[:800]}\n"
        "Return JSON only."
    )
    try:
        timeout_ms = int(min(GEMINI_TIMEOUT_SECONDS, 25) * 1000)
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                api_version="v1beta",
                timeout=timeout_ms,
            ),
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                temperature=0.1,
                max_output_tokens=min(GEMINI_MAX_OUTPUT_TOKENS, 512),
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        data = _extract_json(text)
        if not data:
            logger.info("llm_compile_plan empty_or_unparsed")
            return None
        return _sanitize_plan(data, columns=cols)
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_compile_plan_failed err=%s", type(exc).__name__)
        return None
