from __future__ import annotations

from ai.llm.model import ModelHealthStore, ModelSelector
from ai.llm.routing import RoutingLLMService
from ai.llm.types import (
    ChatMessage,
    ChatRequest,
    ChatStreamChunk,
    LLMProvider,
    LLMService,
    ToolCall,
    ToolSchema,
)
from shared.infrastructure.registry import Registry

llm_registry = Registry("llm")


def create_llm(model_cfg: dict, llm_config: dict) -> LLMService:
    health = ModelHealthStore(
        fail_threshold=int(llm_config["health_fail_threshold"]),
        recover_after_sec=int(llm_config["health_recover_after_sec"]),
    )
    selector = ModelSelector(model_cfg, int(llm_config["timeout_ms"]), health)

    def provider_factory(name: str, model: str) -> LLMProvider:
        if not llm_registry.contains(name):
            return None
        cls = llm_registry.get(name)
        return cls(
            model=model,
            max_tokens=int(llm_config["max_tokens"]),
            request_timeout_sec=float(llm_config["provider_request_timeout_sec"]),
        )

    routing = RoutingLLMService(selector, health, provider_factory)
    return LLMService(routing)
