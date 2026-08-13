
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentDefinition:
    ai_id: str
    version: int
    name: str
    identity: str
    personality: dict[str, Any]
    relationship_policy: dict[str, Any]
    behavior_policy: dict[str, Any]
    extensions: list[dict[str, Any]]
    prompts: dict[str, str]
    model_profile_id: str = "default"
    voice_profile_id: str = "default"
    avatar_profile_id: str = "default"
    model_config: dict[str, Any] = field(default_factory=dict)
    definition_key: str = ""
    fingerprint: str = ""


class AgentDefinitionError(ValueError):
    pass
