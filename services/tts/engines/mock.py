
from __future__ import annotations

import io
import math
import struct
import wave

from services.tts.engine import AudioResult, SynthesizeRequest, TTSEngine, tts_registry


@tts_registry.register("mock")
class MockTTSEngine(TTSEngine):

    def __init__(self, **_) -> None:
        pass

    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            duration = max(1, min(5, len(text) // 4))
            for i in range(16000 * duration):
                w.writeframes(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 16000))))
        return AudioResult(pcm=buf.getvalue(), format="pcm_s16le_16k", latency_ms=10)
