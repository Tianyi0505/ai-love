
from __future__ import annotations

import logging

import httpx

from ai.tts.provider import TTSProvider
from ai.tts.registry import provider_registry

logger = logging.getLogger("ailove.tts.gptsovits")


# 提供GPT-SoVITS引擎服务合成能力
@provider_registry.register("gptsovits")
class GPTSoVITSProvider(TTSProvider):

    # 初始化当前实例
    def __init__(self, ai_id: str, timeout_sec: float, base_url: str, **_) -> None:
        self._ai_id = ai_id
        self._timeout_sec = timeout_sec
        self._base_url = base_url.rstrip("/")

    # 合成语音内容
    async def synthesize(self, text: str) -> dict:
        async with httpx.AsyncClient(timeout=float(self._timeout_sec)) as client:
            resp = await client.post(
                f"{self._base_url}/synthesize",
                json={"ai_id": self._ai_id, "text": text},
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"语音合成失败: {data.get('error', 'unknown')}")
        return {
            "audio_path": data["audio_path"],
            "duration_sec": data["duration_sec"],
        }
