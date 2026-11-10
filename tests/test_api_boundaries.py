"""API contract tests for demo honesty, category gating, upload privacy."""

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


def test_meta_demo_gbp_uk_not_egyptian(client: TestClient):
    r = client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is True
    assert body["currency"] == "GBP"
    assert body["has_category_field"] is False
    assert body["forecast_scope"] == "demo_only"
    assert "UK" in body["provenance"] or "Online Retail" in body["provenance"]
    assert "Cairo" not in body["badge_en"]
    assert "Egyptian store" not in body["badge_en"].lower()
    assert "EGP" not in body["badge_en"]
    assert body["upload_policy"]["logs_file_contents"] is False
    assert body["upload_policy"]["max_bytes"] == 25 * 1024 * 1024


def test_products_omit_category_on_demo(client: TestClient):
    r = client.get("/api/products")
    assert r.status_code == 200
    body = r.json()
    assert body["category_available"] is False
    assert body["categories"] == []
    assert "category" in body["category_omitted_reason_en"].lower()
    assert body["products"], "expected product rows from demo"


def test_predict_is_demo_only(client: TestClient):
    r = client.post(
        "/api/predict",
        json={"customer_id": 1, "recency": 10, "frequency": 2, "monetary": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_scope"] == "demo_only"
    assert body["prediction"]["forecast_scope"] == "demo_only"


def test_customer_profile_separates_estimate(client: TestClient):
    listing = client.get("/api/customers?limit=1").json()["customers"]
    assert listing
    cid = listing[0]["customer_id"]
    r = client.get(f"/api/customers/{cid}")
    assert r.status_code == 200
    body = r.json()
    assert "estimate" in body and "customer" in body
    assert body["estimate"]["forecast_scope"] == "demo_only"
    assert "demo" in body["estimate"]["label_en"].lower()


def test_upload_reject_oversized_and_bad_ext(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    r = client.post(
        "/api/upload",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400

    r2 = client.post(
        "/api/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert r2.status_code == 400

    # Reject > limit without shipping a real 25MB payload (streaming check)
    monkeypatch.setattr("api.services.upload_store.MAX_UPLOAD_BYTES", 64)
    monkeypatch.setattr("api.main.MAX_UPLOAD_BYTES", 64)
    oversized = client.post(
        "/api/upload",
        files={"file": ("big.csv", b"a" * 128, "text/csv")},
    )
    assert oversized.status_code == 400
    assert "exceed" in oversized.json()["detail"].lower() or "mb" in oversized.json()["detail"].lower()


def test_upload_validate_and_proposals_no_invention(client: TestClient):
    df = pd.DataFrame(
        {
            "Invoice": ["1", "2", "C3"],
            "StockCode": ["A", "B", "C"],
            "Description": ["x", None, "z"],
            "Quantity": [1, "bad", 2],
            "InvoiceDate": ["2011-01-01", "not-a-date", "2011-01-03"],
            "Price": [1.5, 2.0, 3.0],
            "Customer ID": [10, None, 12],
            "Country": ["United Kingdom", "United Kingdom", "United Kingdom"],
        }
    )
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    raw = buf.getvalue()
    up = client.post(
        "/api/upload",
        files={"file": ("sample.csv", raw, "text/csv")},
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]

    val = client.post(f"/api/upload/validate?session_id={sid}")
    assert val.status_code == 200
    assert val.json()["validation"]["ok"] is True
    assert val.json()["validation"]["category_available"] is False

    prop = client.post(f"/api/upload/cleaning-proposals?session_id={sid}")
    assert prop.status_code == 200
    body = prop.json()
    assert body["unresolved_preview"], "unresolved rows must remain visible"
    for row in body["unresolved_preview"]:
        # Never invent customer ids
        if "customer_id" in row.get("issues", []):
            assert row["customer_id"] is None
    assert all(p["invents_values"] is False for p in body["proposals"])

    disc = client.delete(f"/api/upload/session?session_id={sid}")
    assert disc.status_code == 200


def test_overview_currency_gbp(client: TestClient):
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "GBP"
    assert body["demo"] is True
    assert "sales_gbp" in body["metrics"]


def test_upload_policy_endpoint(client: TestClient):
    r = client.get("/api/upload/policy")
    assert r.status_code == 200
    body = r.json()
    assert body["logging"]["file_contents"] is False
    assert body["encryption_at_rest_claimed"] is False
    assert body["multi_tenant"] is False


def test_upload_products_category_gated(client: TestClient):
    df = pd.DataFrame(
        {
            "Invoice": ["1", "2"],
            "StockCode": ["A", "B"],
            "Description": ["x", "y"],
            "Quantity": [1, 2],
            "InvoiceDate": ["2011-01-01", "2011-01-02"],
            "Price": [1.5, 2.0],
            "Customer ID": [10, 11],
            "Country": ["United Kingdom", "United Kingdom"],
            "Category": ["Tea", "Coffee"],
        }
    )
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    raw = buf.getvalue()
    up = client.post("/api/upload", files={"file": ("cats.csv", raw, "text/csv")})
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]

    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "GBP",
            "date_format": "iso",
            "confirm_date_format": True,
        },
    )

    # Auto-detect alone must not enable category chart
    before = client.get(f"/api/upload/{sid}/products")
    assert before.status_code == 200
    assert before.json()["category_available"] is False
    assert before.json()["categories"] == []

    mapped = client.post(f"/api/upload/validate?session_id={sid}&category_column=Category")
    assert mapped.status_code == 200
    assert mapped.json()["validation"]["category_available"] is True

    after = client.get(f"/api/upload/{sid}/products")
    assert after.status_code == 200
    body = after.json()
    assert body["category_available"] is True
    assert body["has_category_mapped"] is True
    assert body["demo"] is False
    assert {c["category"] for c in body["categories"]} >= {"Tea", "Coffee"}

    client.delete(f"/api/upload/session?session_id={sid}")
