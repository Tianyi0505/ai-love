
from __future__ import annotations

import json

from mcp import Client
from mcp.types import TextContent

from extensions.host.tool_gateway import ToolDefinition, ToolInvocation, ToolResult


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
        async with Client(url) as client:
            result = await client.list_tools()
        definitions = [
            ToolDefinition(
                tool_id=tool.name,
                description=tool.description or tool.title or tool.name,
                input_schema=dict(tool.input_schema),
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
        async with Client(self._url) as client:
            result = await client.call_tool(invocation.tool_id, invocation.arguments)
        texts = [block.text for block in result.content if isinstance(block, TextContent)]
        data = result.structured_content if isinstance(result.structured_content, dict) else {}
        content = "\n".join(texts) or json.dumps(data, ensure_ascii=False)
        return ToolResult(
            ok=not result.is_error,
            content=content,
            data=data,
            error_code="mcp_tool_error" if result.is_error else "",
        )
