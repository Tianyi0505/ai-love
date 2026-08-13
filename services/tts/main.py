
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from services.tts.engine import SynthesizeRequest, create_tts
from services.tts.engines import azure, gpt_sovits, mimo, mock  # noqa: F401 导入即注册
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.service import BaseService

logger = logging.getLogger("ailove.tts")

SUBJ_SPEECH = "ai.speech.request"
SUBJ_TTS_SYNTH = "tts.synthesize.request"


class TTSService(BaseService):
    name = "tts"

    async def on_start(self) -> None:
        tts_cfg = await self.cfg.section()
        self._engine = create_tts(
            tts_cfg.get("engine", "gpt_sovits"),
            refs=tts_cfg.get("voices", {}),
        )
        await self.bus.subscribe(SUBJ_SPEECH, self._on_speech)
        await self.bus.reply(SUBJ_TTS_SYNTH, self._on_synthesize)

    async def _on_synthesize(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        result = await self._engine.synthesize(
            SynthesizeRequest(ai_id=req.get("ai_id", ""), text=req.get("text", ""), emotion=req.get("emotion", ""))
        )
        audio_dir = "/app/data/voice"
        os.makedirs(audio_dir, exist_ok=True)
        path = f"{audio_dir}/{req.get('ai_id', 'ai')}_{int(time.time() * 1000)}.wav"
        with open(path, "wb") as f:
            f.write(result.pcm)
        return json.dumps({"ok": True, "audio_path": path, "duration_sec": len(result.pcm) // 32000}).encode()

    async def on_stop(self) -> None:
        await self._engine.close()

    async def _on_speech(self, payload: bytes) -> None:
        req = json.loads(payload.decode("utf-8"))
        # TODO: 句子切分 + 预合成管线 + 播放到虚拟声卡1
        await self._engine.synthesize(
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
