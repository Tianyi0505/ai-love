
from __future__ import annotations

from extensions.host.tool_gateway import ToolDefinition, ToolInvocation, ToolResult
from shared.contracts.rpc.grounding import (
    ResolvePeopleRequest,
    ResolvePeopleResponse,
    SearchGroupHistoryRequest,
    SearchGroupHistoryResponse,
)
from shared.contracts.rpc.memory import PersonContextRequest, PersonContextResponse


# 将实体与历史工具转发到拥有数据访问策略的内部服务
class GroundingToolProvider:
    provider_id = "grounding"

    def __init__(self, bus, timeout_sec: float) -> None:
        self._bus = bus
        self._timeout_sec = timeout_sec

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                tool_id="resolve_people",
                description="解析当前群聊中一个称呼可能指向的人；作用域由系统固定。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mention": {"type": "string", "description": "待解析的原文称呼"},
                    },
                    "required": ["mention"],
                    "additionalProperties": False,
                },
                provider_id=self.provider_id,
            ),
            ToolDefinition(
                tool_id="search_group_history",
                description="按关键词检索当前群聊近期历史，结果包含消息发送者 person_id。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "简短、可直接匹配的关键词"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                provider_id=self.provider_id,
            ),
            ToolDefinition(
                tool_id="get_person_context",
                description="读取某人在当前场景允许使用的背景事实，不返回原始人物记忆文档。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "person_id": {"type": "string", "description": "已解析的人物实体 ID"},
                    },
                    "required": ["person_id"],
                    "additionalProperties": False,
                },
                provider_id=self.provider_id,
            ),
        ]

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        if invocation.tool_id == "resolve_people":
            response = await self._bus.request_model(
                "identity.resolve-people.request",
                ResolvePeopleRequest(
                    context=invocation.context,
                    mention=str(invocation.arguments["mention"]),
                ),
                ResolvePeopleResponse,
                timeout=self._timeout_sec,
            )
        elif invocation.tool_id == "search_group_history":
            response = await self._bus.request_model(
                "history.search-group.request",
                SearchGroupHistoryRequest(
                    context=invocation.context,
                    query=str(invocation.arguments["query"]),
                    limit=invocation.arguments.get("limit"),
                ),
                SearchGroupHistoryResponse,
                timeout=self._timeout_sec,
            )
        elif invocation.tool_id == "get_person_context":
            response = await self._bus.request_model(
                "memory.person-context.request",
                PersonContextRequest(
                    context=invocation.context,
                    person_id=str(invocation.arguments["person_id"]),
                ),
                PersonContextResponse,
                timeout=self._timeout_sec,
            )
        else:
            raise KeyError(f"未知实体工具: {invocation.tool_id}")
        data = response.model_dump(mode="json")
        return ToolResult(
            True,
            response.model_dump_json(),
            data=data,
        )
