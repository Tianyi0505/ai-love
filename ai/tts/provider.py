
from __future__ import annotations

from abc import ABC, abstractmethod


# 定义语音合成服务接口
class TTSProvider(ABC):
    # 合成语音内容（引擎不可用直接抛错）
    @abstractmethod
    async def synthesize(self, text: str) -> dict:
        pass
