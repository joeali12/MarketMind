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

    cols = ["Invoice", "Quantity", "Price", "InvoiceDate"]
    strip = dx.parse_transform_intent(
        "Please strip time from the date column", columns=cols
    )
    assert strip and strip["op"] == "strip_time"
    flag = dx.parse_transform_intent(
        "Add a boolean column true for invoices above 1000 EGP", columns=cols
    )
    assert flag and flag["op"] == "add_invoice_flag"
    assert flag["threshold"] == 1000.0


def test_parse_strip_time_spoken_arabic_and_english():
    """Spoken AR/EN strip-time must compile even without LLM (heuristic fallback)."""
    from api.services import data_transforms as dx

    cols = ["Invoice", "Quantity", "Price", "InvoiceDate"]
    cases = [
        "شيل الوقت بالساعات في التاريخ",
        "في عمود التاريخ شيل الوقت اللي هو بالساعات",
        "امسح الوقت من التاريخ",
        "strip hours from the date",
        "remove the time from dates",
        "Please remove the hours from the InvoiceDate column",
    ]
    for phrase in cases:
        parsed = dx.parse_transform_intent(phrase, columns=cols, allow_llm=False)
        assert parsed and parsed["op"] == "strip_time", phrase
        assert parsed.get("confirm_apply") is True, phrase


def test_llm_compile_plan_sanitizes_strip_time(monkeypatch):
    from api.services import plan_intent

    monkeypatch.setattr(plan_intent, "gemini_key_configured", lambda: True)

    def fake_llm(question, *, columns=None, lang="en"):
        return plan_intent._sanitize_plan(
            {
                "op": "strip_time",
                "column": "InvoiceDate",
                "confirm_apply": True,
            },
            columns=list(columns or []),
        )

    monkeypatch.setattr(plan_intent, "llm_compile_plan", fake_llm)
    from api.services import data_transforms as dx

    cols = ["Invoice", "Quantity", "Price", "InvoiceDate"]
    # Force LLM path by using a soft cue that heuristic may miss without allow_llm=False
    parsed = dx.parse_transform_intent(
        "خلّي التاريخ من غير الساعات لو سمحت",
        columns=cols,
        lang="ar",
        allow_llm=True,
    )
    assert parsed and parsed["op"] == "strip_time"
    assert parsed.get("confirm_apply") is True


def test_soft_reshape_cue_covers_user_screenshot_phrasing():
    from api.services import plan_intent

    assert plan_intent.soft_reshape_cue("شيل الوقت بالساعات في التاريخ")
    assert plan_intent.soft_reshape_cue("remove the time from dates")
    assert plan_intent.soft_reshape_cue("شيل الـ 00:00:00 من التاريخ")
    assert not plan_intent.soft_reshape_cue("قارن مبيعات الشهر ده باللي قبله")
    # Bare confirms must not steal cleaning / casual ok turns.
    assert not plan_intent.soft_reshape_cue("طبّق")
    assert not plan_intent.soft_reshape_cue("ok")
    assert not plan_intent.soft_reshape_cue("تمام")


def test_midnight_datetime_counts_as_time_to_strip():
    """UI shows str(Timestamp)='… 00:00:00'; never claim date-only / leave clocks."""
    import pandas as pd

    from api.services import data_transforms as dx

    s = pd.to_datetime(pd.Series(["2025-03-13 00:00:00", "2025-04-06 00:00:00"]))
    has, count = dx._has_time_component(s)
    assert has is True
    assert count == 2
    assert dx.format_date_only(s.iloc[0]) == "2025-03-13"


def test_date_only_slash_dates_do_not_count_as_time():
    import pandas as pd

    from api.services import data_transforms as dx
    from api.services import session_mutate as sm

    s = pd.Series(["04/05/2024", "13/05/2024", "2024-05-04"])
    has, count = dx._has_time_component(s)
    assert has is False
    assert count == 0
    # ``10:00:00`` must not trigger midnight strip / auto-apply.
    assert not sm._mentions_midnight_clock("why is 10:00:00 showing?")
    assert sm._mentions_midnight_clock("شيل الـ 00:00:00 من التاريخ")
    parsed = sm.compile_plan("what does 10:00:00 mean on the invoice?", columns=["InvoiceDate"])
    assert parsed is None or parsed.get("op") != "strip_time"


