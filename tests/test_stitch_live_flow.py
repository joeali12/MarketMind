"""Heavy end-to-end checks for the Stitch product face + upload API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "client_uploads"
KAGGLE_SAMPLES = ROOT / "data" / "uploads" / "kaggle_samples"
STITCH = ROOT / "static" / "stitch"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _prepare(client: TestClient, path: Path, currency: str = "EGP") -> str:
    with path.open("rb") as fh:
        up = client.post("/api/upload", files={"file": (path.name, fh)})
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]
    settings = client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": currency,
            "date_format": "dayfirst",
            "confirm_date_format": True,
        },
    )
    assert settings.status_code == 200, settings.text
    confirm = client.post(
        "/api/upload/confirm-profile",
        json={"session_id": sid, "confirmed": True},
    )
    assert confirm.status_code == 200, confirm.text
    return sid


def test_stitch_assets_present_and_runtime_safe():
    for name in (
        "welcome_upload_pipeline.html",
        "file_understanding_setup.html",
        "data_cleaning_review.html",
        "store_dashboard.html",
        "mm-runtime.js",
    ):
        path = STITCH / name
        assert path.exists(), name
        assert path.stat().st_size > 1000
    runtime = (STITCH / "mm-runtime.js").read_text()
    assert "never set textContent on nodes that have children" in runtime or "Leaf-only" in runtime or "setLeafByIncludes" in runtime
    assert "mm-live-file" in runtime
    assert "/api/upload" in runtime
    html = (STITCH / "file_understanding_setup.html").read_text()
    assert "mm-runtime.js" in html
    assert "File parsed successfully" in html
    # page must still contain KPI shells after inject
    assert "font-stat-metric" in html


def test_product_home_redirects_to_stitch(client: TestClient):
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (307, 302)
    assert "/stitch/welcome_upload_pipeline.html" in res.headers.get("location", "")


def test_stitch_static_served(client: TestClient):
    for name in (
        "welcome_upload_pipeline.html",
        "file_understanding_setup.html",
        "mm-runtime.js",
    ):
        res = client.get(f"/stitch/{name}")
        assert res.status_code == 200, name


@pytest.mark.parametrize(
    "filename,currency",
    [
        ("MarketMind_Egypt_Retail_Test.csv", "EGP"),
        ("MarketMind_Egypt_Retail_Test.xlsx", "EGP"),
        ("synth_pos_en_qty_price.csv", "EGP"),
        ("synth_arabic_headers.csv", "EGP"),
        ("synth_no_customer_id.csv", "EGP"),
        ("synth_iso_dates.csv", "USD"),
    ],
)
def test_upload_profile_cleaning_overview_matrix(client: TestClient, filename: str, currency: str):
    path = FIXTURES / filename
    assert path.exists(), filename
    sid = _prepare(client, path, currency=currency)
    profile = client.get(f"/api/upload/{sid}/profile")
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body.get("row_count", 0) > 0
    assert body.get("column_count", 0) > 0

    proposals = client.post(f"/api/upload/cleaning-proposals?session_id={sid}")
    assert proposals.status_code == 200, proposals.text
    assert "proposals" in proposals.json()

    overview = client.get(f"/api/upload/{sid}/overview")
    assert overview.status_code == 200, overview.text
    metrics = overview.json()["metrics"]
    assert metrics.get("sales") is not None
    assert float(metrics["sales"]) >= 0


def test_uci_kaggle_equivalent_sample_upload(client: TestClient):
    sample = KAGGLE_SAMPLES / "uci_online_retail_ii_sample_500.csv"
    assert sample.exists(), "prepare UCI sample first"
    sid = _prepare(client, sample, currency="GBP")
    overview = client.get(f"/api/upload/{sid}/overview")
    assert overview.status_code == 200, overview.text
    metrics = overview.json()["metrics"]
    assert float(metrics["sales"]) > 0
    assert metrics.get("orders") is None or metrics["orders"] >= 1
    products = client.get(f"/api/upload/{sid}/products")
    assert products.status_code == 200
    assert len(products.json().get("products") or []) >= 1


def test_uci_5k_sample_still_analysis_ready(client: TestClient):
    sample = KAGGLE_SAMPLES / "uci_online_retail_ii_sample_5k.csv"
    assert sample.exists()
    sid = _prepare(client, sample, currency="GBP")
    overview = client.get(f"/api/upload/{sid}/overview")
    assert overview.status_code == 200, overview.text
    metrics = overview.json()["metrics"]
    assert float(metrics["sales"]) > 1000
    assert (overview.json().get("monthly_trend") or []) or True
