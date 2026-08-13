
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from shared.infrastructure.registry import Registry

tts_registry = Registry("tts")


@dataclass
class SynthesizeRequest:
    ai_id: str
    text: str
    emotion: str = ""
    options: dict = None


@dataclass
class AudioResult:
    pcm: bytes
    format: str = "pcm_s16le_16k"
    latency_ms: int = 0


class TTSEngine(ABC):

    async def synthesize(self, req: SynthesizeRequest) -> AudioResult:
        text = await self._preprocess(req.text, req)
        result = await self._do_synthesize(req, text)
        result = await self._postprocess(result, req)
        return result

    async def close(self) -> None:
        pass

    @abstractmethod
    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        pass

    async def _preprocess(self, text: str, req: SynthesizeRequest) -> str:
        return text

    async def _postprocess(self, result: AudioResult, req: SynthesizeRequest) -> AudioResult:
        return result


def create_tts(kind: str, **opts) -> TTSEngine:
    cls = tts_registry.get(kind)
    return cls(**opts)  # type: ignore
