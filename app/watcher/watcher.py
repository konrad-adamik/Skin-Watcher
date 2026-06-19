from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.models import MAX_WATCHED_SKINS, SkinRule
from app.notify_discord.notify import notify
from app.paths import SETTINGS_PATH
from app.runtime import build_watcher_config
from app.settings import load_settings
from app.sites.pirateswap import search_for_skin
from app.state import load_state, save_state
from app.utils.text import full_skin_name, normalize_text
from app.utils.time_utils import timestamp


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def result_id(rule: SkinRule, result_text: str) -> str:
    digest = hashlib.sha256(normalize_text(result_text).lower().encode("utf-8")).hexdigest()
    return f"{full_skin_name(rule).lower()}:stattrak={rule.stattrak}:{digest}"


def watch_signature(config: dict[str, Any]) -> str:
    watched = {
        "url": config.get("url"),
        "skins": config.get("skins", []),
    }
    payload = json.dumps(watched, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def check_once(config: dict[str, Any], state: dict[str, Any], page) -> int:
    rules = [SkinRule(**skin) for skin in config["skins"]]
    signature = watch_signature(config)
    if state.get("watch_signature") != signature:
        state.clear()
        state["watch_signature"] = signature
        state["seen"] = {}
        state["baseline_done"] = False

    seen = state.setdefault("seen", {})
    baseline_done = bool(state.get("baseline_done"))
    new_count = 0

    print(f"[{timestamp()}] checking skins availability for {len(rules)} skin(s)")
    for rule in rules:
        results = search_for_skin(page, rule)
        rule_name = full_skin_name(rule)
        print(f"[{timestamp()}] {rule_name}: found {len(results)} matching block(s)")

        for result in results:
            item_id = result_id(rule, result.identity_text)
            if item_id in seen:
                continue

            should_notify = baseline_done or config.get("notify_initial", False)

            seen[item_id] = {
                "skin": rule.name,
                "full_skin_name": rule_name,
                "first_seen": timestamp(),
                "text": result.text,
                "identity_text": result.identity_text,
                "image_url": result.image_url,
            }

            if not should_notify:
                continue

            new_count += 1

            result_lines = result.text.splitlines()
            skin_title = result_lines[0] if result_lines else rule_name
            message = "\n".join(result_lines[1:])
            if "float=no float" in result.identity_text:
                print(f"[{timestamp()}] float parse fallback: {result.identity_text}")
            print(message)
            notify(config, skin_title, message, result.image_url)

    if not baseline_done:
        state["baseline_done"] = True
        print(f"[{timestamp()}] initial scan complete; matches saved as baseline")

    state["last_checked"] = timestamp()
    return new_count


def main() -> int:
    configure_output_encoding()
    parser = argparse.ArgumentParser(description="Watch configured CS2 skins.")
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH)
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    parser.add_argument("--test-notify", action="store_true", help="Send a test notification and exit.")
    parser.add_argument(
        "--skins-json",
        help="Session-only skins JSON passed by the UI. These skins are not persisted.",
    )
    parser.add_argument(
        "--notify-initial",
        action="store_true",
        help="Notify about matches found during the initial scan.",
    )
    args = parser.parse_args()

    try:
        settings = load_settings(args.settings)
        skins = json.loads(args.skins_json) if args.skins_json else []
        if not args.test_notify and not skins:
            raise ValueError("Add at least one skin before starting the watcher.")
        if len(skins) > MAX_WATCHED_SKINS:
            raise ValueError(
                f"You can watch at most {MAX_WATCHED_SKINS} entries at once."
            )

        config = build_watcher_config(settings, skins)
        config["notify_initial"] = args.notify_initial

        if args.test_notify:
            notify(
                config,
                "Skins Watcher Test",
                "If you see this, notifications are configured correctly.",
            )
            print("Discord test message sent.")
            return 0

        state_path = Path(config.get("state_file", "state.json"))
        state = load_state(state_path)

        with sync_playwright() as playwright:
            browser = None
            page = None
            try:
                while True:
                    try:
                        if page is None or page.is_closed():
                            browser, page = open_pirateswap(playwright, config)
                        new_count = check_once(config, state, page)
                        save_state(state_path, state)
                        print(
                            f"[{timestamp()}] check complete, "
                            f"notifications sent: {new_count}"
                        )
                    except Exception as exc:
                        print(f"[{timestamp()}] check failed: {exc}", file=sys.stderr)
                        if browser is not None:
                            try:
                                browser.close()
                            except Exception:
                                pass
                        browser = None
                        page = None
                        if not args.once:
                            print(
                                f"[{timestamp()}] browser connection will be "
                                "restored on the next check"
                            )

                    if args.once:
                        break

                    interval = int(config.get("check_interval_seconds", 300))
                    print(f"[{timestamp()}] next availability check in {interval} second(s)")
                    time.sleep(interval)
            finally:
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass

    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
