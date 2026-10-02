from __future__ import annotations

from typing import TypeVar

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import ChatModelBase
from pydantic import BaseModel

from memory.memory_prompt_assembler import MemoryPromptAssembler
from shared.agent_output import StructuredOutput
from shared.chat_model_factory import create_chat_model
from shared.contracts.agent import AgentDefinition
from shared.global_settings import LLMSettings, ObservabilitySettings
from shared.model_observability import (
    model_span,
    record_messages_usage,
    record_model_content,
)

OutputT = TypeVar("OutputT", bound=BaseModel)


class MemoryModelPool:
    def __init__(
        self,
        definitions,
        config: LLMSettings,
        observability: ObservabilitySettings,
        output_client_factory,
        model_factory=None,
    ) -> None:
        self._definitions = definitions
        self._config = config
        self._observability = observability
        self._model_factory = model_factory
        self._output_client_factory = output_client_factory
        self._models: dict[str, tuple[str, ChatModelBase]] = {}
        self._outputs: dict[tuple[str, type[BaseModel]], tuple[str, StructuredOutput]] = {}

    async def resources(
        self,
        ai_id: str,
    ) -> tuple[AgentDefinition, ChatModelBase]:
        definition = await self._definitions.load(ai_id)
        cached_model = self._models.get(ai_id)
        if cached_model is None or cached_model[0] != definition.fingerprint:
            model = (self._model_factory or create_chat_model)(
                definition.model_profile.model_id,
                models=self._config.models,
                max_tokens=self._config.memory_max_tokens,
                timeout_sec=self._config.memory_request_timeout_sec,
                max_retries=self._config.retry_count,
            )
            self._models[ai_id] = (definition.fingerprint, model)
            self._outputs = {
                key: value
                for key, value in self._outputs.items()
                if key[0] != ai_id
            }
        else:
            model = cached_model[1]
        return definition, model

    async def _structured_resources(
        self,
        ai_id: str,
        output_type: type[OutputT],
    ) -> tuple[AgentDefinition, StructuredOutput]:
        definition, model = await self.resources(ai_id)

        key = (ai_id, output_type)
        cached_output = self._outputs.get(key)
        if cached_output is None or cached_output[0] != definition.fingerprint:
            attempts = min(
                self._config.memory_max_requests,
                self._config.retry_count + 1,
            )
            runnable = StructuredOutput(
                model,
                output_type,
                attempts,
                self._output_client_factory(ai_id),
            )
            self._outputs[key] = (definition.fingerprint, runnable)
        else:
            runnable = cached_output[1]
        return definition, runnable

    async def generate(
        self,
        ai_id: str,
        prompt: str,
        output_type: type[OutputT],
    ) -> OutputT:
        definition, runnable = await self._structured_resources(ai_id, output_type)
        system_prompt = MemoryPromptAssembler(definition).system()
        model_name = definition.model_profile.model_id
        with model_span(
            "memory.generate",
            model_name,
            self._observability,
            {"max_tokens": self._config.memory_max_tokens},
        ) as span:
            result = await runnable.generate([SystemMsg("system", content=system_prompt), UserMsg("user", content=prompt)])
            output = result["parsed"]
            record_messages_usage(span, [result["raw"]])
            record_model_content(
                span,
                self._observability,
                input_text=system_prompt + "\n\n" + prompt,
                output=output,
            )
        return output
