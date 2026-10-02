from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from shared.contracts.rpc.tools import ToolExecuteRequest, ToolExecuteResponse
from shared.contracts.tools import ToolExecutionContext
from shared.model_observability import tool_span
from shared.structured_output_tools import output_tool

OutputT = TypeVar("OutputT", bound=BaseModel)


class MCPOutputClient:
    def __init__(self, bus, ai_id: str, timeout_sec: float) -> None:
        self._bus = bus
        self._ai_id = ai_id
        self._timeout_sec = timeout_sec

    async def submit(
        self,
        output_type: type[OutputT],
        arguments: dict,
        context: ToolExecutionContext | None = None,
    ) -> OutputT:
        spec = output_tool(output_type)
        validated = spec.arguments_type.model_validate(arguments)
        with tool_span(spec.name):
            response = await self._bus.request_model(
                "tool.execute.request",
                ToolExecuteRequest(
                    ai_id=self._ai_id,
                    tool_id=spec.name,
                    arguments=validated.model_dump(mode="json"),
                    execution_context=context or ToolExecutionContext(),
                ),
                ToolExecuteResponse,
                timeout=self._timeout_sec,
            )
        return output_type.model_validate(response.data)
