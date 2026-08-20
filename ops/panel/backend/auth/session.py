from __future__ import annotations

import hashlib
import secrets

from redis.asyncio import Redis


COOKIE_NAME = "ai_love_session"
SESSION_TTL_SECONDS = 24 * 60 * 60


class RedisSessionStore:
    """只负责在 Redis 中创建、校验和删除面板会话。"""

    _KEY_PREFIX = "ai-love:session:"

    def __init__(self, redis: Redis, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def create(self) -> str:
        token = secrets.token_urlsafe(32)
        await self._redis.set(self._key(token), "1", ex=self._ttl_seconds)
        return token

    async def exists(self, token: str) -> bool:
        return bool(await self._redis.exists(self._key(token)))

    async def delete(self, token: str) -> None:
        await self._redis.delete(self._key(token))

    async def delete_all(self) -> None:
        keys = [key async for key in self._redis.scan_iter(match=f"{self._KEY_PREFIX}*")]
        if keys:
            await self._redis.delete(*keys)

    @classmethod
    def _key(cls, token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{cls._KEY_PREFIX}{digest}"
