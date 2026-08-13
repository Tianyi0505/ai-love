
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# 表示智能体定义数据
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
    model_profile_id: str
    voice_profile_id: str
    avatar_profile_id: str
    model_config: dict[str, Any]
    definition_key: str
    fingerprint: str


# 表示智能体定义错误异常
class AgentDefinitionError(ValueError):
    pass
