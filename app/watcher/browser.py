from __future__ import annotations

from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.utils.time_utils import timestamp


def open_pirateswap(playwright, config: dict[str, Any]):
    print(f"[{timestamp()}] opening PirateSwap: {config['url']}")
    browser = playwright.chromium.launch(headless=config.get("headless", True))
    try:
        page = browser.new_page()
        page.goto(config["url"], wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
            print(f"[{timestamp()}] page network is idle; connection will be reused")
        except PlaywrightTimeoutError:
            print(f"[{timestamp()}] page network idle timed out; continuing")
        return browser, page
    except Exception:
        browser.close()
        raise
