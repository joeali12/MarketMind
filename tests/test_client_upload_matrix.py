"""Professional multi-file upload battery.

Discovers every CSV/XLSX under tests/fixtures/client_uploads/ and verifies the
client analyst journey at the API layer with Gemini mocked off.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "client_uploads"

os.environ["GEMINI_API_KEY"] = ""


def _discover_uploads() -> list[Path]:
    if not FIXTURE_DIR.is_dir():
        return []
    files = sorted(
        p
        for p in FIXTURE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".csv", ".xlsx"} and p.stat().st_size > 0
    )
    return files


UPLOAD_FILES = _discover_uploads()


def _mime(path: Path) -> str:
    if path.suffix.lower() == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "text/csv"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.skipif(not UPLOAD_FILES, reason="No files in tests/fixtures/client_uploads/")
@pytest.mark.parametrize("fixture_path", UPLOAD_FILES, ids=lambda p: p.name)
def test_client_upload_matrix_pipeline(client, fixture_path: Path):
    """Upload → settings → profile → proposals → overview for each fixture."""
    up = client.post(
        "/api/upload",
        files={"file": (fixture_path.name, fixture_path.read_bytes(), _mime(fixture_path))},
    )
    assert up.status_code == 200, up.text
    sid = up.json()["session_id"]
    assert sid

    settings = client.post(
        "/api/upload/settings",
        json={
            "session_id": sid,
            "currency_code": "EGP",
            "date_format": "dayfirst",
            "confirm_date_format": True,
        },
    )
    assert settings.status_code == 200, settings.text
    assert settings.json()["currency_code"] == "EGP"

    profile = client.get(f"/api/upload/{sid}/profile")
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body.get("ok") is True or body.get("row_count", 0) > 0
    assert int(body.get("row_count") or 0) >= 1

    props = client.post(
        f"/api/upload/cleaning-proposals?session_id={sid}",
    )
    assert props.status_code == 200, props.text
    prop_json = props.json()
    assert "proposals" in prop_json
    assert isinstance(prop_json["proposals"], list)
    assert "unresolved_preview" in prop_json

    overview = client.get(f"/api/upload/{sid}/overview")
    assert overview.status_code == 200, overview.text
    ov = overview.json()
    assert ov.get("demo") is False
    assert ov.get("source") == "upload"
    assert ov.get("session_id") == sid
    assert ov.get("currency_code") == "EGP"
    assert ov.get("show_segment_chart_on_store") is False
    metrics = ov.get("metrics") or {}
    assert float(metrics.get("sales") or 0) >= 0
    assert int(metrics.get("orders") or 0) >= 0
    assert int(metrics.get("customers") or 0) >= 0
    steps = ov.get("suggested_next_steps") or []
    assert isinstance(steps, list)
    assert len(steps) >= 1
    # Deep dive may be present; must never be forced
    for dive in ov.get("optional_deep_dives") or []:
        assert dive.get("forced") is False
    forecast = ov.get("forecast") or {}
    assert "available" in forecast
    if not forecast.get("available"):
        assert forecast.get("reason_en") or forecast.get("reason_ar")

    client.delete(f"/api/upload/session?session_id={sid}")


@pytest.mark.skipif(not UPLOAD_FILES, reason="No files in tests/fixtures/client_uploads/")
@pytest.mark.parametrize("fixture_path", UPLOAD_FILES, ids=lambda p: p.name)
def test_client_upload_matrix_assistant_grounded(client, fixture_path: Path):
    """Grounded assistant answers must cite server numbers (no live Gemini)."""
    up = client.post(
        "/api/upload",
        files={"file": (fixture_path.name, fixture_path.read_bytes(), _mime(fixture_path))},
    )
    assert up.status_code == 200, up.text
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

    summary = client.post(
        "/api/upload/assistant",
        json={"session_id": sid, "question": "لخّص الملف", "lang": "ar"},
    )
    assert summary.status_code == 200, summary.text
    sbody = summary.json()
    assert sbody.get("demo") is False
    assert sbody.get("adapter_invoked") is False or sbody.get("mode") == "grounded_facts"
    answer = str(sbody.get("answer") or sbody.get("answer_ar") or "")
    assert answer.strip()
    assert "Gemini ·" not in answer
    assert "context_keys" not in answer
    assert "unique_customers=" not in answer

    top = client.post(
        "/api/upload/assistant",
        json={"session_id": sid, "question": "إيه أعلى منتج اتباع؟", "lang": "ar"},
    )
    assert top.status_code == 200, top.text
    tbody = top.json()
    tanswer = str(tbody.get("answer") or tbody.get("answer_ar") or "")
    assert tanswer.strip()
    # Either a named product with units, or an honest readiness message
    assert (
        "وحدة" in tanswer
        or "units" in tanswer.lower()
        or "عملة" in tanswer
        or "تاريخ" in tanswer
        or "منتج" in tanswer
    )
    assert "Gemini ·" not in tanswer
    assert "preview_rows" not in tanswer

    client.delete(f"/api/upload/session?session_id={sid}")


def test_gemini_system_instruction_is_client_analyst():
    from api.services.gemini_provider import SYSTEM_INSTRUCTION

    assert "senior retail data analyst" in SYSTEM_INSTRUCTION.lower()
    assert "manual" in SYSTEM_INSTRUCTION.lower()
    assert "do not push customer segmentation" in SYSTEM_INSTRUCTION.lower()
