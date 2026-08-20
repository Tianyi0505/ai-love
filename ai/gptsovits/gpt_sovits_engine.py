from __future__ import annotations

import httpx

from ai.gptsovits.speech_engine import AudioResult


# 提供GPT-SoVITS推理引擎合成能力
class GPTSoVITSEngine:
    # 初始化当前实例
    def __init__(
        self,
        refs: dict[str, dict],
        text_lang: str,
        prompt_lang: str,
        output_format: str,
        http_client: httpx.AsyncClient,
        base_url: str,
    ) -> None:
        self._url = base_url.rstrip("/")
        self._refs = refs
        self._client = http_client
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
        params = {"text": text, "text_lang": self._text_lang, **self._ref_for(ai_id)}
        resp = await self._client.post(f"{self._url}/tts", params=params)
        resp.raise_for_status()
        return AudioResult(
            pcm=resp.content,
            format=self._output_format,
        )

    async def close(self) -> None:
        await self._client.aclose()
