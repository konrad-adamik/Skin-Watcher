from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models import SkinRule
from app.notify_discord.notify import notify
from app.sites.pirateswap import search_for_skin
from app.utils.text import full_skin_name, normalize_text
from app.utils.time_utils import timestamp


def result_id(rule: SkinRule, result_text: str) -> str:
    digest = hashlib.sha256(
        normalize_text(result_text).lower().encode("utf-8")
    ).hexdigest()
    return f"{full_skin_name(rule).lower()}:stattrak={rule.stattrak}:{digest}"


def watch_signature(config: dict[str, Any]) -> str:
    watched = {
        "url": config.get("url"),
        "skins": config.get("skins", []),
    }
    payload = json.dumps(watched, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
