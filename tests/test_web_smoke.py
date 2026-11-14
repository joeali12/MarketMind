"""Playwright smoke for Next.js web: no sidebar, RTL/LTR, chat-first upload."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_http(url: str, timeout: float = 90.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_err}")


def _chrome_executable() -> str | None:
    env = os.environ.get("PLAYWRIGHT_CHROME_EXECUTABLE")
    if env and Path(env).exists():
        return env
    candidates = list(
        Path.home().joinpath(".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome")
    )
    candidates += list(
        Path("/tmp/cursor-sandbox-cache").glob("**/chromium-*/chrome-linux64/chrome")
    )
    return str(sorted(candidates)[-1]) if candidates else None


@pytest.fixture(scope="module")
def web_base_url():
    if os.environ.get("SKIP_WEB_SMOKE") == "1":
        pytest.skip("SKIP_WEB_SMOKE=1")

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed")

    api_port = _free_port()
    web_port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT}"
    env["MARKETMIND_API_URL"] = f"http://127.0.0.1:{api_port}"
    # Keep smoke offline for Gemini
    env["GEMINI_API_KEY"] = ""

    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    web_proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(web_port), "-H", "127.0.0.1"],
        cwd=str(WEB),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{web_port}"
    try:
        _wait_http(f"http://127.0.0.1:{api_port}/api/health", timeout=60)
        _wait_http(base, timeout=120)
        yield base
    finally:
        for proc in (web_proc, api_proc):
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="module")
def browser_page(web_base_url: str):
    from playwright.sync_api import sync_playwright

    exe = _chrome_executable()
    if not exe:
        pytest.skip(
            "Playwright Chromium binary not found. "
            "Install with: pip install -r requirements-dev.txt && playwright install chromium "
            "(or set PLAYWRIGHT_CHROME_EXECUTABLE). "
            "CI sets SKIP_WEB_SMOKE=1 to skip this suite."
        )
    with sync_playwright() as p:
        launch_kwargs: dict = {
            "headless": True,
            "args": ["--no-sandbox"],
            "executable_path": exe,
        }
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        yield page, web_base_url
        browser.close()


def test_web_no_aside_rtl_ltr_upload_chat(browser_page):
    page, base = browser_page
    page.goto(f"{base}/upload", wait_until="networkidle", timeout=60000)

    # Default Arabic → RTL; no permanent sidebar
    assert page.locator("aside").count() == 0
    html = page.locator("html")
    assert html.get_attribute("dir") == "rtl"
    main = page.locator("main").inner_text()
    assert "ارفع" in main or "نضّف" in main or "Upload" in main

    page.get_by_role("button", name="EN", exact=True).click()
    page.wait_for_timeout(300)
    assert html.get_attribute("dir") == "ltr"
    expect_hero = page.get_by_test_id("upload-hero-title")
    assert expect_hero.count() >= 1
    assert "Understand your customers" in expect_hero.inner_text()
    # File input present for the chat-first upload journey
    assert page.locator('input[type="file"]').count() >= 1

    page.get_by_role("button", name="عربي", exact=True).click()
    page.wait_for_timeout(300)
    assert page.locator("html").get_attribute("dir") == "rtl"
    assert page.locator("aside").count() == 0
    assert "افهم زبائنك" in page.get_by_test_id("upload-hero-title").inner_text()
