from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolRetryMiddleware
from langchain.tools import ToolRuntime
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

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
from shared.mcp_output_client import MCPOutputClient
from shared.structured_output_tools import output_tool


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
        output_client: MCPOutputClient,
        tool_loader: Callable[[], Awaitable[list[BaseTool]]] | None = None,
    ) -> None:
        self._model_name = model_name
        self._max_tokens = max_tokens
        self._output_policy = output_policy
        self._observability = observability
        self._tool_loader = tool_loader
        self._plan_model = structured_output_runnable(
            model,
            ResponsePlan,
            min(max_requests, retry_count + 1),
            output_client,
        )
        self._participation_model = structured_output_runnable(
            model,
            ParticipationDecision,
            min(participation_max_requests, retry_count + 1),
            output_client,
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

        spec = output_tool(ResponsePlan)

        async def submit_plan(runtime: ToolRuntime[ToolExecutionContext], **arguments):
            if len(runtime.state["messages"][-1].tool_calls) != 1:
                raise ValueError("最终结果对应一次独立的 submit_response_plan 调用")
            plan = await output_client.submit(ResponsePlan, arguments, runtime.context)
            plan = self._output_policy.validate_plan(plan)
            return "本轮回复已完成结构校验。", plan.model_dump(mode="json")

        result_tool = StructuredTool.from_function(
            coroutine=submit_plan,
            name=spec.name,
            description=spec.description,
            args_schema=spec.arguments_type.model_json_schema(),
            infer_schema=False,
            return_direct=True,
            response_format="content_and_artifact",
        )

        def build_agent(current_tools):
            return create_agent(
                model=model,
                tools=[*current_tools, result_tool],
                middleware=middleware,
                context_schema=ToolExecutionContext,
            )

        self._build_agent = build_agent
        self._tool_signature = self._signature(tools)
        self._agent = build_agent(tools)

    @staticmethod
    def _signature(tools: list[BaseTool]) -> str:
        return json.dumps(
            [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "schema": tool.args_schema
                    if isinstance(tool.args_schema, dict)
                    else tool.get_input_schema().model_json_schema(),
                }
                for tool in tools
            ],
            sort_keys=True,
        )

    async def _current_agent(self):
        if self._tool_loader is not None:
            tools = await self._tool_loader()
            signature = self._signature(tools)
            if signature != self._tool_signature:
                self._agent = self._build_agent(tools)
                self._tool_signature = signature
        return self._agent

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
                graph = await self._current_agent()
                state = await graph.ainvoke(
                    {"messages": messages},
                    context=tool_context or ToolExecutionContext(),
                )
                final = state["messages"][-1]
                if not isinstance(final, ToolMessage) or final.name != output_tool(ResponsePlan).name:
                    raise ValueError("本轮回复需要 MCP 结果工具的完成记录")
                plan = ResponsePlan.model_validate(final.artifact)
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
                {
                    "type": "text",
                    "text": image.attribution if image.is_group else f"\n下图对应消息：{image.attribution}",
                },
                {"type": "image_url", "image_url": {"url": image.data_url}},
            ]
        )
    return HumanMessage(content=content)
