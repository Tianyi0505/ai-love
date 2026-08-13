from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImageDescription:
    description: str
    tags: list[str]
    match_quality: float
    emotion: str = ""
    sticker_description: str = ""
