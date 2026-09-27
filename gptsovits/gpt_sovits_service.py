from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack

import httpx
import uvicorn
from stevedore.driver import DriverManager
from stevedore.extension import error_on_conflict

from gptsovits.synthesis_api import create_app
from gptsovits.synthesis_service import (
    SynthesisRequestPolicy,
    SynthesisService,
)
from shared.base_service import BaseService
from shared.contracts.live import SUBJ_SPEECH
from shared.contracts.rpc.social import SpeechRequest
from shared.service_config import ServiceConfig
from shared.service_settings import GPTSoVITSSettings

logger = logging.getLogger("ailove.gptsovits")

# 提供GPT-SoVITS引擎宿主服务能力
class GPTSoVITSService(BaseService):
    name = "gptsovits"

    # 启动服务
    async def on_start(self) -> None:
        self._cleanup = AsyncExitStack()
        cfg = await self.cfg.section(GPTSoVITSSettings)
        engine_config = cfg.engine.model_dump()
        engine_name = str(engine_config.pop("provider"))
        engine_config["refs"] = {
            ai_id: voice.model_dump() for ai_id, voice in cfg.voices.items()
        }
        request_timeout_sec = float(engine_config.pop("request_timeout_sec"))
        engine_config["http_client"] = httpx.AsyncClient(timeout=request_timeout_sec)
        self._cleanup.push_async_callback(engine_config["http_client"].aclose)
        context = getattr(self, "plugin_context", None)
        self._engine = context.require("speech.engines").create(engine_name, **engine_config) if context else DriverManager(
            namespace="ai_love.gptsovits",
            name=engine_name,
            invoke_on_load=True,
            invoke_kwds=engine_config,
            conflict_resolver=error_on_conflict,
        ).driver
        self._cleanup.push_async_callback(self._engine.close)
        self._synthesis = SynthesisService(
            self._engine,
            cfg.output,
            SynthesisRequestPolicy(cfg.request_limits),
        )
        http_config = cfg.http
        self._http = uvicorn.Server(
            uvicorn.Config(
                create_app(self._synthesis),
                host=http_config.bind,
                port=http_config.port,
                log_level=http_config.log_level,
            )
        )
        await self.bus.subscribe_model(SUBJ_SPEECH, SpeechRequest, self._on_speech)
        logger.info(
            "[gptsovits] HTTP 合成接口已配置: %s:%s",
            http_config.bind,
            http_config.port,
        )

    # 停止服务
    async def on_stop(self) -> None:
        if hasattr(self, "_cleanup"):
            await self._cleanup.aclose()

    async def serve(self) -> None:
        await self._http.serve()

    # 处理话语
    async def _on_speech(self, request: SpeechRequest) -> None:
        # 切分句子、预合成语音并播放到虚拟声卡
        await self._synthesis.preview(request.ai_id, request.text)
        logger.info("[gptsovits] 合成: %s", request.text)


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        svc = GPTSoVITSService(await ServiceConfig.load("gptsovits"))
        await svc.start()
        try:
            await svc.serve()
        finally:
            await svc.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
