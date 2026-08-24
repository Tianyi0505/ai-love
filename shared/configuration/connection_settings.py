from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NacosConnectionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AILOVE_NACOS_", extra="ignore")

    addrs: str
    grpc_timeout_ms: int
    namespace: str | None = None
    group: str
    user: str | None = None
    password: str | None = None


class ServiceConnectionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AILOVE_", extra="ignore")

    bus_url: str
    bus_token: str | None = None
    config_retry_count: int
    config_retry_interval_sec: float


class RedisConnectionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AILOVE_REDIS_", extra="ignore")

    url: str
    password: str


class DatabaseURLSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AILOVE_DATABASE_", extra="ignore")

    url: str


class QWeatherConnectionSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    api_key: str = Field(validation_alias="QWEATHER_API_KEY")
    api_host: str = Field(validation_alias="QWEATHER_API_HOST")


class MimoAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    auth_token: str = Field(validation_alias="ANTHROPIC_AUTH_TOKEN")
