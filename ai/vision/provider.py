from __future__ import annotations

from abc import ABC, abstractmethod

from ai.vision.types import ImageDescription


# 定义图像理解服务接口
class VisionProvider(ABC):
    # 描述图片内容
    async def describe(self, image_url: str) -> ImageDescription:
        fetched = await self._fetch(image_url)
        description = await self._do_describe(fetched)
        return await self._finalize(description)

    # 执行图像理解请求
    @abstractmethod
    async def _do_describe(self, image_url: str) -> ImageDescription:
        pass

    # 查询多条数据
    async def _fetch(self, image_url: str) -> str:
        return image_url

    # 完成流式响应处理
    async def _finalize(self, result: ImageDescription) -> ImageDescription:
        result.match_quality = max(0.0, min(1.0, float(result.match_quality)))
        result.description = str(result.description or "").strip()
        result.sticker_description = str(result.sticker_description or "").strip()
        result.tags = [str(tag).strip() for tag in result.tags if str(tag).strip()]
        return result
