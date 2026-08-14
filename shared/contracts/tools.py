from __future__ import annotations

from dataclasses import dataclass


# 运行时注入的可信作用域
@dataclass(frozen=True)
class ToolExecutionContext:
    run_id: str = ""
    ai_id: str = ""
    account_id: str = ""
    conversation_id: str = ""
    platform: str = ""
    chat_type: str = ""
    chat_id: str = ""
    sender_person_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "ai_id": self.ai_id,
            "account_id": self.account_id,
            "conversation_id": self.conversation_id,
            "platform": self.platform,
            "chat_type": self.chat_type,
            "chat_id": self.chat_id,
            "sender_person_id": self.sender_person_id,
        }

    @classmethod
    def from_dict(cls, value: dict | None) -> "ToolExecutionContext":
        data = value if isinstance(value, dict) else {}
        return cls(
            run_id=str(data.get("run_id") or ""),
            ai_id=str(data.get("ai_id") or ""),
            account_id=str(data.get("account_id") or ""),
            conversation_id=str(data.get("conversation_id") or ""),
            platform=str(data.get("platform") or ""),
            chat_type=str(data.get("chat_type") or ""),
            chat_id=str(data.get("chat_id") or ""),
            sender_person_id=str(data.get("sender_person_id") or ""),
        )

    @property
    def is_group(self) -> bool:
        return self.chat_type == "group"
