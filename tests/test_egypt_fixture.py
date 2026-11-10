"""End-to-end checks against the Egyptian retail test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path("/home/youssef/code/test")
CSV = FIXTURE_DIR / "MarketMind_Egypt_Retail_Test.csv"
XLSX = FIXTURE_DIR / "MarketMind_Egypt_Retail_Test.xlsx"


@pytest.fixture(scope="module")
def client():
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from api.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.skipif(not CSV.exists(), reason="Egypt CSV fixture missing")
def test_egypt_csv_journey(client: TestClient):
    raw = CSV.read_bytes()
    up = client.post(
        "/api/upload",
        files={"file": ("MarketMind_Egypt_Retail_Test.csv", raw, "text/csv")},
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]

    val = client.post(f"/api/upload/validate?session_id={sid}").json()["validation"]
    assert val["ok"] is True
    assert val["date_format"]["needs_confirmation"] is True

    # Ambiguous dates block analysis until confirmed
    assert client.get(f"/api/upload/{sid}/overview").status_code == 400

    settings = client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "EGP",
            "date_format": "dayfirst",
            "confirm_date_format": True,
        },
    )
    assert settings.status_code == 200
    assert settings.json()["currency_code"] == "EGP"

    mapped = client.post(
        f"/api/upload/validate?session_id={sid}&category_column=Category"
    )
    assert mapped.status_code == 200
    assert mapped.json()["validation"]["category_available"] is True

    profile = client.get(f"/api/upload/{sid}/profile").json()
    assert profile["ok"] is True
    assert profile["demo"] is False
    assert profile["row_count"] == 2308
    assert profile["currency"]["code"] == "EGP"
    finding_ids = {f["id"] for f in profile["findings"]}
    assert "invalid_dates" in finding_ids
    assert "missing_customer_id" in finding_ids or "missing_price" in finding_ids
    assert "cancellation_candidates" in finding_ids
    # INV-CAI must not be cancelled; C-RET should be
    structure = profile["structure"]
    assert structure["cancellation_rows"] == 1
    assert structure["unique_customers"] >= 99
    assert structure["eligible_rows"] > 0
    assert structure["eligible_spend"] > 0

    prop = client.post(f"/api/upload/cleaning-proposals?session_id={sid}").json()
    assert "eligible_spend_gbp" not in prop["baseline"]
    assert prop["baseline"]["currency_code"] == "EGP"
    destructive = [p for p in prop["proposals"] if p.get("destructive")]
    assert all(p["default_accepted"] is False for p in destructive)
    unresolved_issues = {
        i for row in prop["unresolved_preview"] for i in (row.get("issues") or [])
    }
    assert "invoice_date" in unresolved_issues or "customer_id" in unresolved_issues or "unit_price" in unresolved_issues

    overview = client.get(f"/api/upload/{sid}/overview").json()
    assert overview["demo"] is False
    assert overview["currency_code"] == "EGP"
    assert overview["metrics"]["sales"] > 0
    assert overview["metrics"]["customers"] > 0
    assert overview["metrics"]["orders"] > 0
    assert overview["metrics"]["sales_gbp"] is None
    assert overview["chart_units"]["spend"]  # currency-tied chart unit
    assert "GBP" not in str(overview["chart_units"]["spend"]) or overview["currency_code"] == "GBP"
    evidence = overview.get("evidence_insights") or []
    assert evidence
    evidence_ids = {i["id"] for i in evidence}
    assert "returning_share" in evidence_ids
    assert "top_category" in evidence_ids
    assert overview["suggested_next_steps"]
    assert overview["actions_approved"] is False

    # Egypt fixture after target-window purge: 294 overlapping train snapshots
    # removed; Ridge must beat purged-train holdout baseline to serve estimates.
    forecast = overview["forecast"]
    assert forecast["uses_uk_demo_model"] is False
    assert forecast["history_span_days"] >= 180
    assert forecast["holdout_cutoff"] == "2025-10-02"
    assert forecast["holdout_target_window_end"] == "2025-12-31"
    assert forecast["train_rows_before_purge"] == 797
    assert forecast["purged_overlap_rows"] == 294
    assert forecast["train_rows"] == 503
    assert forecast["holdout_rows"] == 100
    assert forecast["latest_train_target_window_end"] <= forecast["holdout_cutoff"]
    assert forecast["latest_train_cutoff"] == "2025-06-30"
    assert "_model" not in forecast
    assert "_evaluation_model" not in forecast
    # Corrected evaluation (post-purge): candidate does not beat baseline → unavailable
    assert forecast["available"] is False
    assert forecast["forecast_scope"] is None
    assert forecast["metrics"]["beats_baseline"] is False
    assert forecast["metrics"]["candidate_mae"] > forecast["metrics"]["baseline_mae"]
    assert forecast["metrics"]["evaluation_fit"] == "purged_train_only"
    assert forecast["metrics"]["serving_fit"] is None
    assert "did not beat baseline" in forecast["reason_en"]

    products = client.get(f"/api/upload/{sid}/products").json()
    assert products["category_available"] is True
    assert products["categories"]
    assert products["demo"] is False

    # Assistant grounded on upload — no UK demo leakage
    status = client.get("/api/upload/assistant/status").json()
    assert status["mode"] == "grounded_facts"
    assert status["configured"] is False
    ask = client.post(
        "/api/upload/assistant",
        json={"session_id": sid, "question": "How many customers are in it?", "lang": "en"},
    )
    assert ask.status_code == 200
    body = ask.json()
    assert body["demo"] is False
    assert body["mode"] == "grounded_facts"
    assert body["adapter_invoked"] is False
    assert body["raw_rows_sent_externally"] is False
    assert str(structure["unique_customers"]) in body["answer_en"] or any(
        str(c.get("value")) == str(structure["unique_customers"]) for c in body["citations"]
    )
    demo_ask = client.post(
        "/api/upload/assistant",
        json={"session_id": sid, "question": "Tell me about the UK demo", "lang": "en"},
    )
    assert "UK demo" in demo_ask.json()["answer_en"] or "upload" in demo_ask.json()["answer_en"].lower()

    # Cancellation conservatism unit via analytics path
    from marketmind.data.cleaning import is_cancellation_invoice

    assert is_cancellation_invoice("INV-CAI-200001-001") is False
    assert is_cancellation_invoice("CAI-200001") is False
    assert is_cancellation_invoice("C-RET-0001") is True

    client.delete(f"/api/upload/session?session_id={sid}")


@pytest.mark.skipif(not XLSX.exists(), reason="Egypt XLSX fixture missing")
def test_egypt_xlsx_uploads(client: TestClient):
    raw = XLSX.read_bytes()
    up = client.post(
        "/api/upload",
        files={
            "file": (
                "MarketMind_Egypt_Retail_Test.xlsx",
                raw,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]
    val = client.post(f"/api/upload/validate?session_id={sid}")
    assert val.status_code == 200
    assert val.json()["validation"]["ok"] is True
    profile = client.get(f"/api/upload/{sid}/profile").json()
    assert profile["row_count"] == 2308
    client.delete(f"/api/upload/session?session_id={sid}")


def test_cancellation_rule_unit():
    from marketmind.data.cleaning import is_cancellation_invoice
    import pandas as pd

    s = pd.Series(["C536391", "C-RET-0001", "CAI-1", "INV-CAI-1", "A123"])
    flags = is_cancellation_invoice(s)
    assert list(flags) == [True, True, False, False, False]
