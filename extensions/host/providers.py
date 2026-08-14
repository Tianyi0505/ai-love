
from __future__ import annotations

import json

from extensions.host.skill import skill_registry
from extensions.host.tools import ToolDefinition, ToolInvocation, ToolResult


# 提供内置扩展工具
class BuiltinToolProvider:
    provider_id = "builtin"

    # 初始化当前实例
    def __init__(self, config: dict) -> None:
        self._unknown_skill = str(config["messages"]["unknown_skill"])

    # 列出工具定义
    def definitions(self) -> list[ToolDefinition]:
        definitions = []
        for name, cls in skill_registry.all():
            info = cls.info
            definitions.append(
                ToolDefinition(
                    tool_id=name,
                    description=info["description"],
                    input_schema=info["parameters"],
                    provider_id=self.provider_id,
                )
            )
        return definitions

    # 调用工具
    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        if not skill_registry.contains(invocation.tool_id):
            return ToolResult(False, self._unknown_skill, error_code="unknown_skill")
        skill = skill_registry.get(invocation.tool_id)()
        if hasattr(skill, "execute"):
            content = await skill.execute(invocation.arguments)
        else:
            error = await skill._validate(invocation.arguments)
            content = error or str(await skill._do_execute(invocation.arguments))
        return ToolResult(True, str(content))


# 将实体与历史工具转发到拥有数据访问策略的内部服务
class GroundingToolProvider:
    provider_id = "grounding"

    _SUBJECTS = {
        "resolve_people": "identity.resolve-people.request",
        "search_group_history": "history.search-group.request",
        "get_person_context": "memory.person-context.request",
    }

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
                        "limit": {"type": "integer", "minimum": 1},
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
        subject = self._SUBJECTS.get(invocation.tool_id)
        if subject is None:
            return ToolResult(False, "未知实体工具", error_code="unknown_grounding_tool")
        response = await self._bus.request_json(
            subject,
            {
                "context": invocation.context.to_dict(),
                "arguments": invocation.arguments,
            },
            timeout=self._timeout_sec,
        )
        ok = response.get("ok") is not False
        return ToolResult(
            ok,
            json.dumps(response, ensure_ascii=False, default=str),
            data=response,
            error_code="" if ok else "scope_denied",
        )
