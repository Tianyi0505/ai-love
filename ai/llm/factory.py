from __future__ import annotations

from ai.llm.model import ModelHealthStore, ModelSelector
from ai.llm.providers.base import StreamingChatProvider
from ai.llm.registry import provider_registry
from ai.llm.routing import RoutingLLMService
from ai.llm.service import LLMService


# 创建大模型
def create_llm(model_cfg: dict, llm_config: dict) -> LLMService:
    health = ModelHealthStore(
        fail_threshold=int(llm_config["health_fail_threshold"]),
        recover_after_sec=int(llm_config["health_recover_after_sec"]),
    )
    selector = ModelSelector(model_cfg, int(llm_config["timeout_ms"]), health)

    # 创建大模型提供器
    def provider_factory(name: str, model: str) -> StreamingChatProvider | None:
        if not provider_registry.contains(name):
            return None
        provider_type = provider_registry.get(name)
        return provider_type(
            model=model,
            max_tokens=int(llm_config["max_tokens"]),
            request_timeout_sec=float(llm_config["provider_request_timeout_sec"]),
        )

    routing = RoutingLLMService(selector, health, provider_factory)
    return LLMService(routing)
