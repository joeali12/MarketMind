"""Upload source isolation, currency labels, date confirmation, streaming limit."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from api.main import app

    with TestClient(app) as c:
        yield c


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def _retail_frame(*, with_category: bool, ambiguous_dates: bool, missing_cid: bool):
    dates = (
        ["01/02/2011", "03/04/2011", "05/06/2011"]
        if ambiguous_dates
        else ["2011-02-01", "2011-04-03", "2011-06-05"]
    )
    data = {
        "Invoice": ["1", "2", "3"],
        "StockCode": ["A", "B", "C"],
        "Description": ["Tea", "Coffee", None],
        "Quantity": [1, 2, 1],
        "InvoiceDate": dates,
        "Price": [1.5, 2.0, 3.0],
        "Customer ID": [10, None if missing_cid else 11, 12],
        "Country": ["Egypt", "Egypt", "Egypt"],
    }
    if with_category:
        data["Category"] = ["Hot", "Hot", "Cold"]
    return pd.DataFrame(data)


def test_streaming_size_limit_aborts(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("api.services.upload_store.MAX_UPLOAD_BYTES", 64)
    monkeypatch.setattr("api.main.MAX_UPLOAD_BYTES", 64)
    oversized = client.post(
        "/api/upload",
        files={"file": ("big.csv", b"a" * 200, "text/csv")},
    )
    assert oversized.status_code == 400
    assert "exceed" in oversized.json()["detail"].lower()


def test_upload_currency_not_gbp_by_default(client: TestClient):
    raw = _csv_bytes(_retail_frame(with_category=False, ambiguous_dates=False, missing_cid=False))
    up = client.post("/api/upload", files={"file": ("eg.csv", raw, "text/csv")})
    assert up.status_code == 200
    sid = up.json()["session_id"]
    assert up.json().get("currency_code") in (None, "UNSPECIFIED")

    prop = client.post(f"/api/upload/cleaning-proposals?session_id={sid}")
    assert prop.status_code == 200
    baseline = prop.json()["baseline"]
    assert "eligible_spend_gbp" not in baseline
    assert baseline["currency_code"] in (None, "UNSPECIFIED") or baseline["currency_selected"] is False
    assert "gbp" not in str(baseline.get("amount_unit_en", "")).lower() or "select" in str(
        baseline.get("amount_unit_en", "")
    ).lower()

    # Set EGP explicitly — still no silent GBP
    settings = client.post(
        "/api/upload/settings",
        json={"session_id": sid, "currency_code": "EGP", "date_format": "iso", "confirm_date_format": True},
    )
    assert settings.status_code == 200
    assert settings.json()["currency_code"] == "EGP"

    overview = client.get(f"/api/upload/{sid}/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["demo"] is False
    assert body["source"] == "upload"
    assert body["currency_code"] == "EGP"
    assert body["metrics"]["sales_gbp"] is None
    assert "sales" in body["metrics"]

    client.delete(f"/api/upload/session?session_id={sid}")


def test_upload_analysis_never_falls_back_to_demo(client: TestClient):
    raw = _csv_bytes(_retail_frame(with_category=True, ambiguous_dates=False, missing_cid=False))
    up = client.post("/api/upload", files={"file": ("mix.csv", raw, "text/csv")})
    sid = up.json()["session_id"]
    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "EGP",
            "date_format": "iso",
            "confirm_date_format": True,
        },
    )
    client.post(f"/api/upload/validate?session_id={sid}&category_column=Category")

    demo_overview = client.get("/api/overview").json()
    upload_overview = client.get(f"/api/upload/{sid}/overview").json()
    assert demo_overview["demo"] is True
    assert upload_overview["demo"] is False
    assert upload_overview["session_id"] == sid
    # Sales totals must differ in structure/source identity
    assert upload_overview["metrics"]["customers"] <= 3
    assert demo_overview["metrics"]["customers"] > 3

    demo_products = client.get("/api/products").json()
    upload_products = client.get(f"/api/upload/{sid}/products").json()
    assert demo_products["category_available"] is False
    assert upload_products["category_available"] is True
    assert upload_products["demo"] is False
    assert {c["category"] for c in upload_products["categories"]} >= {"Hot", "Cold"}

    # Customer profile must not attach demo_only forecast as store-specific
    cust = client.get(f"/api/upload/{sid}/customers").json()["customers"][0]["customer_id"]
    profile = client.get(f"/api/upload/{sid}/customers/{cust}").json()
    assert profile["demo"] is False
    assert profile["estimate"] is None
    assert profile["forecast"]["available"] is False
    assert profile["forecast_scope"] is None
    assert "demo_only" not in str(profile.get("forecast_scope"))

    client.delete(f"/api/upload/session?session_id={sid}")


def test_ambiguous_dates_require_confirmation(client: TestClient):
    raw = _csv_bytes(_retail_frame(with_category=False, ambiguous_dates=True, missing_cid=True))
    up = client.post("/api/upload", files={"file": ("amb.csv", raw, "text/csv")})
    sid = up.json()["session_id"]
    val = client.post(f"/api/upload/validate?session_id={sid}").json()["validation"]
    assert val["date_format"]["needs_confirmation"] is True

    # Analysis blocked until confirmed
    blocked = client.get(f"/api/upload/{sid}/overview")
    assert blocked.status_code == 400

    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "EGP",
            "date_format": "dayfirst",
            "confirm_date_format": True,
        },
    )
    ok = client.get(f"/api/upload/{sid}/overview")
    assert ok.status_code == 200

    prop = client.post(f"/api/upload/cleaning-proposals?session_id={sid}").json()
    # Missing customer IDs stay unresolved; destructive defaults off
    assert any("customer_id" in (row.get("issues") or []) for row in prop["unresolved_preview"])
    destructive = [p for p in prop["proposals"] if p.get("destructive")]
    assert destructive
    assert all(p["default_accepted"] is False for p in destructive)

    client.delete(f"/api/upload/session?session_id={sid}")


def test_demo_profile_cutoff_separates_retrospective(client: TestClient):
    listing = client.get("/api/customers?limit=5").json()["customers"]
    assert listing
    cid = listing[0]["customer_id"]
    body = client.get(f"/api/customers/{cid}").json()
    assert body["demo"] is True
    assert body["customer"]["prediction_cutoff"]
    for row in body["purchase_history"]:
        assert row.get("available_at_prediction") is True
    assert "retrospective_actual" in body
    assert "target_spend_90d_actual_gbp" in body["retrospective_actual"]
    # Actual must not live on customer as if it were known at prediction time
    assert "target_spend_90d_actual_gbp" not in body["customer"]
    est = body["estimate"]
    assert est["forecast_scope"] == "demo_only"
    if est.get("suggested_action") and not est.get("actions_approved"):
        assert isinstance(est["suggested_action"], dict)
        assert est["suggested_action"].get("provisional") is True


def test_products_without_category_mapping(client: TestClient):
    raw = _csv_bytes(_retail_frame(with_category=True, ambiguous_dates=False, missing_cid=False))
    up = client.post("/api/upload", files={"file": ("nocat.csv", raw, "text/csv")})
    sid = up.json()["session_id"]
    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "USD",
            "date_format": "iso",
            "confirm_date_format": True,
        },
    )
    # Detected but not mapped
    products = client.get(f"/api/upload/{sid}/products").json()
    assert products["category_available"] is False
    assert products["categories"] == []
    client.delete(f"/api/upload/session?session_id={sid}")
