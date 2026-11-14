"""Multi-schema POS upload battery — fixture-specific settings, not blanket EGP/dayfirst."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "client_uploads"
MANIFEST_PATH = FIXTURE_DIR / "matrix_manifest.json"

os.environ["GEMINI_API_KEY"] = ""


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


MANIFEST = _load_manifest()


def _discover_uploads() -> list[Path]:
    if not FIXTURE_DIR.is_dir():
        return []
    return sorted(
        p
        for p in FIXTURE_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in {".csv", ".xlsx"}
        and p.stat().st_size > 0
        and not p.name.startswith(".")
    )


UPLOAD_FILES = _discover_uploads()


def _mime(path: Path) -> str:
    if path.suffix.lower() == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "text/csv"


def _cfg(path: Path) -> dict:
    return MANIFEST.get(path.name) or {
        "currency": "USD",
        "date_format": "iso",
        "confirm_date": True,
        "mapping": None,
        "expect": {"sales_totals": True},
        "synthetic": True,
        "label": path.stem,
    }


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as c:
        yield c


def test_matrix_discovers_distinct_schemas():
    files = UPLOAD_FILES
    assert len(files) >= 8, f"expected diverse fixtures, found {len(files)}: {[p.name for p in files]}"
    # Header fingerprints must differ across synthetic schemas
    import pandas as pd
    from api.services import pos_ingest

    headers = {}
    for p in files:
        if p.name.startswith("MarketMind_Egypt"):
            continue
        if p.suffix.lower() == ".csv":
            df = pos_ingest.read_csv_flexible(p, nrows=2)
        else:
            continue
        headers[p.name] = tuple(df.columns.astype(str).tolist())
    assert len(set(headers.values())) >= 5, headers


@pytest.mark.skipif(not UPLOAD_FILES, reason="No files in tests/fixtures/client_uploads/")
@pytest.mark.parametrize("fixture_path", UPLOAD_FILES, ids=lambda p: p.name)
def test_client_upload_matrix_pipeline(client, fixture_path: Path):
    cfg = _cfg(fixture_path)
    expect = cfg.get("expect") or {}

    up = client.post(
        "/api/upload",
        files={"file": (fixture_path.name, fixture_path.read_bytes(), _mime(fixture_path))},
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]
    body = up.json()

    # Multi-sheet: select sales sheet before mapping/settings
    sheet = cfg.get("selected_sheet")
    if body.get("needs_sheet_selection") or sheet:
        sel = client.post(
            "/api/upload/settings",
            json={"session_id": sid, "selected_sheet": sheet or "SalesLines"},
        )
        assert sel.status_code == 200, sel.text

    # Ambiguous / custom mapping
    if cfg.get("mapping"):
        mapped = client.post(
            "/api/upload/mapping",
            json={"session_id": sid, "mapping": cfg["mapping"], "confirm": True},
        )
        assert mapped.status_code == 200, mapped.text
        assert mapped.json().get("mapping_confirmed") is True
    elif expect.get("needs_mapping"):
        # Without mapping, analysis should not be silently ready for Amount files
        val0 = client.post(f"/api/upload/validate?session_id={sid}")
        assert val0.status_code == 200
        v0 = val0.json()["validation"]
        assert v0.get("needs_user_mapping") or not v0.get("ok") or v0.get("ambiguous_columns") is not None

    settings = client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": cfg.get("currency") or "USD",
            "date_format": cfg.get("date_format") or "iso",
            "confirm_date_format": bool(cfg.get("confirm_date", True)),
        },
    )
    assert settings.status_code == 200, settings.text
    assert settings.json()["currency_code"] == (cfg.get("currency") or "USD")

    # If still needs mapping after settings (ambiguous Amount without map in cfg) — apply now
    if expect.get("needs_mapping") and not cfg.get("mapping"):
        pytest.skip("manifest should supply mapping for ambiguous fixtures")

    # Ensure mapping confirmed for auto cases
    if not cfg.get("mapping"):
        profile = client.get(f"/api/upload/{sid}/profile")
        assert profile.status_code == 200, profile.text
        pj = profile.json()
        if not pj.get("mapping_confirmed") and (pj.get("mapping") or {}).get("effective_mapping"):
            client.post(
                "/api/upload/mapping",
                json={
                    "session_id": sid,
                    "mapping": (pj.get("mapping") or {}).get("effective_mapping") or {},
                    "confirm": True,
                },
            )

    profile = client.get(f"/api/upload/{sid}/profile")
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert int(body.get("row_count") or 0) >= 1

    props = client.post(f"/api/upload/cleaning-proposals?session_id={sid}")
    assert props.status_code == 200, props.text
    assert "proposals" in props.json()

    overview = client.get(f"/api/upload/{sid}/overview")
    assert overview.status_code == 200, overview.text
    ov = overview.json()
    assert ov.get("demo") is False
    assert ov.get("source") == "upload"
    assert ov.get("currency_code") == (cfg.get("currency") or "USD")
    metrics = ov.get("metrics") or {}
    caps = ov.get("capabilities") or {}

    if expect.get("sales_totals", True):
        assert float(metrics.get("sales") or 0) >= 0
        if "sales" in expect:
            assert abs(float(metrics["sales"]) - float(expect["sales"])) < 0.01

    if expect.get("no_double_count"):
        # Line-total fixtures must not multiply LineTotal by Qty again.
        # Recompute from canonical frame money_source marker.
        from api.services import canonical_upload, upload_store

        meta = upload_store.load_meta(sid)
        parsed = canonical_upload.load_canonical_frame(meta, nrows=None, require_mapping=True)
        assert "money_source" in parsed.columns
        assert (parsed["money_source"] == "line_amount").any()
        # If both LineTotal and Qty exist, sales must equal sum(LineTotal) for eligible rows
        # (already asserted via expect["sales"] when present).
        assert "sales" in expect, "no_double_count fixtures must declare expected sales"
        products = client.get(f"/api/upload/{sid}/products")
        assert products.status_code == 200, products.text
        assert len(products.json().get("products") or []) >= 1, (
            "line-total files must still rank products by mapped line amount"
        )

    if expect.get("customer_groups") is False:
        assert caps.get("customer_groups") is False
        assert metrics.get("customers_available") is False or metrics.get("customers") in (0, None)

    if expect.get("customer_groups") is True:
        assert caps.get("customer_groups") is True

    if expect.get("category_analysis") is False:
        assert caps.get("category_analysis") is False

    if expect.get("iso_no_forced_dayfirst"):
        # ISO fixtures should not require dayfirst
        assert (cfg.get("date_format") or "iso") == "iso"

    client.delete(f"/api/upload/session?session_id={sid}")


@pytest.mark.skipif(not UPLOAD_FILES, reason="No files in tests/fixtures/client_uploads/")
@pytest.mark.parametrize("fixture_path", UPLOAD_FILES, ids=lambda p: p.name)
def test_client_upload_matrix_assistant_grounded(client, fixture_path: Path):
    cfg = _cfg(fixture_path)
    up = client.post(
        "/api/upload",
        files={"file": (fixture_path.name, fixture_path.read_bytes(), _mime(fixture_path))},
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]

    if cfg.get("selected_sheet") or up.json().get("needs_sheet_selection"):
        client.post(
            "/api/upload/settings",
            json={"session_id": sid, "selected_sheet": cfg.get("selected_sheet") or "SalesLines"},
        )
    if cfg.get("mapping"):
        client.post(
            "/api/upload/mapping",
            json={"session_id": sid, "mapping": cfg["mapping"], "confirm": True},
        )
    else:
        prof = client.get(f"/api/upload/{sid}/profile").json()
        eff = (prof.get("mapping") or {}).get("effective_mapping") or {}
        if eff and not prof.get("mapping_confirmed"):
            client.post(
                "/api/upload/mapping",
                json={"session_id": sid, "mapping": eff, "confirm": True},
            )

    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": cfg.get("currency") or "USD",
            "date_format": cfg.get("date_format") or "iso",
            "confirm_date_format": True,
        },
    )

    summary = client.post(
        "/api/upload/assistant",
        json={"session_id": sid, "question": "لخّص الملف", "lang": "ar"},
    )
    assert summary.status_code == 200, summary.text
    answer = str(summary.json().get("answer") or "")
    assert answer.strip()
    assert "Gemini ·" not in answer
    assert "preview_rows" not in answer
    assert "filename" not in answer.lower() or "MarketMind" not in answer

    client.delete(f"/api/upload/session?session_id={sid}")


def test_gemini_system_instruction_is_client_analyst():
    from api.services.gemini_provider import SYSTEM_INSTRUCTION

    assert "senior retail data analyst" in SYSTEM_INSTRUCTION.lower()
    assert "manual" in SYSTEM_INSTRUCTION.lower()
    assert "do not push customer segmentation" in SYSTEM_INSTRUCTION.lower()


def test_mixed_currency_not_silently_combined(client, tmp_path):
    import pandas as pd

    path = tmp_path / "mixed_ccy.csv"
    pd.DataFrame(
        {
            "order_id": ["1", "2"],
            "order_date": ["2024-01-01", "2024-01-02"],
            "item": ["A", "B"],
            "qty": [1, 1],
            "unit_price": [10.0, 20.0],
            "currency": ["USD", "EUR"],
        }
    ).to_csv(path, index=False)
    up = client.post(
        "/api/upload",
        files={"file": (path.name, path.read_bytes(), "text/csv")},
    )
    sid = up.json()["session_id"]
    prof = client.get(f"/api/upload/{sid}/profile").json()
    eff = (prof.get("mapping") or {}).get("effective_mapping") or {}
    client.post("/api/upload/mapping", json={"session_id": sid, "mapping": eff, "confirm": True})
    client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "USD",
            "date_format": "iso",
            "confirm_date_format": True,
        },
    )
    ov = client.get(f"/api/upload/{sid}/overview")
    assert ov.status_code == 400
    assert "currenc" in ov.json()["detail"].lower()
    # With filter, totals work for one currency only
    client.post(
        "/api/upload/settings",
        json={"session_id": sid, "analysis_currency_filter": "USD"},
    )
    ov2 = client.get(f"/api/upload/{sid}/overview")
    assert ov2.status_code == 200, ov2.text
    assert abs(float(ov2.json()["metrics"]["sales"]) - 10.0) < 0.01
    client.delete(f"/api/upload/session?session_id={sid}")


def _prepare_currency_file(client, frame, name: str):
    import pandas as pd

    assert isinstance(frame, pd.DataFrame)
    raw = frame.to_csv(index=False).encode()
    up = client.post("/api/upload", files={"file": (name, raw, "text/csv")})
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]
    prof = client.get(f"/api/upload/{sid}/profile").json()
    eff = (prof.get("mapping") or {}).get("effective_mapping") or {}
    mapped = client.post(
        "/api/upload/mapping",
        json={"session_id": sid, "mapping": eff, "confirm": True},
    )
    assert mapped.status_code == 200, mapped.text
    settings = client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "USD",
            "date_format": "iso",
            "confirm_date_format": True,
        },
    )
    assert settings.status_code == 200, settings.text
    return sid


def test_mixed_currency_excludes_blank_and_other(client):
    """USD + EUR + blank: no combined total; USD keeps only the USD row."""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "order_id": ["1", "2", "3"],
            "order_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "item": ["A", "B", "C"],
            "qty": [1, 1, 1],
            "unit_price": [10.0, 20.0, 30.0],
            "currency": ["USD", "EUR", None],
        }
    )
    sid = _prepare_currency_file(client, frame, "mixed_blank_ccy.csv")
    blocked = client.get(f"/api/upload/{sid}/overview")
    assert blocked.status_code == 400
    assert "currenc" in blocked.json()["detail"].lower()

    chosen = client.post(
        "/api/upload/settings",
        json={"session_id": sid, "analysis_currency_filter": "USD"},
    )
    assert chosen.status_code == 200, chosen.text
    ov = client.get(f"/api/upload/{sid}/overview")
    assert ov.status_code == 200, ov.text
    body = ov.json()
    assert abs(float(body["metrics"]["sales"]) - 10.0) < 0.01
    exclusion = body["currency_exclusion"]
    assert exclusion["selected_currency"] == "USD"
    assert exclusion["blank_or_unknown_excluded"] == 1
    assert exclusion["other_currency_excluded"] == 1
    assert exclusion["included_rows"] == 1
    assert exclusion["fx_conversion"] is False
    assert "blank or unknown" in exclusion["reason_en"].lower()
    products = client.get(f"/api/upload/{sid}/products")
    assert products.status_code == 200
    spend = sum(float(p["spend"]) for p in products.json()["products"])
    assert abs(spend - 10.0) < 0.01
    client.delete(f"/api/upload/session?session_id={sid}")


def test_partial_blank_currency_rows_excluded(client):
    """One known currency plus blank rows: blanks stay out of the USD total."""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "order_id": ["1", "2", "3"],
            "order_date": ["2024-02-01", "2024-02-02", "2024-02-03"],
            "item": ["A", "B", "C"],
            "qty": [1, 1, 1],
            "unit_price": [10.0, 5.0, 8.0],
            "currency": ["USD", "USD", ""],
        }
    )
    sid = _prepare_currency_file(client, frame, "partial_blank_ccy.csv")
    ov = client.get(f"/api/upload/{sid}/overview")
    assert ov.status_code == 200, ov.text
    body = ov.json()
    assert abs(float(body["metrics"]["sales"]) - 15.0) < 0.01
    exclusion = body["currency_exclusion"]
    assert exclusion["blank_or_unknown_excluded"] == 1
    assert exclusion["other_currency_excluded"] == 0
    assert exclusion["included_rows"] == 2
    assert exclusion["fx_conversion"] is False
    client.delete(f"/api/upload/session?session_id={sid}")


def test_ambiguous_dates_not_used_before_confirmation(client):
    """Slash dates stay unresolved until the user confirms day-first or month-first."""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "order_id": ["1", "2"],
            "order_date": ["03/04/2024", "05/06/2024"],
            "item": ["A", "B"],
            "qty": [1, 2],
            "unit_price": [4.0, 5.0],
        }
    )
    raw = frame.to_csv(index=False).encode()
    up = client.post("/api/upload", files={"file": ("ambiguous_dates.csv", raw, "text/csv")})
    sid = up.json()["session_id"]
    prof = client.get(f"/api/upload/{sid}/profile").json()
    eff = (prof.get("mapping") or {}).get("effective_mapping") or {}
    client.post("/api/upload/mapping", json={"session_id": sid, "mapping": eff, "confirm": True})
    client.post(
        "/api/upload/settings",
        json={"session_id": sid, "currency_code": "USD"},
    )
    blocked = client.get(f"/api/upload/{sid}/overview")
    assert blocked.status_code == 400
    assert "date" in blocked.json()["detail"].lower()
    client.post(
        "/api/upload/settings",
        json={"session_id": sid, "date_format": "dayfirst", "confirm_date_format": True},
    )
    ov = client.get(f"/api/upload/{sid}/overview")
    assert ov.status_code == 200, ov.text
    assert ov.json()["metrics"]["trends_available"] is True
    assert ov.json()["monthly_trend"]
    client.delete(f"/api/upload/session?session_id={sid}")
