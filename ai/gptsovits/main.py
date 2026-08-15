
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from ai.gptsovits.engine import create_engine
from ai.gptsovits.http_api import SynthesisHTTPServer
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.service import BaseService

logger = logging.getLogger("ailove.gptsovits")

SUBJ_SPEECH = "ai.speech.request"


# 提供GPT-SoVITS引擎宿主服务能力
class GPTSoVITSService(BaseService):
    name = "gptsovits"

    # 启动服务
    async def on_start(self) -> None:
        cfg = await self.cfg.section()
        self._engine = create_engine(cfg["engine"], cfg["voices"])
        self._output_config = cfg["output"]
        bind = str(cfg["http"].get("bind", "127.0.0.1"))
        self._http = SynthesisHTTPServer(port=cfg["http"]["port"], bind=bind)
        self._http.start(self, asyncio.get_running_loop())
        await self.bus.subscribe(SUBJ_SPEECH, self._on_speech)
        logger.info("[gptsovits] HTTP 合成接口已启动: %s:%s", bind, cfg["http"]["port"])

    # 停止服务
    async def on_stop(self) -> None:
        self._http.stop()

    # 合成语音并落盘
    async def synthesize(self, ai_id: str, text: str) -> dict:
        result = await self._engine.synthesize(ai_id, text)
        audio_dir = str(self._output_config["audio_dir"])
        os.makedirs(audio_dir, exist_ok=True)
        extension = str(self._output_config["file_extension"])
        path = f"{audio_dir}/{ai_id}_{int(time.time() * 1000)}.{extension}"
        with open(path, "wb") as f:
            f.write(result.pcm)
        duration_sec = len(result.pcm) / float(self._output_config["pcm_bytes_per_sec"])
        return {"ok": True, "audio_path": path, "duration_sec": duration_sec}

    # 处理话语
    async def _on_speech(self, payload: bytes) -> None:
        req = json.loads(payload.decode("utf-8"))
        # 切分句子、预合成语音并播放到虚拟声卡
        await self._engine.synthesize(
            str(req.get("ai_id", "")),
            str(req.get("text", "")),
        )
        logger.info("[gptsovits] 合成: %s", str(req.get("text", ""))[:30])


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        svc = GPTSoVITSService(await ServiceConfig.load("gptsovits"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()