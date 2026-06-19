from __future__ import annotations

import ctypes
import sys
from tkinter import PhotoImage, TclError, Tk

from app.paths import APP_ICON_ICO, APP_ICON_PNG


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SkinWatcher")
    except OSError:
        pass


def apply_app_icon(root: Tk) -> PhotoImage:
    icon = load_app_icon()
    root.iconphoto(True, icon)
    if sys.platform == "win32" and APP_ICON_ICO.exists():
        try:
            root.iconbitmap(str(APP_ICON_ICO))
        except TclError:
            pass
    return icon


def load_app_icon() -> PhotoImage:
    if APP_ICON_PNG.exists():
        try:
            return PhotoImage(file=str(APP_ICON_PNG))
        except TclError:
            pass
    return create_fallback_icon()


def create_fallback_icon() -> PhotoImage:
    icon = PhotoImage(width=32, height=32)
    transparent = "#f0f0f0"
    icon.put(transparent, to=(0, 0, 32, 32))
    icon.transparency_set(0, 0, True)

    pixels = {
        "#111827": [
            (9, 5, 23, 7),
            (7, 8, 25, 11),
            (6, 12, 26, 15),
            (7, 16, 25, 19),
            (9, 20, 23, 22),
            (12, 23, 20, 24),
        ],
        "#38bdf8": [
            (10, 6, 22, 8),
            (8, 9, 24, 12),
            (8, 13, 24, 16),
            (10, 17, 22, 20),
            (13, 21, 19, 23),
        ],
        "#f59e0b": [
            (17, 7, 22, 9),
            (16, 10, 25, 12),
            (15, 13, 26, 15),
            (14, 16, 24, 18),
            (13, 19, 21, 21),
        ],
        "#ffffff": [
            (11, 9, 15, 11),
            (10, 12, 14, 14),
            (9, 15, 13, 17),
            (10, 18, 14, 20),
        ],
    }
    for color, rectangles in pixels.items():
        for x1, y1, x2, y2 in rectangles:
            icon.put(color, to=(x1, y1, x2, y2))
    return icon
