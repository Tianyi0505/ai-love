from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SynthesizeRequest:
    ai_id: str
    text: str
    emotion: str = ""
    options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AudioResult:
    pcm: bytes
    format: str
    latency_ms: int
