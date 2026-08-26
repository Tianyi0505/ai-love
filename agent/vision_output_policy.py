from __future__ import annotations

from agent.image_description import ImageDescription
from shared.global_settings import VisionOutputLimits


class VisionOutputPolicy:
    def __init__(self, limits: VisionOutputLimits) -> None:
        self._limits = limits

    def validate(self, result: ImageDescription) -> ImageDescription:
        limits = self._limits
        if not limits.description_min_chars <= len(result.description) <= limits.description_max_chars:
            raise ValueError("图片描述长度不符合配置")
        if len(result.sticker_description) > limits.sticker_description_max_chars:
            raise ValueError("表情描述长度不符合配置")
        if len(result.emotion) > limits.emotion_max_chars:
            raise ValueError("图片情绪长度不符合配置")
        if len(result.tags) > limits.tags_max_count:
            raise ValueError("图片标签数量不符合配置")
        if not limits.match_quality_min <= result.match_quality <= limits.match_quality_max:
            raise ValueError("表情匹配质量不符合配置")
        return result
