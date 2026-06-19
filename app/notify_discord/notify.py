from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import requests


def notify(
    config: dict[str, Any],
    title: str,
    message: str,
    image_url: str | None = None,
) -> None:
    webhook_url = config.get("notify", {}).get("webhook_url")

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
            "username": "Skins availability watcher",
            "embeds": [embed],
        },
        timeout=20,
    )
    response.raise_for_status()
