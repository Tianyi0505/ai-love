
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

SUBJ_SOCIAL_CHAT = "social.chat.{ai_id}"
SUBJ_SOCIAL_SEND = "social.send.request"
SUBJ_SOCIAL_HISTORY = "social.history.request"


class ContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    STICKER = "sticker"
    FORWARD = "forward"
    QUOTE = "quote"
    FILE = "file"
    AT = "at"


class ChatType(Enum):
    PRIVATE = "private"
    GROUP = "group"


@dataclass
class SocialSender:
    user_id: str
    name: str = ""
    avatar_url: str = ""


@dataclass
class Chat:

    chat_id: str
    chat_type: ChatType
    chat_name: str = ""
    ai_identity: str = ""
    members: list[SocialSender] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "chat_type": self.chat_type.value,
            "chat_name": self.chat_name,
            "ai_identity": self.ai_identity,
            "members": [{"user_id": m.user_id, "name": m.name, "avatar_url": m.avatar_url} for m in self.members],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Chat":
        return cls(
            chat_id=data.get("chat_id", ""),
            chat_type=ChatType(data.get("chat_type", "private")),
            chat_name=data.get("chat_name", ""),
            ai_identity=data.get("ai_identity", ""),
            members=[SocialSender(**m) for m in data.get("members", [])],
        )


@dataclass
class SocialMessage:

    chat: Chat
    sender: SocialSender
    type: ContentType
    text: str = ""
    media_url: str = ""
    media_desc: str = ""
    media_urls: list[str] = field(default_factory=list)
    media_descs: list[str] = field(default_factory=list)
    media_duration_sec: int = 0
    sub_messages: list["SocialMessage"] = field(default_factory=list)
    quote_ref: "SocialMessage | None" = None
    at_user_id: str = ""
    to_ai: bool = False
    message_id: str = ""
    timestamp: int = 0
    account_id: str = ""
    platform: str = ""
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "chat": self.chat.to_dict(),
            "sender": {"user_id": self.sender.user_id, "name": self.sender.name, "avatar_url": self.sender.avatar_url},
            "type": self.type.value,
            "text": self.text,
            "media_url": self.media_url,
            "media_desc": self.media_desc,
            "media_urls": self.media_urls,
            "media_descs": self.media_descs,
            "media_duration_sec": self.media_duration_sec,
            "at_user_id": self.at_user_id,
            "to_ai": self.to_ai,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "account_id": self.account_id,
            "platform": self.platform,
            "meta": self.meta,
        }
        if self.sub_messages:
            d["sub_messages"] = [m.to_dict() for m in self.sub_messages]
        if self.quote_ref:
            d["quote_ref"] = self.quote_ref.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SocialMessage":
        return cls(
            chat=Chat.from_dict(data.get("chat", {})),
            sender=SocialSender(**data.get("sender", {})),
            type=ContentType(data.get("type", "text")),
            text=data.get("text", ""),
            media_url=data.get("media_url", ""),
            media_desc=data.get("media_desc", ""),
            media_urls=list(data.get("media_urls") or []),
            media_descs=list(data.get("media_descs") or []),
            media_duration_sec=data.get("media_duration_sec", 0),
            sub_messages=[cls.from_dict(m) for m in data.get("sub_messages", [])],
            quote_ref=cls.from_dict(data["quote_ref"]) if data.get("quote_ref") else None,
            at_user_id=data.get("at_user_id", ""),
            to_ai=data.get("to_ai", False),
            message_id=data.get("message_id", ""),
            timestamp=data.get("timestamp", 0),
            account_id=data.get("account_id", ""),
            platform=data.get("platform", ""),
            meta=data.get("meta", {}),
        )

    def all_media_urls(self) -> list[str]:
        if self.media_urls:
            return [str(url) for url in self.media_urls if str(url)]
        return [self.media_url] if self.media_url else []
