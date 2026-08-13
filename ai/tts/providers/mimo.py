
from __future__ import annotations

import base64
import time
from pathlib import Path

from openai import AsyncOpenAI

from ai.tts.provider import TTSProvider
from ai.tts.registry import provider_registry
from ai.tts.types import AudioResult, SynthesizeRequest
from shared.infrastructure.runtime_config import ConfigKey, required_setting, required_value


# 提供Mimo语音合成能力
@provider_registry.register("mimo")
class MimoTTSProvider(TTSProvider):

    # 初始化当前实例
    def __init__(self, refs: dict[str, dict], request_timeout_sec: float, api_audio_format: str, output_format: str, api_key: str | None = None, base_url: str | None = None, model: str | None = None, **_) -> None:
        self._client = AsyncOpenAI(
            api_key=required_setting(api_key, ConfigKey.ANTHROPIC_AUTH_TOKEN),
            base_url=required_setting(base_url, ConfigKey.MIMO_BASE_URL),
            timeout=request_timeout_sec,
        )
        self._model = required_setting(model, ConfigKey.MIMO_MODEL)
        self._refs = refs
        self._api_audio_format = api_audio_format
        self._output_format = output_format

    # 生成语音数据地址
    def _voice_data_uri(self, ai_id: str) -> str:
        path = required_value(self._refs[ai_id]["ref_audio_path"], f"service.tts.voices.{ai_id}.ref_audio_path")
        if not Path(path).exists():
            raise RuntimeError(f"缺少参考音频（声线样本）: ai_id={ai_id}")
        data = Path(path).read_bytes()
        mime = "audio/wav" if path.endswith(".wav") else "audio/mpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    # 执行语音合成请求
    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        t0 = time.perf_counter()
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "user", "content": ""},
                {"role": "assistant", "content": text},
            ],
            audio={"format": self._api_audio_format, "voice": self._voice_data_uri(req.ai_id)},
            stream=False,
        )
        audio_b64 = resp.choices[0].message.audio.data
        pcm = base64.b64decode(audio_b64)
        return AudioResult(
            pcm=pcm,
            format=self._output_format,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
