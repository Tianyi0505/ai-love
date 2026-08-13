
from __future__ import annotations

import os

from services.tts.engine import AudioResult, SynthesizeRequest, TTSEngine, tts_registry
from shared.infrastructure.runtime_config import required_setting


@tts_registry.register("azure")
class AzureTTSEngine(TTSEngine):
    def __init__(self, key: str | None = None, region: str | None = None, voices: dict[str, str] | None = None) -> None:
        self._key = key or os.environ.get("AZURE_SPEECH_KEY", "")
        self._region = required_setting(region, "AZURE_SPEECH_REGION")
        self._voices = voices or {}

    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        # TODO: 用 azure-cognitiveservices-speech SDK 实现
        raise NotImplementedError(
            f"Azure 引擎待实现: voice={self._voices.get(req.ai_id, '未配置')}"
        )
