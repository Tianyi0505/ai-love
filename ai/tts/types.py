from __future__ import annotations

from dataclasses import dataclass, field


# 表示语音合成请求数据
@dataclass(frozen=True)
class SynthesizeRequest:
    ai_id: str
    text: str
    emotion: str = ""
    options: dict = field(default_factory=dict)


# 表示音频结果数据
@dataclass(frozen=True)
class AudioResult:
    pcm: bytes
    format: str
    latency_ms: int
