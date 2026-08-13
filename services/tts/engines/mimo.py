
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

from openai import AsyncOpenAI

from services.tts.engine import AudioResult, SynthesizeRequest, TTSEngine, tts_registry
from shared.infrastructure.runtime_config import required_setting


@tts_registry.register("mimo")
class MimoTTSEngine(TTSEngine):

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None,
                 refs: dict[str, dict] | None = None, **_) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
            base_url=required_setting(base_url, "MIMO_BASE_URL"),
        )
        self._model = required_setting(model, "MIMO_MODEL")
        self._refs = refs or {}

    def _voice_data_uri(self, ai_id: str) -> str:
        ref = self._refs.get(ai_id, {})
        path = ref.get("ref_audio_path", "") or os.environ.get("MIMO_REF_AUDIO", "")
        if not path or not Path(path).exists():
            raise RuntimeError(f"缺少参考音频（声线样本）: ai_id={ai_id}")
        data = Path(path).read_bytes()
        mime = "audio/wav" if path.endswith(".wav") else "audio/mpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        t0 = time.perf_counter()
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "user", "content": ""},
                {"role": "assistant", "content": text},
            ],
            audio={"format": "wav", "voice": self._voice_data_uri(req.ai_id)},
            stream=False,
        )
        audio_b64 = resp.choices[0].message.audio.data
        pcm = base64.b64decode(audio_b64)
        return AudioResult(
            pcm=pcm,
            format="wav",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
