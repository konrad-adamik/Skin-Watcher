from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkinRule:
    name: str | None = None
    type: str | None = None
    weapon: str | None = None
    skin: str | None = None
    query: str | None = None
    stattrak: bool = False


@dataclass(frozen=True)
class SkinMatch:
    text: str
    identity_text: str
    image_url: str | None = None
