from __future__ import annotations

import os

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI


def create_chat_model(
    model_ref: str,
    *,
    max_tokens: int,
    timeout_sec: float,
    max_retries: int,
) -> BaseChatModel:
    provider, separator, model = model_ref.partition(":")
    if not separator or not provider or not model:
        raise ValueError(f"模型配置必须使用 provider:model 格式: {model_ref}")

    if provider == "deepseek":
        options = _base_url_option("DEEPSEEK_BASE_URL")
        return ChatDeepSeek(
            model=model,
            api_key=_required_env("DEEPSEEK_API_KEY"),
            extra_body={"thinking": {"type": "disabled"}},
            max_tokens=max_tokens,
            timeout=timeout_sec,
            max_retries=max_retries,
            **options,
        )
    if provider == "anthropic":
        options = _base_url_option("ANTHROPIC_BASE_URL")
        return ChatAnthropic(
            model=model,
            api_key=_first_env("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"),
            max_tokens=max_tokens,
            timeout=timeout_sec,
            max_retries=max_retries,
            **options,
        )
    if provider == "openai":
        options = _base_url_option("OPENAI_BASE_URL")
        return ChatOpenAI(
            model=model,
            api_key=_required_env("OPENAI_API_KEY"),
            max_tokens=max_tokens,
            timeout=timeout_sec,
            max_retries=max_retries,
            **options,
        )
    raise ValueError(f"不支持的模型 provider: {provider}")


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


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"缺少模型凭据环境变量: {name}")
    return value


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"缺少模型凭据环境变量: {' / '.join(names)}")


def _base_url_option(name: str) -> dict[str, str]:
    value = os.getenv(name)
    return {"base_url": value} if value else {}
