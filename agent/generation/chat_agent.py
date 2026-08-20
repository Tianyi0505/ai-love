from __future__ import annotations

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from agent.generation.response_output_policy import ResponseOutputPolicy
from agent.generation.response_plan import ParticipationDecision, ResponsePlan
from shared.configuration.global_settings import ObservabilitySettings
from shared.contracts.tools import ToolExecutionContext


class ChatAgent:
    def __init__(
        self,
        model: str,
        toolset: FunctionToolset[ToolExecutionContext],
        output_policy: ResponseOutputPolicy,
        max_requests: int,
        participation_max_requests: int,
        max_tokens: int,
        retry_count: int,
        observability: ObservabilitySettings,
    ) -> None:
        self._toolset = toolset
        self._output_policy = output_policy
        self._usage_limits = UsageLimits(request_limit=max_requests)
        self._participation_usage_limits = UsageLimits(request_limit=participation_max_requests)
        self._agent = Agent(
            model=model,
            deps_type=ToolExecutionContext,
            model_settings=ModelSettings(max_tokens=max_tokens),
            retries=retry_count,
        )
        self._agent.instrument = InstrumentationSettings(
            include_content=observability.include_model_content,
            include_binary_content=observability.include_binary_content,
            include_model_request_parameters=observability.include_model_request_parameters,
        )

    async def generate_plan(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_context: ToolExecutionContext | None = None,
        allow_tools: bool = True,
    ) -> ResponsePlan:
        result = await self._agent.run(
            user_prompt,
            output_type=ResponsePlan,
            instructions=system_prompt,
            deps=tool_context or ToolExecutionContext(),
            usage_limits=self._usage_limits,
            toolsets=[self._toolset] if allow_tools else [],
        )
        return self._output_policy.validate_plan(result.output)

    async def decide_participation(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> ParticipationDecision:
        result = await self._agent.run(
            user_prompt,
            output_type=ParticipationDecision,
            instructions=system_prompt,
            deps=ToolExecutionContext(),
            usage_limits=self._participation_usage_limits,
            toolsets=[],
        )
        return self._output_policy.validate_participation(result.output)
