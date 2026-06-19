from __future__ import annotations

import os
import sys

from app.paths import APP_HOME


if getattr(sys, "frozen", False):
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH",
        str(APP_HOME / "playwright-browsers"),
    )

from app.watcher.watcher import main


if __name__ == "__main__":
    raise SystemExit(main())
