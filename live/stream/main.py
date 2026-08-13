
from __future__ import annotations

import asyncio
import json
import logging

from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.runtime_config import required_value
from shared.infrastructure.service import BaseService

logger = logging.getLogger("ailove.stream")

SUBJ_OBS_CONTROL = "obs.control"


class StreamService(BaseService):
    name = "stream"

    async def on_start(self) -> None:
        section = await self.cfg.section()
        self._obs_url = required_value(section["obs_ws_url"], "service.stream.obs_ws_url")
        self._stream_key = required_value(section["stream_key"], "service.stream.stream_key")
        # 通过 OBS WebSocket 创建场景并配置推流地址
        await self.bus.subscribe(SUBJ_OBS_CONTROL, self._on_control)

    async def on_stop(self) -> None:
        pass

    async def _on_control(self, payload: bytes) -> None:
        cmd = json.loads(payload.decode("utf-8"))
        # 处理开播、停播和场景切换命令
        logger.info("[stream] 控制: %s", cmd.get("action"))


def main() -> None:
    async def run() -> None:
        svc = StreamService(await ServiceConfig.load("stream"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
