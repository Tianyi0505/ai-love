
from __future__ import annotations

import json

from mcp import Client
from mcp.types import TextContent

from extensions.host.tools import ToolDefinition, ToolInvocation, ToolResult


class MCPToolProvider:
    def __init__(self, provider_id: str, url: str, definitions: list[ToolDefinition]) -> None:
        self.provider_id = provider_id
        self._url = url
        self._definitions = definitions

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

    def definitions(self) -> list[ToolDefinition]:
        return self._definitions

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        try:
            async with Client(self._url) as client:
                result = await client.call_tool(invocation.tool_id, invocation.arguments)
        except Exception as exc:
            return ToolResult(
                False,
                f"MCP 工具调用失败：{exc}",
                error_code="mcp_transport_error",
            )
        texts = [block.text for block in result.content if isinstance(block, TextContent)]
        data = result.structured_content if isinstance(result.structured_content, dict) else {}
        if not data and len(texts) == 1:
            try:
                parsed = json.loads(texts[0])
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                pass
        content = "\n".join(texts) or json.dumps(data, ensure_ascii=False)
        return ToolResult(
            ok=not result.is_error,
            content=content,
            data=data,
            error_code="mcp_tool_error" if result.is_error else "",
        )
