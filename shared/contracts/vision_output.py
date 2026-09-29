from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ImageType = Literal["sticker", "screenshot", "photo", "illustration", "other"]


class StickerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_type: ImageType
    suitable: bool
    reason: str


# 表示图片描述数据
class ImageDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    image_type: ImageType
    tags: list[str]
    match_quality: float
    emotion: str
    sticker_description: str
