
from __future__ import annotations

import time

import httpx

from services.tts.engine import AudioResult, SynthesizeRequest, TTSEngine, tts_registry
from shared.infrastructure.runtime_config import required_setting


@tts_registry.register("gpt_sovits")
class GPTSovitsEngine(TTSEngine):
    def __init__(self, base_url: str | None = None, refs: dict[str, dict] | None = None) -> None:
        self._url = required_setting(base_url, "GPT_SOVITS_URL").rstrip("/")
        self._refs = refs or {}

    def _ref_for(self, ai_id: str) -> dict:
        ref = self._refs.get(ai_id, {})
        return {
            "text_lang": "zh",
            "prompt_lang": "zh",
            "ref_audio_path": ref.get("ref_audio_path", ""),
            "ref_text": ref.get("ref_text", ""),
            **ref,
        }

    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        t0 = time.perf_counter()
        params = {"text": text, "text_lang": "zh", **self._ref_for(req.ai_id)}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._url}/tts", params=params)
            resp.raise_for_status()
        return AudioResult(
            pcm=resp.content,
            format="pcm_s16le_16k",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
