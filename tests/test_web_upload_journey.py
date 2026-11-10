"""Playwright browser E2E: Egypt upload → cleaning → dashboard → assistant.

Mocks Gemini by leaving GEMINI_API_KEY unset on the test API process so answers
stay grounded; product ranking is still computed deterministically server-side.
"""

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
FIXTURE = Path("/home/youssef/code/test/MarketMind_Egypt_Retail_Test.csv")
SHOT_DIR = ROOT / "docs" / "screenshots" / "e2e"


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


@pytest.fixture(scope="module")
def egypt_top_by_units():
    """Independent server-side ranking from the same fixture (not via the UI)."""
    if not FIXTURE.exists():
        pytest.skip(f"Egypt fixture missing: {FIXTURE}")
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    # Ensure no live Gemini during independent calc either
    os.environ["GEMINI_API_KEY"] = ""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.services import upload_analytics

    with TestClient(app) as client:
        up = client.post(
            "/api/upload",
            files={"file": ("MarketMind_Egypt_Retail_Test.csv", FIXTURE.read_bytes(), "text/csv")},
        )
        assert up.status_code == 200, up.text
        sid = up.json()["session_id"]
        settings = client.post(
            "/api/upload/settings",
            json={
                "session_id": sid,
                "currency_code": "EGP",
                "date_format": "dayfirst",
                "confirm_date_format": True,
            },
        )
        assert settings.status_code == 200
        meta = upload_analytics.get_meta_or_404(sid)
        leaders = upload_analytics.product_leaders(meta)
        client.delete(f"/api/upload/session?session_id={sid}")
    assert leaders.get("available") is True
    top = leaders["top_by_units"]
    assert top and top.get("product_name")
    return top


@pytest.fixture(scope="module")
def journey_servers():
    if os.environ.get("SKIP_WEB_SMOKE") == "1":
        pytest.skip("SKIP_WEB_SMOKE=1")
    if not FIXTURE.exists():
        pytest.skip(f"Egypt fixture missing: {FIXTURE}")
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed")

    api_port = _free_port()
    web_port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT}"
    env["MARKETMIND_API_URL"] = f"http://127.0.0.1:{api_port}"
    # No live Gemini — grounded assistant path for this browser journey
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
    api_base = f"http://127.0.0.1:{api_port}"
    try:
        _wait_http(f"{api_base}/api/health", timeout=60)
        _wait_http(base, timeout=120)
        yield {"base": base, "api": api_base}
    finally:
        for proc in (web_proc, api_proc):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def _close_assistant_if_open(page) -> None:
    dialog = page.get_by_role("dialog")
    if dialog.count() == 0:
        return
    # Prefer accessible close control
    close = dialog.get_by_role("button", name="إغلاق")
    if close.count() == 0:
        close = dialog.get_by_role("button", name="Close")
    if close.count():
        close.first.click()
    else:
        page.keyboard.press("Escape")
    page.get_by_role("dialog").wait_for(state="hidden", timeout=15000)


def _format_units_like_assistant(quantity: object) -> str:
    """Match api.services.upload_assistant._num for integer unit counts."""
    f = float(quantity)
    if abs(f - round(f)) < 1e-9:
        return f"{int(round(f)):,}"
    return f"{f:,.2f}"


def _assert_no_horizontal_overflow(page) -> None:
    metrics = page.evaluate(
        """() => {
          const root = document.documentElement;
          const body = document.body;
          const scrollW = Math.max(root.scrollWidth, body ? body.scrollWidth : 0);
          const clientW = root.clientWidth;
          return { scrollW, clientW, innerW: window.innerWidth };
        }"""
    )
    # Allow 1px subpixel slack on some engines
    assert metrics["scrollW"] <= metrics["clientW"] + 1, (
        f"horizontal overflow: scrollWidth={metrics['scrollW']} "
        f"clientWidth={metrics['clientW']} innerWidth={metrics['innerW']}"
    )


