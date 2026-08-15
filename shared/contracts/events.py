
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from shared.infrastructure.snowflake import new_snowflake_id


SCHEMA_VERSION = 1


# 封装消息总线事件
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
    correlation_id: str = field(default_factory=new_snowflake_id)
    causation_id: str = ""
    event_id: str = field(default_factory=new_snowflake_id)
    occurred_at: int = field(default_factory=lambda: int(time.time() * 1000))
    schema_version: int = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    # 转换为字典
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

    # 从字典创建实例
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventEnvelope":
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            event_id=data.get("event_id", "") or new_snowflake_id(),
            event_type=data.get("event_type", ""),
            occurred_at=int(data.get("occurred_at", 0) or int(time.time() * 1000)),
            correlation_id=data.get("correlation_id", "") or new_snowflake_id(),
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

# 表示轮次请求数据
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
    correlation_id: str = field(default_factory=new_snowflake_id)
    metadata: dict[str, Any] = field(default_factory=dict)

    # 转换为事件信封
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

    # 从事件信封创建实例
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
