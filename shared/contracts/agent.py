from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.contracts.relationship_policy_config import RelationshipPolicyConfig


class AgentDefinitionError(ValueError):
    pass


class AgentConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PersonalityConfig(AgentConfigModel):
    traits: list[str]
    speaking_style: str
    catchphrases: list[str]
    taboos: list[str]


class ExtensionConfig(AgentConfigModel):
    tool_id: str
    enabled: bool
    permission: str
    config: dict[str, Any]


class WorkPeriodConfig(AgentConfigModel):
    start: str
    end: str


class ParticipationWeights(AgentConfigModel):
    activity_willingness: float
    belonging: float
    affinity: float
    familiarity: float


class ProactiveConfig(AgentConfigModel):
    enabled: bool
    timezone: str
    private_interval_sec: int
    private_quiet_period_sec: int
    private_cooldown_sec: int
    private_min_weight: float
    group_min_score: float
    group_join_window_sec: int
    group_join_min_messages: int
    group_session_idle_sec: int
    group_session_max_sec: int
    group_session_rest_sec: int
    group_min_cooldown_sec: int
    group_max_cooldown_sec: int
    group_turn_in_flight_sec: int
    group_join_history_messages: int
    group_cooldown_curve_exponent: float
    participation_score_ceiling: float
    group_participation_weights: ParticipationWeights
    work_hours: list[WorkPeriodConfig]


class BehaviorPolicyConfig(AgentConfigModel):
    private_reply: str
    proactive: ProactiveConfig


class ModelSelectionConfig(AgentConfigModel):
    model: str


class AgentDefinition(AgentConfigModel):
    ai_id: str
    version: int
    name: str
    identity: str
    personality: PersonalityConfig
    relationship_policy: RelationshipPolicyConfig
    behavior_policy: BehaviorPolicyConfig
    extensions: list[ExtensionConfig]
    prompts: dict[str, str]
    model_profile_id: str
    voice_profile_id: str
    avatar_profile_id: str
    model_profile: ModelSelectionConfig = Field(alias="model_config")
    definition_key: str
    fingerprint: str
