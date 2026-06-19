from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ROOT = (
    Path(getattr(sys, "_MEIPASS"))
    if getattr(sys, "frozen", False)
    else PROJECT_ROOT
)
APP_HOME = Path(
    os.environ.get(
        "SKINWATCHER_HOME",
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path.cwd(),
    )
)
ASSETS_DIR = BUNDLE_ROOT / "assets"
APP_ICON_ICO = ASSETS_DIR / "skinwatcher.ico"
APP_ICON_PNG = ASSETS_DIR / "skinwatcher.png"
SETTINGS_PATH = APP_HOME / "settings.json"
PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PIRATESWAP_URL = "https://pirateswap.com/exchanger"
STATE_FILE = APP_HOME / "state.json"
