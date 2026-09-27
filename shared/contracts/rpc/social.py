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
    repeat_message_id: str = ""
    sticker: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    delivery_kind: str = ""
    source_job_id: str = ""
    claim_version: int = 0
    person_id: str = ""


class SocialSendResponse(RpcModel):
    message_id: str


class SocialSendStatusRequest(RpcModel):
    ai_id: str
    account_id: str
    run_id: str


class SocialSendStatusResponse(RpcModel):
    status: str
    message_id: str = ""
    reason_code: str = ""
    retryable: bool = False


class DeliveryInProgress(RuntimeError):
    pass


class DeliveryUnknown(RuntimeError):
    pass


class DeliveryConflict(RuntimeError):
    pass


class DeliveryRejected(RuntimeError):
    pass


class DeliveryRetryable(RuntimeError):
    pass


class StaleClaim(RuntimeError):
    pass


class ReplyUnavailable(DeliveryRejected):
    """渠道已证明引用目标无效且整次发送未发生。"""


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
