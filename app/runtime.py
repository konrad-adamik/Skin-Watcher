from __future__ import annotations

from typing import Any

from .paths import PIRATESWAP_URL, STATE_FILE


def runtime_config() -> dict[str, Any]:
    return {
        "url": PIRATESWAP_URL,
        "check_interval_seconds": 300,
        "headless": True,
        "state_file": STATE_FILE,
        "notify": {
            "webhook_url": "",
        },
        "skins": [],
    }


def build_watcher_config(settings: dict[str, Any], skins: list[dict[str, Any]]) -> dict[str, Any]:
    config = runtime_config()
    config["check_interval_seconds"] = settings.get("check_interval_seconds", 300)
    config["notify"]["webhook_url"] = settings.get("discord_webhook_url", "")
    config["skins"] = skins
    config["notify_initial"] = False
    return config
