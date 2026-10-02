from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from agentscope.message import SystemMsg, TextBlock, UserMsg
from agentscope.model import ChatModelBase
from agentscope.tool import ToolBase, Toolkit

from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.response_output_policy import ResponseOutputPolicy
from agent.conversation.response_plan import ParticipationDecision, ResponsePlan
from shared.agent_output import StructuredOutput, image_block
from shared.contracts.tools import ToolExecutionContext
from shared.global_settings import ObservabilitySettings
from shared.mcp_output_client import MCPOutputClient
from shared.model_observability import model_span, record_messages_usage, record_model_content


class ChatAgent:
    def __init__(
        self,
        model: ChatModelBase,
        model_name: str,
        tools: list[ToolBase],
        output_policy: ResponseOutputPolicy,
        max_requests: int,
        participation_max_requests: int,
        max_tokens: int,
        retry_count: int,
        observability: ObservabilitySettings,
        output_client: MCPOutputClient,
        tool_loader: Callable[[], Awaitable[list[ToolBase]]] | None = None,
    ) -> None:
        self._model_name = model_name
        self._max_tokens = max_tokens
        self._output_policy = output_policy
        self._observability = observability
        self._tool_loader = tool_loader
        self._tools = tools
        self._plan_model = StructuredOutput(model, ResponsePlan, max_requests, output_client)
        self._direct_model = StructuredOutput(model, ResponsePlan, min(max_requests, retry_count + 1), output_client)
        self._participation_model = StructuredOutput(
            model, ParticipationDecision, min(participation_max_requests, retry_count + 1), output_client,
        )

    async def generate_plan(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_context: ToolExecutionContext | None = None,
        allow_tools: bool = True,
        images: Sequence[ImageAttachment] = (),
    ) -> ResponsePlan:
        tools = (await self._tool_loader() if self._tool_loader else self._tools) if allow_tools else []
        with model_span(
            "chat-agent.generate-plan", self._model_name, self._observability, {"max_tokens": self._max_tokens},
        ) as span:
            result = await (self._plan_model if allow_tools else self._direct_model).generate(
                [SystemMsg("system", system_prompt), _human_message(user_prompt, images)],
                toolkit=Toolkit(tools=tools), context=tool_context,
            )
            plan = self._output_policy.validate_plan(result["parsed"])
            record_messages_usage(span, [result["raw"]])
            record_model_content(
                span, self._observability, input_text=f"{system_prompt}\n\n{user_prompt}", output=plan,
            )
        return plan

    async def decide_participation(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: Sequence[ImageAttachment] = (),
    ) -> ParticipationDecision:
        with model_span(
            "chat-agent.decide-participation", self._model_name, self._observability, {"max_tokens": self._max_tokens},
        ) as span:
            result = await self._participation_model.generate(
                [SystemMsg("system", system_prompt), _human_message(user_prompt, images)],
            )
            decision = self._output_policy.validate_participation(result["parsed"])
            record_messages_usage(span, [result["raw"]])
            record_model_content(
                span, self._observability, input_text=f"{system_prompt}\n\n{user_prompt}", output=decision,
            )
        return decision


def _human_message(user_prompt: str, images: Sequence[ImageAttachment]):
    content = [TextBlock(text=user_prompt)]
    for image in images:
        content.extend([
            TextBlock(text=image.attribution if image.is_group else f"\n下图对应消息：{image.attribution}"),
            image_block(image.data_url),
        ])
    return UserMsg("user", content)
