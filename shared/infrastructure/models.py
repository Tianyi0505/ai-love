
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType


# 表示向量类型
class VectorType(UserDefinedType):
    cache_ok = True

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def get_col_spec(self, **kw) -> str:
        return f"vector({self._dim})"


class Base(DeclarativeBase):
    pass


# 表示AI档案记录
class AIProfile(Base):
    __tablename__ = "ai_profiles"
    ai_id: Mapped[str] = mapped_column(Text, primary_key=True)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    model_profile_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    voice_profile_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    avatar_profile_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示社交平台账号
class SocialAccount(Base):
    __tablename__ = "social_accounts"
    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    platform_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    credential_ref: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="offline")
    is_live_platform: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    allows_multi_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("platform", "platform_account_id"),)


# 表示账号与AI绑定
class AIAccountBinding(Base):
    __tablename__ = "ai_account_bindings"
    binding_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    bound_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    ended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


# 表示人物
class Person(Base):
    __tablename__ = "persons"
    person_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示平台身份
class PlatformIdentity(Base):
    __tablename__ = "platform_identities"
    identity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    verified_by: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("platform", "account_id", "platform_user_id"),)


# 表示群成员
class GroupMember(Base):
    __tablename__ = "group_members"
    platform: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    platform_user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nickname: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    group_card: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (
        Index(
            "idx_group_members_scope_role",
            "platform",
            "account_id",
            "chat_id",
            "role",
            postgresql_where=text("is_active"),
        ),
        Index("idx_group_members_person", "person_id", text("last_seen_at DESC")),
    )


# 表示群内称呼证据
class PersonMention(Base):
    __tablename__ = "person_mentions"
    mention_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mention_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_mention: Mapped[str] = mapped_column(Text, nullable=False)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_message_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (
        UniqueConstraint(
            "normalized_mention",
            "person_id",
            "scope_type",
            "scope_id",
            "evidence_type",
            "source_message_id",
        ),
        Index("idx_person_mentions_lookup", "normalized_mention", "scope_type", "scope_id", text("observed_at DESC")),
    )


# 表示会话
class Conversation(Base):
    __tablename__ = "conversations"
    conversation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    platform_chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    chat_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("platform", "account_id", "platform_chat_id"),)


# 表示消息
class Message(Base):
    __tablename__ = "messages"
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ai_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_identity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    retain_until: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)


# 表示直播会话
class LiveSession(Base):
    __tablename__ = "live_sessions"
    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    director_policy_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


# 表示直播会话角色
class LiveSessionActor(Base):
    __tablename__ = "live_session_actors"
    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, primary_key=True)
    stage_slot: Mapped[str] = mapped_column(Text, nullable=False)
    is_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    talk_weight: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1"))


# 表示人物关系
class PersonRelationship(Base):
    __tablename__ = "person_relationships"
    ai_id: Mapped[str] = mapped_column(Text, primary_key=True)
    person_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    familiarity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    affinity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    trust: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    importance: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    ceiling_policy: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    last_interaction_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


# 表示群关系
class GroupRelationship(Base):
    __tablename__ = "group_relationships"
    ai_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    platform_group_id: Mapped[str] = mapped_column(Text, primary_key=True)
    familiarity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    belonging: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    affinity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    activity_willingness: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    ceiling_policy: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    last_interaction_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


# 表示记忆
class Memory(Base):
    __tablename__ = "memories"
    memory_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_ai_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[object | None] = mapped_column(VectorType(1536), nullable=True)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    emotion_intensity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    dormant: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    shared_with: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    consolidated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    reference_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_strength_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_recalled_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


# 表示记忆修订
class MemoryRevision(Base):
    __tablename__ = "memory_revisions"
    revision_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    memory_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    supersedes_memory_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    changed_by: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示会话片段
class ConversationEpisode(Base):
    __tablename__ = "conversation_episodes"
    episode_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    activity_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    source_message_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default=text("'{}'"))
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (Index("idx_conversation_episodes_owner", "ai_id", "person_id", "conversation_id", text("ended_at DESC")),)


# 表示原子记忆
class MemoryAtom(Base):
    __tablename__ = "memory_atoms"
    atom_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    owner_type: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(Text, nullable=False)
    person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    episode_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_message_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default=text("'{}'"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (Index("idx_memory_atoms_owner", "ai_id", "owner_type", "owner_id", text("created_at DESC")),)


# 表示记忆文档
class MemoryDocument(Base):
    __tablename__ = "memory_documents"
    ai_id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_type: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_id: Mapped[str] = mapped_column(Text, primary_key=True)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示会话摘要
class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"
    ai_id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示审计日志
class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示扩展目录
class ExtensionCatalog(Base):
    __tablename__ = "extension_catalog"
    tool_id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示扩展绑定
class AIExtensionBinding(Base):
    __tablename__ = "ai_extension_bindings"
    ai_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tool_id: Mapped[str] = mapped_column(Text, primary_key=True)
    permission: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


# 表示模型档案
class ModelProfile(Base):
    __tablename__ = "model_profiles"
    model_profile_id: Mapped[str] = mapped_column(Text, primary_key=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示面板设置
class PanelSetting(Base):
    __tablename__ = "panel_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


# 表示执行链路
class AgentRun(Base):
    __tablename__ = "agent_runs"
    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    chat_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    chat_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    sender_person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="social")
    message_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    reply_to_message_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    outcome: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    tool_rounds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    response_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("idx_agent_runs_conversation", "ai_id", "conversation_id", text("started_at DESC")),
        Index("idx_agent_runs_message", "platform", "account_id", "message_id"),
    )


# 表示执行步骤
class AgentRunStep(Base):
    __tablename__ = "agent_run_steps"
    step_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ok")
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (Index("idx_agent_run_steps_run", "run_id", "step_index"),)
