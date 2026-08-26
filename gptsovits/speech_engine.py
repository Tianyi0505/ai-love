from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


# 表示音频结果数据
@dataclass(frozen=True)
class AudioResult:
    pcm: bytes
    format: str


class SpeechEngine(Protocol):
    async def synthesize(self, ai_id: str, text: str) -> AudioResult: ...

    async def close(self) -> None: ...
