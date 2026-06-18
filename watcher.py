from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_SETTINGS = Path("settings.json")
PIRATESWAP_URL = "https://pirateswap.com/exchanger"
STATE_FILE = "state.json"


@dataclass(frozen=True)
class SkinRule:
    name: str | None = None
    type: str | None = None
    weapon: str | None = None
    skin: str | None = None
    query: str | None = None
    stattrak: bool = False


@dataclass(frozen=True)
class SkinMatch:
    text: str
    identity_text: str
    image_url: str | None = None


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as settings_file:
        return json.load(settings_file)


def build_config(settings: dict[str, Any], skins: list[dict[str, Any]]) -> dict[str, Any]:
    config = {
        "url": PIRATESWAP_URL,
        "check_interval_seconds": settings.get("check_interval_seconds", 300),
        "headless": True,
        "state_file": STATE_FILE,
        "notify": {
            "type": "discord",
            "webhook_url": settings.get("discord_webhook_url", ""),
        },
        "skins": skins,
    }
    return config


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen": {}}

    with path.open("r", encoding="utf-8") as state_file:
        return json.load(state_file)


def save_state(path: Path, state: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, sort_keys=True)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_message_text(value: str) -> str:
    return "\n".join(
        line for line in (normalize_text(part) for part in value.splitlines()) if line
    )


def normalize_match_text(value: str) -> str:
    return (
        normalize_text(value)
        .replace("★", "")
        .replace("™", "")
        .replace("â„¢", "")
        .replace("ST™", "StatTrak")
        .lower()
    )


def result_id(rule: SkinRule, result_text: str) -> str:
    digest = hashlib.sha256(normalize_text(result_text).lower().encode("utf-8")).hexdigest()
    return f"{full_skin_name(rule).lower()}:stattrak={rule.stattrak}:{digest}"


def stattrak_matches(rule: SkinRule, text: str) -> bool:
    if is_glove(rule):
        return True

    normalized = normalize_match_text(text)
    has_stattrak = "stattrak" in normalized or "stat trak" in normalized

    return has_stattrak if rule.stattrak else not has_stattrak


def watch_signature(config: dict[str, Any]) -> str:
    watched = {
        "url": config.get("url"),
        "skins": config.get("skins", []),
    }
    payload = json.dumps(watched, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def send_ntfy(config: dict[str, Any], title: str, message: str) -> None:
    notify = config.get("notify", {})
    topic = notify.get("topic")
    server = notify.get("server", "https://ntfy.sh").rstrip("/")

    if not topic or topic == "replace-with-your-secret-topic":
        print("Notification skipped: configure ntfy settings first.")
        return

    response = requests.post(
        f"{server}/{topic}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "high",
            "Tags": "mag,video_game",
        },
        timeout=20,
    )
    response.raise_for_status()


