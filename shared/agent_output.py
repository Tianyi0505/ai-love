from __future__ import annotations

from agentscope.agent import Agent, InjectionConfig, ReActConfig
from agentscope.message import Base64Source, DataBlock, Msg
from agentscope.model import ChatModelBase
from agentscope.state import AgentState
from agentscope.tool import Toolkit
from pydantic import BaseModel

from shared.contracts.tools import ToolExecutionContext
from shared.mcp_output_client import MCPOutputClient
from shared.snowflake_id_generator import snowflake_ids


def image_block(data_url: str) -> DataBlock:
    header, data = data_url.split(",", 1)
    return DataBlock(source=Base64Source(media_type=header[5:].split(";")[0], data=data))


class StructuredOutput:
    """Use AgentScope's bounded ReAct and schema validation before the authorized MCP submission."""

    def __init__(
        self,
        model: ChatModelBase,
        output_type: type[BaseModel],
        max_requests: int,
        output_client: MCPOutputClient,
    ) -> None:
        self._model = model
        self._output_type = output_type
        self._max_requests = max_requests
        self._output_client = output_client

    async def generate(
        self,
        messages: list[Msg],
        *,
        toolkit: Toolkit | None = None,
        context: ToolExecutionContext | None = None,
    ) -> dict:
        context = context or ToolExecutionContext()
        system = "\n\n".join(message.get_text_content() or "" for message in messages if message.role == "system")
        agent = Agent(
            name="ai-love",
            system_prompt=system,
            model=self._model,
            toolkit=toolkit,
            state=AgentState(
                session_id=str(snowflake_ids().next_id()),
                middle_context={"execution_context": context.model_dump(mode="json")},
            ),
            react_config=ReActConfig(
                max_iters=max(0, self._max_requests - 1),
                structured_output_grace_iters=1,
                interruption_raise_cancelled_error=True,
            ),
            injection_config=InjectionConfig(inject_runtime_state=False),
        )
        raw = await agent.reply(
            [message for message in messages if message.role != "system"],
            structured_schema=self._output_type,
        )
        if raw.structured_output is None:
            raise ValueError(f"AgentScope 未在请求限额内生成 {self._output_type.__name__}")
        output = await self._output_client.submit(
            self._output_type, {"result": raw.structured_output}, context,
        )
        return {"raw": raw, "parsed": output}
