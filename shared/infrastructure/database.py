
from __future__ import annotations

from typing import Any

import asyncpg

from shared.infrastructure.runtime_config import ConfigKey, required_setting


class Database:
    def __init__(self) -> None:
        self._url = required_setting(None, ConfigKey.AILOVE_DATABASE_URL)
        self._pool_min_size = int(
            required_setting(None, ConfigKey.AILOVE_DATABASE_POOL_MIN_SIZE)
        )
        self._pool_max_size = int(
            required_setting(None, ConfigKey.AILOVE_DATABASE_POOL_MAX_SIZE)
        )
        self._pool = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._url,
            min_size=self._pool_min_size,
            max_size=self._pool_max_size,
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self):
        if self._pool is None:
            raise RuntimeError("Database 未 connect")
        return self._pool

    async def fetch(self, query: str, *args: Any):
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any):
        return await self.pool.fetchrow(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self.pool.execute(query, *args)
