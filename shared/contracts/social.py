from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SUBJ_SOCIAL_CHAT = "social.chat.{ai_id}"
SUBJ_SOCIAL_SEND = "social.send.request"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    STICKER = "sticker"
    FORWARD = "forward"
    QUOTE = "quote"
    FILE = "file"
    AT = "at"


class ChatType(str, Enum):
    PRIVATE = "private"
    GROUP = "group"


class SocialSender(ContractModel):
    user_id: str
    name: str = ""
    avatar_url: str = ""


class Chat(ContractModel):
    chat_id: str
    chat_type: ChatType
    chat_name: str = ""
    ai_identity: str = ""
    members: list[SocialSender] = Field(default_factory=list)


class SocialMessage(ContractModel):
    chat: Chat
    sender: SocialSender
    type: ContentType
    text: str = ""
    media_url: str = ""
    media_desc: str = ""
    media_urls: list[str] = Field(default_factory=list)
    media_descs: list[str] = Field(default_factory=list)
    media_duration_sec: int = 0
    sub_messages: list[SocialMessage] = Field(default_factory=list)
    quote_ref: SocialMessage | None = None
    at_user_id: str = ""
    to_ai: bool = False
    message_id: str = ""
    timestamp: int = 0
    account_id: str = ""
    platform: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)

    def all_media_urls(self) -> list[str]:
        if self.media_urls:
            return self.media_urls
        return [self.media_url] if self.media_url else []


SocialMessage.model_rebuild()
