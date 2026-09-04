from __future__ import annotations

import os
from collections.abc import Mapping

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from shared.chat_model_strategy import CHAT_MODEL_STRATEGIES, ChatModelParameters
from shared.global_settings import ChatModelSettings


def create_chat_model(
    model_id: str,
    *,
    models: Mapping[str, ChatModelSettings],
    max_tokens: int,
    timeout_sec: float,
    max_retries: int,
) -> BaseChatModel:
    model_config = models.get(model_id)
    if model_config is None:
        raise ValueError(f"未配置模型: {model_id}")

    strategy = CHAT_MODEL_STRATEGIES.get(model_config.provider)
    if strategy is None:
        raise ValueError(f"不支持的模型 provider: {model_config.provider}")
    api_key = os.getenv(model_config.api_key_env)
    if not api_key:
        raise RuntimeError(f"缺少模型凭据环境变量: {model_config.api_key_env}")
    return strategy.create(
        ChatModelParameters(
            model=model_config.model,
            api_key=api_key,
            base_url=model_config.base_url,
            max_tokens=max_tokens,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
        )
    )


def create_openai_compatible_chat_model(
    model: str,
    *,
    api_key: str,
    base_url: str,
    max_tokens: int,
    timeout_sec: float,
    max_retries: int,
    http_async_client: httpx.AsyncClient | None = None,
) -> BaseChatModel:
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
        timeout=timeout_sec,
        max_retries=max_retries,
        http_async_client=http_async_client,
    )
