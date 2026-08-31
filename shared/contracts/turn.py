from __future__ import annotations

from dataclasses import dataclass

from shared.contracts.rpc.social import SocialSendRequest
from shared.contracts.tools import ToolExecutionContext
from shared.snowflake_id_generator import snowflake_ids


# 生成一次执行链路标识
def new_run_id() -> str:
    return str(snowflake_ids().next_id())


# 描述一轮消息执行上下文
@dataclass(frozen=True)
class AgentExecutionContext:
    run_id: str
    ai_id: str
    account_id: str
    conversation_id: str
    platform: str
    chat_type: str
    chat_id: str
    sender_person_id: str
    sender_platform_user_id: str
    message_id: str
    reply_to_message_id: str
    occurred_at: int
    source: str

    # 从社交消息构建执行上下文
    @classmethod
    def from_social_message(cls, message, ai_id: str, run_id: str | None = None) -> "AgentExecutionContext":
        resolved_run_id = run_id or message.meta.get("run_id") or new_run_id()
        return cls(
            run_id=str(resolved_run_id),
            ai_id=ai_id,
            account_id=message.account_id,
            conversation_id=str(message.meta.get("conversation_id", "")),
            platform=message.platform,
            chat_type=message.chat.chat_type.value,
            chat_id=message.chat.chat_id,
            sender_person_id=str(message.meta.get("person_id", "")),
            sender_platform_user_id=message.sender.user_id,
            message_id=message.message_id,
            reply_to_message_id=str(message.quote_ref.message_id) if message.quote_ref else "",
            occurred_at=message.timestamp,
            source="social",
        )

    # 返回工具执行作用域
    def tool_context(self) -> ToolExecutionContext:
        return ToolExecutionContext(
            run_id=self.run_id,
            ai_id=self.ai_id,
            account_id=self.account_id,
            conversation_id=self.conversation_id,
            platform=self.platform,
            chat_type=self.chat_type,
            chat_id=self.chat_id,
            sender_person_id=self.sender_person_id,
        )

    # 返回会话串行化键
    @property
    def conversation_key(self) -> str:
        return f"{self.ai_id}\x1f{self.conversation_id or self.chat_id}"


# 表示统一回复指令
@dataclass(frozen=True)
class ResponseCommand:
    run_id: str
    ai_id: str
    account_id: str
    conversation_id: str
    platform: str
    chat: dict
    reply_to_message_id: str
    text: str
    sticker: dict | None
    voice: dict | None
    repeat_message_id: str = ""

    # 返回发送负载
    def send_request(self) -> SocialSendRequest:
        return SocialSendRequest(
            ai_id=self.ai_id,
            account_id=self.account_id,
            conversation_id=self.conversation_id,
            channel=self.platform,
            chat=self.chat,
            type="repeat" if self.repeat_message_id else "text",
            text=self.text,
            run_id=self.run_id,
            reply_to_message_id=self.reply_to_message_id,
            repeat_message_id=self.repeat_message_id,
            sticker=self.sticker,
            voice=self.voice,
        )
