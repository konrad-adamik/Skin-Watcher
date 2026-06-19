from __future__ import annotations

from tkinter import messagebox

from app.cs2_resources.catalog import CS2_GLOVES, CS2_KNIVES, CS2_WEAPONS
from app.cs2_resources.rules import item_type_for_weapon
from app.models import MAX_WATCHED_SKINS


class SkinEditorMixin:
    def refresh_skin_list(self) -> None:
        rows = self.skin_list.get_children()
        if rows:
            self.skin_list.delete(*rows)

        skins = self.config.get("skins", [])
        for index, entry in enumerate(skins):
            weapon, skin = self.skin_parts(entry)
            item_type = entry.get("type") or self.item_type_for_weapon(weapon)
            stattrak = "Yes" if entry.get("stattrak") else "No"
            self.skin_list.insert(
                "",
                "end",
                iid=str(index),
                tags=("even" if index % 2 == 0 else "odd",),
                values=(
                    item_type,
                    weapon,
                    skin,
                    stattrak,
                    self.describe_float_filter(entry),
                ),
            )
        self.skins_outer.configure(
            text=f"Skins To Watch ({len(skins)}/{MAX_WATCHED_SKINS})"
        )
        self.update_skin_action_buttons()

    @staticmethod
    def skin_parts(entry: dict) -> tuple[str, str]:
        weapon = entry.get("weapon", "")
        skin = entry.get("skin", "")
        legacy_name = entry.get("name", "")
        if legacy_name and (not weapon or not skin) and "|" in legacy_name:
            legacy_weapon, legacy_skin = legacy_name.split("|", 1)
            weapon = weapon or legacy_weapon.strip()
            skin = skin or legacy_skin.strip()
        return weapon, skin

    @staticmethod
    def describe_float_filter(entry: dict) -> str:
        lower = entry.get("float_min")
        upper = entry.get("float_max")
        if lower is None and upper is None:
            return "Any"
        if lower is None:
            return f"\u2264 {upper:.3f}"
        if upper is None:
            return f"\u2265 {lower:.3f}"
        return f"{lower:.3f} - {upper:.3f}"

    def toggle_skin_selection(self, event):
        row_id = self.skin_list.identify_row(event.y)
        if not row_id:
            return None
        if row_id in self.skin_list.selection():
            self.skin_list.selection_remove(row_id)
            self.update_skin_action_buttons()
            return "break"

        self.root.after_idle(self.update_skin_action_buttons)
        return None

    def on_skin_selection_changed(self, _event=None) -> None:
        self.update_skin_action_buttons()

    def update_skin_action_buttons(self) -> None:
        has_selection = bool(self.skin_list.selection())
        edit_enabled = self.editing_index is not None or has_selection
        self.edit_button.configure(
            state="normal" if edit_enabled and not self.watching else "disabled"
        )
        self.remove_button.configure(
            state="normal" if has_selection and not self.watching else "disabled"
        )

    def add_skin(self) -> None:
        if (
            self.editing_index is None
            and len(self.config.setdefault("skins", [])) >= MAX_WATCHED_SKINS
        ):
            messagebox.showerror(
                "Watch Limit",
                f"You can watch at most {MAX_WATCHED_SKINS} entries at once.",
            )
            return

        item_type = self.item_type_var.get().strip()
        weapon = self.weapon_var.get().strip()
        skin = self.skin_var.get().strip()
        if not item_type or not weapon or not skin:
            messagebox.showerror(
                "Missing Skin",
                "Select type and item, then enter skin name.",
            )
            return

        try:
            float_min, float_max = self.read_float_filter()
        except ValueError as exc:
            messagebox.showerror("Invalid Float Range", str(exc))
            return

        entry = {
            "type": item_type,
            "weapon": weapon,
            "skin": skin,
            "stattrak": bool(self.stattrak_var.get()),
        }
        if float_min is not None:
            entry["float_min"] = float_min
        if float_max is not None:
            entry["float_max"] = float_max
        if self.editing_index is None:
            self.config["skins"].append(entry)
        else:
            self.config["skins"][self.editing_index] = entry

        self.refresh_skin_list()
        self.cancel_edit()

    def reset_skin_form(self) -> None:
        self.item_type_var.set("")
        self.weapon_var.set("")
        self.weapon_combo.configure(values=[])
        self.skin_var.set("")
        self.stattrak_var.set(False)
        self.float_min_var.set("")
        self.float_max_var.set("")
        self.stattrak_check.configure(state="normal")

    def toggle_edit_selected_skin(self) -> None:
        if self.editing_index is None:
            self.edit_selected_skin()
        else:
            self.cancel_edit()

    def edit_selected_skin(self, _event=None) -> None:
        selection = self.skin_list.selection()
        if not selection:
            return

        index = int(selection[0])
        entry = self.config.get("skins", [])[index]
        weapon, skin = self.skin_parts(entry)
        item_type = entry.get("type") or self.item_type_for_weapon(weapon)
        item_values = {
            "Weapon": CS2_WEAPONS,
            "Knife": CS2_KNIVES,
            "Gloves": CS2_GLOVES,
        }.get(item_type, [])

        self.editing_index = index
        self.item_type_var.set(item_type)
        self.weapon_combo.configure(values=item_values)
        self.weapon_var.set(weapon)
        self.skin_var.set(skin)
        self.stattrak_var.set(bool(entry.get("stattrak")))
        self.float_min_var.set(self.format_float_input(entry.get("float_min")))
        self.float_max_var.set(self.format_float_input(entry.get("float_max")))
        self.stattrak_check.configure(
            state="disabled" if item_type == "Gloves" else "normal"
        )
        self.add_button.configure(text="Save Changes")
        self.edit_button.configure(text="Cancel Edit")
        self.update_skin_action_buttons()

    @staticmethod
    def format_float_input(value) -> str:
        if value is None:
            return ""
        return f"{float(value):.3f}".rstrip("0").rstrip(".")

    def cancel_edit(self) -> None:
        self.editing_index = None
        self.add_button.configure(text="Add Skin")
        self.edit_button.configure(text="Edit Selected")
        selection = self.skin_list.selection()
        if selection:
            self.skin_list.selection_remove(*selection)
        self.reset_skin_form()
        self.update_skin_action_buttons()

    def read_float_filter(self) -> tuple[float | None, float | None]:
        values: list[float | None] = []
        for label, raw in (
            ("Minimum float", self.float_min_var.get().strip()),
            ("Maximum float", self.float_max_var.get().strip()),
        ):
            if not raw:
                values.append(None)
                continue
            normalized = raw.replace(",", ".")
            decimal_part = normalized.split(".", 1)[1] if "." in normalized else ""
            if len(decimal_part) > 3:
                raise ValueError(f"{label} can have at most 3 decimal places.")
            try:
                value = float(normalized)
            except ValueError as exc:
                raise ValueError(
                    f"{label} must be a number between 0 and 1."
                ) from exc
            if not 0 <= value <= 1:
                raise ValueError(f"{label} must be between 0 and 1.")
            values.append(value)

        float_min, float_max = values
        if float_min is not None and float_max is not None and float_min > float_max:
            raise ValueError("Minimum float cannot be greater than maximum float.")
        return float_min, float_max

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
        else:
            self.stattrak_check.configure(state="normal")

    def on_weapon_selected(self, _event=None) -> None:
        if "gloves" in self.weapon_var.get().lower():
            self.stattrak_var.set(False)
            self.stattrak_check.configure(state="disabled")

    @staticmethod
    def item_type_for_weapon(weapon: str) -> str:
        return item_type_for_weapon(weapon)

    def remove_selected_skin(self) -> None:
        selection = self.skin_list.selection()
        if not selection:
            return
        del self.config["skins"][int(selection[0])]
        self.refresh_skin_list()
        self.cancel_edit()
