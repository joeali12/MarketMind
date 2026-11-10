"""Aggregate context privacy — fail closed; no raw rows or user question forwarding."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api.services import assistant_context
from api.services.assistant_context import ContextPrivacyError
from api.services.gemini_tool_loop import ToolLoopResult
from api.services.upload_store import UploadSessionMeta


def _profile():
    return {
        "session_id": "sess-1",
        "row_count": 100,
        "column_count": 8,
        "classification": {
            "phrase_en": "retail transactions",
            "phrase_ar": "مبيعات",
            "confidence": 0.9,
        },
        "currency": {"code": "EGP", "selected": True},
        "date_format_confirmed": True,
        "profile_confirmed": True,
        "structure": {
            "unique_customers": 12,
            "unique_products": 20,
            "unique_invoices": 40,
            "eligible_rows": 90,
            "eligible_spend": 5000.0,
            "cancellation_rows": 2,
        },
        "findings": [
            {
                "id": "dup",
                "title_en": "Duplicates",
                "title_ar": "مكرر",
                "count": 3,
                "severity": "warning",
            }
        ],
        "preview_rows": [
            {
                "invoice": "INV-99",
                "customer_id": "C-SECRET",
                "email": "a@b.com",
                "phone": "01001234567",
            }
        ],
    }


def _proposals():
    return {
        "proposals": [
            {
                "id": "drop_dup",
                "title_en": "Drop duplicates",
                "title_ar": "حذف المكرر",
                "rows_affected": 3,
                "destructive": True,
                "default_accepted": False,
                "estimated_impact": {"eligible_spend_delta": -10.0},
            }
        ],
        "baseline": {"rows": 100, "eligible_spend": 5000.0, "currency_code": "EGP"},
        "gap_fill": {
            "smart_fillable_fields": ["description"],
            "manual_only_fields": ["customer_id", "invoice"],
            "note_en": "No invented IDs",
            "note_ar": "بدون اختراع معرفات",
        },
        "unresolved_preview": [
            {"invoice": "INV-1", "customer_id": "C1", "email": "x@y.com"}
        ],
    }


def _ready_profile(**extra):
    base = {
        "session_id": "t",
        "row_count": 10,
        "column_count": 5,
        "structure": {
            "unique_customers": 3,
            "unique_products": 4,
            "unique_invoices": 5,
            "eligible_rows": 8,
            "eligible_spend": 100.0,
        },
        "currency": {"code": "EGP", "selected": True},
        "date_format_confirmed": True,
        "profile_confirmed": True,
        "findings": [
            {
                "id": "dup",
                "title_en": "Duplicates",
                "title_ar": "مكرر",
                "count": 2,
                "severity": "warning",
            }
        ],
        "classification": {"phrase_en": "retail", "phrase_ar": "بيع", "confidence": 0.9},
    }
    base.update(extra)
    return base


def _meta() -> UploadSessionMeta:
    return UploadSessionMeta(
        session_id="s1",
        created_at=time.time(),
        filename="t.csv",
        extension=".csv",
        byte_size=10,
        currency_code="EGP",
        date_format="dayfirst",
        date_format_confirmed=True,
    )


def test_context_excludes_raw_rows_and_identifiers():
    ctx = assistant_context.build_aggregate_context(
        profile=_profile(),
        proposals=_proposals(),
        analytics={
            "segments": [
                {
                    "label_en": "Loyal",
                    "n_customers": 5,
                    "share": 0.4,
                    "spend_share": 0.6,
                    "monetary_mean": 200.0,
                    "recency_mean": 10.0,
                    "frequency_mean": 3.0,
                    "customer_id": "must-drop",
                }
            ]
        },
        lang="en",
    )
    blob = json.dumps(ctx)
    assert "preview_rows" not in blob
    assert "unresolved_preview" not in blob
    assert "C-SECRET" not in blob
    assert "a@b.com" not in blob
    assert "INV-99" not in blob
    assert "must-drop" not in blob
    assert "customer_id" not in blob
    assistant_context.assert_context_has_no_identifiers(ctx)


def test_context_contains_allowed_aggregates():
    ctx = assistant_context.build_aggregate_context(
        profile=_profile(), proposals=_proposals(), analytics=None, lang="ar"
    )
    assert ctx["file"]["row_count"] == 100
    assert ctx["structure"]["eligible_spend"] == 5000.0
    assert ctx["baseline"]["currency_code"] == "EGP"
    assert ctx["findings"][0]["count"] == 3
    assert ctx["cleaning_proposals"][0]["rows_affected"] == 3
    assert ctx["gap_fill_policy"]["manual_only_count"] == 2
    assert ctx["lang"] == "ar"
    text = assistant_context.context_as_json(ctx, max_chars=5000)
    assert json.loads(text)["file"]["row_count"] == 100


def test_validation_fails_closed_on_forbidden_key():
    ctx = assistant_context.build_aggregate_context(
        profile=_profile(), proposals=_proposals(), analytics=None, lang="en"
    )
    ctx["customer_id"] = "C-1"
    with pytest.raises(ContextPrivacyError) as exc:
        assistant_context.assert_context_has_no_identifiers(ctx)
    assert exc.value.reason_code in {"forbidden_key", "forbidden_id_key", "unknown_top_key"}


def test_validation_fails_closed_on_identifier_like_value():
    ctx = assistant_context.build_aggregate_context(
        profile=_profile(), proposals=_proposals(), analytics=None, lang="en"
    )
    ctx["file"]["classification_en"] = "leak a@b.com here"
    with pytest.raises(ContextPrivacyError) as exc:
        assistant_context.assert_context_has_no_identifiers(ctx)
    assert exc.value.reason_code == "identifier_like_email"


def test_context_size_bound_preserves_valid_json():
    ctx = assistant_context.build_aggregate_context(
        profile=_profile(),
        proposals=_proposals(),
        analytics={
            "segments": [
                {
                    "label_en": f"Seg{i}",
                    "n_customers": i,
                    "share": 0.1,
                    "spend_share": 0.1,
                    "monetary_mean": 10.0,
                    "recency_mean": 1.0,
                    "frequency_mean": 1.0,
                }
                for i in range(12)
            ]
        },
        lang="en",
        safe_intent="explain_counts",
        safe_question="Summarize counts from CONTEXT_JSON.",
    )
    text = assistant_context.context_as_json(ctx, max_chars=900)
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    assert "file" in parsed
    assert len(text) <= 900


def test_context_size_bound_rejects_when_impossible():
    ctx = assistant_context.build_aggregate_context(
        profile=_profile(), proposals=None, analytics=None, lang="en"
    )
    with pytest.raises(ContextPrivacyError) as exc:
        assistant_context.context_as_json(ctx, max_chars=40)
    assert exc.value.reason_code in {"max_chars_too_small", "context_exceeds_budget"}


def test_answer_unsupported_skips_gemini(monkeypatch: pytest.MonkeyPatch):
    """Off-topic asks stay grounded without a live upload meta (no tool loop)."""
    from api.services import upload_assistant

    called = {"n": 0}

    def boom(**k):
        called["n"] += 1
        raise AssertionError("tool loop must not run without meta")

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn", boom
    )
    result = upload_assistant.answer(
        "What is the meaning of life?",
        profile=_ready_profile(),
        lang="en",
    )
    assert result["mode"] == "grounded_facts"
    assert called["n"] == 0
    assert result["raw_user_question_sent_externally"] is False
    assert result.get("answer_en")


def test_safe_ask_may_reach_provider_but_not_as_template(
    monkeypatch: pytest.MonkeyPatch,
):
    """With upload meta, open-ended tool loop may call Gemini — not fixed templates."""
    from api.services import upload_assistant

    def fake_loop(**k):
        assert k["question"]
        assert k["meta"].session_id == "s1"
        return ToolLoopResult(
            ok=True,
            text="Counts look healthy from tools.",
            mode="gemini",
            tools_called=["get_upload_profile"],
        )

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn", fake_loop
    )
    user_q = "How many rows are in the file?"
    result = upload_assistant.answer(
        user_q, profile=_ready_profile(), lang="en", meta=_meta()
    )
    assert result["mode"] == "gemini"
    assert result["raw_user_question_sent_externally"] is False
    assert "get_upload_profile" in (result.get("tools_called") or [])
    assert "gemini-2.5-flash" not in json.dumps(result)


@pytest.mark.parametrize(
    "question,reason_substr",
    [
        ("How many rows? email me at owner@shop.example", "email"),
        ("How many customers? call +201001234567", "phone"),
        ("Explain findings for INV-12345", "invoice"),
        ("Segment for customer id C-998877", "customer"),
        (
            "How many rows?\na,widget,10,red\nb,gadget,20,blue\nc,thing,30,green\n",
            "row",
        ),
    ],
)
def test_pii_or_row_questions_skip_gemini(
    monkeypatch: pytest.MonkeyPatch, question: str, reason_substr: str
):
    from api.services import upload_assistant

    called = {"n": 0}

    def boom(**k):
        called["n"] += 1
        raise AssertionError("tool loop must not be called")

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn", boom
    )
    result = upload_assistant.answer(question, profile=_ready_profile(), lang="en")
    assert called["n"] == 0
    assert result["mode"] == "grounded_facts"
    assert result["raw_user_question_sent_externally"] is False
    skip = result.get("gemini_skip_reason") or result.get("fallback_code") or ""
    assert reason_substr in skip


def test_supported_intent_sends_fixed_template_plus_cleared_ask(
    monkeypatch: pytest.MonkeyPatch,
):
    """Open-ended path returns gemini mode when tool loop succeeds."""
    from api.services import upload_assistant

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn",
        lambda **k: ToolLoopResult(
            ok=True,
            text="Plain explanation.",
            mode="gemini",
            tools_called=["get_sales_kpis"],
        ),
    )
    result = upload_assistant.answer(
        "How many rows are in the file?",
        profile=_ready_profile(),
        lang="en",
        meta=_meta(),
    )
    assert result["mode"] == "gemini"
    assert result["adapter_invoked"] is True
    assert "get_sales_kpis" in (result.get("tools_called") or [])


def test_validation_failure_prevents_provider(monkeypatch: pytest.MonkeyPatch):
    """Privacy-blocked user text never reaches the tool loop."""
    from api.services import upload_assistant

    called = {"n": 0}

    def boom(**k):
        called["n"] += 1
        raise AssertionError("must not call tool loop")

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn", boom
    )
    result = upload_assistant.answer(
        "How many rows? email me at owner@shop.example",
        profile=_ready_profile(),
        lang="en",
        meta=_meta(),
    )
    assert called["n"] == 0
    assert result["mode"] == "grounded_facts"
    skip = result.get("gemini_skip_reason") or result.get("fallback_code") or ""
    assert "email" in skip
    assert result["raw_user_question_sent_externally"] is False


def test_arabic_safe_template_used(monkeypatch: pytest.MonkeyPatch):
    from api.services import upload_assistant

    captured: dict = {}

    def fake_loop(**k):
        captured["lang"] = k["lang"]
        return ToolLoopResult(
            ok=True, text="شرح", mode="gemini", tools_called=["get_upload_profile"]
        )

    monkeypatch.setattr(
        "api.services.gemini_tool_loop.run_tool_assisted_turn", fake_loop
    )
    result = upload_assistant.answer(
        "كام صف في الملف؟",
        profile=_ready_profile(),
        lang="ar",
        meta=_meta(),
    )
    assert result["mode"] == "gemini"
    assert captured["lang"] == "ar"
