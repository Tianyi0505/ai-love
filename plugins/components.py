from __future__ import annotations

import asyncio
import importlib
from contextlib import AsyncExitStack

from plugin_runtime import Plugin
from plugin_runtime.adapters import ScopedASGI, ScopedBus, ScopedScheduler, scoped_config


def load_symbol(reference: str):
    module, symbol = reference.split(":")
    return getattr(importlib.import_module(module), symbol)


class ServicePlugin(Plugin):
    """Adapt an existing domain service while the host owns all infrastructure."""

    async def initialize(self, context) -> None:
        await super().initialize(context)
        config = scoped_config(await context.ports["configuration"](), context.resources)
        service_type = load_symbol(context.config["implementation"])
        self.service = service_type(config, ScopedBus(context.ports["bus"], context.resources))
        self.service.scheduler = ScopedScheduler(context.ports["scheduler"], context.resources)
        self.service.spawn = context.resources.spawn
        self.service.plugin_context = context

    async def start(self) -> None:
        await self.service.on_start()
        for capability in self.context.manifest.provides:
            self.context.provide(capability, self.service)

    async def stop(self) -> None:
        if hasattr(self, "service"):
            await self.service.on_stop()


class AgentEnvironmentPlugin(Plugin):
    async def initialize(self, context) -> None:
        await super().initialize(context)
        self._cleanup = AsyncExitStack()
        from redis.asyncio import Redis

        from shared.account_ownership_repository import AccountOwnershipRepository
        from shared.ai_profile_repository import AIProfileRepository
        from shared.connection_settings import RedisConnectionSettings
        from shared.database import Database
        from shared.nacos_agent_definition_store import NacosAgentDefinitionStore

        self.config = await context.ports["configuration"]()
        settings = RedisConnectionSettings()
        self.redis = Redis.from_url(settings.url, password=settings.password, decode_responses=True)
        self._cleanup.push_async_callback(self.redis.aclose)
        self.database = Database()
        self._cleanup.push_async_callback(self.database.close)
        await self.redis.ping()
        await self.database.connect()
        self.definitions = NacosAgentDefinitionStore(self.config.nacos)
        self.profiles = AIProfileRepository(self.database)
        self.accounts = AccountOwnershipRepository(self.database)

    async def start(self) -> None:
        self.context.provide("agent.environment", self)

    async def dispose(self) -> None:
        await self._cleanup.aclose()


class MemoryPlugin(Plugin):
    async def initialize(self, context) -> None:
        await super().initialize(context)
        from memory.memory_module import MemoryModule

        environment = context.require("agent.environment")
        self.module = MemoryModule(
            nacos=scoped_config(environment.config, context.resources).nacos,
            bus=ScopedBus(context.ports["bus"], context.resources),
            scheduler=ScopedScheduler(context.ports["scheduler"], context.resources),
            database=environment.database,
            definitions=environment.definitions,
            model_factory=context.require("model.factory"),
        )

    async def start(self) -> None:
        await self.module.start()
        self.context.provide("memory.runtime", self.module)

    async def stop(self) -> None:
        if hasattr(self, "module"):
            await self.module.stop()


class ModulePlugin(Plugin):
    async def initialize(self, context) -> None:
        await super().initialize(context)
        module_type = load_symbol(context.config["implementation"])
        args = [ScopedBus(context.ports["bus"], context.resources)]
        if context.config.get("settings"):
            config = await context.ports["configuration"]()
            args.append(await config.section(load_symbol(context.config["settings"])))
        self.module = module_type(*args)

    async def start(self) -> None:
        await self.module.start()
        for capability in self.context.manifest.provides:
            self.context.provide(capability, self.module)

    async def stop(self) -> None:
        if hasattr(self, "module"):
            await self.module.stop()


class SpeechServerPlugin(ServicePlugin):
    async def start(self) -> None:
        await super().start()
        self.service._http.config.app = ScopedASGI(self.service._http.config.app, self.context.resources)
        self._server_task = self.context.resources.spawn(self.service.serve())
        # Do not report active until Uvicorn has bound the listening socket.
        while not self.service._http.started:
            if self._server_task.done():
                await self._server_task
                raise RuntimeError("语音 HTTP 服务未能启动")
            await asyncio.sleep(0.02)

    async def stop(self) -> None:
        if hasattr(self, "_server_task"):
            self.service._http.should_exit = True
            await self._server_task
        await super().stop()
