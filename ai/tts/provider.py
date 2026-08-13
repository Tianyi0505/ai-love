
from __future__ import annotations

from abc import ABC, abstractmethod

from ai.tts.types import AudioResult, SynthesizeRequest
class TTSProvider(ABC):

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
