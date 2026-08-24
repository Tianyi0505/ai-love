from __future__ import annotations

from pydantic_ai import RunContext, Tool
from pydantic_ai.toolsets import FunctionToolset

from shared.configuration.global_settings import TimeoutSettings
from shared.contracts.rpc.tools import (
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolListRequest,
    ToolListResponse,
)
from shared.contracts.tools import ToolExecutionContext


async def load_toolset(
    bus,
    ai_id: str,
    timeouts: TimeoutSettings,
    max_retries: int,
) -> FunctionToolset[ToolExecutionContext]:
    response = await bus.request_model(
        "tool.list.request",
        ToolListRequest(ai_id=ai_id),
        ToolListResponse,
        timeout=timeouts.tool_list_sec,
    )
    tools: list[Tool[ToolExecutionContext]] = []
    for info in response.tools:
        name = info.name

        async def execute(
            ctx: RunContext[ToolExecutionContext],
            _tool_id: str = name,
            **arguments,
        ) -> str:
            result = await bus.request_model(
                "tool.execute.request",
                ToolExecuteRequest(
                    ai_id=ai_id,
                    tool_id=_tool_id,
                    arguments=arguments,
                    execution_context=ctx.deps,
                ),
                ToolExecuteResponse,
                timeout=timeouts.tool_execute_sec,
            )
            return result.content

        tools.append(
            Tool.from_schema(
                execute,
                name=name,
                description=info.description,
                json_schema=info.parameters,
                takes_ctx=True,
            )
        )
    return FunctionToolset(tools, max_retries=max_retries)
