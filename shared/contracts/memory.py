from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MemoryActivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_id: str
    person_id: str
    conversation_id: str
    message_id: str
    sequence: int
    active_at: float
