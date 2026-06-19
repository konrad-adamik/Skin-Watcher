from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.models import MAX_WATCHED_SKINS
from app.notify_discord.notify import notify
from app.paths import SETTINGS_PATH
from app.runtime import build_watcher_config
from app.settings import load_settings
from app.state import load_state, save_state
from app.utils.time_utils import timestamp
from app.watcher.browser import open_pirateswap
from app.watcher.checker import check_once


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


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
