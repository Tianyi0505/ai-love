
from __future__ import annotations

import logging

from ai.tts.provider import TTSProvider

logger = logging.getLogger("ailove.tts.routing")


# 按配置顺序提供语音合成与故障切换
class TTSRouter(TTSProvider):

    # 初始化当前实例
    def __init__(self, providers: list[TTSProvider]) -> None:
        self._providers = providers

    # 合成语音内容
    async def synthesize(self, text: str) -> dict:
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                return await provider.synthesize(text)
            except Exception as exc:
                logger.warning("[tts] 供应商失败，尝试下一个: %s", str(exc)[:120])
                last_error = exc
        raise RuntimeError("全部语音供应商不可用") from last_error