@pytest.mark.skipif(not FIXTURE.exists(), reason="Egypt CSV fixture missing")
def test_egypt_upload_to_dashboard_browser_journey(journey_servers, egypt_top_by_units):
    from playwright.sync_api import expect, sync_playwright

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    base = journey_servers["base"]
    product_name = str(egypt_top_by_units["product_name"])
    units = egypt_top_by_units["quantity"]
    units_str = _format_units_like_assistant(units)
    assert product_name == "شاي أسود 250 جم"
    assert units_str == "245"

    exe = _chrome_executable()
    with sync_playwright() as p:
        launch_kwargs: dict = {"headless": True, "args": ["--no-sandbox"]}
        if exe:
            launch_kwargs["executable_path"] = exe
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # 1–2. Upload page Arabic RTL, no aside
        page.goto(f"{base}/upload", wait_until="networkidle", timeout=90000)
        html = page.locator("html")
        expect(html).to_have_attribute("dir", "rtl")
        assert page.locator("aside").count() == 0
        expect(
            page.get_by_role("heading", name="ارفع · اسأل · نظّف · حلّل")
        ).to_be_visible()

        # 3. Upload real fixture
        page.locator('input[type="file"]').set_input_files(str(FIXTURE))

        # 4. Wait for profile completion (progress ends; profile section appears)
        expect(page.get_by_text("افهم الملف ده")).to_be_visible(timeout=120000)
        # Progress block unmounts only after proposals finish (stage 4 → clear)
        expect(page.locator(".upload-progress")).to_have_count(0, timeout=120000)
        expect(
            page.get_by_text("تم الرفع — المساعد هيقرأ ملفك", exact=False)
        ).to_be_visible(timeout=30000)
        # Assistant opens for setup
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible(timeout=30000)

        # 5. Currency EGP then date dayfirst via quick replies
        dialog.get_by_role("button", name="EGP", exact=True).click()
        expect(
            dialog.get_by_text("هعتبر المبالغ في الملف EGP", exact=False)
        ).to_be_visible(timeout=30000)
        # Date format chips appear after currency when confirmation needed
        dayfirst = dialog.get_by_role("button", name="dayfirst", exact=True)
        expect(dayfirst).to_be_visible(timeout=30000)
        dayfirst.click()
        # After date confirm: profile summary + yes chip, or cleaning walkthrough
        expect(
            dialog.get_by_text("قرأت الملف", exact=False).or_(
                dialog.get_by_text("فراغات", exact=False)
            ).or_(dialog.get_by_text("صيغة التاريخ", exact=False))
        ).to_be_visible(timeout=30000)
        yes = dialog.get_by_role("button", name="صح كده")
        if yes.count() == 0:
            yes = dialog.get_by_role("button", name="yes correct")
        if yes.count():
            yes.first.click()
            expect(dialog.locator(".assistant-bubble.bot").last).to_be_visible(
                timeout=30000
            )
            # Optional gap-fill preference — pick manual to proceed without inventing
            manual = dialog.get_by_role("button", name="ملء يدوي")
            if manual.count() == 0:
                manual = dialog.get_by_role("button", name="manual fill")
            if manual.count():
                manual.first.click()
                expect(dialog.locator(".assistant-bubble.bot").last).to_be_visible(
                    timeout=30000
                )

        _close_assistant_if_open(page)

        # Session status should show EGP
        expect(
            page.locator("section.band").filter(has_text="حالة الجلسة").get_by_text(
                "EGP", exact=True
            )
        ).to_be_visible(timeout=15000)

        # 6–7. Finish cleaning → dashboard
        finish = page.get_by_role(
            "button", name="خلّص التنظيف وافتح لوحة التحليل"
        )
        expect(finish).to_be_enabled(timeout=30000)
        finish.click()
        page.wait_for_url("**/store", timeout=60000)

        # 8. Upload-specific dashboard
        expect(page.locator("html")).to_have_attribute("dir", "rtl")
        badge = page.locator(".badge-upload")
        expect(badge).to_be_visible(timeout=60000)
        badge_text = badge.inner_text()
        assert "EGP" in badge_text
        assert "مش بيانات العرض" in badge_text or "not demo" in badge_text.lower()
        # Demo badge must not claim UK sample
        assert page.get_by_text("Sample UK retail dataset").count() == 0
        assert page.get_by_text("بيانات تجريبية من متجر بريطاني").count() == 0

        main = page.locator("main")
        expect(main).to_contain_text("EGP", timeout=30000)
        # Metrics should render non-empty KPI values
        kpis = page.locator(".kpi .value")
        expect(kpis.first).to_be_visible(timeout=30000)
        assert kpis.count() >= 3
        # Forecast unavailable explanation (gate failure)
        expect(
            page.get_by_text("توقع خاص بالمتجر مش متاح").or_(
                page.get_by_text("Store-specific forecast not available")
            )
        ).to_be_visible(timeout=30000)
        # Analyst dashboard: KPIs, trend, products, decisions; segments not forced
        expect(page.get_by_test_id("store-kpi-row")).to_be_visible(timeout=30000)
        expect(page.get_by_test_id("store-trend-card")).to_be_visible()
        expect(page.get_by_test_id("store-products-card")).to_be_visible()
        expect(page.get_by_test_id("store-suggested-steps")).to_be_visible(timeout=30000)
        expect(page.get_by_test_id("store-evidence-insights")).to_be_visible()
        assert page.get_by_test_id("store-segment-chart").count() == 0

        page.screenshot(
            path=str(SHOT_DIR / "egypt_dashboard_ar.png"), full_page=True
        )

        nav = page.get_by_role("navigation", name="تنقل")

        # 9. Products + Groups same upload session
        nav.get_by_role("link", name="المنتجات").click()
        page.wait_for_url("**/products", timeout=30000)
        expect(page.locator(".badge-upload")).to_be_visible(timeout=60000)
        expect(page.locator(".badge-upload")).to_contain_text("EGP")
        # Top product should appear in products table/list
        expect(page.get_by_text(product_name, exact=False)).to_be_visible(timeout=60000)

        nav.get_by_role("link", name="المجموعات").click()
        page.wait_for_url("**/groups", timeout=30000)
        expect(page.locator(".badge-upload")).to_be_visible(timeout=60000)
        expect(page.locator(".badge-upload")).to_contain_text("EGP")

        # 10. Assistant top-product question (upload page rehydrates session)
        nav.get_by_role("link", name="الرفع").click()
        page.wait_for_url("**/upload", timeout=30000)
        expect(page.get_by_role("button", name="افتح المساعد")).to_be_visible(
            timeout=60000
        )
        page.get_by_role("button", name="افتح المساعد").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible(timeout=15000)
        input_box = dialog.locator("input").last
        input_box.fill("إيه أعلى منتج اتباع؟")
        dialog.get_by_role("button", name="ابعت").or_(
            dialog.get_by_role("button", name="Send")
        ).click()
        # Wait for bot answer with exact product name + exact formatted units
        bot = dialog.locator(".assistant-bubble.bot").last
        expect(bot).to_contain_text(product_name, timeout=60000)
        expect(bot).to_contain_text(units_str, timeout=15000)
        answer = bot.inner_text()
        assert product_name in answer
        assert units_str in answer
        assert "Gemini ·" not in answer
        assert "unique_customers=" not in answer
        assert "context_keys" not in answer
        assert "preview_rows" not in answer
        # Not merely the opening file summary
        assert "تمام، استلمت" not in answer
        meta = bot.locator(".muted")
        if meta.count():
            meta_text = meta.inner_text()
            assert "unique_customers=" not in meta_text
            assert "Gemini ·" not in meta_text

        page.screenshot(
            path=str(SHOT_DIR / "egypt_assistant_top_product_ar.png"), full_page=True
        )
        _close_assistant_if_open(page)

        # 11. English LTR
        page.get_by_role("button", name="English").click()
        expect(page.locator("html")).to_have_attribute("dir", "ltr", timeout=10000)
        en_nav = page.get_by_role("navigation", name="Navigation")
        expect(en_nav.get_by_role("link", name="Dashboard")).to_be_visible()
        en_nav.get_by_role("link", name="Dashboard").click()
        page.wait_for_url("**/store", timeout=30000)
        expect(page.locator(".badge-upload")).to_contain_text("EGP")
        expect(page.locator(".badge-upload")).to_contain_text("not demo data")

        # 12. Reload must keep upload source (sessionStorage)
        page.reload(wait_until="networkidle", timeout=60000)
        expect(page.locator(".badge-upload")).to_be_visible(timeout=60000)
        expect(page.locator(".badge-upload")).to_contain_text("EGP")
        assert page.get_by_text("Sample UK retail dataset").count() == 0

        # 13. Mobile Arabic (~375px): dashboard, products, assistant
        page.get_by_role("button", name="العربية").click()
        expect(page.locator("html")).to_have_attribute("dir", "rtl", timeout=10000)
        page.set_viewport_size({"width": 375, "height": 812})

        page.goto(f"{base}/store", wait_until="networkidle", timeout=90000)
        expect(page.locator("html")).to_have_attribute("dir", "rtl")
        badge_m = page.locator(".badge-upload")
        expect(badge_m).to_be_visible(timeout=60000)
        expect(badge_m).to_contain_text("EGP")
        expect(page.locator("main")).to_be_visible()
        expect(page.locator(".kpi .value").first).to_be_visible(timeout=30000)
        _assert_no_horizontal_overflow(page)
        page.screenshot(
            path=str(SHOT_DIR / "egypt_dashboard_ar_mobile.png"), full_page=True
        )

        mobile_nav = page.get_by_role("navigation", name="تنقل")
        mobile_nav.get_by_role("link", name="المنتجات").click()
        page.wait_for_url("**/products", timeout=30000)
        expect(page.locator(".badge-upload")).to_be_visible(timeout=60000)
        expect(page.locator(".badge-upload")).to_contain_text("EGP")
        expect(page.get_by_text(product_name, exact=False)).to_be_visible(timeout=60000)
        expect(page.locator("main")).to_be_visible()
        _assert_no_horizontal_overflow(page)

        mobile_nav.get_by_role("link", name="الرفع").click()
        page.wait_for_url("**/upload", timeout=30000)
        expect(page.get_by_role("button", name="افتح المساعد")).to_be_visible(
            timeout=60000
        )
        _assert_no_horizontal_overflow(page)
        page.get_by_role("button", name="افتح المساعد").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible(timeout=15000)
        input_box = dialog.locator("input").last
        expect(input_box).to_be_visible()
        send_btn = dialog.get_by_role("button", name="ابعت").or_(
            dialog.get_by_role("button", name="Send")
        )
        expect(send_btn).to_be_visible()
        input_box.fill("إيه أعلى منتج اتباع؟")
        expect(send_btn).to_be_enabled()
        send_btn.click()
        bot = dialog.locator(".assistant-bubble.bot").last
        expect(bot).to_contain_text(product_name, timeout=60000)
        expect(bot).to_contain_text(units_str, timeout=15000)
        _assert_no_horizontal_overflow(page)
        _close_assistant_if_open(page)

        browser.close()

    # Record for the report
    print(
        f"E2E_OK fixture={FIXTURE} product={product_name!r} units={units_str} "
        f"dashboard=/store upload-badge=EGP shots={SHOT_DIR}"
    )
