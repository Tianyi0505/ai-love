
from __future__ import annotations

import asyncio
import json
import logging

from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.service import BaseService

logger = logging.getLogger("ailove.music")

SUBJ_MUSIC_CMD = "music.command.{ai_id}"


class MusicService(BaseService):
    name = "music"

    async def on_start(self) -> None:
        await self.bus.subscribe(SUBJ_MUSIC_CMD.replace("{ai_id}", ">"), self._on_command)

    async def on_stop(self) -> None:
        pass

    async def _on_command(self, payload: bytes) -> None:
        cmd = json.loads(payload.decode("utf-8"))
        # TODO: 控制 OBS 音频轨
        logger.info("[music] 指令: %s", cmd.get("type"))


def main() -> None:
    async def run() -> None:
        svc = MusicService(await ServiceConfig.load("music"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
