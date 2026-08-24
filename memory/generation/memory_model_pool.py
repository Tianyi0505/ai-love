from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.usage import UsageLimits

from shared.configuration.global_settings import LLMSettings, ObservabilitySettings

OutputT = TypeVar("OutputT", bound=BaseModel)


class MemoryModelPool:
    def __init__(
        self,
        definitions,
        config: LLMSettings,
        observability: ObservabilitySettings,
    ) -> None:
        self._definitions = definitions
        self._max_tokens = config.max_tokens
        self._retry_count = config.retry_count
        self._usage_limits = UsageLimits(request_limit=config.memory_max_requests)
        self._cache: dict[str, tuple[str, Agent]] = {}
        self._instrumentation = InstrumentationSettings(
            include_content=observability.include_model_content,
            include_binary_content=observability.include_binary_content,
            include_model_request_parameters=observability.include_model_request_parameters,
        )

    async def resources(self, ai_id: str):
        definition = await self._definitions.load(ai_id)
        cached = self._cache.get(ai_id)
        if cached is not None and cached[0] == definition.fingerprint:
            return definition, cached[1]
        agent = Agent(
            model=definition.model_profile.model,
            model_settings=ModelSettings(max_tokens=self._max_tokens),
            retries=self._retry_count,
        )
        agent.instrument = self._instrumentation
        self._cache[ai_id] = (definition.fingerprint, agent)
        return definition, agent

    async def generate(self, ai_id: str, prompt: str, output_type: type[OutputT]) -> OutputT:
        _, agent = await self.resources(ai_id)
        result = await agent.run(
            prompt,
            output_type=output_type,
            usage_limits=self._usage_limits,
        )
        return result.output
