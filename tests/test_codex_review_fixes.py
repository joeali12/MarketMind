"""Regression coverage for Codex review findings on the graduation PR."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "client_uploads"


@pytest.fixture()
def client():
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from api.main import app

    with TestClient(app) as c:
        yield c


def test_line_total_mapping_not_flagged_for_missing_unit_price(client: TestClient):
    path = FIXTURES / "synth_supermarket_line_total.csv"
    assert path.exists()
    with path.open("rb") as fh:
        up = client.post("/api/upload", files={"file": (path.name, fh)})
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
    client.post(
        "/api/upload/mapping",
        json={
            "session_id": sid,
            "confirm": True,
            "mapping": {
                "invoice_date": "SaleDate",
                "description": "ItemName",
                "quantity": "Qty",
                "line_amount": "LineTotal",
            },
        },
    )
    prop = client.post(f"/api/upload/cleaning-proposals?session_id={sid}")
    assert prop.status_code == 200, prop.text
    body = prop.json()
    assert float(body["baseline"]["eligible_spend"]) > 0
    drop = next(
        (p for p in body["proposals"] if p["id"] == "drop_non_finite_qty_price"),
        None,
    )
    # Valid line-total rows must not be treated as missing unit price
    if drop:
        assert drop["rows_affected"] < body["baseline"]["rows"]
    for row in body.get("unresolved_preview") or []:
        assert "unit_price" not in (row.get("issues") or [])


def test_gap_fill_preserves_other_excel_sheets(client: TestClient, tmp_path: Path):
    from api.services import gap_fill as gap_fill_svc

    book = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(book, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(
            {
                "Invoice": ["1"],
                "StockCode": ["A"],
                "Description": ["x"],
                "Quantity": [1],
                "InvoiceDate": ["2011-01-01"],
                "Price": [2.0],
                "Customer ID": [10],
                "Country": ["EG"],
            }
        ).to_excel(writer, sheet_name="SalesLines", index=False)
    sales = pd.read_excel(book, sheet_name="SalesLines")
    sales.loc[0, "Description"] = "patched"
    gap_fill_svc.write_source_dataframe(book, sales, sheet_name="SalesLines")
    sheets = pd.read_excel(book, sheet_name=None)
    assert set(sheets) == {"Summary", "SalesLines"}
    assert sheets["Summary"]["a"].tolist() == [1]
    assert sheets["SalesLines"]["Description"].tolist() == ["patched"]


def test_analysis_currency_filter_labels_totals(client: TestClient):
    df = pd.DataFrame(
        {
            "Invoice": ["1", "2"],
            "StockCode": ["A", "B"],
            "Description": ["x", "y"],
            "Quantity": [1, 1],
            "InvoiceDate": ["2011-01-01", "2011-01-02"],
            "Price": [10.0, 20.0],
            "Customer ID": [1, 2],
            "Country": ["EG", "EG"],
            "Currency": ["USD", "EUR"],
        }
    )
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    up = client.post(
        "/api/upload", files={"file": ("multi_cur.csv", buf.getvalue(), "text/csv")}
    )
    sid = up.json()["session_id"]
    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "USD",
            "date_format": "iso",
            "confirm_date_format": True,
            "analysis_currency_filter": "EUR",
        },
    )
    client.post(f"/api/upload/validate?session_id={sid}&category_column=")
    client.post(
        "/api/upload/mapping",
        json={
            "session_id": sid,
            "confirm": True,
            "mapping": {
                "invoice": "Invoice",
                "stock_code": "StockCode",
                "description": "Description",
                "quantity": "Quantity",
                "invoice_date": "InvoiceDate",
                "unit_price": "Price",
                "customer_id": "Customer ID",
                "country": "Country",
                "row_currency": "Currency",
            },
        },
    )
    ov = client.get(f"/api/upload/{sid}/overview")
    assert ov.status_code == 200, ov.text
    body = ov.json()
    assert body["currency_code"] in {"EUR", "USD"}
    assert body["currency_label"] == "EUR"
    assert body["metrics"]["sales"] == 20.0
    assert body["metrics"].get("sales_gbp") in (None, 0, 0.0)


def test_alphanumeric_customer_ids_survive_listing(client: TestClient):
    df = pd.DataFrame(
        {
            "Invoice": ["1", "2"],
            "StockCode": ["A", "B"],
            "Description": ["x", "y"],
            "Quantity": [1, 2],
            "InvoiceDate": ["2011-01-01", "2011-01-02"],
            "Price": [3.0, 4.0],
            "Customer ID": ["C-100", "C-200"],
            "Country": ["EG", "EG"],
        }
    )
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    up = client.post(
        "/api/upload", files={"file": ("alnum.csv", buf.getvalue(), "text/csv")}
    )
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
    client.post(
        "/api/upload/mapping",
        json={
            "session_id": sid,
            "confirm": True,
            "mapping": {
                "invoice": "Invoice",
                "stock_code": "StockCode",
                "description": "Description",
                "quantity": "Quantity",
                "invoice_date": "InvoiceDate",
                "unit_price": "Price",
                "customer_id": "Customer ID",
                "country": "Country",
            },
        },
    )
    listing = client.get(f"/api/upload/{sid}/customers")
    assert listing.status_code == 200, listing.text
    ids = {str(c["customer_id"]) for c in listing.json()["customers"]}
    assert ids >= {"C-100", "C-200"}
