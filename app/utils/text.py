from __future__ import annotations

import re

from app.models import SkinRule


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_message_text(value: str) -> str:
    return "\n".join(
        line for line in (normalize_text(part) for part in value.splitlines()) if line
    )


def normalize_match_text(value: str) -> str:
    normalized = normalize_text(value).lower()
    for marker in (
        "\u2605",
        "\u2122",
        "\ufffd",
        "â…",
        "â„¢",
        "Ă˘Ââ€¦",
        "Ă˘â€žË",
        "Ă˘â€žÂ˘",
        "Ä‚ËĂ˘â‚¬ĹľĂ‚Ë",
    ):
        normalized = normalized.replace(marker, "")
    normalized = re.sub(r"\bst\s+", "stattrak ", normalized)
    normalized = re.sub(r"\bstat\s+trak\b", "stattrak", normalized)
    normalized = re.sub(r"\bstattrak\s*", "stattrak ", normalized)
    return normalize_text(normalized)


def clean_display_text(value: str) -> str:
    cleaned = value
    replacements = {
        "\u2122": "",
        "\ufffd": "",
        "â„¢": "",
        "Ă˘â€žË": "",
        "Ă˘â€žÂ˘": "",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"\bst[\ufffd?]*(?=\s|$)", "StatTrak", cleaned, flags=re.I)
    cleaned = re.sub(r"\bstat\s*trak[\ufffd?]*(?=\s|$)", "StatTrak", cleaned, flags=re.I)
    cleaned = re.sub(r"\bstattrak[\ufffd?]*(?=\s|$)", "StatTrak", cleaned, flags=re.I)
    cleaned = re.sub(r"\bstatrak[\ufffd?]*(?=\s|$)", "StatTrak", cleaned, flags=re.I)
    return normalize_text(cleaned)


def full_skin_name(rule: SkinRule) -> str:
    if rule.name:
        return rule.name
    if rule.weapon and rule.skin:
        return f"{rule.weapon} | {rule.skin}"
    raise ValueError("Skin rule must contain either name or weapon + skin.")


def skin_name_part(rule: SkinRule) -> str:
    if rule.skin:
        return rule.skin.strip()
    return full_skin_name(rule).split("|")[-1].strip()
