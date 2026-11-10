"""Guided currency / date / cleaning intents via grounded assistant actions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api.services import upload_assistant


def _profile(**overrides):
    base = {
        "session_id": "s1",
        "demo": False,
        "source": "upload",
        "row_count": 100,
        "column_count": 8,
        "structure": {
            "unique_customers": 10,
            "unique_products": 5,
            "unique_invoices": 20,
            "eligible_rows": 90,
            "eligible_spend": 1000.0,
        },
        "currency": {"code": "UNSPECIFIED", "selected": False},
        "date_format": {"needs_confirmation": True},
        "date_format_confirmed": False,
        "findings": [],
        "classification": {"phrase_en": "retail", "phrase_ar": "بيع", "confidence": 0.9},
        "category_mapped": False,
    }
    base.update(overrides)
    return base


PROPOSALS = {
    "proposals": [
        {
            "id": "drop_invalid_dates",
            "title_en": "Drop invalid dates",
            "title_ar": "احذف تواريخ باطلة",
            "reason_en": "bad dates",
            "reason_ar": "تواريخ باظ",
            "rows_affected": 3,
            "destructive": True,
            "default_accepted": False,
            "estimated_impact": {"eligible_spend_delta": -10},
        },
        {
            "id": "flag_dupes",
            "title_en": "Flag duplicates",
            "title_ar": "علّم المكرر",
            "reason_en": "dupes",
            "reason_ar": "مكرر",
            "rows_affected": 2,
            "destructive": False,
            "default_accepted": True,
            "estimated_impact": {"eligible_spend_delta": 0},
        },
    ],
    "unresolved_preview": [{"invoice": "X", "issues": ["customer_id"]}],
}


def test_currency_egp_sets_action_and_asks_date():
    r = upload_assistant.answer(
        "EGP", profile=_profile(), proposals=PROPOSALS, lang="en"
    )
    assert r["mode"] == "grounded_facts"
    assert r["adapter_invoked"] is False
    assert any(
        a.get("type") == "set_currency" and a.get("currency_code") == "EGP"
        for a in r["actions"]
    )
    assert "day-first" in r["answer_en"].lower() or "dayfirst" in str(r["quick_replies"]).lower()


def test_arabic_currency_alias():
    r = upload_assistant.answer(
        "جنيه", profile=_profile(), proposals=PROPOSALS, lang="ar"
    )
    assert any(a.get("currency_code") == "EGP" for a in r["actions"])


def test_date_format_then_asks_profile_confirm():
    profile = _profile(
        currency={"code": "EGP", "selected": True},
        date_format={"needs_confirmation": True},
        date_format_confirmed=False,
    )
    r = upload_assistant.answer(
        "dayfirst", profile=profile, proposals=PROPOSALS, lang="en"
    )
    assert any(
        a.get("type") == "set_date_format" and a.get("date_format") == "dayfirst"
        for a in r["actions"]
    )
    assert "correct" in r["answer_en"].lower()
    assert any(a.get("field") == "profile_confirm" for a in r["actions"])


def test_confirm_then_gap_preference():
    profile = _profile(
        currency={"code": "EGP", "selected": True},
        date_format_confirmed=True,
        date_format={"needs_confirmation": False},
        profile_confirmed=False,
    )
    r = upload_assistant.answer(
        "yes correct", profile=profile, proposals=PROPOSALS, lang="en"
    )
    assert any(a.get("type") == "confirm_profile" and a.get("confirmed") for a in r["actions"])
    assert "smart" in r["answer_en"].lower() or "manual" in r["answer_en"].lower()


def test_accept_all_safe_emits_proposal_actions():
    profile = _profile(
        currency={"code": "EGP", "selected": True},
        date_format={"needs_confirmation": False},
        date_format_confirmed=True,
    )
    r = upload_assistant.answer(
        "accept all safe", profile=profile, proposals=PROPOSALS, lang="en"
    )
    accepts = [a for a in r["actions"] if a.get("type") == "set_proposal"]
    assert any(a["proposal_id"] == "flag_dupes" and a["accepted"] is True for a in accepts)
    assert not any(
        a["proposal_id"] == "drop_invalid_dates" and a["accepted"] is True for a in accepts
    )


def test_show_cleaning_asks_how_to_handle_gaps():
    profile = _profile(
        currency={"code": "EGP", "selected": True},
        date_format_confirmed=True,
        date_format={"needs_confirmation": False},
    )
    r = upload_assistant.answer(
        "ورّيني التنظيف", profile=profile, proposals=PROPOSALS, lang="ar"
    )
    assert "فراغ" in r["answer_ar"] or "تنظيف" in r["answer_ar"]
    assert r["quick_replies"]
