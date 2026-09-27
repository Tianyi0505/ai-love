from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .catalog import PluginCatalog
from .control import PluginControlServer
from .manager import PluginManager
from .store import PluginStore

logger = logging.getLogger("ailove.plugin-host")


class HostFileLock:
    """Prevent two local hosts from consuming the same role and control journal."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise RuntimeError("该插件宿主已在运行，不能重复启动同一控制库") from None

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None


class PluginHost:
    def __init__(self, role: str, *, bus, roots: list[Path], state_directory: Path, configuration=None) -> None:
        self.role = role
        self.bus = bus
        self._configuration_factory = configuration
        self._config = None
        self._config_lock = asyncio.Lock()
        self.scheduler = AsyncIOScheduler()
        self._file_lock = HostFileLock(state_directory / f"{role}.lock")
        self._state_path = state_directory / f"{role}.sqlite3"
        self._roots = roots
        self.manager = None
        self.control = None
        self._closed = False

    async def configuration(self):
        async with self._config_lock:
            if self._config is None:
                if self._configuration_factory:
                    self._config = await self._configuration_factory()
                else:
                    from shared.service_config import ServiceConfig

                    self._config = await ServiceConfig.load(self.role)
            return self._config

    async def start(self) -> None:
        self._file_lock.acquire()
        try:
            async with asyncio.timeout(10):
                await self.bus.connect()
            self.manager = PluginManager(
                PluginCatalog(self._roots, self.role),
                PluginStore(self._state_path),
                ports={"bus": self.bus, "scheduler": self.scheduler, "configuration": self.configuration},
            )
            self.control = PluginControlServer(self.manager, self.bus)
            # The control plane stays available even if every business plugin fails.
            await self.control.start()
            self.scheduler.start(paused=True)
            await self.manager.start()
            self.scheduler.resume()
            logger.info("[%s] 插件宿主已就绪", self.role)
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.control:
                await self.control.close()
            if self.manager:
                await self.manager.close()
        finally:
            try:
                if self.scheduler.running:
                    self.scheduler.shutdown(wait=True)
                if self._config:
                    await self._config.config_provider.close()
                await self.bus.close()
            finally:
                if self.manager:
                    self.manager.store.close()
                self._file_lock.close()
