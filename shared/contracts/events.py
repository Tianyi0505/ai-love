
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION = 1
_CONVERSATION_NAMESPACE = uuid.UUID("3d1da1d1-cd6d-4ccd-9f34-69469e5b906e")


def make_conversation_id(
    platform: str,
    account_id: str,
    platform_chat_id: str,
    thread_id: str = "",
) -> str:

    raw = "\x1f".join((platform, account_id, platform_chat_id, thread_id))
    return str(uuid.uuid5(_CONVERSATION_NAMESPACE, raw))


@dataclass
class EventEnvelope:
    event_type: str
    account_id: str
    payload: dict[str, Any]
    ai_id: str = ""
    person_id: str = ""
    platform_identity_id: str = ""
    conversation_id: str = ""
    session_id: str = ""
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    causation_id: str = ""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: int = field(default_factory=lambda: int(time.time() * 1000))
    schema_version: int = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "ai_id": self.ai_id,
            "account_id": self.account_id,
            "person_id": self.person_id,
            "platform_identity_id": self.platform_identity_id,
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventEnvelope":
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            event_id=data.get("event_id", "") or uuid.uuid4().hex,
            event_type=data.get("event_type", ""),
            occurred_at=int(data.get("occurred_at", 0) or int(time.time() * 1000)),
            correlation_id=data.get("correlation_id", "") or uuid.uuid4().hex,
            causation_id=data.get("causation_id", ""),
            ai_id=data.get("ai_id", ""),
            account_id=data.get("account_id", ""),
            person_id=data.get("person_id", ""),
            platform_identity_id=data.get("platform_identity_id", ""),
            conversation_id=data.get("conversation_id", ""),
            session_id=data.get("session_id", ""),
            payload=dict(data.get("payload", {})),
            metadata=dict(data.get("metadata", {})),
        )

@dataclass(frozen=True)
class InboundSocialMessage:
    account_id: str
    platform: str
    platform_message_id: str
    platform_chat_id: str
    chat_type: str
    sender_identity_id: str
    sender_platform_user_id: str
    sender_name: str
    content_type: str
    text: str = ""
    media_url: str = ""
    to_ai: bool = False
    at_ai_id: str = ""
    timestamp: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def conversation_id(self) -> str:
        return make_conversation_id(self.platform, self.account_id, self.platform_chat_id)

    def to_envelope(self, *, person_id: str = "", correlation_id: str = "") -> EventEnvelope:
        return EventEnvelope(
            event_type="social.message.received",
            account_id=self.account_id,
            person_id=person_id,
            platform_identity_id=self.sender_identity_id,
            conversation_id=self.conversation_id,
            correlation_id=correlation_id or uuid.uuid4().hex,
            payload={
                "platform": self.platform,
                "platform_message_id": self.platform_message_id,
                "platform_chat_id": self.platform_chat_id,
                "chat_type": self.chat_type,
                "sender_platform_user_id": self.sender_platform_user_id,
                "sender_name": self.sender_name,
                "content_type": self.content_type,
                "text": self.text,
                "media_url": self.media_url,
                "to_ai": self.to_ai,
                "at_ai_id": self.at_ai_id,
                "timestamp": self.timestamp,
                "metadata": self.metadata,
            },
        )


@dataclass
class TurnRequest:
    ai_id: str
    account_id: str
    conversation_id: str
    source: str
    input_text: str
    chat_type: str = ""
    person_id: str = ""
    platform_identity_id: str = ""
    session_id: str = ""
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_envelope(self) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent.turn.requested",
            ai_id=self.ai_id,
            account_id=self.account_id,
            person_id=self.person_id,
            platform_identity_id=self.platform_identity_id,
            conversation_id=self.conversation_id,
            session_id=self.session_id,
            correlation_id=self.correlation_id,
            payload={
                "source": self.source,
                "input_text": self.input_text,
                "chat_type": self.chat_type,
                "metadata": self.metadata,
            },
        )

    @classmethod
    def from_envelope(cls, envelope: EventEnvelope) -> "TurnRequest":
        payload = envelope.payload
        return cls(
            ai_id=envelope.ai_id,
            account_id=envelope.account_id,
            conversation_id=envelope.conversation_id,
            source=payload.get("source", ""),
            input_text=payload.get("input_text", ""),
            chat_type=payload.get("chat_type", ""),
            person_id=envelope.person_id,
            platform_identity_id=envelope.platform_identity_id,
            session_id=envelope.session_id,
            correlation_id=envelope.correlation_id,
            metadata=dict(payload.get("metadata", {})),
        )
