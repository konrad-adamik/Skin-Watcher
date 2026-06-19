from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as settings_file:
        return json.load(settings_file)


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file, indent=2)
        settings_file.write("\n")
