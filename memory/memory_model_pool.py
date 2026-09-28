from __future__ import annotations

from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from memory.memory_prompt_assembler import MemoryPromptAssembler
from shared.chat_model_factory import create_chat_model
from shared.contracts.agent import AgentDefinition
from shared.global_settings import LLMSettings, ObservabilitySettings
from shared.langchain_observability import (
    model_span,
    record_messages_usage,
    record_model_content,
)
from shared.langchain_structured_output import (
    parsed_output,
    structured_output_runnable,
)

OutputT = TypeVar("OutputT", bound=BaseModel)


class MemoryModelPool:
    def __init__(
        self,
        definitions,
        config: LLMSettings,
        observability: ObservabilitySettings,
        model_factory=None,
    ) -> None:
        self._definitions = definitions
        self._config = config
        self._observability = observability
        self._model_factory = model_factory
        self._models: dict[str, tuple[str, BaseChatModel]] = {}
        self._outputs: dict[tuple[str, type[BaseModel]], tuple[str, Runnable]] = {}

    async def resources(
        self,
        ai_id: str,
    ) -> tuple[AgentDefinition, BaseChatModel]:
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
    ) -> tuple[AgentDefinition, Runnable]:
        definition, model = await self.resources(ai_id)

        key = (ai_id, output_type)
        cached_output = self._outputs.get(key)
        if cached_output is None or cached_output[0] != definition.fingerprint:
            attempts = min(
                self._config.memory_max_requests,
                self._config.retry_count + 1,
            )
            runnable = structured_output_runnable(
                model,
                output_type,
                attempts,
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
            result = await runnable.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
            output = parsed_output(result, output_type)
            record_messages_usage(span, [result["raw"]])
            record_model_content(
                span,
                self._observability,
                input_text=system_prompt + "\n\n" + prompt,
                output=output,
            )
        return output
