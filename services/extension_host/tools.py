
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class PermissionLevel(str, Enum):
    ALLOW = "allow"
    CONDITIONAL = "conditional"
    CONFIRM = "confirm"
    DENY = "deny"


PERMANENTLY_FORBIDDEN_OPERATIONS = frozenset(
    {
        "social.delete_message",
        "social.modify_profile",
        "credential.read",
        "credential.export",
    }
)


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    description: str
    input_schema: dict[str, Any]
    provider_id: str
    operation: str = "read"
    side_effect: str = "none"


@dataclass(frozen=True)
class ToolInvocation:
    tool_id: str
    ai_id: str
    arguments: dict[str, Any]
    account_id: str = ""
    conversation_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    requires_confirmation: bool = False


@dataclass(frozen=True)
class ToolGrant:
    permission: PermissionLevel
    config: dict[str, Any] = field(default_factory=dict)


class ToolProvider(Protocol):
    provider_id: str

    def definitions(self) -> list[ToolDefinition]: ...
    async def invoke(self, invocation: ToolInvocation) -> ToolResult: ...


class ToolGateway:
    def __init__(self) -> None:
        self._providers: dict[str, ToolProvider] = {}
        self._definitions: dict[str, ToolDefinition] = {}
        self._bindings: dict[tuple[str, str], ToolGrant] = {}

    def register_provider(self, provider: ToolProvider) -> None:
        self._providers[provider.provider_id] = provider
        for definition in provider.definitions():
            if definition.tool_id in self._definitions:
                raise ValueError(f"重复工具 ID: {definition.tool_id}")
            self._definitions[definition.tool_id] = definition

    def bind(self, ai_id: str, tool_id: str, grant: ToolGrant) -> None:
        self._bindings[(ai_id, tool_id)] = grant

    def list_for_ai(self, ai_id: str) -> list[ToolDefinition]:
        return [
            definition
            for tool_id, definition in sorted(self._definitions.items())
            if self._is_exposed(ai_id, tool_id, definition)
        ]

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        definition = self._definitions.get(invocation.tool_id)
        if definition is None:
            return ToolResult(False, "未知工具", error_code="unknown_tool")
        grant = self._bindings.get((invocation.ai_id, invocation.tool_id))
        denied = self._authorize(definition, grant)
        if denied is not None:
            return denied
        provider = self._providers[definition.provider_id]
        return await provider.invoke(invocation)

    def _is_exposed(self, ai_id: str, tool_id: str, definition: ToolDefinition) -> bool:
        if definition.operation in PERMANENTLY_FORBIDDEN_OPERATIONS:
            return False
        grant = self._bindings.get((ai_id, tool_id))
        return grant is not None and grant.permission in (PermissionLevel.ALLOW, PermissionLevel.CONDITIONAL)

    @staticmethod
    def _authorize(definition: ToolDefinition, grant: ToolGrant | None) -> ToolResult | None:
        if definition.operation in PERMANENTLY_FORBIDDEN_OPERATIONS:
            return ToolResult(False, "该操作被系统永久禁止", error_code="permanently_forbidden")
        if grant is None or grant.permission == PermissionLevel.DENY:
            return ToolResult(False, "AI 未获此工具授权", error_code="not_granted")
        if grant.permission == PermissionLevel.CONFIRM:
            return ToolResult(False, "需要主人确认", error_code="confirmation_required", requires_confirmation=True)
        return None
