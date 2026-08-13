from __future__ import annotations

from abc import ABC, abstractmethod


class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_url: str) -> str:
        pass
