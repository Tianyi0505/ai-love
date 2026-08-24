from __future__ import annotations

from functools import cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from snowflake import SnowflakeGenerator


class SnowflakeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AILOVE_SNOWFLAKE_", extra="ignore")

    worker_id: int


class SnowflakeIdGenerator:
    def __init__(self, worker_id: int) -> None:
        self._generator = SnowflakeGenerator(worker_id)

    def next_id(self) -> int:
        return next(self._generator)


@cache
def snowflake_ids() -> SnowflakeIdGenerator:
    return SnowflakeIdGenerator(SnowflakeSettings().worker_id)
