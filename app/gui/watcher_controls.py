from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from tkinter import messagebox

from app.models import MAX_WATCHED_SKINS
from app.paths import (
    APP_HOME,
    PIRATESWAP_URL,
    PYTHON,
    SETTINGS_PATH,
    STATE_FILE,
)
from app.settings import save_settings


class WatcherControlsMixin:
    def reset_state_file(self) -> None:
        with STATE_FILE.open("w", encoding="utf-8") as state_file:
            json.dump({"seen": {}, "baseline_done": False}, state_file, indent=2)
            state_file.write("\n")

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
        self.config["state_file"] = STATE_FILE
        return self.config

    def save_settings(self, require_skins: bool = False, log: bool = True) -> bool:
        try:
            config = self.current_config()
        except ValueError as exc:
            messagebox.showerror("Invalid Config", str(exc))
            return False

        if require_skins and not config.get("skins"):
            messagebox.showerror(
                "No Skins",
                "Add at least one skin before starting the watcher.",
            )
            return False
        if require_skins and len(config.get("skins", [])) > MAX_WATCHED_SKINS:
            messagebox.showerror(
                "Watch Limit",
                f"Remove entries until no more than {MAX_WATCHED_SKINS} remain.",
            )
            return False

        save_settings(
            SETTINGS_PATH,
            {
                "discord_webhook_url": config["notify"]["webhook_url"],
                "check_interval_seconds": config["check_interval_seconds"],
                "remember_skins": bool(self.remember_skins_var.get()),
                "skins": (
                    config.get("skins", [])
                    if self.remember_skins_var.get()
                    else []
                ),
            },
        )

        if log:
            self.append_log("Settings saved.")
        return True

    def run_command(self, args: list[str]) -> None:
        if "--test-notify" in args and not self.webhook_var.get().strip():
            messagebox.showerror(
                "Missing Webhook",
                "Paste your Discord webhook URL first.",
            )
            return

        if not self.save_settings(require_skins="--test-notify" not in args):
            return
        if self.process and self.process.poll() is None:
            messagebox.showwarning(
                "Watcher Running",
                "Stop the running watcher first.",
            )
            return

        if "--test-notify" in args:
            self.append_log("")
            self.append_log("==== Test Discord ====")

        command = self.watcher_command(args)
        if "--test-notify" not in args:
            command.extend(
                ["--skins-json", json.dumps(self.config.get("skins", []))]
            )
        threading.Thread(
            target=self.capture_process,
            args=(command, False),
            daemon=True,
        ).start()

    def start_watching(self) -> None:
        if not self.save_settings(require_skins=True):
            return
        if self.process and self.process.poll() is None:
            messagebox.showinfo(
                "Already Running",
                "The watcher is already running.",
            )
            return

        self.reset_state_file()
        command = self.watcher_command(
            [
                "--skins-json",
                json.dumps(self.config.get("skins", [])),
            ]
        )
        if self.notify_initial_var.get():
            command.append("--notify-initial")
        self.stop_requested = False
        self.set_watching_state(True)
        self.append_log("")
        self.append_log("==== Start Watching ====")
        threading.Thread(
            target=self.capture_process,
            args=(command, True),
            daemon=True,
        ).start()

    @staticmethod
    def watcher_command(args: list[str]) -> list[str]:
        if getattr(sys, "frozen", False):
            worker = APP_HOME / "worker" / "SkinWatcherWorker.exe"
            return [str(worker), *args]
        return [
            str(PYTHON if PYTHON.exists() else sys.executable),
            "-u",
            "-m",
            "app.watcher.watcher",
            *args,
        ]

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
            self.append_log(
                "Watcher started."
                if keep_process
                else "Running watcher command..."
            )
        process_options = {}
        if getattr(sys, "frozen", False):
            environment = os.environ.copy()
            environment["SKINWATCHER_HOME"] = str(APP_HOME)
            process_options.update(
                cwd=APP_HOME,
                env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **process_options,
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

    @staticmethod
    def is_expected_stop_noise(line: str) -> bool:
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
        self.watching = watching
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

        self.item_type_combo.configure(
            state="disabled" if watching else "readonly"
        )
        self.weapon_combo.configure(
            state="disabled" if watching else "readonly"
        )
        self.skin_entry.configure(state=state)
        self.float_min_entry.configure(state=state)
        self.float_max_entry.configure(state=state)
        self.add_button.configure(state=state)
        self.update_skin_action_buttons()
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
