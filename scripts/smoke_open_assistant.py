#!/usr/bin/env python3
"""Opt-in manual smoke: one natural-language question + one safe-fill preview.

Usage (never prints the API key):
  MARKETMIND_SMOKE_LIVE=1 GEMINI_API_KEY=… PYTHONPATH=src:. python scripts/smoke_open_assistant.py

Without MARKETMIND_SMOKE_LIVE=1 this script exits without calling Gemini.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = Path("/home/youssef/code/test/MarketMind_Egypt_Retail_Test.csv")


def main() -> int:
    if os.environ.get("MARKETMIND_SMOKE_LIVE") != "1":
        print("Set MARKETMIND_SMOKE_LIVE=1 to run (Gemini may be billed). Skipping.")
        return 0
    if not FIXTURE.exists():
        print("Egypt fixture missing — skip.")
        return 1
    # Do not print key material
    key_set = bool(os.environ.get("GEMINI_API_KEY"))
    print(f"gemini_key_configured={key_set}")

    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as client:
        up = client.post(
            "/api/upload",
            files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "text/csv")},
        )
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
        q = client.post(
            "/api/upload/assistant",
            json={
                "session_id": sid,
                "question": "قارن مبيعات الشهر ده بالشهر اللي قبله، وإيه أعلى منتج بالكمية؟",
                "lang": "ar",
            },
        )
        body = q.json()
        print("mode=", body.get("mode"))
        print("tools=", body.get("tools_called"))
        print("answer_preview=", str(body.get("answer") or "")[:400])
        fill = client.post(
            "/api/upload/assistant",
            json={
                "session_id": sid,
                "question": "ورّيني ملء القيم الناقصة الآمن من غير ما تطبق",
                "lang": "ar",
            },
        )
        print("fill_mode=", fill.json().get("mode"))
        print("fill_preview=", str(fill.json().get("answer") or "")[:400])
        client.delete(f"/api/upload/session?session_id={sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