def test_strip_time_persists_date_only_strings_for_midnight(tmp_path, monkeypatch):
    import pandas as pd

    from api.services import data_transforms as dx
    from api.services import upload_store

    monkeypatch.setenv("MARKETMIND_USE_TMP_UPLOADS", "1")
    monkeypatch.setattr(upload_store, "UPLOAD_TMP_ROOT", tmp_path)

    raw = (
        "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
        "1,A,Tea,1,2025-03-13 00:00:00,10,C1,EG\n"
        "2,B,Coffee,2,2025-04-06 00:00:00,20,C2,EG\n"
    ).encode()
    meta = upload_store.create_session("midnight.csv", raw)
    meta.date_format = "iso"
    meta.date_format_confirmed = True
    meta.column_mapping = {
        "invoice": "Invoice",
        "stock_code": "StockCode",
        "description": "Description",
        "quantity": "Quantity",
        "invoice_date": "InvoiceDate",
        "unit_price": "Price",
        "customer_id": "Customer ID",
        "country": "Country",
    }
    upload_store.save_meta(meta)

    result = dx.preview_or_apply(meta, op="strip_time", confirm_apply=True)
    assert result.get("ok") is True, result
    assert result.get("error_code") != "no_time_component"

    path = upload_store.upload_path(meta.session_id)
    df = pd.read_csv(path)
    vals = df["InvoiceDate"].astype(str).tolist()
    assert vals == ["2025-03-13", "2025-04-06"]
    assert all(":" not in v for v in vals)
    # Must not claim “already date-only” for midnight datetime columns.
    preview = dx.preview_or_apply(meta, op="strip_time", confirm_apply=False)
    # After strip, pure YYYY-MM-DD strings → truly date-only.
    assert preview.get("error_code") == "no_time_component"


def test_parse_intent_ignores_weak_and_picks_threshold_near_comparison():
    from api.services import data_transforms as dx

    cols = ["Invoice", "Quantity", "Price", "InvoiceDate"]
    assert dx.parse_transform_intent("What is the invoice timestamp format?") is None
    assert dx.parse_transform_intent("rename something later") is None
    flag = dx.parse_transform_intent(
        "In 2024 add a flag column true for invoices above 2500 EGP", columns=cols
    )
    assert flag and flag["op"] == "add_invoice_flag"
    assert flag["threshold"] == 2500.0


def test_strip_time_honors_dayfirst(client: TestClient):
    raw = (
        "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
        "1,A,Tea,1,04/05/2024 14:00,10,C1,EG\n"
    ).encode()
    up = client.post("/api/upload", files={"file": ("dmy.csv", raw, "text/csv")})
    sid = up.json()["session_id"]
    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "EGP",
            "date_format": "dayfirst",
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
    res = client.post(
        "/api/upload/assistant",
        json={"session_id": sid, "question": "شيل الساعة من التاريخ", "lang": "ar"},
    )
    assert res.status_code == 200
    from api.services import upload_store, cleaning_proposals as clean_svc

    meta = upload_store.load_meta(sid)
    df = clean_svc.read_upload_dataframe(
        upload_store.upload_path(sid), nrows=None, sheet_name=meta.selected_sheet
    )
    assert str(df["InvoiceDate"].iloc[0]) == "2024-05-04"


