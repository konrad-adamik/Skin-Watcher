from __future__ import annotations

from dataclasses import dataclass


MAX_WATCHED_SKINS = 3


@dataclass(frozen=True)
class SkinRule:
    name: str | None = None
    type: str | None = None
    weapon: str | None = None
    skin: str | None = None
    query: str | None = None
    stattrak: bool = False
    float_min: float | None = None
    float_max: float | None = None


@dataclass(frozen=True)
class SkinMatch:
    text: str
    identity_text: str
    image_url: str | None = None
