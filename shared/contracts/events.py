from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.infrastructure.snowflake_id_generator import snowflake_ids


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_id: str
    account_id: str
    conversation_id: str
    source: str
    input_text: str
    chat_type: str = ""
    person_id: str = ""
    platform_identity_id: str = ""
    session_id: str = ""
    correlation_id: str = Field(default_factory=lambda: str(snowflake_ids().next_id()))
    metadata: dict[str, Any] = Field(default_factory=dict)
