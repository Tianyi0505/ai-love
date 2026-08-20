from __future__ import annotations

from ai.llm.openai_compatible import OpenAICompatibleProvider
from ai.llm.registry import provider_registry
from shared.infrastructure.runtime_config import ConfigKey, required_setting


# 提供DeepSeek大模型调用能力
@provider_registry.register("deepseek")
class DeepSeekProvider(OpenAICompatibleProvider):
    # 初始化当前实例
    def __init__(
        self,
        model: str,
        max_tokens: int,
        request_timeout_sec: float,
        api_key: str | None = None,
        base_url: str | None = None,
        **_,
    ) -> None:
        super().__init__(
            model=model,
            max_tokens=max_tokens,
            request_timeout_sec=request_timeout_sec,
            api_key=required_setting(api_key, ConfigKey.DEEPSEEK_API_KEY),
            base_url=required_setting(base_url, ConfigKey.DEEPSEEK_BASE_URL),
        )
