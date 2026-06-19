from __future__ import annotations

from tkinter import font as tkfont
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Menu,
    StringVar,
    Text,
    Tk,
)
from tkinter.ttk import Combobox, LabelFrame, Separator, Style, Treeview

from app.cs2_resources.catalog import ITEM_TYPES
from app.gui.app_icon import apply_app_icon, set_windows_app_id
from app.gui.skin_editor import SkinEditorMixin
from app.gui.watcher_controls import WatcherControlsMixin
from app.models import MAX_WATCHED_SKINS
from app.paths import SETTINGS_PATH
from app.runtime import runtime_config
from app.settings import load_settings


class SkinWatcherGui(SkinEditorMixin, WatcherControlsMixin):
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Skin Watcher")
        self.root.geometry("1120x720")
        self.root.minsize(980, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        self.icon = apply_app_icon(self.root)
        self.process = None
        self.stop_requested = False
        self.closing = False
        self.watching = False
        self.editing_index: int | None = None

        self.settings = load_settings(SETTINGS_PATH)
        self.config = runtime_config()
        if self.settings.get("remember_skins", True):
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
        self.float_min_var = StringVar()
        self.float_max_var = StringVar()
        self.notify_initial_var = BooleanVar(value=False)
        self.remember_skins_var = BooleanVar(
            value=bool(self.settings.get("remember_skins", True))
        )

        self.build_menu()
        self.build_ui()
        self.refresh_skin_list()

    def build_menu(self) -> None:
        menu_bar = Menu(self.root)
        options_menu = Menu(menu_bar, tearoff=False)
        options_menu.add_checkbutton(
            label="Remember skins",
            variable=self.remember_skins_var,
            onvalue=True,
            offvalue=False,
        )
        options_menu.add_separator()
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

        self.skins_outer = LabelFrame(root, text=f"Skins To Watch (0/{MAX_WATCHED_SKINS})")
        self.skins_outer.pack(fill="x", padx=12, pady=8)
        skins_frame = Frame(self.skins_outer, padx=12, pady=10)
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
        self.edit_button = Button(
            skins_frame,
            text="Edit Selected",
            command=self.toggle_edit_selected_skin,
            state="disabled",
        )
        self.edit_button.grid(row=1, column=5, padx=(0, 8))
        self.remove_button = Button(
            skins_frame,
            text="Remove Selected",
            command=self.remove_selected_skin,
            state="disabled",
        )
        self.remove_button.grid(row=1, column=6)

        self.float_filter_frame = Frame(skins_frame)
        self.float_filter_frame.grid(
            row=2,
            column=0,
            columnspan=7,
            sticky="w",
            pady=(8, 0),
        )
        Label(
            self.float_filter_frame,
            text="Float range (optional, max 3 decimals)",
        ).pack(side="left")
        Label(self.float_filter_frame, text="min").pack(side="left", padx=(10, 3))
        self.float_min_entry = Entry(
            self.float_filter_frame,
            textvariable=self.float_min_var,
            width=9,
        )
        self.float_min_entry.pack(side="left")
        Label(self.float_filter_frame, text="max").pack(side="left", padx=(8, 3))
        self.float_max_entry = Entry(
            self.float_filter_frame,
            textvariable=self.float_max_var,
            width=9,
        )
        self.float_max_entry.pack(side="left")

        skins_frame.columnconfigure(0, weight=1)
        skins_frame.columnconfigure(1, weight=1)
        skins_frame.columnconfigure(2, weight=1)

        self.table_heading_font = tkfont.nametofont("TkDefaultFont").copy()
        self.table_heading_font.configure(weight="bold")
        table_style = Style(root)
        table_style.configure("SkinWatcher.Treeview", rowheight=30)
        table_style.configure(
            "SkinWatcher.Treeview.Heading",
            font=self.table_heading_font,
        )
        self.skin_list = Treeview(
            self.skins_outer,
            columns=("type", "item", "skin", "stattrak", "float"),
            show="headings",
            height=3,
            selectmode="browse",
            style="SkinWatcher.Treeview",
        )
        for column, heading, width in (
            ("type", "Type", 100),
            ("item", "Item", 210),
            ("skin", "Skin", 260),
            ("stattrak", "StatTrak", 110),
            ("float", "Float Range", 150),
        ):
            self.skin_list.heading(column, text=heading, anchor="w")
            self.skin_list.column(column, width=width, minwidth=80, anchor="w")
        self.skin_list.tag_configure("even", background="#f7f8fa")
        self.skin_list.tag_configure("odd", background="#e4e9ef")
        self.skin_list.pack(fill="x", padx=12, pady=(0, 10))
        self.skin_list.bind("<Button-1>", self.toggle_skin_selection)
        self.skin_list.bind("<<TreeviewSelect>>", self.on_skin_selection_changed)

        controls = Frame(root, padx=12, pady=10)
        controls.pack(fill="x")

        self.start_button = Button(controls, text="Start Watching", command=self.start_watching)
        self.start_button.pack(side="left")
        self.stop_button = Button(controls, text="Stop Watching", command=self.stop_watching)

        Label(root, text="Activity").pack(anchor="w", padx=12)
        self.log = Text(root, height=18, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

def main() -> None:
    set_windows_app_id()
    root = Tk()
    SkinWatcherGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
