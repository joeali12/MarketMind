#!/usr/bin/env python3
"""Run Playwright web smoke against a running Next.js server.

Usage:
  # terminals: uvicorn api.main:app --port 8000 ; cd web && npm run dev
  python scripts/smoke_web.py [http://127.0.0.1:3000]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"


def _chrome_executable() -> str | None:
    env = os.environ.get("PLAYWRIGHT_CHROME_EXECUTABLE")
    if env and Path(env).exists():
        return env
    candidates = list(Path.home().joinpath(".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome"))
    return str(sorted(candidates)[-1]) if candidates else None


def main() -> int:
    exe = _chrome_executable()
    with sync_playwright() as p:
        kwargs: dict = {"headless": True, "args": ["--no-sandbox"]}
        if exe:
            kwargs["executable_path"] = exe
        browser = p.chromium.launch(**kwargs)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE.rstrip("/") + "/", wait_until="networkidle", timeout=60000)
        assert page.locator("aside").count() == 0, "sidebar <aside> must not exist"
        assert page.locator("html").get_attribute("dir") == "rtl"
        ar_badge = page.locator(".badge").first.inner_text()
        assert "جنيه إسترليني" in ar_badge or "GBP" in ar_badge
        page.get_by_role("button", name="English").click()
        page.wait_for_timeout(300)
        assert page.locator("html").get_attribute("dir") == "ltr"
        assert "GBP" in page.locator(".badge").first.inner_text()
        page.goto(BASE.rstrip("/") + "/products", wait_until="networkidle", timeout=60000)
        body = page.locator("main").inner_text().lower()
        assert (
            "no product-category" in body
            or "mapped category" in body
            or "no category chart" in body
            or "مفيهاش عمود تصنيف" in body
        )
        assert page.locator(".bar-chart[aria-label='Category spend']").count() == 0
        browser.close()
    print("web smoke OK", BASE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
