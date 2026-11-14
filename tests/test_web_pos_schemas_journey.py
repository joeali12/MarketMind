"""Browser journeys for distinct POS schemas (qty×price, line total, no CID, multi-sheet, Amount).

Mocks Gemini by leaving GEMINI_API_KEY unset. Expected sales come from fixture math,
not hard-coded UI strings.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
FIXTURES = ROOT / "tests" / "fixtures" / "client_uploads"
POS = FIXTURES / "synth_pos_en_qty_price.csv"
LINE_TOTAL = FIXTURES / "synth_supermarket_line_total.csv"
NO_CID = FIXTURES / "synth_no_customer_id.csv"
MULTI = FIXTURES / "synth_multisheet_sales.xlsx"
AMOUNT = FIXTURES / "synth_ambiguous_amount.csv"
SHOT_DIR = ROOT / "docs" / "screenshots" / "e2e"

# Fixture-derived expected eligible sales (qty×price or LineTotal — see matrix README).
EXPECTED = {
    "pos": 69.0,
    "line_total": 81.0,
    "no_cid": 41.0,
    "multi": 170.0,
    "amount": 67.5,
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_http(url: str, timeout: float = 120.0) -> None:
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
            time.sleep(0.4)
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


def _parse_money(text: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    assert cleaned, f"no numeric sales in {text!r}"
    return float(cleaned)


def _assert_sales_kpi(page, expected: float, *, api: str | None = None, session_hint: bool = True) -> None:
    """UI money may round; exact total is verified from the same fixture math via API when possible."""
    sales = page.get_by_test_id("store-kpi-sales-value")
    shown = _parse_money(sales.inner_text())
    # Display formatting may round (e.g. 67.5 → 68); allow ±1 for UI.
    assert abs(shown - expected) <= 1.0, f"UI sales {shown} vs expected {expected}"
    if api and session_hint:
        import json
        import urllib.request

        raw = page.evaluate("() => sessionStorage.getItem('mm_data_source')")
        data = json.loads(raw) if raw else {}
        sid = data.get("sessionId")
        assert sid, "missing sessionId in sessionStorage"
        with urllib.request.urlopen(f"{api}/api/upload/{sid}/overview") as resp:
            body = json.loads(resp.read().decode())
        exact = float((body.get("metrics") or {}).get("sales") or 0)
        assert abs(exact - expected) < 0.05, f"API sales {exact} vs expected {expected}"


def _assert_no_horizontal_overflow(page) -> None:
    overflow = page.evaluate(
        """() => {
          const doc = document.documentElement;
          return doc.scrollWidth - doc.clientWidth;
        }"""
    )
    assert overflow <= 2, f"horizontal overflow {overflow}px"


@pytest.fixture(scope="module")
def journey_servers():
    if os.environ.get("SKIP_WEB_SMOKE") == "1":
        pytest.skip("SKIP_WEB_SMOKE=1")
    needed = [POS, LINE_TOTAL, NO_CID, MULTI, AMOUNT]
    if not all(p.exists() for p in needed):
        missing = [p.name for p in needed if not p.exists()]
        pytest.skip(f"POS schema fixtures missing: {missing}")
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed")

    api_port = _free_port()
    web_port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT}"
    env["MARKETMIND_API_URL"] = f"http://127.0.0.1:{api_port}"
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
        yield {"base": base, "api": f"http://127.0.0.1:{api_port}"}
    finally:
        for proc in (web_proc, api_proc):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def _close_assistant(page) -> None:
    """Dismiss assistant dialog/backdrop so later clicks are not intercepted."""
    for _ in range(3):
        dialog = page.get_by_role("dialog")
        backdrop = page.locator(".assistant-backdrop")
        if dialog.count() == 0 and backdrop.count() == 0:
            return
        if dialog.count():
            close = dialog.get_by_role("button", name="إغلاق")
            if close.count() == 0:
                close = dialog.get_by_role("button", name="Close")
            if close.count():
                close.first.click(force=True)
            else:
                page.keyboard.press("Escape")
        else:
            page.keyboard.press("Escape")
        try:
            page.get_by_role("dialog").wait_for(state="hidden", timeout=5000)
        except Exception:  # noqa: BLE001
            pass
        try:
            backdrop.wait_for(state="hidden", timeout=3000)
        except Exception:  # noqa: BLE001
            page.evaluate(
                """() => {
                  document.querySelectorAll('.assistant-backdrop,[role="dialog"]').forEach((el) => el.remove());
                }"""
            )
            return
    page.evaluate(
        """() => {
          document.querySelectorAll('.assistant-backdrop,[role="dialog"]').forEach((el) => el.remove());
        }"""
    )


def _confirm_via_dialog_or_assistant(
    page,
    *,
    currency: str,
    date_fmt: str,
    lang: str = "en",
) -> None:
    dialog = page.get_by_role("dialog")
    if dialog.count():
        cur_btn = dialog.get_by_role("button", name=currency, exact=True)
        if cur_btn.count():
            cur_btn.first.click()
            page.wait_for_timeout(400)
        iso = dialog.get_by_role("button", name=date_fmt, exact=True)
        if iso.count() == 0 and date_fmt.lower() == "iso":
            iso = dialog.get_by_role("button", name="ISO", exact=True)
        if iso.count() == 0 and date_fmt == "dayfirst":
            iso = dialog.get_by_role("button", name="dayfirst", exact=True)
        if iso.count():
            iso.first.click()
            page.wait_for_timeout(400)
        yes = dialog.get_by_role("button", name="yes correct")
        if yes.count() == 0:
            yes = dialog.get_by_role("button", name="صح كده")
        if yes.count():
            yes.first.click()
            page.wait_for_timeout(400)
        _close_assistant(page)

    finish_en = page.get_by_role("button", name="Finish cleaning and open my dashboard")
    finish_ar = page.get_by_role("button", name="خلّص التنظيف وافتح لوحة التحليل")
    finish = finish_en if finish_en.count() else finish_ar
    if finish.count() and finish.is_disabled():
        _close_assistant(page)
        open_name = "Open assistant" if lang == "en" else "افتح المساعد"
        send_name = "Send" if lang == "en" else "ابعت"
        open_btn = page.get_by_role("button", name=open_name)
        if open_btn.count():
            open_btn.click(force=True)
            d = page.get_by_role("dialog")
            box = d.locator("input").last
            box.fill(currency)
            d.get_by_role("button", name=send_name).click()
            page.wait_for_timeout(1200)
            box.fill(date_fmt)
            d.get_by_role("button", name=send_name).click()
            page.wait_for_timeout(1200)
            _close_assistant(page)
    _close_assistant(page)


def _finish_to_store(page, *, finish_en: bool = True) -> None:
    finish = page.get_by_role(
        "button",
        name="Finish cleaning and open my dashboard"
        if finish_en
        else "خلّص التنظيف وافتح لوحة التحليل",
    )
    expect = __import__("playwright.sync_api", fromlist=["expect"]).expect
    expect(finish).to_be_enabled(timeout=60000)
    finish.click(force=True)
    page.wait_for_url("**/store", timeout=60000)


def _open_browser(journey_servers):
    from playwright.sync_api import sync_playwright

    exe = _chrome_executable()
    if not exe:
        pytest.skip(
            "Playwright Chromium binary not found. "
            "Install: pip install -r requirements-dev.txt && playwright install chromium"
        )
    pw = sync_playwright().start()
    kwargs = {
        "headless": True,
        "args": ["--no-sandbox"],
        "executable_path": exe,
    }
    browser = pw.chromium.launch(**kwargs)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    return pw, browser, page, journey_servers["base"]


@pytest.mark.skipif(not POS.exists(), reason="POS fixture missing")
def test_pos_en_qty_price_browser_journey(journey_servers):
    from playwright.sync_api import expect

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    pw, browser, page, base = _open_browser(journey_servers)
    try:
        page.goto(f"{base}/upload", wait_until="networkidle", timeout=90000)
        page.get_by_role("button", name="EN", exact=True).click()
        expect(page.locator("html")).to_have_attribute("dir", "ltr")
        page.locator('input[type="file"]').set_input_files(str(POS))
        expect(
            page.get_by_test_id("understand-file").or_(page.get_by_test_id("column-mapping-panel"))
        ).to_be_visible(timeout=120000)
        if page.get_by_test_id("confirm-column-mapping").count():
            page.get_by_test_id("confirm-column-mapping").click()
            page.wait_for_timeout(800)
        _confirm_via_dialog_or_assistant(page, currency="USD", date_fmt="iso", lang="en")
        _finish_to_store(page, finish_en=True)
        expect(page.locator(".badge-upload")).to_contain_text("USD")
        expect(page.get_by_test_id("store-kpi-sales-value")).to_be_visible(timeout=30000)
        _assert_sales_kpi(page, EXPECTED["pos"], api=journey_servers["api"])
        page.screenshot(path=str(SHOT_DIR / "pos_en_dashboard_en.png"), full_page=True)
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{base}/store", wait_until="networkidle", timeout=90000)
        expect(page.get_by_test_id("store-kpi-sales-value")).to_be_visible(timeout=30000)
        _assert_no_horizontal_overflow(page)
        page.screenshot(path=str(SHOT_DIR / "pos_en_dashboard_en_mobile.png"), full_page=True)
        page.goto(f"{base}/products", wait_until="networkidle", timeout=90000)
        expect(page.locator("main")).not_to_contain_text("Demo data", timeout=15000)
    finally:
        browser.close()
        pw.stop()
    print(f"E2E_POS_OK fixture={POS} sales={EXPECTED['pos']} shots={SHOT_DIR}")


@pytest.mark.skipif(not LINE_TOTAL.exists(), reason="Line-total fixture missing")
def test_line_total_no_double_count_browser_journey(journey_servers):
    from playwright.sync_api import expect

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    pw, browser, page, base = _open_browser(journey_servers)
    try:
        page.goto(f"{base}/upload", wait_until="networkidle", timeout=90000)
        page.get_by_role("button", name="EN", exact=True).click()
        page.locator('input[type="file"]').set_input_files(str(LINE_TOTAL))
        expect(
            page.get_by_test_id("understand-file").or_(page.get_by_test_id("column-mapping-panel"))
        ).to_be_visible(timeout=120000)
        if page.get_by_test_id("confirm-column-mapping").count():
            page.get_by_test_id("confirm-column-mapping").click()
            page.wait_for_timeout(800)
        _confirm_via_dialog_or_assistant(page, currency="GBP", date_fmt="dayfirst", lang="en")
        _finish_to_store(page, finish_en=True)
        expect(page.locator(".badge-upload")).to_contain_text("GBP")
        expect(page.get_by_test_id("store-kpi-sales-value")).to_be_visible(timeout=30000)
        value = _parse_money(page.get_by_test_id("store-kpi-sales-value").inner_text())
        assert abs(value - 239.0) > 1.0, "looks like Qty×LineTotal double-count in UI"
        _assert_sales_kpi(page, EXPECTED["line_total"], api=journey_servers["api"])
        page.screenshot(path=str(SHOT_DIR / "line_total_dashboard_en.png"), full_page=True)
    finally:
        browser.close()
        pw.stop()
    print(f"E2E_LINE_TOTAL_OK sales={EXPECTED['line_total']}")


@pytest.mark.skipif(not NO_CID.exists(), reason="No-customer fixture missing")
def test_no_customer_id_browser_journey(journey_servers):
    from playwright.sync_api import expect

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    pw, browser, page, base = _open_browser(journey_servers)
    try:
        page.goto(f"{base}/upload", wait_until="networkidle", timeout=90000)
        expect(page.locator("html")).to_have_attribute("dir", "rtl")
        page.locator('input[type="file"]').set_input_files(str(NO_CID))
        expect(
            page.get_by_test_id("understand-file").or_(page.get_by_test_id("column-mapping-panel"))
        ).to_be_visible(timeout=120000)
        if page.get_by_test_id("confirm-column-mapping").count():
            page.get_by_test_id("confirm-column-mapping").click()
            page.wait_for_timeout(800)
        _confirm_via_dialog_or_assistant(page, currency="EUR", date_fmt="iso", lang="ar")
        _finish_to_store(page, finish_en=False)
        expect(page.locator(".badge-upload")).to_contain_text("EUR")
        expect(page.get_by_test_id("store-kpi-sales-value")).to_be_visible(timeout=30000)
        _assert_sales_kpi(page, EXPECTED["no_cid"], api=journey_servers["api"])
        main = page.locator("main").inner_text()
        assert "غير متاح" in main or "N/A" in main or "مش متاحة" in main
        page.screenshot(path=str(SHOT_DIR / "no_cid_dashboard_ar.png"), full_page=True)
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{base}/store", wait_until="networkidle", timeout=90000)
        expect(page.get_by_test_id("store-kpi-sales-value")).to_be_visible(timeout=30000)
        _assert_no_horizontal_overflow(page)
        page.screenshot(path=str(SHOT_DIR / "no_cid_dashboard_ar_mobile.png"), full_page=True)
    finally:
        browser.close()
        pw.stop()
    print(f"E2E_NO_CID_OK fixture={NO_CID} sales={EXPECTED['no_cid']}")


@pytest.mark.skipif(not MULTI.exists(), reason="Multi-sheet fixture missing")
def test_multisheet_excel_browser_journey(journey_servers):
    from playwright.sync_api import expect

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    pw, browser, page, base = _open_browser(journey_servers)
    try:
        page.goto(f"{base}/upload", wait_until="networkidle", timeout=90000)
        page.get_by_role("button", name="EN", exact=True).click()
        page.locator('input[type="file"]').set_input_files(str(MULTI))
        # Must show sheet / mapping panel — not silently use Summary
        expect(page.get_by_test_id("column-mapping-panel")).to_be_visible(timeout=120000)
        sheet_select = page.get_by_test_id("sheet-select")
        expect(sheet_select).to_be_visible(timeout=30000)
        sheet_select.select_option("SalesLines")
        page.wait_for_timeout(1200)
        if page.get_by_test_id("confirm-column-mapping").count():
            page.get_by_test_id("confirm-column-mapping").click()
            page.wait_for_timeout(800)
        _confirm_via_dialog_or_assistant(page, currency="USD", date_fmt="iso", lang="en")
        _finish_to_store(page, finish_en=True)
        expect(page.locator(".badge-upload")).to_contain_text("USD")
        expect(page.get_by_test_id("store-kpi-sales-value")).to_be_visible(timeout=30000)
        _assert_sales_kpi(page, EXPECTED["multi"], api=journey_servers["api"])
        page.screenshot(path=str(SHOT_DIR / "multisheet_dashboard_en.png"), full_page=True)
    finally:
        browser.close()
        pw.stop()
    print(f"E2E_MULTISHEET_OK sales={EXPECTED['multi']}")


@pytest.mark.skipif(not AMOUNT.exists(), reason="Ambiguous Amount fixture missing")
def test_ambiguous_amount_requires_manual_mapping_browser(journey_servers):
    from playwright.sync_api import expect

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    pw, browser, page, base = _open_browser(journey_servers)
    try:
        page.goto(f"{base}/upload", wait_until="networkidle", timeout=90000)
        page.get_by_role("button", name="EN", exact=True).click()
        page.locator('input[type="file"]').set_input_files(str(AMOUNT))
        expect(page.get_by_test_id("column-mapping-panel")).to_be_visible(timeout=120000)
        _close_assistant(page)
        panel = page.get_by_test_id("column-mapping-panel")
        expect(panel).to_contain_text("Amount")
        expect(panel).to_contain_text("ambiguous")
        # Explicit user choice: Amount → unit selling price (never auto-applied)
        page.get_by_label("Map Amount").select_option("unit_price")
        for label, canon in [
            ("Map TxnID", "invoice"),
            ("Map TxnDate", "invoice_date"),
            ("Map Product", "description"),
            ("Map Qty", "quantity"),
        ]:
            sel = page.get_by_label(label)
            if sel.count():
                sel.select_option(canon)
        page.get_by_test_id("confirm-column-mapping").click(force=True)
        page.wait_for_timeout(1200)
        # If mapping still incomplete, surface error rather than silent auto-map
        err = panel.locator("p").filter(has_text=re.compile(r"map|required|ربط", re.I))
        if err.count() and page.get_by_role(
            "button", name="Finish cleaning and open my dashboard"
        ).is_disabled():
            # Ensure required non-ambiguous fields are set from seed, then re-confirm
            for label, canon in [
                ("Map TxnID", "invoice"),
                ("Map TxnDate", "invoice_date"),
                ("Map Product", "description"),
                ("Map Qty", "quantity"),
            ]:
                sel = page.get_by_label(label)
                if sel.count():
                    sel.select_option(canon)
            page.get_by_label("Map Amount").select_option("unit_price")
            page.get_by_test_id("confirm-column-mapping").click()
            page.wait_for_timeout(1000)
        _confirm_via_dialog_or_assistant(page, currency="USD", date_fmt="iso", lang="en")
        _finish_to_store(page, finish_en=True)
        expect(page.get_by_test_id("store-kpi-sales-value")).to_be_visible(timeout=30000)
        _assert_sales_kpi(page, EXPECTED["amount"], api=journey_servers["api"])
        page.screenshot(path=str(SHOT_DIR / "ambiguous_amount_dashboard_en.png"), full_page=True)
    finally:
        browser.close()
        pw.stop()
    print(f"E2E_AMOUNT_OK sales={EXPECTED['amount']} (manual mapping required)")
