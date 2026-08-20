
from __future__ import annotations

import asyncio
import logging

from shared.contracts.avatar_command import AvatarCommand
from shared.infrastructure.base_service import BaseService
from shared.infrastructure.service_config import ServiceConfig

logger = logging.getLogger("ailove.avatar")

SUBJ_AVATAR = "avatar.command.{ai_id}"


# 提供虚拟形象服务能力
class AvatarService(BaseService):
    name = "avatar"

    # 启动服务
    async def on_start(self) -> None:
        # 托管供 OBS 浏览器源访问的 Live2D 页面
        await self.bus.subscribe_model(
            SUBJ_AVATAR.replace("{ai_id}", ">"), AvatarCommand, self._on_command
        )

    # 停止服务
    async def on_stop(self) -> None:
        pass

    # 处理命令
    async def _on_command(self, command: AvatarCommand) -> None:
        # 转换舞台事件并推送到 WebSocket
        logger.info("[avatar] 指令: %s", command.type)


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        svc = AvatarService(await ServiceConfig.load("avatar"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
