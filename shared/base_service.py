from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from shared.nats_bus import Bus, create_bus
from shared.service_config import ServiceConfig
from shared.telemetry_runtime import TelemetryRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("ailove.service")


# 定义基础服务接口
class BaseService(ABC):
    name: str

    # 初始化当前实例
    def __init__(self, cfg: ServiceConfig, bus: Bus | None = None) -> None:
        self.cfg = cfg
        self.bus = bus if bus is not None else create_bus(cfg.bus_url, cfg.bus_token)
        self._tasks: list[asyncio.Task] = []
        self.scheduler = AsyncIOScheduler()
        self.telemetry: TelemetryRuntime | None = None

    # 启动服务
    async def start(self) -> None:
        logger.info("[%s] 启动中 ...", self.name)
        if self.telemetry is None:
            self.telemetry = TelemetryRuntime(self.name)
        self.telemetry.start()
        await self.bus.connect()
        await self._register_to_discovery()
        await self.on_start()
        self.scheduler.start()
        logger.info("[%s] 启动完成", self.name)

    # 停止服务
    async def stop(self) -> None:
        logger.info("[%s] 停止中 ...", self.name)
        self.scheduler.shutdown(wait=True)
        for task in list(self._tasks):
            task.cancel()
        await self.on_stop()
        await self.cfg.nacos.close()
        await self.bus.close()
        if self.telemetry is not None:
            self.telemetry.stop()
        logger.info("[%s] 已停止", self.name)

    # 持续运行服务
    async def serve_forever(self) -> None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        # 发送服务停止信号
        def _signal() -> None:
            stop_event.set()

        try:
            for sig in ("SIGINT", "SIGTERM"):
                loop.add_signal_handler(getattr(__import__("signal"), sig), _signal)
        except NotImplementedError:
            pass

        await stop_event.wait()

    # 注册服务发现信息
    async def _register_to_discovery(self) -> None:
        await self.cfg.nacos.register(self.name, self.cfg.instance_id, self.cfg.instance_addr)
        logger.info("[%s] 已注册到 Nacos (instance=%s)", self.name, self.cfg.instance_id)

    # 启动服务
    @abstractmethod
    async def on_start(self) -> None:
        pass

    # 停止服务
    @abstractmethod
    async def on_stop(self) -> None:
        pass

    # 创建后台任务
    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        task.add_done_callback(self._discard_task)
        return task

    # 清理已结束的后台任务
    def _discard_task(self, task: asyncio.Task) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("[%s] 后台任务失败: %s", self.name, task.exception())

    # 订阅消息
    def subscribe(self, subject: str, handler):
        return self.spawn(self._subscribe_loop(subject, handler))

    # 持续执行订阅循环
    async def _subscribe_loop(self, subject: str, handler):
        sub = await self.bus.subscribe(subject, handler)
        try:
            await asyncio.Event().wait()
        finally:
            sub.unsubscribe()
