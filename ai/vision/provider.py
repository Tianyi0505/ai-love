from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod

import httpx

from ai.vision.types import ImageDescription


# 定义图像理解服务接口
class VisionProvider(ABC):
    # 初始化当前实例
    def __init__(self, fetch_timeout_sec: float, fetch_headers: dict) -> None:
        self._fetch_timeout_sec = fetch_timeout_sec
        self._fetch_headers = fetch_headers

    # 描述图片内容
    async def describe(self, image_url: str) -> ImageDescription:
        fetched = await self._fetch(image_url)
        description = await self._do_describe(fetched)
        return await self._finalize(description)

    # 执行图像理解请求
    @abstractmethod
    async def _do_describe(self, image_url: str) -> ImageDescription:
        pass

    # 下载图片并转 base64
    async def _fetch(self, image_url: str) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self._fetch_timeout_sec, headers=self._fetch_headers, follow_redirects=True
            ) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
            return base64.b64encode(resp.content).decode()
        except Exception:
            try:
                async with httpx.AsyncClient(
                    timeout=self._fetch_timeout_sec, follow_redirects=True
                ) as client:
                    resp = await client.get(image_url)
                    resp.raise_for_status()
                return base64.b64encode(resp.content).decode()
            except Exception:
                return ""

    # 从模型输出解析图片描述
    def _parse_response(self, text: str, limits: dict, fallbacks: dict) -> ImageDescription:
        try:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start : end + 1])
                description = str(
                    parsed.get("description") or fallbacks["default_description"]
                )[: int(limits["description_chars"])]
                sticker_description = str(parsed.get("sticker_description") or "")[
                    : int(limits["sticker_description_chars"])
                ]
                tags = parsed.get("tags", [])
                if not isinstance(tags, list):
                    tags = []
                match_quality = float(parsed.get("match_quality", fallbacks["match_quality"]))
                return ImageDescription(
                    description=description,
                    sticker_description=sticker_description,
                    tags=tags[: int(limits["tags"])],
                    match_quality=match_quality,
                )
            plain = text.replace("```json", "").replace("```", "").strip()
            return ImageDescription(
                description=plain[: int(limits["plain_description_chars"])]
                or str(fallbacks["unrecognized"]),
                tags=[],
                match_quality=float(fallbacks["match_quality"]),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return ImageDescription(
                description=str(fallbacks["unrecognized"]),
                tags=[],
                match_quality=float(fallbacks["match_quality"]),
            )

    # 完成流式响应处理
    async def _finalize(self, result: ImageDescription) -> ImageDescription:
        result.match_quality = max(0.0, min(1.0, float(result.match_quality)))
        result.description = str(result.description or "").strip()
        result.sticker_description = str(result.sticker_description or "").strip()
        result.tags = [str(tag).strip() for tag in result.tags if str(tag).strip()]
        return result
