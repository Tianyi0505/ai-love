from __future__ import annotations

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool

from shared.configuration.global_settings import TimeoutSettings
from shared.contracts.rpc.tools import (
    ToolDescriptor,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolListRequest,
    ToolListResponse,
)
from shared.contracts.tools import ToolExecutionContext
from shared.infrastructure.langchain_observability import tool_span


async def load_toolset(
    bus,
    ai_id: str,
    timeouts: TimeoutSettings,
) -> list[BaseTool]:
    response = await bus.request_model(
        "tool.list.request",
        ToolListRequest(ai_id=ai_id),
        ToolListResponse,
        timeout=timeouts.tool_list_sec,
    )
    return [_build_tool(bus, ai_id, timeouts, info) for info in response.tools]


def _build_tool(
    bus,
    ai_id: str,
    timeouts: TimeoutSettings,
    info: ToolDescriptor,
) -> BaseTool:
    tool_id = info.name

    async def execute(
        runtime: ToolRuntime[ToolExecutionContext],
        **arguments,
    ) -> str:
        with tool_span(tool_id):
            result = await bus.request_model(
                "tool.execute.request",
                ToolExecuteRequest(
                    ai_id=ai_id,
                    tool_id=tool_id,
                    arguments=arguments,
                    execution_context=runtime.context,
                ),
                ToolExecuteResponse,
                timeout=timeouts.tool_execute_sec,
            )
        return result.content

    return StructuredTool.from_function(
        coroutine=execute,
        name=info.name,
        description=info.description,
        args_schema=info.parameters,
        infer_schema=False,
    )
