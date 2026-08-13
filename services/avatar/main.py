
from __future__ import annotations

import asyncio
import json
import logging

from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.service import BaseService

logger = logging.getLogger("ailove.avatar")

SUBJ_AVATAR = "avatar.command.{ai_id}"


class AvatarService(BaseService):
    name = "avatar"

    async def on_start(self) -> None:
        # TODO: 托管 live2d.html（OBS 浏览器源指向本端口）
        await self.bus.subscribe(SUBJ_AVATAR.replace("{ai_id}", ">"), self._on_command)

    async def on_stop(self) -> None:
        pass

    async def _on_command(self, payload: bytes) -> None:
        cmd = json.loads(payload.decode("utf-8"))
        # TODO: SPEAK→viseme / EMOTION→表情 / ACTION→动作 → WS 推送
        logger.info("[avatar] 指令: %s", cmd.get("type"))


def main() -> None:
    async def run() -> None:
        svc = AvatarService(await ServiceConfig.load("avatar"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
