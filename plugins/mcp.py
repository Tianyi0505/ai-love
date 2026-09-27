from __future__ import annotations

import asyncio
import functools
import inspect
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import get_type_hints

from plugin_runtime import Plugin
from plugin_runtime.adapters import ScopedASGI

from .components import load_symbol


class MCPServerPlugin(Plugin):
    async def initialize(self, context) -> None:
        await super().initialize(context)
        from mcp.server import MCPServer

        self.resources = SimpleNamespace(weather=None, web_search=None)

        @asynccontextmanager
        async def lifespan(_server):
            yield self.resources

        self.server = MCPServer("ailove", instructions="AI-Love 动态工具插件", lifespan=lifespan)

    async def start(self) -> None:
        import uvicorn

        config = self.context.config
        app = self.server.streamable_http_app(
            json_response=True,
            stateless_http=True,
            host=config.get("bind", "0.0.0.0"),
        )
        app = ScopedASGI(app, self.context.resources)
        self.http = uvicorn.Server(
            uvicorn.Config(app, host=config.get("bind", "0.0.0.0"), port=config.get("port", 8011), log_level="warning")
        )
        self.task = self.context.resources.spawn(self.http.serve())
        while not self.http.started:
            if self.task.done():
                await self.task
                raise RuntimeError("MCP HTTP 服务未能启动")
            await asyncio.sleep(0.02)
        self.context.provide("mcp.server", self)

    async def stop(self) -> None:
        if hasattr(self, "task"):
            self.http.should_exit = True
            await self.task


class ToolRegistrar:
    """Preserve MCP function schemas while scoping every real tool invocation."""

    def __init__(self, server, scope) -> None:
        self.server = server
        self.scope = scope

    def tool(self, **options):
        def decorate(function):
            guarded = functools.wraps(function)(self.scope.guard(function))
            guarded.__annotations__ = get_type_hints(function, include_extras=True)
            guarded.__signature__ = inspect.signature(function, eval_str=True)
            self.server.tool(**options)(guarded)
            self.scope.on_quiesce(lambda: self.server.remove_tool(options["name"]))
            return guarded

        return decorate


class MCPToolPlugin(Plugin):
    async def start(self) -> None:
        owner = self.context.require("mcp.server")
        config = self.context.config
        if config.get("resource_factory"):
            resource = await load_symbol(config["resource_factory"])(self.context)
            setattr(owner.resources, config["resource_name"], resource)
            self.context.resources.defer(lambda: setattr(owner.resources, config["resource_name"], None))
        register = load_symbol(config["registration"])
        register(ToolRegistrar(owner.server, self.context.resources))
        for capability in self.context.manifest.provides:
            self.context.provide(capability, self)


async def weather_resource(context):
    import httpx

    from extensions.mcp.weather.qweather_client import QWeatherClient
    from extensions.mcp.weather.weather_tool import CLIENT_SETTINGS
    from shared.connection_settings import QWeatherConnectionSettings

    config = QWeatherConnectionSettings()
    client = httpx.AsyncClient(
        timeout=CLIENT_SETTINGS.request_timeout_sec,
        follow_redirects=False,
        headers={"X-QW-Api-Key": config.api_key, "Accept-Encoding": CLIENT_SETTINGS.accept_encoding},
    )
    context.resources.defer(client.aclose)
    return QWeatherClient(
        client,
        host=config.api_host,
        location_result_limit=CLIENT_SETTINGS.location_result_limit,
        coordinate_precision=CLIENT_SETTINGS.coordinate_precision,
        percent_multiplier=CLIENT_SETTINGS.percent_multiplier,
    )


async def search_resource(context):
    import httpx

    from extensions.mcp.web_search.web_search_client import WebSearchClient
    from extensions.mcp.web_search.web_search_tool import SEARCH_SETTINGS

    client = httpx.AsyncClient(
        timeout=SEARCH_SETTINGS.request_timeout_sec,
        follow_redirects=True,
        headers={"User-Agent": SEARCH_SETTINGS.user_agent},
    )
    context.resources.defer(client.aclose)
    return WebSearchClient(client, endpoint=SEARCH_SETTINGS.endpoint, result_limit=SEARCH_SETTINGS.result_limit)
