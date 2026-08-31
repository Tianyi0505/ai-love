from __future__ import annotations

import hashlib
import json

from redis.asyncio import Redis

from shared.contracts.social import SocialMessage

_REPEAT_SCRIPT = """
local previous_hash = redis.call('HGET', KEYS[1], 'hash')
local repeated = redis.call('HGET', KEYS[1], 'repeated')
if previous_hash == ARGV[1] then
    if repeated == '1' then
        return 0
    end
    redis.call('HSET', KEYS[1], 'repeated', '1')
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return 1
end
redis.call('HSET', KEYS[1], 'hash', ARGV[1], 'repeated', '0')
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 0
"""


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
        scope = f"{message.account_id}:{message.chat.chat_id}"
        key = f"{self._prefix}{scope}"
        return bool(await self._redis.eval(_REPEAT_SCRIPT, 1, key, digest, self._ttl_sec))