def test_bare_apply_after_preview_beats_cleaning(client: TestClient):
    from api.services import data_transforms as dx
    from api.services import upload_store

    raw = (
        "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
        "1,A,Tea,1,2024-01-15 14:30:00,10,C1,EG\n"
    ).encode()
    sid = _sid_with_mapping(client, raw)
    meta = upload_store.load_meta(sid)
    preview = dx.preview_or_apply(meta, op="strip_time", confirm_apply=False)
    assert preview.get("ok") and preview.get("needs_confirm")
    meta = upload_store.load_meta(sid)
    assert meta.pending_transform

    confirm = client.post(
        "/api/upload/assistant",
        json={"session_id": sid, "question": "طبّق", "lang": "ar"},
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert "apply_data_transform" in (body.get("tools_called") or [])
    assert body.get("data_mutated") is True
    # Must not have fallen into cleaning "No proposals to adjust."
    assert "proposals" not in (body.get("answer_en") or "").lower()


def test_blank_invoice_rows_not_pooled():
    from api.services import data_transforms as dx
    from api.services.upload_store import UploadSessionMeta

    df = pd.DataFrame(
        {
            "Invoice": ["A", "", ""],
            "Quantity": [1, 2, 2],
            "Price": [100, 100, 100],
        }
    )
    meta = UploadSessionMeta(
        session_id="t",
        created_at=0.0,
        filename="t.csv",
        extension=".csv",
        byte_size=1,
        currency_code="EGP",
        column_mapping={"invoice": "Invoice", "quantity": "Quantity", "unit_price": "Price"},
    )
    out = dx._op_add_invoice_flag(
        df, meta=meta, mapping=meta.column_mapping, new_column="over_1000", threshold=1000, apply=True
    )
    assert out["ok"]
    flags = out["dataframe"]["over_1000"].tolist()
    assert flags == ["false", "false", "false"]


def test_line_amount_nan_falls_back_to_qty_price():
    from api.services import data_transforms as dx
    from api.services.upload_store import UploadSessionMeta

    df = pd.DataFrame(
        {
            "Invoice": ["A", "A"],
            "Quantity": [10, 5],
            "Price": [100, 100],
            "LineTotal": [None, 200],
        }
    )
    meta = UploadSessionMeta(
        session_id="t",
        created_at=0.0,
        filename="t.csv",
        extension=".csv",
        byte_size=1,
        currency_code="EGP",
        column_mapping={
            "invoice": "Invoice",
            "quantity": "Quantity",
            "unit_price": "Price",
            "line_amount": "LineTotal",
        },
    )
    out = dx._op_add_invoice_flag(
        df, meta=meta, mapping=meta.column_mapping, new_column="over_1000", threshold=1000, apply=True
    )
    assert out["ok"]
    # 1000 (filled) + 200 = 1200 > 1000
    assert out["dataframe"]["over_1000"].tolist() == ["true", "true"]


def test_protect_underscore_aliases_and_rename_mapping():
    from api.services import data_transforms as dx
    from api.services.upload_store import UploadSessionMeta

    df = pd.DataFrame({"customer_id": [1], "unit_price": [2.0], "notes": ["x"]})
    meta = UploadSessionMeta(
        session_id="t",
        created_at=0.0,
        filename="t.csv",
        extension=".csv",
        byte_size=1,
        column_mapping={"customer_id": "customer_id", "unit_price": "unit_price"},
    )
    drop = dx._op_drop_column(
        df, column="customer_id", mapping=meta.column_mapping, apply=False
    )
    assert drop["ok"] is False
    assert drop["error_code"] == "protected_column"

    ren = dx._op_rename_column(
        df,
        meta=meta,
        column="notes",
        rename_to="memo",
        mapping={"extra": "notes"},
        apply=True,
    )
    assert ren["ok"]
    assert meta.column_mapping["extra"] == "memo"


def test_general_plan_filter_sort_assign_via_assistant(client: TestClient):
    raw = (
        "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
        "1,A,Tea,1,2024-01-15,10,C1,EG\n"
        "2,B,Coffee,2,2024-01-16,20,C2,UK\n"
        "3,C,Sugar,5,2024-01-17,5,C3,EG\n"
    ).encode()
    sid = _sid_with_mapping(client, raw)

    res = client.post(
        "/api/upload/assistant",
        json={
            "session_id": sid,
            "question": "filter Country == 'EG'",
            "lang": "en",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    tools = body.get("tools_called") or []
    assert "apply_data_transform" in tools or "preview_data_transform" in tools
    if "apply_data_transform" not in tools:
        res = client.post(
            "/api/upload/assistant",
            json={"session_id": sid, "question": "apply", "lang": "en"},
        )
        assert res.status_code == 200
        assert res.json().get("data_mutated") is True

    from api.services import upload_store, cleaning_proposals as clean_svc

    meta = upload_store.load_meta(sid)
    df = clean_svc.read_upload_dataframe(
        upload_store.upload_path(sid), nrows=None, sheet_name=meta.selected_sheet
    )
    assert len(df) == 2
    assert set(df["Country"].astype(str)) == {"EG"}

    # Non-templated assign expression
    res2 = client.post(
        "/api/upload/assistant",
        json={
            "session_id": sid,
            "question": "add column high = Quantity * Price > 15",
            "lang": "en",
        },
    )
    assert res2.status_code == 200, res2.text
    body2 = res2.json()
    if "apply_data_transform" not in (body2.get("tools_called") or []):
        res2 = client.post(
            "/api/upload/assistant",
            json={"session_id": sid, "question": "apply", "lang": "en"},
        )
        assert res2.json().get("data_mutated") is True
    meta = upload_store.load_meta(sid)
    df = clean_svc.read_upload_dataframe(
        upload_store.upload_path(sid), nrows=None, sheet_name=meta.selected_sheet
    )
    assert "high" in df.columns
    flags = df["high"].astype(str).str.lower().tolist()
    assert flags == ["false", "true"]  # 10 vs 25


def test_safe_expr_rejects_attribute_and_import():
    from api.services import session_mutate as sm
    import pandas as pd

    df = pd.DataFrame({"Quantity": [1, 2]})
    try:
        sm.eval_expr(df, "__import__('os').system('x')")
        assert False, "should refuse"
    except sm.SafeExprError:
        pass
    try:
        sm.eval_expr(df, "Quantity.apply")
        assert False, "should refuse"
    except sm.SafeExprError:
        pass
    out = sm.eval_expr(df, "Quantity * 2")
    assert list(out) == [2, 4]


def test_refuse_unsafe_out_of_scope():
    from api.services import data_transforms as dx

    bad = dx.parse_transform_intent("retrain the model on this file")
    assert bad and bad["op"] == "refuse"
