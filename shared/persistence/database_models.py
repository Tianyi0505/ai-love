from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# 表示AI档案记录
class AIProfile(Base):
    __tablename__ = "ai_profiles"
    profile_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    model_profile_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    voice_profile_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    avatar_profile_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示社交平台账号
class SocialAccount(Base):
    __tablename__ = "social_accounts"
    social_account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
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
    group_member_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nickname: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    group_card: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (
        UniqueConstraint("platform", "account_id", "chat_id", "platform_user_id"),
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


# 表示称呼与人物之间的聚合 LFU 频率
class PersonMentionFrequency(Base):
    __tablename__ = "person_mention_frequencies"
    person_mention_frequency_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    normalized_mention: Mapped[str] = mapped_column(Text, nullable=False)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    lfu_state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (
        UniqueConstraint("normalized_mention", "person_id", "scope_type", "scope_id"),
        Index("idx_person_mention_frequencies_lookup", "normalized_mention", "scope_type", "scope_id"),
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
    live_session_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    director_policy_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


# 表示直播会话角色
class LiveSessionActor(Base):
    __tablename__ = "live_session_actors"
    live_session_actor_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    stage_slot: Mapped[str] = mapped_column(Text, nullable=False)
    is_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    talk_weight: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1"))
    __table_args__ = (UniqueConstraint("session_id", "ai_id"),)


# 表示人物关系
class PersonRelationship(Base):
    __tablename__ = "person_relationships"
    person_relationship_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    familiarity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    affinity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    trust: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    importance: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    lfu_state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ceiling_policy: Mapped[str] = mapped_column(Text, nullable=False)
    last_interaction_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("ai_id", "person_id"),)


# 表示群关系
class GroupRelationship(Base):
    __tablename__ = "group_relationships"
    group_relationship_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    platform_group_id: Mapped[str] = mapped_column(Text, nullable=False)
    familiarity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    belonging: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    affinity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    activity_willingness: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    lfu_state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ceiling_policy: Mapped[str] = mapped_column(Text, nullable=False)
    last_interaction_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("ai_id", "account_id", "platform_group_id"),)


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
    embedding: Mapped[object | None] = mapped_column(Vector(), nullable=True)
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
    last_strength_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_recalled_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lfu_state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


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
    source_message_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default=text("'{}'")
    )
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (
        Index("idx_conversation_episodes_owner", "ai_id", "person_id", "conversation_id", text("ended_at DESC")),
    )


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
    source_message_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    consolidated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lfu_state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    __table_args__ = (Index("idx_memory_atoms_owner", "ai_id", "owner_type", "owner_id", text("created_at DESC")),)


# 表示记忆文档
class MemoryDocument(Base):
    __tablename__ = "memory_documents"
    memory_document_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    owner_type: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(Text, nullable=False)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    lfu_state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("ai_id", "owner_type", "owner_id"),)


# 表示会话摘要
class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"
    conversation_summary_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("ai_id", "conversation_id"),)


class Sticker(Base):
    __tablename__ = "stickers"
    sticker_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    match_quality: Mapped[float] = mapped_column(Float, nullable=False)
    usage_strength: Mapped[float] = mapped_column(Float, nullable=False)
    boost_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QZoneCommentedFeed(Base):
    __tablename__ = "qzone_commented_feeds"
    qzone_commented_feed_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    feed_id: Mapped[str] = mapped_column(Text, nullable=False)
    commented_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("account_id", "feed_id"),)


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
    extension_catalog_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tool_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider_id: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示扩展绑定
class AIExtensionBinding(Base):
    __tablename__ = "ai_extension_bindings"
    ai_extension_binding_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ai_id: Mapped[str] = mapped_column(Text, nullable=False)
    tool_id: Mapped[str] = mapped_column(Text, nullable=False)
    permission: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    __table_args__ = (UniqueConstraint("ai_id", "tool_id"),)


# 表示模型档案
class ModelProfile(Base):
    __tablename__ = "model_profiles"
    model_profile_record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_profile_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# 表示面板设置
class PanelSetting(Base):
    __tablename__ = "panel_settings"
    panel_setting_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
