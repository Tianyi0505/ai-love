
from __future__ import annotations

import os
from collections.abc import Mapping
from enum import Enum
from typing import TypeVar


T = TypeVar("T")


# 定义配置键枚举
class ConfigKey(str, Enum):
    AILOVE_NACOS_ADDRS = "AILOVE_NACOS_ADDRS"
    AILOVE_NACOS_GROUP = "AILOVE_NACOS_GROUP"
    AILOVE_NACOS_GRPC_TIMEOUT_MS = "AILOVE_NACOS_GRPC_TIMEOUT_MS"
    AILOVE_CONFIG_RETRY_COUNT = "AILOVE_CONFIG_RETRY_COUNT"
    AILOVE_CONFIG_RETRY_INTERVAL_SEC = "AILOVE_CONFIG_RETRY_INTERVAL_SEC"
    AILOVE_BUS_URL = "AILOVE_BUS_URL"
    AILOVE_DATABASE_URL = "AILOVE_DATABASE_URL"
    AILOVE_DATABASE_POOL_MIN_SIZE = "AILOVE_DATABASE_POOL_MIN_SIZE"
    AILOVE_DATABASE_POOL_MAX_SIZE = "AILOVE_DATABASE_POOL_MAX_SIZE"
    AILOVE_SNOWFLAKE_WORKER_ID = "AILOVE_SNOWFLAKE_WORKER_ID"
    AILOVE_LEGACY_DATA_DIR = "AILOVE_LEGACY_DATA_DIR"
    AILOVE_AI_ID = "AILOVE_AI_ID"
    ANTHROPIC_AUTH_TOKEN = "ANTHROPIC_AUTH_TOKEN"
    DEEPSEEK_API_KEY = "DEEPSEEK_API_KEY"
    ANTHROPIC_BASE_URL = "ANTHROPIC_BASE_URL"
    DEEPSEEK_BASE_URL = "DEEPSEEK_BASE_URL"
    OLLAMA_BASE_URL = "OLLAMA_BASE_URL"
    VISION_BASE_URL = "VISION_BASE_URL"
    VISION_MODEL = "VISION_MODEL"
    GPT_SOVITS_URL = "GPT_SOVITS_URL"
    MIMO_BASE_URL = "MIMO_BASE_URL"
    MIMO_MODEL = "MIMO_MODEL"
    AZURE_SPEECH_REGION = "AZURE_SPEECH_REGION"
    AZURE_SPEECH_KEY = "AZURE_SPEECH_KEY"
    NAPCAT_WS_URL = "NAPCAT_WS_URL"
    NAPCAT_HTTP_URL = "NAPCAT_HTTP_URL"
    QWEATHER_API_KEY = "QWEATHER_API_KEY"
    QWEATHER_API_HOST = "QWEATHER_API_HOST"


# 读取必填配置值
def required_value(value: str | None, config_name: str | ConfigKey) -> str:
    name = config_name.value if isinstance(config_name, ConfigKey) else config_name
    if value is None:
        raise RuntimeError(f"未配置 {name}")
    resolved = value.strip()
    if not resolved:
        raise RuntimeError(f"未配置 {name}")
    return resolved


# 读取必填设置项
def required_setting(value: str | None, env_name: ConfigKey) -> str:
    resolved = value if value is not None else os.environ.get(env_name.value)
    return required_value(resolved, env_name)


# 读取必填配置项
def required_config(config: Mapping[str, T], key: str, config_name: str) -> T:
    try:
        return config[key]
    except KeyError as exc:
        raise RuntimeError(f"未配置 {config_name}") from exc
