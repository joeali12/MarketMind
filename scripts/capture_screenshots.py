#!/usr/bin/env python3
"""Capture local Streamlit screenshots with Playwright (app must already be running)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
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
            try:
                browser = p.chromium.launch(headless=True, channel="chrome")
            except Exception:
                browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        for name, path in PAGES.items():
            url = BASE.rstrip("/") + path
            page.goto(url, wait_until="commit", timeout=60000)
            try:
                page.wait_for_selector("h1", timeout=20000)
            except Exception:
                page.wait_for_timeout(8000)
            page.wait_for_timeout(1500)
            target = OUT / name
            page.screenshot(path=str(target), full_page=True)
            print("wrote", target, target.stat().st_size)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
