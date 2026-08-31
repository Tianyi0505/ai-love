from __future__ import annotations

import hashlib
import json

from redis.asyncio import Redis

from shared.contracts.social import SocialMessage


class GroupRepeatService:
    def __init__(self, redis: Redis, ai_id: str, ttl_sec: int) -> None:
        self._redis = redis
        self._prefix = f"ai-love:group-repeat:{ai_id}:"
        self._ttl_sec = ttl_sec

    @staticmethod
    def content_hash(message: SocialMessage) -> str:
        content = {
            "type": message.type.value,
            "text": message.text.strip(),
            "media_url": message.media_url,
            "media_urls": message.media_urls,
            "media_desc": message.media_desc,
            "media_descs": message.media_descs,
            "at_user_ids": message.meta.get("at_user_ids", []),
        }
        encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def should_repeat(self, message: SocialMessage) -> bool:
        if not message.message_id:
            return False
        digest = self.content_hash(message)
        scope = f"{message.account_id}:{message.chat.chat_id}:{digest}"
        observed_key = f"{self._prefix}observed:{scope}"
        if await self._redis.set(observed_key, "1", ex=self._ttl_sec, nx=True):
            return False
        repeated_key = f"{self._prefix}repeated:{scope}"
        return bool(await self._redis.set(repeated_key, "1", ex=self._ttl_sec, nx=True))
