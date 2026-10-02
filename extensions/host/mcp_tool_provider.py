
from __future__ import annotations

import json

from mcp.types import TextContent

from extensions.host.tool_gateway import ToolDefinition, ToolInvocation, ToolResult
from shared.mcp_session import mcp_session


# 通过MCP提供扩展工具
class MCPToolProvider:
    # 初始化当前实例
    def __init__(self, provider_id: str, url: str, definitions: list[ToolDefinition]) -> None:
        self.provider_id = provider_id
        self._url = url
        self._definitions = definitions

    # 发现可用工具
    @classmethod
    async def discover(cls, provider_id: str, url: str) -> "MCPToolProvider":
        async with mcp_session(url) as client:
            result = await client.list_tools()
        definitions = [
            ToolDefinition(
                tool_id=tool.name,
                description=tool.description or tool.title or tool.name,
                input_schema=dict(tool.inputSchema),
                provider_id=provider_id,
                operation="network.read",
            )
            for tool in result.tools
        ]
        return cls(provider_id, url, definitions)

    # 列出工具定义
    def definitions(self) -> list[ToolDefinition]:
        return self._definitions

    # 调用工具
    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        async with mcp_session(self._url) as client:
            result = await client.call_tool(invocation.tool_id, invocation.arguments)
        texts = [block.text for block in result.content if isinstance(block, TextContent)]
        data = result.structuredContent if isinstance(result.structuredContent, dict) else {}
        content = "\n".join(texts) or json.dumps(data, ensure_ascii=False)
        return ToolResult(
            ok=not result.isError,
            content=content,
            data=data,
            error_code="mcp_tool_error" if result.isError else "",
        )
