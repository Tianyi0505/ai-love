from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# 表示图片描述数据
class ImageDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    tags: list[str]
    match_quality: float
    emotion: str
    sticker_description: str
