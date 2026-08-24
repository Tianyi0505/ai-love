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


def is_snowflake_id(value: object) -> bool:
    if not isinstance(value, str) or not value.isdigit():
        return False
    return 0 < int(value) <= (1 << 63) - 1


@cache
def snowflake_ids() -> SnowflakeIdGenerator:
    return SnowflakeIdGenerator(SnowflakeSettings().worker_id)
