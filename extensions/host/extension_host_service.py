
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from extensions.host.grounding_tool_provider import GroundingToolProvider
from extensions.host.mcp_tool_provider import MCPToolProvider
from extensions.host.tool_gateway import PermissionLevel, ToolGateway, ToolGrant, ToolInvocation
from shared.base_service import BaseService
from shared.contracts.rpc.tools import (
    ToolDescriptor,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolListRequest,
    ToolListResponse,
)
from shared.contracts.tools import ToolExecutionContext
from shared.nacos_agent_definition_store import NacosAgentDefinitionStore
from shared.service_config import ServiceConfig
from shared.service_settings import ExtensionHostSettings

logger = logging.getLogger("ailove.extension-host")


# 托管并调用扩展工具
class ExtensionHostService(BaseService):
    name = "extension-host"

    # 启动服务
    async def on_start(self) -> None:
        self._service_config = await self.cfg.section(ExtensionHostSettings)
        self._definitions = NacosAgentDefinitionStore(self.cfg.nacos)
        self._fingerprint: str | None = None
        self._mcp_providers: list[MCPToolProvider] = []
        self._reload_lock = asyncio.Lock()
        await self._reload_bindings()
        await self.bus.reply_model(
            "tool.list.request", ToolListRequest, ToolListResponse, self._on_list
        )
        await self.bus.reply_model(
            "tool.execute.request", ToolExecuteRequest, ToolExecuteResponse, self._on_execute
        )
        self.scheduler.add_job(
            self._reload_bindings,
            "interval",
            seconds=self._service_config.binding_poll_interval_sec,
            next_run_time=datetime.now(timezone.utc),
        )

    # 停止服务
    async def on_stop(self) -> None:
        pass

    # 重新加载账号绑定
    async def _reload_bindings(self) -> None:
        async with self._reload_lock:
            await self._load_bindings()

    async def _load_bindings(self) -> None:
        definitions = await self._definitions.list_active()
        await self._discover_mcp()
        mcp_fingerprint = json.dumps(
            [asdict(item) for provider in self._mcp_providers for item in provider.definitions()], sort_keys=True,
        )
        fingerprint = "|".join(f"{item.ai_id}:{item.fingerprint}" for item in definitions) + mcp_fingerprint
        if fingerprint == self._fingerprint:
            return
        providers = [
            GroundingToolProvider(
                self.bus,
                self._service_config.grounding_timeout_sec,
            ),
            *self._mcp_providers,
        ]
        bindings: dict[tuple[str, str], ToolGrant] = {}
        for definition in definitions:
            for item in definition.extensions:
                if not item.enabled:
                    continue
                permission = PermissionLevel(item.permission)
                bindings[(definition.ai_id, item.tool_id)] = ToolGrant(
                    permission,
                    item.config,
                )
        self._gateway = ToolGateway(providers, bindings)
        self._fingerprint = fingerprint

    # 发现MCP工具
    async def _discover_mcp(self) -> None:
        mcp_url = self._service_config.mcp_url
        try:
            async with asyncio.timeout(self._service_config.mcp_discovery_timeout_sec):
                provider = await MCPToolProvider.discover("mcp.ailove", mcp_url)
        except Exception as exc:
            # A stopped MCP plugin withdraws its tools without taking local tools offline.
            self._mcp_providers = []
            logger.warning("[extension-host] MCP 暂不可用，撤销远程工具: %s", type(exc).__name__)
        else:
            self._mcp_providers = [provider]

    # 处理列表请求
    async def _on_list(self, request: ToolListRequest) -> ToolListResponse:
        await self._reload_bindings()
        tools = [
            ToolDescriptor(
                name=item.tool_id,
                description=item.description,
                parameters=item.input_schema,
                provider=item.provider_id,
            )
            for item in self._gateway.list_for_ai(request.ai_id)
        ]
        return ToolListResponse(tools=tools)

    # 处理工具执行请求
    async def _on_execute(self, request: ToolExecuteRequest) -> ToolExecuteResponse:
        context = request.execution_context
        # 忽略上下文中的 ai_id
        context = ToolExecutionContext(
            run_id=context.run_id,
            ai_id=request.ai_id,
            account_id=context.account_id,
            conversation_id=context.conversation_id,
            platform=context.platform,
            chat_type=context.chat_type,
            chat_id=context.chat_id,
            sender_person_id=context.sender_person_id,
        )
        result = await self._gateway.invoke(
            ToolInvocation(
                tool_id=request.tool_id,
                ai_id=request.ai_id,
                arguments=request.arguments,
                context=context,
                reason=request.reason,
            )
        )
        if not result.ok:
            raise PermissionError(result.error_code)
        return ToolExecuteResponse(content=result.content, data=result.data)


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        service = ExtensionHostService(await ServiceConfig.load("extension-host"))
        await service.start()
        await service.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
