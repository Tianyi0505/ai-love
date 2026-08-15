
from __future__ import annotations

import logging

from ai.vision.provider import VisionProvider
from ai.vision.types import ImageDescription

logger = logging.getLogger("ailove.vision.routing")


# 按配置顺序提供视觉理解与故障切换
class VisionRouter(VisionProvider):

    # 初始化当前实例
    def __init__(self, providers: list[VisionProvider], fallbacks: dict) -> None:
        super().__init__(fetch_timeout_sec=0.0, fetch_headers={})
        self._providers = providers
        self._fallbacks = fallbacks

    # 描述图片内容
    async def describe(self, image_url: str) -> ImageDescription:
        for index, provider in enumerate(self._providers):
            try:
                result = await provider.describe(image_url)
                if result.description not in {
                    str(self._fallbacks.get("unreadable", "")),
                    str(self._fallbacks.get("unrecognized", "")),
                }:
                    return result
                logger.warning("[vision] 供应商 %s 返回兜底描述，尝试下一个", index)
            except Exception:
                logger.warning("[vision] 供应商 %s 失败，尝试下一个", index, exc_info=True)
        return ImageDescription(
            description=str(self._fallbacks.get("unrecognized", "")),
            tags=[],
            match_quality=float(self._fallbacks.get("match_quality", 0.0)),
        )

    # 执行图像理解请求
    async def _do_describe(self, image_url: str) -> ImageDescription:
        return ImageDescription(
            description=str(self._fallbacks.get("unrecognized", "")),
            tags=[],
            match_quality=float(self._fallbacks.get("match_quality", 0.0)),
        )
