from __future__ import annotations

import time

from redis.asyncio import Redis


class SessionManager:
    def __init__(self, redis: Redis, ai_id: str, ttl_sec: int) -> None:
        self._redis = redis
        self._prefix = f"ai-love:speaking:{ai_id}:"
        self._ttl_sec = ttl_sec

    def _key(self, chat_key: str) -> str:
        return f"{self._prefix}{chat_key}"

    async def can_speak(self, chat_key: str) -> bool:
        replied = await self._redis.hget(self._key(chat_key), "replied")
        return replied is None or replied == "true"

    async def can_initiate(self, chat_key: str, cooldown_sec: int) -> bool:
        state = await self._redis.hgetall(self._key(chat_key))
        if not state:
            return True
        if state["replied"] != "true":
            return False
        last_spoke = state.get("last_spoke")
        return last_spoke is None or time.time() - float(last_spoke) >= cooldown_sec

    async def mark_spoke(self, chat_key: str) -> None:
        key = self._key(chat_key)
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.hset(
                key,
                mapping={"last_spoke": str(time.time()), "replied": "false"},
            )
            pipeline.expire(key, self._ttl_sec)
            await pipeline.execute()

    async def mark_replied(self, chat_key: str) -> None:
        key = self._key(chat_key)
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.hset(key, "replied", "true")
            pipeline.expire(key, self._ttl_sec)
            await pipeline.execute()
