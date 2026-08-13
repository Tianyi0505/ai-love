
from __future__ import annotations

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