def send_discord(
    config: dict[str, Any],
    title: str,
    message: str,
    image_url: str | None = None,
) -> None:
    notify_config = config.get("notify", {})
    webhook_url = notify_config.get("webhook_url")

    if not webhook_url or "replace-with-your-webhook" in webhook_url:
        print("Discord webhook URL is missing. Paste it in the app first.")
        return

    embed: dict[str, Any] = {
        "title": title,
        "description": message[:4096],
        "color": 16753205,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if image_url:
        embed["thumbnail"] = {"url": image_url}

    response = requests.post(
        webhook_url,
        json={
            "username": "PirateSwap Watcher",
            "embeds": [embed],
        },
        timeout=20,
    )
    response.raise_for_status()


def notify(
    config: dict[str, Any],
    title: str,
    message: str,
    image_url: str | None = None,
) -> None:
    notify_type = config.get("notify", {}).get("type", "discord").lower()

    if notify_type == "discord":
        send_discord(config, title, message, image_url)
        return

    if notify_type == "ntfy":
        send_ntfy(config, title, message)
        return

    raise ValueError(f"Unsupported notify.type '{notify_type}'. Use discord or ntfy.")


def find_search_box(page):
    candidates = [
        page.locator("input[data-testid='search-autocomplete-input']").first,
        page.locator("input[placeholder='Search']").first,
        page.locator("input[placeholder='SEARCH']").first,
        page.get_by_placeholder(re.compile("^search$", re.I)),
        page.locator("input[type='search']"),
        page.get_by_role("textbox"),
    ]

    for locator in candidates:
        try:
            count = min(locator.count(), 8)
            for index in range(count):
                item = locator.nth(index)
                if item.is_visible() and item.is_enabled():
                    return item
        except PlaywrightError:
            continue

    raise RuntimeError("Could not find a visible search input on the page.")


def expected_option_text(rule: SkinRule) -> str:
    name = full_skin_name(rule)
    if is_glove(rule):
        return f"★ {name}"
    if is_knife(rule):
        return f"★ StatTrak {name}" if rule.stattrak else f"★ {name}"
    return f"StatTrak {name}" if rule.stattrak else name


def search_query_for(rule: SkinRule) -> str:
    if rule.query:
        return rule.query

    return skin_name_part(rule) or full_skin_name(rule)


def full_skin_name(rule: SkinRule) -> str:
    if rule.name:
        return rule.name
    if rule.weapon and rule.skin:
        return f"{rule.weapon} | {rule.skin}"
    raise ValueError("Skin rule must contain either name or weapon + skin.")


def skin_name_part(rule: SkinRule) -> str:
    if rule.skin:
        return rule.skin.strip()
    return full_skin_name(rule).split("|")[-1].strip()


def is_glove(rule: SkinRule) -> bool:
    return "gloves" in (rule.weapon or full_skin_name(rule).split("|")[0]).lower()


def is_knife(rule: SkinRule) -> bool:
    weapon = (rule.weapon or full_skin_name(rule).split("|")[0]).lower()
    return "knife" in weapon or weapon in {
        "bayonet",
        "butterfly knife",
        "classic knife",
        "falchion knife",
        "flip knife",
        "gut knife",
        "huntsman knife",
        "karambit",
        "kukri knife",
        "m9 bayonet",
        "navaja knife",
        "nomad knife",
        "paracord knife",
        "shadow daggers",
        "skeleton knife",
        "stiletto knife",
        "survival knife",
        "talon knife",
        "ursus knife",
    }


def select_autocomplete_option(page, rule: SkinRule) -> str:
    expected = normalize_match_text(expected_option_text(rule))
    search_term = skin_name_part(rule)
    options = page.locator("li").filter(has_text=re.compile(re.escape(search_term), re.I))

    deadline = time.time() + 10
    while time.time() < deadline:
        count = options.count()
        for index in range(count):
            option = options.nth(index)
            if not option.is_visible():
                continue

            text = normalize_text(option.inner_text())
            if normalize_match_text(text) == expected:
                option.click()
                page.wait_for_timeout(4000)
                return text
        page.wait_for_timeout(250)

    raise RuntimeError(f"Could not find exact autocomplete option: {expected_option_text(rule)}")


def extract_cards(page, selected_label: str) -> list[dict[str, Any]]:
    cards = page.locator("[data-testid='exchanger-card']")
    try:
        cards.first.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        return []

    return cards.evaluate_all(
        """
        (els, selectedLabel) => {
          function compact(text) {
            return (text || "").replace(/\\s+/g, " ").trim();
          }

          return els.map((card, index) => {
            const name = compact(card.querySelector("[data-testid='skin-card-name']")?.innerText);
            const cardText = compact(card.innerText);
            const paragraphs = Array.from(card.querySelectorAll("p"))
              .map((p) => compact(p.innerText))
              .filter(Boolean);
            const price = paragraphs.find((text) => /^\\$/.test(text)) || "";
            const details =
              paragraphs.find((text) => /^(FN|MW|FT|WW|BS)\\b/.test(text)) ||
              cardText.match(/\\b(FN|MW|FT|WW|BS)\\s*-\\s*\\d+(?:\\.\\d+)?\\b/)?.[0] ||
              "";
            const lock = paragraphs.find((text) => /^\\d+D$/.test(text)) || "";
            const image = card.querySelector("img[alt]");
            const imageAlt = image?.getAttribute("alt") || "";
            const imageSrc = image?.currentSrc || image?.getAttribute("src") || "";
            const imageUrl = imageSrc ? new URL(imageSrc, window.location.origin).href : "";

            if (!name && !price && !details) return "";
            return {
              text: `${selectedLabel}\\n### Float: ${details || "no float"}`,
              identity_text: `${selectedLabel} | card=${index + 1} | lock=${lock || "no lock"} | float=${details || "no float"} | price=${price || "no price"} | image=${imageAlt}`,
              image_url: imageUrl,
            };
          }).filter(Boolean);
        }
        """,
        selected_label,
    )


def search_for_skin(page, rule: SkinRule) -> list[SkinMatch]:
    query = search_query_for(rule)
    search_box = find_search_box(page)
    search_box.click()
    search_box.press("Control+A")
    search_box.press("Backspace")
    search_box.type(query, delay=35)
    page.wait_for_timeout(1000)

    selected_label = select_autocomplete_option(page, rule)
    cards = extract_cards(page, selected_label)
    return [
        SkinMatch(
            text=normalize_message_text(card["text"]),
            identity_text=normalize_text(card["identity_text"]),
            image_url=card.get("image_url"),
        )
        for card in cards
        if stattrak_matches(rule, selected_label)
    ]


def check_once(config: dict[str, Any], state: dict[str, Any]) -> int:
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

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.get("headless", True))
        page = browser.new_page()

        try:
            page.goto(config["url"], wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass

            for rule in rules:
                results = search_for_skin(page, rule)
                rule_name = full_skin_name(rule)
                print(f"[{timestamp()}] {rule_name}: found {len(results)} matching block(s)")

                for result in results:
                    item_id = result_id(rule, result.identity_text)
                    if item_id in seen:
                        continue

                    seen[item_id] = {
                        "skin": rule.name,
                        "full_skin_name": rule_name,
                        "first_seen": timestamp(),
                        "text": result.text,
                        "identity_text": result.identity_text,
                        "image_url": result.image_url,
                    }

                    if not baseline_done:
                        continue

                    new_count += 1

                    result_lines = result.text.splitlines()
                    skin_title = result_lines[0] if result_lines else rule_name
                    message = "\n".join(result_lines[1:])
                    print(message)
                    notify(config, skin_title, message, result.image_url)
        finally:
            browser.close()

    if not baseline_done:
        state["baseline_done"] = True
        print(f"[{timestamp()}] baseline saved; existing matches will not be notified")

    state["last_checked"] = timestamp()
    return new_count


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch PirateSwap for configured CS2 skins.")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    parser.add_argument("--test-notify", action="store_true", help="Send a test notification and exit.")
    parser.add_argument(
        "--skins-json",
        help="Session-only skins JSON passed by the UI. These skins are not persisted.",
    )
    args = parser.parse_args()

    try:
        settings = load_settings(args.settings)
        skins = json.loads(args.skins_json) if args.skins_json else []
        if not args.test_notify and not skins:
            raise ValueError("Add at least one skin before starting the watcher.")

        config = build_config(settings, skins)

        if args.test_notify:
            notify(
                config,
                "PirateSwap watcher test",
                "If you see this, notifications are configured correctly.",
            )
            print("Discord test message sent.")
            return 0

        state_path = Path(config.get("state_file", "state.json"))
        state = load_state(state_path)

        while True:
            try:
                new_count = check_once(config, state)
                save_state(state_path, state)
                print(f"[{timestamp()}] check complete, new matches: {new_count}")
            except Exception as exc:
                print(f"[{timestamp()}] check failed: {exc}", file=sys.stderr)

            if args.once:
                break

            interval = int(config.get("check_interval_seconds", 300))
            time.sleep(interval)

    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
