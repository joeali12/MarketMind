#!/usr/bin/env python3
"""Capture local Streamlit academic screenshots (app must already be running).

Writes under docs/screenshots/streamlit/ so Next product shots in
docs/screenshots/{home,overview,upload,products,store,e2e}/ stay untouched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots" / "streamlit"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8510"

PAGES = {
    "home.png": "/",
    "data_validation.png": "/data_validation",
    "overview.png": "/overview",
    "segments.png": "/segments",
    "customer_lookup.png": "/customer_lookup",
    "model_quality.png": "/model_quality",
}


def _chrome_executable() -> str | None:
    env = os.environ.get("PLAYWRIGHT_CHROME_EXECUTABLE")
    if env and Path(env).exists():
        return env
    candidates = list(Path("/tmp/cursor-sandbox-cache").glob("**/chromium-*/chrome-linux64/chrome"))
    candidates += list(Path.home().joinpath(".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))
    return str(sorted(candidates)[-1]) if candidates else None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    exe = _chrome_executable()
    with sync_playwright() as p:
        if exe:
            browser = p.chromium.launch(headless=True, executable_path=exe, args=["--no-sandbox"])
        else:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for name, path in PAGES.items():
            url = f"{BASE.rstrip('/')}{path}"
            # Streamlit keeps a WebSocket open, so networkidle never settles.
            page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_timeout(2500)
            out = OUT / name
            page.screenshot(path=str(out), full_page=True)
            print(f"wrote {out}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
