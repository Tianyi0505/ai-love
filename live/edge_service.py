from __future__ import annotations

import asyncio

from live.avatar.avatar_module import AvatarModule
from live.stream.stream_module import StreamModule
from shared.configuration.service_settings import LiveEdgeSettings
from shared.infrastructure.base_service import BaseService
from shared.infrastructure.service_config import ServiceConfig


class LiveEdgeService(BaseService):
    name = "live-edge"

    async def on_start(self) -> None:
        settings = await self.cfg.section(LiveEdgeSettings)
        modules = [AvatarModule(self.bus), StreamModule(self.bus, settings)]
        self._started_modules = []
        try:
            for module in modules:
                await module.start()
                self._started_modules.append(module)
        except Exception:
            await self._stop_modules()
            raise

    async def on_stop(self) -> None:
        await self._stop_modules()

    async def _stop_modules(self) -> None:
        for module in reversed(self._started_modules):
            await module.stop()
        self._started_modules.clear()


def main() -> None:
    async def run() -> None:
        service = LiveEdgeService(await ServiceConfig.load("live-edge"))
        await service.start()
        try:
            await service.serve_forever()
        finally:
            await service.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
