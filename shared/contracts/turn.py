from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from shared.contracts.tools import ToolExecutionContext


# 生成一次执行链路标识
def new_run_id() -> str:
    return uuid.uuid4().hex


# 描述一轮消息执行上下文
@dataclass(frozen=True)
class AgentExecutionContext:
    run_id: str = field(default_factory=new_run_id)
    ai_id: str = ""
    account_id: str = ""
    conversation_id: str = ""
    platform: str = ""
    chat_type: str = ""
    chat_id: str = ""
    sender_person_id: str = ""
    sender_platform_user_id: str = ""
    message_id: str = ""
    reply_to_message_id: str = ""
    occurred_at: int = 0
    source: str = "social"

    # 从社交消息构建执行上下文
    @classmethod
    def from_social_message(cls, message, ai_id: str, run_id: str = "") -> "AgentExecutionContext":
        return cls(
            run_id=run_id or str(message.meta.get("run_id") or "") or new_run_id(),
            ai_id=ai_id,
            account_id=str(message.account_id or ""),
            conversation_id=str(message.meta.get("conversation_id") or ""),
            platform=str(message.platform or ""),
            chat_type=message.chat.chat_type.value,
            chat_id=str(message.chat.chat_id or ""),
            sender_person_id=str(message.meta.get("person_id") or ""),
            sender_platform_user_id=str(message.sender.user_id or ""),
            message_id=str(message.message_id or ""),
            reply_to_message_id=str(message.quote_ref.message_id) if message.quote_ref else "",
            occurred_at=int(message.timestamp or 0),
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
    platform: str = "qq"
    chat: dict = field(default_factory=dict)
    reply_to_message_id: str = ""
    text: str = ""
    sticker: dict | None = None
    voice: dict | None = None

    # 返回发送负载
    def send_payload(self) -> dict:
        payload: dict = {
            "ai_id": self.ai_id,
            "account_id": self.account_id,
            "conversation_id": self.conversation_id,
            "channel": self.platform or "qq",
            "chat": self.chat,
            "type": "text",
            "text": self.text,
            "run_id": self.run_id,
        }
        if self.reply_to_message_id:
            payload["reply_to_message_id"] = self.reply_to_message_id
        if self.sticker:
            payload["sticker"] = self.sticker
        if self.voice:
            payload["voice"] = self.voice
        return payload

    # 返回去掉表情后的重试指令
    def without_sticker(self) -> "ResponseCommand":
        if self.sticker is None:
            return self
        return ResponseCommand(
            run_id=self.run_id,
            ai_id=self.ai_id,
            account_id=self.account_id,
            conversation_id=self.conversation_id,
            platform=self.platform,
            chat=self.chat,
            reply_to_message_id=self.reply_to_message_id,
            text=self.text,
            sticker=None,
            voice=self.voice,
        )
