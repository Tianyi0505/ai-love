from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.contracts.rpc.rpc_model import RpcModel
from shared.contracts.social import Chat


class SocialSendRequest(RpcModel):
    ai_id: str
    account_id: str
    conversation_id: str
    channel: str
    chat: Chat
    type: str
    text: str
    run_id: str
    reply_to_message_id: str = ""
    sticker: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None


class SocialSendResponse(RpcModel):
    message_id: str


class CommentRequest(RpcModel):
    ai_id: str
    account_id: str
    feed_text: str
    author_name: str
    picture_urls: list[str] = Field(default_factory=list)


class CommentResponse(RpcModel):
    comment: str


class SpeechRequest(RpcModel):
    ai_id: str
    session_id: str
    text: str
    meta: dict[str, Any] = Field(default_factory=dict)
