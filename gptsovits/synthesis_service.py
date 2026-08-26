from __future__ import annotations

from pathlib import Path

from gptsovits.speech_engine import SpeechEngine
from shared.service_settings import GPTSoVITSOutputSettings, GPTSoVITSRequestLimits
from shared.snowflake_id_generator import snowflake_ids


class SynthesisRequestPolicy:
    def __init__(self, limits: GPTSoVITSRequestLimits) -> None:
        self._limits = limits

    def validate(self, ai_id: str, text: str) -> None:
        if not self._limits.ai_id_min_chars <= len(ai_id) <= self._limits.ai_id_max_chars:
            raise ValueError("ai_id 长度不符合配置")
        if not self._limits.text_min_chars <= len(text) <= self._limits.text_max_chars:
            raise ValueError("合成文本长度不符合配置")


class SynthesisService:
    def __init__(
        self,
        engine: SpeechEngine,
        output_config: GPTSoVITSOutputSettings,
        request_policy: SynthesisRequestPolicy,
    ) -> None:
        self._engine = engine
        self._audio_dir = Path(output_config.audio_dir)
        self._extension = output_config.file_extension
        self._pcm_bytes_per_sec = output_config.pcm_bytes_per_sec
        self._request_policy = request_policy

    async def synthesize(self, ai_id: str, text: str) -> dict:
        self._request_policy.validate(ai_id, text)
        result = await self._engine.synthesize(ai_id, text)
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        path = self._audio_dir / f"{ai_id}_{snowflake_ids().next_id()}.{self._extension}"
        path.write_bytes(result.pcm)
        return {
            "audio_path": str(path),
            "duration_sec": len(result.pcm) / self._pcm_bytes_per_sec,
        }

    async def preview(self, ai_id: str, text: str) -> None:
        self._request_policy.validate(ai_id, text)
        await self._engine.synthesize(ai_id, text)

    async def close(self) -> None:
        await self._engine.close()
