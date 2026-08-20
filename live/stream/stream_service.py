
from __future__ import annotations

import asyncio
import logging

from shared.configuration.service_settings import StreamSettings
from shared.contracts.stream_control import StreamControl
from shared.infrastructure.base_service import BaseService
from shared.infrastructure.service_config import ServiceConfig

logger = logging.getLogger("ailove.stream")

SUBJ_OBS_CONTROL = "obs.control"


# 提供直播流服务能力
class StreamService(BaseService):
    name = "stream"

    # 启动服务
    async def on_start(self) -> None:
        section = await self.cfg.section(StreamSettings)
        self._obs_url = section.obs_ws_url
        self._stream_key = section.stream_key
        # 通过 OBS WebSocket 创建场景并配置推流地址
        await self.bus.subscribe_model(SUBJ_OBS_CONTROL, StreamControl, self._on_control)

    # 停止服务
    async def on_stop(self) -> None:
        pass

    # 处理控制命令
    async def _on_control(self, command: StreamControl) -> None:
        # 处理开播、停播和场景切换命令
        logger.info("[stream] 控制: %s", command.action)


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        svc = StreamService(await ServiceConfig.load("stream"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
