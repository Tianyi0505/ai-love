from __future__ import annotations

from ai.llm.anthropic_compatible import AnthropicCompatibleProvider
from ai.llm.registry import provider_registry
from shared.infrastructure.runtime_config import ConfigKey, required_setting


# 通过 Anthropic 兼容协议调用 DeepSeek V4 Flash 0731 模型
@provider_registry.register("deepseek_v4_flash_0731")
class DeepSeekV4Flash0731Provider(AnthropicCompatibleProvider):
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
            api_key=required_setting(api_key, ConfigKey.ANTHROPIC_AUTH_TOKEN),
            base_url=required_setting(base_url, ConfigKey.ANTHROPIC_BASE_URL),
        )
