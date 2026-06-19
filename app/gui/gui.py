from __future__ import annotations

import json
import ctypes
import subprocess
import sys
import threading
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Listbox,
    Menu,
    PhotoImage,
    StringVar,
    Text,
    Tk,
    messagebox,
)
from tkinter.ttk import Combobox, LabelFrame, Separator

from app.cs2_resources.catalog import CS2_GLOVES, CS2_KNIVES, CS2_WEAPONS, ITEM_TYPES
from app.paths import PIRATESWAP_URL, PYTHON, SETTINGS_PATH, STATE_FILE
from app.runtime import runtime_config
from app.settings import load_settings, save_settings


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "PirateSwap.SkinWatcher"
        )
    except OSError:
        pass


class PirateSwapGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("PirateSwap Skin Watcher")
        self.root.geometry("1120x720")
        self.root.minsize(980, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        self.icon = self.create_app_icon()
        self.root.iconphoto(True, self.icon)
        self.process: subprocess.Popen | None = None
        self.stop_requested = False
        self.closing = False

        self.settings = load_settings(SETTINGS_PATH)
        self.config = runtime_config()
        if self.settings.get("remember_skins"):
            self.config["skins"] = self.settings.get("skins", [])
        self.reset_state_file()

        self.webhook_var = StringVar(
            value=self.settings.get("discord_webhook_url", "")
        )
        self.interval_var = StringVar(
            value=str(
                self.settings.get("check_interval_seconds", self.config["check_interval_seconds"])
            )
        )
        self.item_type_var = StringVar()
        self.weapon_var = StringVar()
        self.skin_var = StringVar()
        self.stattrak_var = BooleanVar(value=False)
        self.notify_initial_var = BooleanVar(value=False)
        self.remember_skins_var = BooleanVar(value=bool(self.settings.get("remember_skins", False)))

        self.build_menu()
        self.build_ui()
        self.refresh_skin_list()

    def create_app_icon(self) -> PhotoImage:
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

    def reset_state_file(self) -> None:
        with open(STATE_FILE, "w", encoding="utf-8") as state_file:
            json.dump({"seen": {}, "baseline_done": False}, state_file, indent=2)
            state_file.write("\n")

    def build_menu(self) -> None:
        menu_bar = Menu(self.root)
        options_menu = Menu(menu_bar, tearoff=False)
        options_menu.add_checkbutton(
            label="Notify about initial findings",
            variable=self.notify_initial_var,
            onvalue=True,
            offvalue=False,
        )
        menu_bar.add_cascade(label="Options", menu=options_menu)
        menu_bar.add_command(label="Exit", command=self.exit_app)
        self.root.config(menu=menu_bar)

    def build_ui(self) -> None:
        root = self.root

        config_outer = LabelFrame(root, text="Discord Notifications")
        config_outer.pack(fill="x", padx=12, pady=10)
        config_frame = Frame(config_outer, padx=12, pady=10)
        config_frame.pack(fill="x")

        Label(config_frame, text="Discord webhook URL").grid(row=0, column=0, sticky="w")
        Entry(config_frame, textvariable=self.webhook_var).grid(row=0, column=1, sticky="ew", padx=8)
        Button(config_frame, text="Test Discord", command=lambda: self.run_command(["--test-notify"])).grid(
            row=0, column=2
        )

        Label(config_frame, text="Check every").grid(row=1, column=0, sticky="w", pady=(8, 0))
        Entry(config_frame, textvariable=self.interval_var, width=12).grid(
            row=1, column=1, sticky="w", padx=8, pady=(8, 0)
        )
        Label(config_frame, text="seconds").grid(row=1, column=1, sticky="w", padx=(90, 8), pady=(8, 0))
        config_frame.columnconfigure(1, weight=1)

        Separator(root).pack(fill="x", padx=12, pady=4)

        skins_outer = LabelFrame(root, text="Skins To Watch")
        skins_outer.pack(fill="x", padx=12, pady=8)
        skins_frame = Frame(skins_outer, padx=12, pady=10)
        skins_frame.pack(fill="x")

        Label(skins_frame, text="Type").grid(row=0, column=0, sticky="w")
        self.item_type_combo = Combobox(
            skins_frame,
            textvariable=self.item_type_var,
            values=ITEM_TYPES,
            state="readonly",
            width=14,
        )
        self.item_type_combo.grid(row=1, column=0, sticky="ew")
        self.item_type_combo.bind("<<ComboboxSelected>>", self.on_item_type_selected)

        Label(skins_frame, text="Item").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.weapon_combo = Combobox(
            skins_frame,
            textvariable=self.weapon_var,
            values=[],
            state="readonly",
            width=24,
        )
        self.weapon_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        self.weapon_combo.bind("<<ComboboxSelected>>", self.on_weapon_selected)

        Label(skins_frame, text="Skin").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.skin_entry = Entry(skins_frame, textvariable=self.skin_var, width=24)
        self.skin_entry.grid(
            row=1, column=2, sticky="ew", padx=(8, 0)
        )

        self.stattrak_check = Checkbutton(skins_frame, text="StatTrak", variable=self.stattrak_var)
        self.stattrak_check.grid(row=1, column=3, padx=8)
        self.add_button = Button(skins_frame, text="Add Skin", command=self.add_skin)
        self.add_button.grid(row=1, column=4, padx=(0, 8))
        self.remove_button = Button(skins_frame, text="Remove Selected", command=self.remove_selected_skin)
        self.remove_button.grid(row=1, column=5)

        skins_frame.columnconfigure(0, weight=1)
        skins_frame.columnconfigure(1, weight=1)
        skins_frame.columnconfigure(2, weight=1)

        remember_frame = Frame(root, padx=12)
        remember_frame.pack(fill="x")
        self.remember_skins_check = Checkbutton(
            remember_frame,
            text="Remember skins",
            variable=self.remember_skins_var,
        )
        self.remember_skins_check.pack(anchor="w")

        self.skin_list = Listbox(root, height=8)
        self.skin_list.pack(fill="x", padx=12)

        controls = Frame(root, padx=12, pady=10)
        controls.pack(fill="x")

        self.start_button = Button(controls, text="Start Watching", command=self.start_watching)
        self.start_button.pack(side="left")
        self.stop_button = Button(controls, text="Stop Watching", command=self.stop_watching)

        Label(root, text="Activity").pack(anchor="w", padx=12)
        self.log = Text(root, height=18, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def refresh_skin_list(self) -> None:
        self.skin_list.delete(0, "end")
        for skin in self.config.get("skins", []):
            stattrak = "StatTrak" if skin.get("stattrak") else "Regular"
            name = skin.get("name") or f"{skin.get('weapon', '')} | {skin.get('skin', '')}"
            item_type = skin.get("type", self.item_type_for_weapon(skin.get("weapon", "")))
            self.skin_list.insert(
                "end",
                f"{item_type}: {name} | {stattrak}",
            )

    def add_skin(self) -> None:
        item_type = self.item_type_var.get().strip()
        weapon = self.weapon_var.get().strip()
        skin = self.skin_var.get().strip()
        if not item_type or not weapon or not skin:
            messagebox.showerror("Missing Skin", "Select type and item, then enter skin name.")
            return

        self.config.setdefault("skins", []).append(
            {
                "type": item_type,
                "weapon": weapon,
                "skin": skin,
                "stattrak": bool(self.stattrak_var.get()),
            }
        )
        self.item_type_var.set("")
        self.weapon_var.set("")
        self.weapon_combo.configure(values=[])
        self.skin_var.set("")
        self.stattrak_var.set(False)
        self.stattrak_check.configure(state="normal")
        self.refresh_skin_list()

    def on_item_type_selected(self, _event=None) -> None:
        item_type = self.item_type_var.get()
        values = {
            "Weapon": CS2_WEAPONS,
            "Knife": CS2_KNIVES,
            "Gloves": CS2_GLOVES,
        }.get(item_type, [])
        self.weapon_combo.configure(values=values)
        self.weapon_var.set("")
        if item_type == "Gloves":
            self.stattrak_var.set(False)
            self.stattrak_check.configure(state="disabled")
        elif item_type == "Weapon":
            self.stattrak_check.configure(state="normal")
        else:
            self.stattrak_check.configure(state="normal")

    def on_weapon_selected(self, _event=None) -> None:
        if "gloves" in self.weapon_var.get().lower():
            self.stattrak_var.set(False)
            self.stattrak_check.configure(state="disabled")

    def item_type_for_weapon(self, weapon: str) -> str:
        if weapon in CS2_GLOVES:
            return "Gloves"
        if weapon in CS2_KNIVES:
            return "Knife"
        return "Weapon"

    def remove_selected_skin(self) -> None:
        selection = self.skin_list.curselection()
        if not selection:
            return
        del self.config["skins"][selection[0]]
        self.refresh_skin_list()

    def current_config(self) -> dict:
        try:
            interval = int(self.interval_var.get().strip())
        except ValueError as exc:
            raise ValueError("Interval must be a whole number.") from exc

        if interval <= 0:
            raise ValueError("Interval must be above 0.")

        self.config["check_interval_seconds"] = interval
        self.config["headless"] = True
        self.config.setdefault("notify", {})
        self.config["notify"]["webhook_url"] = self.webhook_var.get().strip()
        self.config["url"] = PIRATESWAP_URL
        self.config["headless"] = True
        self.config["state_file"] = STATE_FILE
        return self.config

    def save_settings(self, require_skins: bool = False, log: bool = True) -> bool:
        try:
            config = self.current_config()
        except ValueError as exc:
            messagebox.showerror("Invalid Config", str(exc))
            return False

        if require_skins and not config.get("skins"):
            messagebox.showerror("No Skins", "Add at least one skin before starting the watcher.")
            return False

        save_settings(
            SETTINGS_PATH,
            {
                "discord_webhook_url": config["notify"]["webhook_url"],
                "check_interval_seconds": config["check_interval_seconds"],
                "remember_skins": bool(self.remember_skins_var.get()),
                "skins": config.get("skins", []) if self.remember_skins_var.get() else [],
            },
        )

        if log:
            self.append_log("Settings saved.")
        return True

    def run_command(self, args: list[str]) -> None:
        if "--test-notify" in args and not self.webhook_var.get().strip():
            messagebox.showerror("Missing Webhook", "Paste your Discord webhook URL first.")
            return

        if not self.save_settings(require_skins="--test-notify" not in args):
            return
        if self.process and self.process.poll() is None:
            messagebox.showwarning("Watcher Running", "Stop the running watcher first.")
            return

        if "--test-notify" in args:
            self.append_log("")
            self.append_log("==== Test Discord ====")

        command = [
            str(PYTHON if PYTHON.exists() else sys.executable),
            "-u",
            "-m",
            "app.watcher.watcher",
            *args,
        ]
        if "--test-notify" not in args:
            command.extend(["--skins-json", json.dumps(self.config.get("skins", []))])
        threading.Thread(target=self.capture_process, args=(command, False), daemon=True).start()

    def start_watching(self) -> None:
        if not self.save_settings(require_skins=True):
            return
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Already Running", "Watcher is already running.")
            return

        self.reset_state_file()
        command = [
            str(PYTHON if PYTHON.exists() else sys.executable),
            "-u",
            "-m",
            "app.watcher.watcher",
            "--skins-json",
            json.dumps(self.config.get("skins", [])),
        ]
        if self.notify_initial_var.get():
            command.append("--notify-initial")
        self.stop_requested = False
        self.set_watching_state(True)
        self.append_log("")
        self.append_log("==== Start Watching ====")
        threading.Thread(target=self.capture_process, args=(command, True), daemon=True).start()

    def stop_watching(self) -> None:
        if self.process and self.process.poll() is None:
            self.stop_requested = True
            self.stop_button.configure(state="disabled")
            self.process.terminate()
            self.append_log("")
            self.append_log("==== Stop Watching ====")
            self.append_log("Stopping watcher...")
        else:
            self.append_log("Watcher is not running.")

    def exit_app(self) -> None:
        if not self.save_settings(require_skins=False, log=False):
            return
        self.closing = True
        if self.process and self.process.poll() is None:
            self.stop_requested = True
            self.process.terminate()
        self.root.destroy()

    def capture_process(self, command: list[str], keep_process: bool) -> None:
        if "--test-notify" in command:
            self.append_log("Sending a test message to Discord...")
        else:
            self.append_log("Watcher started." if keep_process else "Running watcher command...")
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert self.process.stdout is not None
        for line in self.process.stdout:
            if self.stop_requested and self.is_expected_stop_noise(line):
                continue
            self.append_log(line.rstrip())

        code = self.process.wait()
        if self.stop_requested:
            self.append_log("Watcher stopped.")
            code = 0
        elif code == 0:
            self.append_log("Done.")
        else:
            self.append_log(f"Something went wrong. Exit code: {code}")
        if keep_process:
            self.set_watching_state(False)
        self.process = None
        self.stop_requested = False

    def is_expected_stop_noise(self, line: str) -> bool:
        noisy_parts = (
            "node:events",
            "throw er;",
            "Unhandled 'error' event",
            "Error: EPIPE",
            "PipeTransport.send",
            "playwright",
            "coreBundle.js",
            "DispatcherConnection",
            "BrowserTypeDispatcher",
            "PlaywrightDispatcher",
            "Emitted 'error' event",
            "processTicksAndRejections",
            "errno:",
            "syscall:",
            "code: 'EPIPE'",
            "Node.js v",
            "Socket._write",
            "writeOrBuffer",
            "Writable.write",
            "at new Dispatcher",
        )
        return any(part in line for part in noisy_parts)

    def set_watching_state(self, watching: bool) -> None:
        self.root.after(0, self._set_watching_state, watching)

    def _set_watching_state(self, watching: bool) -> None:
        if watching:
            self.start_button.pack_forget()
            self.stop_button.configure(state="normal")
            self.stop_button.pack(side="left")
            state = "disabled"
        else:
            self.stop_button.pack_forget()
            self.stop_button.configure(state="normal")
            self.start_button.pack(side="left")
            state = "normal"

        self.item_type_combo.configure(state="disabled" if watching else "readonly")
        self.weapon_combo.configure(state="disabled" if watching else "readonly")
        self.skin_entry.configure(state=state)
        self.add_button.configure(state=state)
        self.remove_button.configure(state=state)
        self.remember_skins_check.configure(state=state)
        if watching or self.item_type_var.get() == "Gloves":
            self.stattrak_check.configure(state="disabled")
        else:
            self.stattrak_check.configure(state="normal")

    def append_log(self, text: str) -> None:
        if self.closing:
            return
        self.root.after(0, self._append_log, text)

    def _append_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")


def main() -> None:
    set_windows_app_id()
    root = Tk()
    PirateSwapGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
