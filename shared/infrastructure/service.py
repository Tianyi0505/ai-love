
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from shared.infrastructure.bus import Bus, create_bus
from shared.infrastructure.config import ServiceConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("ailove.service")


class BaseService(ABC):

    name: str = ""

    def __init__(self, cfg: ServiceConfig, bus: Bus | None = None) -> None:
        self.cfg = cfg
        self.bus = bus or create_bus(cfg.bus_url, cfg.bus_token)
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        logger.info("[%s] 启动中 ...", self.name)
        await self.bus.connect()
        await self._register_to_discovery()
        await self.on_start()
        logger.info("[%s] 启动完成", self.name)

    async def stop(self) -> None:
        logger.info("[%s] 停止中 ...", self.name)
        for task in list(self._tasks):
            task.cancel()
        await self.on_stop()
        if self.cfg.nacos is not None:
            await self.cfg.nacos.close()
        await self.bus.close()
        logger.info("[%s] 已停止", self.name)

    async def serve_forever(self) -> None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _signal() -> None:
            stop_event.set()

        try:
            for sig in ("SIGINT", "SIGTERM"):
                loop.add_signal_handler(getattr(__import__("signal"), sig), _signal)
        except NotImplementedError:
            pass

        await stop_event.wait()

    async def _register_to_discovery(self) -> None:
        if self.cfg.nacos is None:
            logger.info("[%s] 未配置 Nacos，跳过注册", self.name)
            return
        await self.cfg.nacos.register(self.name, self.cfg.instance_id, self.cfg.instance_addr)
        logger.info("[%s] 已注册到 Nacos (instance=%s)", self.name, self.cfg.instance_id)

    @abstractmethod
    async def on_start(self) -> None:
        pass

    @abstractmethod
    async def on_stop(self) -> None:
        pass

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        task.add_done_callback(self._discard_task)
        return task

    def _discard_task(self, task: asyncio.Task) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("[%s] 后台任务失败: %s", self.name, task.exception())

    def subscribe(self, subject: str, handler):
        return self.spawn(self._subscribe_loop(subject, handler))

    async def _subscribe_loop(self, subject: str, handler):
        sub = await self.bus.subscribe(subject, handler)
        try:
            await asyncio.Event().wait()
        finally:
            sub.unsubscribe()
