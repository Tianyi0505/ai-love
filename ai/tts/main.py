
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from ai.tts.factory import create_tts
from ai.tts.providers import azure, gpt_sovits, mimo
from ai.tts.types import SynthesizeRequest
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.service import BaseService

logger = logging.getLogger("ailove.tts")

SUBJ_SPEECH = "ai.speech.request"
SUBJ_TTS_SYNTH = "tts.synthesize.request"


class TTSService(BaseService):
    name = "tts"

    async def on_start(self) -> None:
        tts_cfg = await self.cfg.section()
        self._provider = create_tts(
            tts_cfg["engine"],
            refs=tts_cfg["voices"],
            **tts_cfg["engine_options"],
        )
        self._output_config = tts_cfg["output"]
        await self.bus.subscribe(SUBJ_SPEECH, self._on_speech)
        await self.bus.reply(SUBJ_TTS_SYNTH, self._on_synthesize)

    async def _on_synthesize(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        result = await self._provider.synthesize(
            SynthesizeRequest(ai_id=req.get("ai_id", ""), text=req.get("text", ""), emotion=req.get("emotion", ""))
        )
        audio_dir = str(self._output_config["audio_dir"])
        os.makedirs(audio_dir, exist_ok=True)
        ai_id = str(req["ai_id"])
        extension = str(self._output_config["file_extension"])
        path = f"{audio_dir}/{ai_id}_{int(time.time() * 1000)}.{extension}"
        with open(path, "wb") as f:
            f.write(result.pcm)
        duration_sec = len(result.pcm) / float(self._output_config["pcm_bytes_per_sec"])
        return json.dumps({"ok": True, "audio_path": path, "duration_sec": duration_sec}).encode()

    async def on_stop(self) -> None:
        await self._provider.close()

    async def _on_speech(self, payload: bytes) -> None:
        req = json.loads(payload.decode("utf-8"))
        # 切分句子、预合成语音并播放到虚拟声卡
        await self._provider.synthesize(
            SynthesizeRequest(ai_id=req.get("ai_id", ""), text=req.get("text", ""), emotion=req.get("meta", {}).get("emotion", ""))
        )
        logger.info("[tts] 合成: %s", req.get("text", "")[:30])


def main() -> None:
    async def run() -> None:
        svc = TTSService(await ServiceConfig.load("tts"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
