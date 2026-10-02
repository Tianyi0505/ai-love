from __future__ import annotations

import hashlib
import json
import logging

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import ChatModelBase
from redis.asyncio import Redis

from agent.conversation.conversation_context import ConversationContext, format_group_entries
from agent.conversation.prompt_assembler import PromptAssembler
from shared.agent_output import StructuredOutput
from shared.contracts.social import ContentType, SocialMessage
from shared.global_settings import ObservabilitySettings
from shared.mcp_output_client import MCPOutputClient
from shared.model_observability import model_span, record_messages_usage, record_model_content
from shared.structured_output_tools import GroupRepeatDecision as GroupRepeatDecision

logger = logging.getLogger("ailove.ai-agent.group-repeat")

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

    async def claim_candidate(self, message: SocialMessage) -> bool:
        if not message.message_id:
            return False
        digest = self.content_hash(message)
        scope = f"{message.account_id}:{message.chat.chat_id}"
        key = f"{self._prefix}{scope}"
        claimed = bool(await self._redis.eval(_REPEAT_SCRIPT, 1, key, digest, self._ttl_sec))
        return claimed and message.type == ContentType.TEXT and not message.meta.get("at_user_ids")


class GroupRepeatJudge:
    def __init__(
        self,
        *,
        model: ChatModelBase,
        model_name: str,
        conversation: ConversationContext,
        prompt_assembler: PromptAssembler,
        ai_name: str,
        history_limit: int,
        max_attempts: int,
        max_tokens: int,
        observability: ObservabilitySettings,
        output_client: MCPOutputClient,
    ) -> None:
        self._model_name = model_name
        self._conversation = conversation
        self._prompt_assembler = prompt_assembler
        self._ai_name = ai_name
        self._history_limit = max(2, history_limit)
        self._max_tokens = max_tokens
        self._observability = observability
        self._decision_model = StructuredOutput(model, GroupRepeatDecision, max_attempts, output_client)

    async def should_repeat(self, chat_id: str) -> bool:
        try:
            entries = list(self._conversation.window("group", chat_id))[-self._history_limit :]
            if len(entries) < 2:
                logger.info("群聊 +1 候选缺少可判断的连续上下文，已跳过: chat_id=%s", chat_id)
                return False

            system_prompt = (
                self._prompt_assembler.template("group-repeat-decision")
                + "\n\n" + self._prompt_assembler.template("group-message-format")
            )
            user_prompt = format_group_entries(entries, self._ai_name)
            messages = [SystemMsg("system", content=system_prompt), UserMsg("user", content=user_prompt)]
            with model_span(
                "group-repeat.decide",
                self._model_name,
                self._observability,
                {"max_tokens": self._max_tokens},
            ) as span:
                result = await self._decision_model.generate(messages)
                decision = result["parsed"]
                record_messages_usage(span, [result["raw"]])
                record_model_content(
                    span,
                    self._observability,
                    input_text=f"{system_prompt}\n\n{user_prompt}",
                    output=decision,
                )
            logger.info("群聊 +1 判断: chat_id=%s repeat=%s", chat_id, decision.repeat)
            return decision.repeat
        except Exception:
            logger.exception("群聊 +1 小模型判断失败，已跳过: chat_id=%s", chat_id)
            return False
