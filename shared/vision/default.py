
from __future__ import annotations

import base64
import json
import os

import httpx

from shared.infrastructure.runtime_config import required_setting
from shared.vision.registry import describer_registry
from shared.vision.types import ImageDesc, ImageDescriber


@describer_registry.register("mcp_default")
class DefaultDescriber(ImageDescriber):

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None, **_) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        self._base_url = required_setting(base_url, "VISION_BASE_URL")
        self._model = required_setting(model, "VISION_MODEL")

    async def _fetch(self, image_url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://qzone.qq.com/",
        }
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
            return base64.b64encode(resp.content).decode()
        except Exception:
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.get(image_url)
                    resp.raise_for_status()
                return base64.b64encode(resp.content).decode()
            except Exception:
                return ""

    async def _do_describe(self, image_b64: str) -> ImageDesc:
        if not image_b64:
            return ImageDesc(description="图片内容暂时无法读取", tags=[], match_quality=0.0)
        payload = {
            "model": self._model,
            "max_tokens": 400,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                        {
                            "type": "text",
                            "text": (
                                "同时完成聊天识图和表情素材判断，只输出紧凑 JSON，不要 Markdown："
                                "{\"description\":\"客观描述画面和可见文字，不超过100字\","
                                "\"sticker_description\":\"若作为表情，它表达的情绪、态度和适用语境，不超过40字\","
                                "\"tags\":[\"核心情绪\",\"聊天意图\",\"适用语境\"],"
                                "\"match_quality\":0到1}。"
                                "match_quality 只衡量能否作为聊天表情反复发送：含明确情绪/态度的表情包可为0.7到1；"
                                "普通照片、角色立绘、风景、游戏截图、信息截图、头像即使画面精美也应为0到0.4。"
                                "表情语义不要罗列服饰背景，只写对话中代表什么。"
                            ),
                        },
                    ],
                }
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self._base_url,
                    headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    break
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start : end + 1])
                description = str(parsed.get("description") or "图片")[:200]
                sticker_description = str(parsed.get("sticker_description") or "")[:100]
                tags = parsed.get("tags", [])
                if not isinstance(tags, list):
                    tags = []
                match_quality = float(parsed.get("match_quality", 0.0))
                return ImageDesc(
                    description=description,
                    sticker_description=sticker_description,
                    tags=tags[:8],
                    match_quality=match_quality,
                )
            plain = text.replace("```json", "").replace("```", "").strip()
            return ImageDesc(description=plain[:120] or "图片内容暂时无法识别", tags=[], match_quality=0.0)
        except Exception:
            return ImageDesc(description="图片内容暂时无法识别", tags=[], match_quality=0.0)
