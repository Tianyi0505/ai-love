from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolRetryMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.response_output_policy import ResponseOutputPolicy
from agent.conversation.response_plan import ParticipationDecision, ResponsePlan
from shared.contracts.tools import ToolExecutionContext
from shared.global_settings import ObservabilitySettings
from shared.langchain_observability import (
    model_span,
    record_messages_usage,
    record_model_content,
)
from shared.langchain_structured_output import (
    parsed_output,
    structured_output_runnable,
)


class ChatAgent:
    def __init__(
        self,
        model: BaseChatModel,
        model_name: str,
        tools: list[BaseTool],
        output_policy: ResponseOutputPolicy,
        max_requests: int,
        participation_max_requests: int,
        max_tokens: int,
        retry_count: int,
        tool_retry_count: int,
        observability: ObservabilitySettings,
    ) -> None:
        self._model_name = model_name
        self._max_tokens = max_tokens
        self._output_policy = output_policy
        self._observability = observability
        self._plan_model = structured_output_runnable(
            model,
            ResponsePlan,
            min(max_requests, retry_count + 1),
        )
        self._participation_model = structured_output_runnable(
            model,
            ParticipationDecision,
            min(participation_max_requests, retry_count + 1),
        )

        middleware = [ModelCallLimitMiddleware(run_limit=max_requests, exit_behavior="error")]
        if tool_retry_count > 0:
            middleware.append(
                ToolRetryMiddleware(
                    max_retries=tool_retry_count,
                    initial_delay=0,
                    backoff_factor=0,
                    jitter=False,
                )
            )
        self._agent = create_agent(
            model=model,
            tools=tools,
            middleware=middleware,
            response_format=ToolStrategy(
                ResponsePlan,
                handle_errors=retry_count > 0,
            ),
            context_schema=ToolExecutionContext,
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
        messages = [
            SystemMessage(content=system_prompt),
            _human_message(user_prompt, images),
        ]
        with model_span(
            "chat-agent.generate-plan",
            self._model_name,
            self._observability,
            {"max_tokens": self._max_tokens},
        ) as span:
            if allow_tools:
                state = await self._agent.ainvoke(
                    {"messages": messages},
                    context=tool_context or ToolExecutionContext(),
                )
                plan = cast(ResponsePlan, state["structured_response"])
                record_messages_usage(span, state["messages"])
            else:
                result = await self._plan_model.ainvoke(messages)
                plan = parsed_output(result, ResponsePlan)
                record_messages_usage(span, [result["raw"]])
            record_model_content(
                span,
                self._observability,
                input_text=f"{system_prompt}\n\n{user_prompt}",
                output=plan,
            )
        return self._output_policy.validate_plan(plan)

    async def decide_participation(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: Sequence[ImageAttachment] = (),
    ) -> ParticipationDecision:
        messages = [
            SystemMessage(content=system_prompt),
            _human_message(user_prompt, images),
        ]
        with model_span(
            "chat-agent.decide-participation",
            self._model_name,
            self._observability,
            {"max_tokens": self._max_tokens},
        ) as span:
            result = await self._participation_model.ainvoke(messages)
            decision = parsed_output(result, ParticipationDecision)
            record_messages_usage(span, [result["raw"]])
            record_model_content(
                span,
                self._observability,
                input_text=f"{system_prompt}\n\n{user_prompt}",
                output=decision,
            )
        return self._output_policy.validate_participation(decision)


def _human_message(user_prompt: str, images: Sequence[ImageAttachment]) -> HumanMessage:
    if not images:
        return HumanMessage(content=user_prompt)
    content: list[dict] = [{"type": "text", "text": user_prompt}]
    for image in images:
        content.extend(
            [
                {"type": "text", "text": f"\n下图对应消息：{image.attribution}"},
                {"type": "image_url", "image_url": {"url": image.data_url}},
            ]
        )
    return HumanMessage(content=content)
