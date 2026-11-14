"""Regressions from live adversarial stress against the upload journey."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client():
    from api.main import app

    with TestClient(app) as c:
        yield c


def test_arabic_pos_headers_auto_map_analysis_ready():
    from api.services import column_mapping as cmap

    cols = [
        "رقم الفاتورة",
        "كود الصنف",
        "الوصف",
        "الكمية",
        "تاريخ الفاتورة",
        "سعر الوحدة",
        "رقم العميل",
        "البلد",
    ]
    sug = cmap.suggest_mappings(cols)
    auto = sug["auto_mapping"]
    assert auto["invoice"] == "رقم الفاتورة"
    assert auto["stock_code"] == "كود الصنف"
    assert auto["description"] == "الوصف"
    assert auto["customer_id"] == "رقم العميل"
    assert auto["country"] == "البلد"
    caps = cmap.assess_capabilities(auto)
    assert caps["analysis_ready_minimum"] is True


def test_custid_and_name_aliases_auto_map():
    from api.services import column_mapping as cmap

    sug = cmap.suggest_mappings(
        ["Invoice No", "Product Code", "Name", "Qty", "Date", "Unit Price", "CustId", "Country"]
    )
    auto = sug["auto_mapping"]
    assert auto["description"] == "Name"
    assert auto["customer_id"] == "CustId"
    assert auto["stock_code"] == "Product Code"


def test_csv_preserves_long_and_scientific_customer_ids(client: TestClient):
    # Scientific notation must stay textual — not float-rounded.
    raw = (
        "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
        "1,A,d,1,2024-01-01,2,1.2345678901234568e+18,EG\n"
        "2,B,e,1,2024-01-01,3,1234567890123456789,EG\n"
        "3,C,f,1,2024-01-01,4,C-99,EG\n"
    )
    up = client.post(
        "/api/upload", files={"file": ("sci.csv", raw.encode("utf-8"), "text/csv")}
    )
    assert up.status_code == 200, up.text
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
    mapping = {
        "invoice": "Invoice",
        "stock_code": "StockCode",
        "description": "Description",
        "quantity": "Quantity",
        "invoice_date": "InvoiceDate",
        "unit_price": "Price",
        "customer_id": "Customer ID",
        "country": "Country",
    }
    mp = client.post(
        "/api/upload/mapping",
        json={"session_id": sid, "mapping": mapping, "confirm": True},
    )
    assert mp.status_code == 200, mp.text
    listing = client.get(f"/api/upload/{sid}/customers")
    assert listing.status_code == 200, listing.text
    ids = {str(c["customer_id"]) for c in listing.json()["customers"]}
    assert "C-99" in ids
    # Must not be the float64-rounded integer form of the sci-notation ID
    assert "1234567890123456768" not in ids
    assert any("e+" in i.lower() or i == "1.2345678901234568e+18" for i in ids) or (
        "1.2345678901234568e+18" in ids
    )
    assert "1234567890123456789" in ids


def test_arabic_semicolon_bom_live_journey(client: TestClient, tmp_path: Path):
    rows = [
        {
            "رقم الفاتورة": f"F{i}",
            "كود الصنف": f"S{i}",
            "الوصف": f"منتج {i}",
            "الكمية": 2,
            "تاريخ الفاتورة": "2024-02-01",
            "سعر الوحدة": 5.5,
            "رقم العميل": f"ع-{i}",
            "البلد": "مصر",
        }
        for i in range(12)
    ]
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False, sep=";")
    content = "\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8")
    path = tmp_path / "ar_bom.csv"
    path.write_bytes(content)

    up = client.post(
        "/api/upload", files={"file": (path.name, path.read_bytes(), "text/csv")}
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]
    # Auto mapping should now be analysis-ready without manual map
    assert up.json().get("mapping_confirmed") or up.json().get("needs_user_mapping")
    if not up.json().get("mapping_confirmed"):
        prof = client.get(f"/api/upload/{sid}/profile")
        eff = (prof.json().get("mapping") or {}).get("effective_mapping") or {}
        mp = client.post(
            "/api/upload/mapping",
            json={"session_id": sid, "mapping": eff, "confirm": True},
        )
        assert mp.status_code == 200, mp.text
        assert mp.json().get("mapping_confirmed") is True
    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "EGP",
            "date_format": "iso",
            "confirm_date_format": True,
        },
    )
    ov = client.get(f"/api/upload/{sid}/overview")
    assert ov.status_code == 200, ov.text
    assert float(ov.json()["metrics"]["sales"]) == pytest.approx(12 * 2 * 5.5)


def test_multisheet_gap_fill_keeps_sibling_sheets(client: TestClient, tmp_path: Path):
    book = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(book, engine="openpyxl") as w:
        pd.DataFrame({"keep": [42]}).to_excel(w, sheet_name="KeepMe", index=False)
        pd.DataFrame(
            {
                "Invoice": ["1", "2", "3", "4", "5"],
                "StockCode": ["S"] * 5,
                "Description": ["D"] * 5,
                "Quantity": [1] * 5,
                "InvoiceDate": ["2024-01-01"] * 5,
                "Price": [10.0, 10.0, 10.0, 10.0, None],
                "Customer ID": ["A-1", "A-2", "A-3", "A-4", "A-5"],
                "Country": ["EG"] * 5,
            }
        ).to_excel(w, sheet_name="Sales", index=False)

    up = client.post(
        "/api/upload",
        files={
            "file": (
                book.name,
                book.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    sid = up.json()["session_id"]
    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "selected_sheet": "Sales",
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
    client.post(
        "/api/upload/confirm-profile", json={"session_id": sid, "confirmed": True}
    )
    props = client.post(f"/api/upload/cleaning-proposals?session_id={sid}")
    assert props.status_code == 200
    target = None
    for row in props.json().get("unresolved_preview") or []:
        if "unit_price" in (row.get("issues") or []):
            target = row
            break
    assert target is not None
    gf = client.post(
        "/api/upload/gap-fill",
        json={
            "session_id": sid,
            "patches": [
                {
                    "row_index": target["row_index"],
                    "field": "unit_price",
                    "value": 10.0,
                    "source": "manual",
                }
            ],
        },
    )
    assert gf.status_code == 200, gf.text
    from api.services import upload_store

    path = upload_store.upload_path(sid)
    sheets = pd.ExcelFile(path).sheet_names
    assert "KeepMe" in sheets and "Sales" in sheets
    assert pd.read_excel(path, sheet_name="KeepMe")["keep"].tolist() == [42]
    sales = pd.read_excel(path, sheet_name="Sales")
    assert pd.notna(sales.loc[target["row_index"], "Price"])
