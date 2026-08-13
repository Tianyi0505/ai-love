
from __future__ import annotations

import asyncio
import json
import logging
import os

from services.extension_host.tools import PermissionLevel, ToolGateway, ToolGrant, ToolInvocation
from shared.infrastructure.agent_store import NacosAgentDefinitionStore
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.service import BaseService
from services.extension_host.providers import BuiltinToolProvider
from services.extension_host.mcp_provider import MCPToolProvider

logger = logging.getLogger("ailove.extension-host")


class ExtensionHostService(BaseService):
    name = "extension-host"

    async def on_start(self) -> None:
        self._definitions = NacosAgentDefinitionStore(self.cfg.nacos)
        self._fingerprint = ""
        self._mcp_providers: list[MCPToolProvider] = []
        await self._reload_bindings()
        await self.bus.reply("tool.list.request", self._on_list)
        await self.bus.reply("tool.execute.request", self._on_execute)
        self.spawn(self._binding_loop())

    async def on_stop(self) -> None:
        pass

    async def _reload_bindings(self) -> None:
        definitions = await self._definitions.list_active()
        await self._discover_mcp()
        mcp_fingerprint = "|".join(
            f"{provider.provider_id}:{','.join(item.tool_id for item in provider.definitions())}"
            for provider in self._mcp_providers
        )
        fingerprint = "|".join(f"{item.ai_id}:{item.fingerprint}" for item in definitions) + mcp_fingerprint
        if fingerprint == self._fingerprint:
            return
        gateway = ToolGateway()
        gateway.register_provider(BuiltinToolProvider())
        for provider in self._mcp_providers:
            gateway.register_provider(provider)
        for definition in definitions:
            for item in definition.extensions:
                if not item.get("enabled", True):
                    continue
                permission = PermissionLevel(str(item.get("permission", "deny")))
                gateway.bind(
                    definition.ai_id,
                    str(item.get("tool_id", "")),
                    ToolGrant(permission, dict(item.get("config", {}))),
                )
        self._gateway = gateway
        self._fingerprint = fingerprint

    async def _discover_mcp(self) -> None:
        if self._mcp_providers:
            return
        weather_url = os.environ.get("MCP_WEATHER_URL", "").strip()
        if not weather_url:
            return
        try:
            self._mcp_providers = [await MCPToolProvider.discover("mcp.qweather", weather_url)]
            logger.info("[extension-host] MCP 已连接: qweather")
        except Exception as exc:
            logger.warning("[extension-host] qweather MCP 暂不可用: %s", exc)

    async def _binding_loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            try:
                await self._reload_bindings()
            except Exception:
                pass

    async def _on_list(self, payload: bytes) -> bytes:
        request = json.loads(payload)
        tools = [
            {
                "name": item.tool_id,
                "description": item.description,
                "parameters": item.input_schema,
            }
            for item in self._gateway.list_for_ai(str(request.get("ai_id", "")))
        ]
        return json.dumps({"tools": tools}, ensure_ascii=False).encode()

    async def _on_execute(self, payload: bytes) -> bytes:
        request = json.loads(payload)
        result = await self._gateway.invoke(
            ToolInvocation(
                tool_id=str(request.get("tool_id", "")),
                ai_id=str(request.get("ai_id", "")),
                account_id=str(request.get("account_id", "")),
                conversation_id=str(request.get("conversation_id", "")),
                arguments=dict(request.get("arguments", {})),
                reason=str(request.get("reason", "")),
            )
        )
        return json.dumps(
            {
                "ok": result.ok,
                "content": result.content,
                "data": result.data,
                "error_code": result.error_code,
                "requires_confirmation": result.requires_confirmation,
            },
            ensure_ascii=False,
        ).encode()


def main() -> None:
    async def run() -> None:
        service = ExtensionHostService(await ServiceConfig.load("extension-host"))
        await service.start()
        await service.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
