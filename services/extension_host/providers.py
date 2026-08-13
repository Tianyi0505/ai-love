
from __future__ import annotations

from services.extension_host.skill import skill_registry
from services.extension_host.tools import ToolDefinition, ToolInvocation, ToolResult
from services.extension_host.web_search import WebSearchTool


class BuiltinToolProvider:
    provider_id = "builtin"

    def __init__(self, config: dict) -> None:
        self._web_search = WebSearchTool(config["web_search"])
        self._unknown_skill = str(config["messages"]["unknown_skill"])

    def definitions(self) -> list[ToolDefinition]:
        definitions = [
            ToolDefinition(
                tool_id="web_search",
                description=self._web_search.info["description"],
                input_schema=self._web_search.info["parameters"],
                provider_id=self.provider_id,
                operation="network.read",
            )
        ]
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

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        if invocation.tool_id == "web_search":
            content = await self._web_search.execute(invocation.arguments)
            return ToolResult(True, content)
        if not skill_registry.contains(invocation.tool_id):
            return ToolResult(False, self._unknown_skill, error_code="unknown_skill")
        skill = skill_registry.get(invocation.tool_id)()
        if hasattr(skill, "execute"):
            content = await skill.execute(invocation.arguments)
        else:
            error = await skill._validate(invocation.arguments)
            content = error or str(await skill._do_execute(invocation.arguments))
        return ToolResult(True, str(content))
