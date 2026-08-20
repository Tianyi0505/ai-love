from __future__ import annotations

from datetime import datetime

from shared.contracts.rpc.rpc_model import RpcModel


class RelationshipChatRequest(RpcModel):
    ai_id: str
    person_id: str
    platform_user_id: str
    account_id: str
    chat_type: str
    group_id: str
    quality: float


class RelationshipSummaryRequest(RpcModel):
    ai_id: str
    person_id: str


class RelationshipSummaryResponse(RpcModel):
    summary: str


class RelationshipListRequest(RpcModel):
    ai_id: str


class PersonRelationshipRecord(RpcModel):
    person_id: str
    display_name: str
    user_id: str
    account_id: str
    familiarity: float
    affinity: float
    trust: float
    importance: float
    last_interaction_at: datetime | None
    priority_contact: bool


class RelationshipListResponse(RpcModel):
    relationships: list[PersonRelationshipRecord]


class GroupRelationshipRequest(RpcModel):
    ai_id: str
    account_id: str
    group_id: str


class GroupRelationshipData(RpcModel):
    familiarity: float
    belonging: float
    affinity: float
    activity_willingness: float


class GroupRelationshipResponse(RpcModel):
    relationship: GroupRelationshipData
