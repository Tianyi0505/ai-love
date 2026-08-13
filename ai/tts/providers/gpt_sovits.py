
from __future__ import annotations

import time

import httpx

from ai.tts.provider import TTSProvider, provider_registry
from ai.tts.types import AudioResult, SynthesizeRequest
from shared.infrastructure.runtime_config import ConfigKey, required_setting


@provider_registry.register("gpt_sovits")
class GPTSovitsProvider(TTSProvider):
    def __init__(
        self,
        refs: dict[str, dict],
        request_timeout_sec: float,
        text_lang: str,
        prompt_lang: str,
        output_format: str,
        base_url: str | None = None,
    ) -> None:
        self._url = required_setting(base_url, ConfigKey.GPT_SOVITS_URL).rstrip("/")
        self._refs = refs
        self._request_timeout_sec = request_timeout_sec
        self._text_lang = text_lang
        self._prompt_lang = prompt_lang
        self._output_format = output_format

    def _ref_for(self, ai_id: str) -> dict:
        ref = self._refs[ai_id]
        return {
            "text_lang": self._text_lang,
            "prompt_lang": self._prompt_lang,
            "ref_audio_path": ref["ref_audio_path"],
            "ref_text": ref["ref_text"],
            **ref,
        }

    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        t0 = time.perf_counter()
        params = {"text": text, "text_lang": self._text_lang, **self._ref_for(req.ai_id)}
        async with httpx.AsyncClient(timeout=self._request_timeout_sec) as client:
            resp = await client.post(f"{self._url}/tts", params=params)
            resp.raise_for_status()
        return AudioResult(
            pcm=resp.content,
            format=self._output_format,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
