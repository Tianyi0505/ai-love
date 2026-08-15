from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from ai.gptsovits.types import AudioResult
from shared.infrastructure.registry import Registry
from shared.infrastructure.runtime_config import ConfigKey, required_setting, required_value

logger = logging.getLogger("ailove.gptsovits.engine")

engine_registry = Registry("gptsovits_engine")


# 提供GPT-SoVITS推理引擎合成能力
@engine_registry.register("gptsovits")
class GPTSoVITSEngine:

    # 初始化当前实例
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

    # 生成语音引用标识
    def _ref_for(self, ai_id: str) -> dict:
        ref = self._refs[ai_id]
        return {
            "text_lang": self._text_lang,
            "prompt_lang": self._prompt_lang,
            "ref_audio_path": ref["ref_audio_path"],
            "ref_text": ref.get("ref_text", ""),
            **ref,
        }

    # 执行语音合成请求
    async def synthesize(self, ai_id: str, text: str) -> AudioResult:
        t0 = time.perf_counter()
        params = {"text": text, "text_lang": self._text_lang, **self._ref_for(ai_id)}
        async with httpx.AsyncClient(timeout=self._request_timeout_sec) as client:
            resp = await client.post(f"{self._url}/tts", params=params)
            resp.raise_for_status()
        return AudioResult(
            pcm=resp.content,
            format=self._output_format,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )


# 提供Mimo语音克隆合成能力
@engine_registry.register("mimo")
class MimoEngine:

    # 初始化当前实例
    def __init__(
        self,
        refs: dict[str, dict],
        request_timeout_sec: float,
        api_audio_format: str,
        output_format: str,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=required_setting(None, ConfigKey.ANTHROPIC_AUTH_TOKEN),
            base_url=required_setting(base_url, ConfigKey.MIMO_BASE_URL),
            timeout=request_timeout_sec,
        )
        self._model = required_setting(model, ConfigKey.MIMO_MODEL)
        self._refs = refs
        self._api_audio_format = api_audio_format
        self._output_format = output_format

    # 生成语音数据地址
    def _voice_data_uri(self, ai_id: str) -> str:
        path = required_value(
            self._refs[ai_id]["ref_audio_path"],
            f"service.gptsovits.voices.{ai_id}.ref_audio_path",
        )
        if not Path(path).exists():
            raise RuntimeError(f"缺少参考音频（声线样本）: ai_id={ai_id}")
        data = Path(path).read_bytes()
        mime = "audio/wav" if path.endswith(".wav") else "audio/mpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    # 执行语音合成请求
    async def synthesize(self, ai_id: str, text: str) -> AudioResult:
        t0 = time.perf_counter()
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "user", "content": ""},
                {"role": "assistant", "content": text},
            ],
            audio={"format": self._api_audio_format, "voice": self._voice_data_uri(ai_id)},
            stream=False,
        )
        audio_b64 = resp.choices[0].message.audio.data
        return AudioResult(
            pcm=base64.b64decode(audio_b64),
            format=self._output_format,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )


# 按配置顺序合成并故障切换
class EngineRouter:

    # 初始化当前实例
    def __init__(self, engines: list) -> None:
        self._engines = engines

    # 合成语音内容
    async def synthesize(self, ai_id: str, text: str) -> AudioResult:
        last_error: Exception | None = None
        for engine in self._engines:
            try:
                return await engine.synthesize(ai_id, text)
            except Exception as exc:
                logger.warning("[gptsovits] 引擎失败，尝试下一个: %s", str(exc)[:120])
                last_error = exc
        raise RuntimeError("全部语音引擎不可用") from last_error


# 创建语音引擎路由
def create_engine(engine_cfg: dict, refs: dict[str, dict]) -> EngineRouter:
    engines = []
    for entry in engine_cfg["providers"]:
        opts = {key: value for key, value in entry.items() if key != "provider"}
        cls = engine_registry.get(entry["provider"])
        engines.append(cls(refs=refs, **opts))
    return EngineRouter(engines)
