from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class EntityContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EntityCandidate(EntityContract):
    person_id: str
    display_name: str
    confidence: float
    evidence: tuple[dict[str, Any], ...]


class EntityReference(EntityContract):
    text: str
    status: str
    person_id: str
    display_name: str
    candidates: tuple[EntityCandidate, ...]
    evidence: tuple[dict[str, Any], ...]


class EntityContext(EntityContract):
    current_sender: dict[str, Any]
    references: tuple[EntityReference, ...]
    recent_participants: tuple[dict[str, Any], ...]
