from __future__ import annotations

import logging

from agentscope.message import TextBlock, ToolResultState
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, ToolBase, ToolChunk
from nats.errors import NoRespondersError

from shared.contracts.rpc.tools import (
    ToolDescriptor,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolListRequest,
    ToolListResponse,
)
from shared.contracts.tools import ToolExecutionContext
from shared.global_settings import TimeoutSettings
from shared.model_observability import tool_span
from shared.structured_output_tools import OUTPUT_TOOL_NAMES

logger = logging.getLogger("ailove.ai-agent.tools")


async def load_toolset(
    bus,
    ai_id: str,
    timeouts: TimeoutSettings,
) -> list[ToolBase]:
    try:
        response = await bus.request_model(
            "tool.list.request",
            ToolListRequest(ai_id=ai_id),
            ToolListResponse,
            timeout=timeouts.tool_list_sec,
        )
    except NoRespondersError:
        logger.warning("[tools] 扩展服务无响应，先以无工具模式启动: ai=%s", ai_id)
        return []
    return [_build_tool(bus, ai_id, timeouts, info) for info in response.tools if info.name not in OUTPUT_TOOL_NAMES]


def _build_tool(
    bus,
    ai_id: str,
    timeouts: TimeoutSettings,
    info: ToolDescriptor,
) -> ToolBase:
    tool_id = info.name

    async def execute(
        _agent_state: AgentState,
        **arguments,
    ) -> ToolChunk:
        with tool_span(tool_id):
            result = await bus.request_model(
                "tool.execute.request",
                ToolExecuteRequest(
                    ai_id=ai_id,
                    tool_id=tool_id,
                    arguments=arguments,
                    execution_context=ToolExecutionContext.model_validate(_agent_state.middle_context["execution_context"]),
                ),
                ToolExecuteResponse,
                timeout=timeouts.tool_execute_sec,
            )
        return ToolChunk(content=[TextBlock(text=result.content)], state=ToolResultState.SUCCESS)

    return FunctionTool(
        func=execute,
        name=info.name,
        description=info.description,
        input_schema=info.parameters,
        is_state_injected=True,
        is_concurrency_safe=False,
        permission=PermissionDecision(behavior=PermissionBehavior.ALLOW, message="授权由 Extension Host 校验"),
    )
