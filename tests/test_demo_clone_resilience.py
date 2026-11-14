"""Demo API must work after a clean clone without full transactions_cleaned.parquet."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from api.services import demo_data

    demo_data.metadata.cache_clear()
    demo_data.store_snapshot.cache_clear()
    demo_data.transactions_cleaned.cache_clear()
    demo_data.eda_insights.cache_clear()
    demo_data.customers_with_segments.cache_clear()
    demo_data.customers_combined.cache_clear()
    demo_data.customer_train.cache_clear()
    demo_data.customer_test.cache_clear()
    demo_data.artifacts.cache_clear()

    # Force the sample/snapshot path even if a local full parquet exists.
    monkeypatch.setattr(demo_data, "_TX_FULL", ROOT / "data" / "processed" / "__missing_full__.parquet")

    from api.main import app

    with TestClient(app) as c:
        yield c

    demo_data.metadata.cache_clear()
    demo_data.store_snapshot.cache_clear()
    demo_data.transactions_cleaned.cache_clear()


def test_overview_uses_snapshot_without_full_parquet(client: TestClient):
    r = client.get("/api/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["currency"] == "GBP"
    assert body["metrics"]["customers"] > 3
    assert body["metrics"]["sales_gbp"] > 0


def test_products_use_snapshot_without_full_parquet(client: TestClient):
    r = client.get("/api/products")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["products"], "expected snapshot product rows"
    assert body["category_available"] is False


def test_customer_profile_uses_demo_sample(client: TestClient):
    listing = client.get("/api/customers?limit=1").json()["customers"]
    assert listing
    cid = listing[0]["customer_id"]
    r = client.get(f"/api/customers/{cid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estimate"]["forecast_scope"] == "demo_only"
