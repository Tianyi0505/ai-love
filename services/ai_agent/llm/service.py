from __future__ import annotations

from services.ai_agent.llm.model import ModelHealthStore, ModelSelector
from services.ai_agent.llm.routing import RoutingLLMService
from services.ai_agent.llm.types import (
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


def create_llm(model_cfg: dict, timeout_ms: int) -> LLMService:
    health = ModelHealthStore()
    selector = ModelSelector(model_cfg, timeout_ms, health)

    def provider_factory(name: str, model: str) -> LLMProvider:
        if not llm_registry.contains(name):
            return None  # type: ignore
        cls = llm_registry.get(name)
        return cls(model=model)  # type: ignore

    routing = RoutingLLMService(selector, health, provider_factory)
    return LLMService(routing)
