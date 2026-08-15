
from __future__ import annotations

import os

from openai import AsyncOpenAI

from ai.vision.provider import VisionProvider
from ai.vision.registry import provider_registry
from ai.vision.types import ImageDescription
from shared.infrastructure.runtime_config import required_value


# 提供OpenAI兼容协议图像理解能力（供应商与模型全部由配置声明）
@provider_registry.register("openai_compatible")
class OpenAICompatibleVisionProvider(VisionProvider):

    # 初始化当前实例
    def __init__(
        self,
        fetch_timeout_sec: float,
        request_timeout_sec: float,
        max_tokens: int,
        prompt: str,
        fetch_headers: dict,
        media_type: str,
        limits: dict,
        fallbacks: dict,
        model: str,
        base_url: str,
        api_key_env: str = "",
        api_key: str | None = None,
        **_,
    ) -> None:
        super().__init__(fetch_timeout_sec, fetch_headers)
        self._api_key = required_value(
            api_key or (os.environ.get(api_key_env) if api_key_env else None),
            api_key_env or "vision api_key",
        )
        self._base_url = base_url
        self._model = model
        self._prompt = prompt
        self._request_timeout_sec = request_timeout_sec
        self._max_tokens = max_tokens
        self._media_type = media_type
        self._limits = limits
        self._fallbacks = fallbacks
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=float(self._request_timeout_sec),
        )

    # 执行图像理解请求
    async def _do_describe(self, image_b64: str) -> ImageDescription:
        if not image_b64:
            return ImageDescription(
                description=str(self._fallbacks["unreadable"]),
                tags=[],
                match_quality=float(self._fallbacks["match_quality"]),
            )
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=int(self._max_tokens),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{self._media_type};base64,{image_b64}"},
                            },
                            {"type": "text", "text": self._prompt},
                        ],
                    }
                ],
            )
            text = resp.choices[0].message.content or ""
            return self._parse_response(text, self._limits, self._fallbacks)
        except Exception:
            return ImageDescription(
                description=str(self._fallbacks["unrecognized"]),
                tags=[],
                match_quality=float(self._fallbacks["match_quality"]),
            )
