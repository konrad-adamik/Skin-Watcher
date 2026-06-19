from __future__ import annotations

from app.cs2_resources.catalog import CS2_GLOVES
from app.models import SkinRule
from app.utils.text import full_skin_name, normalize_match_text


KNIFE_NAMES = {
    "bayonet",
    "butterfly knife",
    "classic knife",
    "falchion knife",
    "flip knife",
    "gut knife",
    "huntsman knife",
    "karambit",
    "kukri knife",
    "m9 bayonet",
    "navaja knife",
    "nomad knife",
    "paracord knife",
    "shadow daggers",
    "skeleton knife",
    "stiletto knife",
    "survival knife",
    "talon knife",
    "ursus knife",
}


def is_glove(rule: SkinRule) -> bool:
    return "gloves" in (rule.weapon or full_skin_name(rule).split("|")[0]).lower()


def is_knife(rule: SkinRule) -> bool:
    weapon = (rule.weapon or full_skin_name(rule).split("|")[0]).lower()
    return "knife" in weapon or weapon in KNIFE_NAMES


def item_type_for_weapon(weapon: str) -> str:
    if weapon in CS2_GLOVES:
        return "Gloves"
    if "knife" in weapon.lower() or weapon.lower() in KNIFE_NAMES:
        return "Knife"
    return "Weapon"


def stattrak_matches(rule: SkinRule, text: str) -> bool:
    if is_glove(rule):
        return True

    normalized = normalize_match_text(text)
    has_stattrak = "stattrak" in normalized or "stat trak" in normalized

    return has_stattrak if rule.stattrak else not has_stattrak
