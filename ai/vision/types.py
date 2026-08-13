from __future__ import annotations

from dataclasses import dataclass


# 表示图片描述数据
@dataclass
class ImageDescription:
    description: str
    tags: list[str]
    match_quality: float
    emotion: str = ""
    sticker_description: str = ""
