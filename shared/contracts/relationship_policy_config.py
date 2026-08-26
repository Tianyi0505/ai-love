from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RelationshipConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RelationshipBounds(RelationshipConfigModel):
    quality_min: float
    quality_max: float
    score_min: float
    neutral_quality: float


class ConversationRelationshipConfig(RelationshipConfigModel):
    familiarity_delta: float
    affinity_quality_multiplier: float


class TrustRelationshipConfig(RelationshipConfigModel):
    positive_delta: float
    negative_delta: float


class GroupConversationRelationshipConfig(RelationshipConfigModel):
    familiarity_delta: float
    belonging_quality_multiplier: float
    affinity_quality_multiplier: float
    activity_quality_multiplier: float


class RelationshipSummaryConfig(RelationshipConfigModel):
    familiarity_high_threshold: float
    familiarity_medium_threshold: float
    familiarity_high_text: str
    familiarity_medium_text: str
    familiarity_low_text: str
    affinity_high_threshold: float
    affinity_positive_threshold: float
    affinity_negative_threshold: float
    affinity_high_text: str
    affinity_positive_text: str
    affinity_negative_text: str
    affinity_neutral_text: str
    trust_high_threshold: float
    trust_medium_threshold: float
    trust_high_text: str
    trust_medium_text: str
    trust_low_text: str
    template: str


class RelationshipPolicyConfig(RelationshipConfigModel):
    default_ceiling: float
    whitelist_ceiling: float
    inherit_qq_whitelist_ceiling: bool
    person_ceiling_whitelist: tuple[str | int, ...]
    group_ceiling_whitelist: tuple[str | int, ...]
    bounds: RelationshipBounds
    conversation: ConversationRelationshipConfig
    trust: TrustRelationshipConfig
    group_conversation: GroupConversationRelationshipConfig
    summary: RelationshipSummaryConfig
