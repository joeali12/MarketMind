"""Assistant-driven safe data transforms on the upload session file."""

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


def _sid_with_mapping(client: TestClient, csv_bytes: bytes, name: str = "t.csv") -> str:
    up = client.post("/api/upload", files={"file": (name, csv_bytes, "text/csv")})
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
    return sid


def test_strip_time_from_dates_via_assistant(client: TestClient):
    raw = (
        "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
        "1,A,Tea,1,2024-01-15 14:30:00,10,C1,EG\n"
        "2,B,Coffee,2,2024-01-16 09:05:00,20,C2,EG\n"
        "3,C,Sugar,1,2024-01-17,5,C3,EG\n"
    ).encode()
    sid = _sid_with_mapping(client, raw)

    # Imperative: should apply
    res = client.post(
        "/api/upload/assistant",
        json={
            "session_id": sid,
            "question": "شيل الساعة من التاريخ في الملف",
            "lang": "ar",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("unsupported") is not True
    tools = body.get("tools_called") or []
    assert "apply_data_transform" in tools or "preview_data_transform" in tools
    answer = (body.get("answer_ar") or body.get("answer_en") or "").lower()
    assert "تاريخ" in (body.get("answer_ar") or "") or "time" in answer or "strip" in answer or "اتشال" in (
        body.get("answer_ar") or ""
    )

    # If preview-only, apply explicitly
    if "apply_data_transform" not in tools:
        res2 = client.post(
            "/api/upload/assistant",
            json={"session_id": sid, "question": "طبّق شيل الساعة من التاريخ", "lang": "ar"},
        )
        assert res2.status_code == 200, res2.text
        body = res2.json()
        assert "apply_data_transform" in (body.get("tools_called") or [])
        assert body.get("data_mutated") is True

    from api.services import upload_store, cleaning_proposals as clean_svc

    meta = upload_store.load_meta(sid)
    df = clean_svc.read_upload_dataframe(
        upload_store.upload_path(sid), nrows=None, sheet_name=meta.selected_sheet
    )
    vals = df["InvoiceDate"].astype(str).tolist()
    assert all(":" not in v for v in vals)
    assert "2024-01-15" in vals[0]


def test_add_invoice_flag_over_1000_via_assistant(client: TestClient):
    # Invoice 1 totals 1500 (>1000); invoice 2 totals 400
    raw = (
        "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
        "INV1,A,Tea,10,2024-02-01,100,C1,EG\n"
        "INV1,B,Coffee,5,2024-02-01,100,C1,EG\n"
        "INV2,C,Sugar,2,2024-02-01,200,C2,EG\n"
    ).encode()
    sid = _sid_with_mapping(client, raw)

    res = client.post(
        "/api/upload/assistant",
        json={
            "session_id": sid,
            "question": "ضيف عمود true للفواتير اللي أكبر من 1000",
            "lang": "ar",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    tools = body.get("tools_called") or []
    assert "apply_data_transform" in tools or "preview_data_transform" in tools

    if "apply_data_transform" not in tools:
        res = client.post(
            "/api/upload/assistant",
            json={
                "session_id": sid,
                "question": "طبّق ضيف عمود true للفواتير أكبر من 1000",
                "lang": "ar",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("data_mutated") is True
        tools = body.get("tools_called") or []
        assert "apply_data_transform" in tools

    from api.services import upload_store, cleaning_proposals as clean_svc

    meta = upload_store.load_meta(sid)
    df = clean_svc.read_upload_dataframe(
        upload_store.upload_path(sid), nrows=None, sheet_name=meta.selected_sheet
    )
    flag_cols = [c for c in df.columns if "over_1000" in str(c).lower() or "invoice_over" in str(c).lower()]
    assert flag_cols, list(df.columns)
    col = flag_cols[0]
    flags = df[col].astype(str).str.lower().tolist()
    # First two rows INV1 → true; third INV2 → false
    assert flags[0] == "true"
    assert flags[1] == "true"
    assert flags[2] == "false"


def test_parse_transform_intent_english():
    from api.services import data_transforms as dx

    strip = dx.parse_transform_intent("Please strip time from the date column")
    assert strip and strip["op"] == "strip_time"
    flag = dx.parse_transform_intent("Add a boolean column true for invoices above 1000 EGP")
    assert flag and flag["op"] == "add_invoice_flag"
    assert flag["threshold"] == 1000.0
