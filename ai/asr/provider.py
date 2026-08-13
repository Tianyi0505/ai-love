from __future__ import annotations

from abc import ABC, abstractmethod


# 定义语音识别服务接口
class ASRProvider(ABC):
    # 转写音频内容
    @abstractmethod
    async def transcribe(self, audio_url: str) -> str:
        pass
