
from __future__ import annotations

import base64
import json

import httpx

from ai.vision.provider import VisionProvider
from ai.vision.registry import provider_registry
from ai.vision.types import ImageDescription
from shared.infrastructure.runtime_config import ConfigKey, required_setting


@provider_registry.register("anthropic")
class AnthropicVisionProvider(VisionProvider):

    def __init__(
        self,
        fetch_timeout_sec: float,
        request_timeout_sec: float,
        max_tokens: int,
        prompt: str,
        fetch_headers: dict,
        anthropic_version: str,
        media_type: str,
        limits: dict,
        fallbacks: dict,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        **_,
    ) -> None:
        self._api_key = required_setting(api_key, ConfigKey.ANTHROPIC_AUTH_TOKEN)
        self._base_url = required_setting(base_url, ConfigKey.VISION_BASE_URL)
        self._model = required_setting(model, ConfigKey.VISION_MODEL)
        self._prompt = prompt
        self._fetch_timeout_sec = fetch_timeout_sec
        self._request_timeout_sec = request_timeout_sec
        self._max_tokens = max_tokens
        self._fetch_headers = fetch_headers
        self._anthropic_version = anthropic_version
        self._media_type = media_type
        self._limits = limits
        self._fallbacks = fallbacks

    async def _fetch(self, image_url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._fetch_timeout_sec, headers=self._fetch_headers, follow_redirects=True) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
            return base64.b64encode(resp.content).decode()
        except Exception:
            try:
                async with httpx.AsyncClient(timeout=self._fetch_timeout_sec, follow_redirects=True) as client:
                    resp = await client.get(image_url)
                    resp.raise_for_status()
                return base64.b64encode(resp.content).decode()
            except Exception:
                return ""

    async def _do_describe(self, image_b64: str) -> ImageDescription:
        if not image_b64:
            return ImageDescription(
                description=str(self._fallbacks["unreadable"]),
                tags=[],
                match_quality=float(self._fallbacks["match_quality"]),
            )
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": self._media_type, "data": image_b64}},
                        {
                            "type": "text",
                            "text": self._prompt,
                        },
                    ],
                }
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_sec) as client:
                resp = await client.post(
                    self._base_url,
                    headers={"x-api-key": self._api_key, "anthropic-version": self._anthropic_version},
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
                description = str(parsed.get("description") or self._fallbacks["default_description"])[
                    : int(self._limits["description_chars"])
                ]
                sticker_description = str(parsed.get("sticker_description") or "")[
                    : int(self._limits["sticker_description_chars"])
                ]
                tags = parsed.get("tags", [])
                if not isinstance(tags, list):
                    tags = []
                match_quality = float(parsed.get("match_quality", self._fallbacks["match_quality"]))
                return ImageDescription(
                    description=description,
                    sticker_description=sticker_description,
                    tags=tags[: int(self._limits["tags"])],
                    match_quality=match_quality,
                )
            plain = text.replace("```json", "").replace("```", "").strip()
            return ImageDescription(
                description=plain[: int(self._limits["plain_description_chars"])]
                or str(self._fallbacks["unrecognized"]),
                tags=[],
                match_quality=float(self._fallbacks["match_quality"]),
            )
        except Exception:
            return ImageDescription(
                description=str(self._fallbacks["unrecognized"]),
                tags=[],
                match_quality=float(self._fallbacks["match_quality"]),
            )
