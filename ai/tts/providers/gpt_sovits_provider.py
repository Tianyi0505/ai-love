from __future__ import annotations

import httpx

from ai.tts.tts_provider import TTSProvider
from shared.contracts.tts import SynthesizeResponse


# 提供GPT-SoVITS引擎服务合成能力
class GPTSoVITSProvider(TTSProvider):
    # 初始化当前实例
    def __init__(self, ai_id: str, base_url: str, http_client: httpx.AsyncClient) -> None:
        self._ai_id = ai_id
        self._base_url = base_url.rstrip("/")
        self._client = http_client

    # 合成语音内容
    async def synthesize(self, text: str) -> dict:
        response = await self._client.post(
            f"{self._base_url}/synthesize",
            json={"ai_id": self._ai_id, "text": text},
        )
        response.raise_for_status()
        return SynthesizeResponse.model_validate_json(response.content).model_dump()
