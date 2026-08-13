
from __future__ import annotations

import os
from typing import Any

import asyncpg


class Database:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.environ.get("AILOVE_DATABASE_URL", "")
        self._pool = None

    async def connect(self) -> None:
        if not self._url:
            raise RuntimeError("未配置 AILOVE_DATABASE_URL")
        self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=10)

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
