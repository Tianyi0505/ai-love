from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from gptsovits.speech_engine import AudioResult
from shared.connection_settings import MimoAuthSettings


class MimoEngine:
    def __init__(
        self,
        refs: dict[str, dict],
        api_audio_format: str,
        output_format: str,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
    ) -> None:
        auth = MimoAuthSettings()
        self._client = AsyncOpenAI(
            api_key=auth.auth_token,
            base_url=base_url,
            http_client=http_client,
        )
        self._model = model
        self._refs = refs
        self._api_audio_format = api_audio_format
        self._output_format = output_format

    def _voice_data_uri(self, ai_id: str) -> str:
        audio_path = Path(str(self._refs[ai_id]["ref_audio_path"]))
        data = audio_path.read_bytes()
        mime = mimetypes.guess_type(audio_path)[0]
        if mime is None:
            raise ValueError(f"无法识别参考音频媒体类型: {audio_path}")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    async def synthesize(self, ai_id: str, text: str) -> AudioResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "user", "content": ""},
                {"role": "assistant", "content": text},
            ],
            audio={"format": self._api_audio_format, "voice": self._voice_data_uri(ai_id)},
            stream=False,
        )
        audio_b64 = response.choices[0].message.audio.data
        return AudioResult(
            pcm=base64.b64decode(audio_b64),
            format=self._output_format,
        )

    async def close(self) -> None:
        await self._client.close()
