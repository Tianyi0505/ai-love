
from __future__ import annotations

from dataclasses import dataclass
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.contracts.relationship import GroupRelationship, PersonRelationship
from shared.infrastructure.database import Database
from shared.infrastructure import models as m
from shared.infrastructure.snowflake import new_snowflake_id


# 表示AI档案记录数据
@dataclass(frozen=True)
class AIProfileRecord:
    ai_id: str
    definition_version: int


# 管理AI档案存储库持久化
class AIProfileRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 列出启用的配置
    async def list_active(self) -> list[AIProfileRecord]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(m.AIProfile.ai_id, m.AIProfile.definition_version)
                .where(m.AIProfile.status == "active")
                .order_by(m.AIProfile.ai_id)
            )
            return [AIProfileRecord(row.ai_id, row.definition_version) for row in rows]


# 管理账号归属存储库持久化
class AccountOwnershipRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 获取社交账号所属智能体
    async def owner_for_social_account(self, account_id: str) -> str | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(m.AIAccountBinding.ai_id)
                    .select_from(m.AIAccountBinding)
                    .join(m.SocialAccount, m.SocialAccount.account_id == m.AIAccountBinding.account_id)
                    .where(
                        m.AIAccountBinding.account_id == account_id,
                        m.AIAccountBinding.ended_at.is_(None),
                        m.SocialAccount.allows_multi_ai.is_(False),
                    )
                )
            ).first()
            return row.ai_id if row else None

    # 选择直播互动候选人
    async def live_candidates(self, account_id: str) -> list[str]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(m.AIAccountBinding.ai_id)
                .where(m.AIAccountBinding.account_id == account_id, m.AIAccountBinding.ended_at.is_(None))
                .order_by(m.AIAccountBinding.ai_id)
            )
            return [row for (row,) in rows]

    # 列出智能体绑定的账号
    async def accounts_for_ai(self, ai_id: str) -> list[str]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(m.AIAccountBinding.account_id)
                .where(m.AIAccountBinding.ai_id == ai_id, m.AIAccountBinding.ended_at.is_(None))
                .order_by(m.AIAccountBinding.bound_at)
            )
            return [row for (row,) in rows]


# 管理身份存储库持久化
class IdentityRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 解析联系人
    async def resolve_person(
        self,
        platform: str,
        account_id: str,
        platform_user_id: str,
    ) -> tuple[str, str] | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(m.PlatformIdentity.identity_id, m.PlatformIdentity.person_id).where(
                        m.PlatformIdentity.platform == platform,
                        m.PlatformIdentity.account_id == account_id,
                        m.PlatformIdentity.platform_user_id == platform_user_id,
                    )
                )
            ).first()
            if row is None:
                return None
            return str(row.identity_id), str(row.person_id)

    # 解析或创建平台身份
    async def resolve_or_create(
        self,
        platform: str,
        account_id: str,
        platform_user_id: str,
        display_name: str = "",
    ) -> tuple[str, str]:
        existing = await self.resolve_person(platform, account_id, platform_user_id)
        if existing is not None:
            if display_name:
                async with self._db.session() as session:
                    await session.execute(
                        update(m.Person)
                        .where(
                            m.Person.person_id == int(existing[1]),
                            or_(m.Person.display_name.is_(None), m.Person.display_name == ""),
                        )
                        .values(display_name=display_name)
                    )
                    await session.commit()
            return existing
        identity_id = int(new_snowflake_id())
        person_id = int(new_snowflake_id())
        async with self._db.session() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        select(m.PlatformIdentity.identity_id, m.PlatformIdentity.person_id)
                        .where(
                            m.PlatformIdentity.platform == platform,
                            m.PlatformIdentity.account_id == account_id,
                            m.PlatformIdentity.platform_user_id == platform_user_id,
                        )
                        .with_for_update()
                    )
                ).first()
                if row is not None:
                    return str(row.identity_id), str(row.person_id)
                session.add(m.Person(person_id=person_id, display_name=display_name))
                session.add(
                    m.PlatformIdentity(
                        identity_id=identity_id,
                        person_id=person_id,
                        platform=platform,
                        account_id=account_id,
                        platform_user_id=platform_user_id,
                        verified_by="platform-observed",
                    )
                )
        return str(identity_id), str(person_id)

    # 批量解析群成员，避免逐成员往返数据库
    async def resolve_or_create_many(
        self,
        platform: str,
        account_id: str,
        people: list[dict],
    ) -> dict[str, tuple[str, str]]:
        user_ids = [str(item.get("platform_user_id") or "") for item in people]
        user_ids = [item for item in user_ids if item]
        if not user_ids:
            return {}
        async with self._db.session() as session:
            async with session.begin():
                rows = await session.execute(
                    select(
                        m.PlatformIdentity.identity_id,
                        m.PlatformIdentity.person_id,
                        m.PlatformIdentity.platform_user_id,
                    ).where(
                        m.PlatformIdentity.platform == platform,
                        m.PlatformIdentity.account_id == account_id,
                        m.PlatformIdentity.platform_user_id.in_(user_ids),
                    )
                )
                result = {
                    str(row.platform_user_id): (str(row.identity_id), str(row.person_id))
                    for row in rows
                }
                for person in people:
                    user_id = str(person.get("platform_user_id") or "")
                    if not user_id or user_id in result:
                        continue
                    identity_id = int(new_snowflake_id())
                    person_id = int(new_snowflake_id())
                    display_name = str(
                        person.get("group_card") or person.get("nickname") or user_id
                    )
                    session.add(m.Person(person_id=person_id, display_name=display_name))
                    session.add(
                        m.PlatformIdentity(
                            identity_id=identity_id,
                            person_id=person_id,
                            platform=platform,
                            account_id=account_id,
                            platform_user_id=user_id,
                            verified_by="platform-observed",
                        )
                    )
                    result[user_id] = (str(identity_id), str(person_id))
        return result


# 管理会话存储库持久化
class ConversationRepository:

    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 获取或创建会话
    async def get_or_create(
        self,
        platform: str,
        account_id: str,
        platform_chat_id: str,
        chat_type: str,
    ) -> str:
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.Conversation)
                .values(
                    conversation_id=int(new_snowflake_id()),
                    platform=platform,
                    account_id=account_id,
                    platform_chat_id=platform_chat_id,
                    chat_type=chat_type,
                )
                .on_conflict_do_update(
                    index_elements=[
                        m.Conversation.platform,
                        m.Conversation.account_id,
                        m.Conversation.platform_chat_id,
                    ],
                    set_={"chat_type": chat_type},
                )
                .returning(m.Conversation.conversation_id)
            )
            conversation_id = (await session.execute(stmt)).scalar_one()
            await session.commit()
            return str(conversation_id)

    # 记录入站消息
    async def record_inbound(self, message, ai_id: str) -> str:
        conversation_id = await self.get_or_create(
            message.platform,
            message.account_id,
            message.chat.chat_id,
            message.chat.chat_type.value,
        )
        platform_message_id = str(message.message_id or "")
        source_key = (
            f"in:{message.platform}:{message.account_id}:{platform_message_id}"
            if platform_message_id
            else None
        )
        occurred_at = datetime.fromtimestamp(
            float(message.timestamp or 0) or time.time(), tz=timezone.utc
        )
        content = {
            "type": message.type.value,
            "text": message.text,
            "media_url": message.media_url,
            "media_desc": message.media_desc,
            "media_urls": message.media_urls,
            "media_descs": message.media_descs,
            "platform_message_id": platform_message_id,
        }
        identity_id = message.meta.get("platform_identity_id") or None
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.Message)
                .values(
                    message_id=int(new_snowflake_id()),
                    conversation_id=int(conversation_id),
                    ai_id=ai_id,
                    platform_identity_id=int(identity_id) if identity_id else None,
                    role="user",
                    content=content,
                    occurred_at=occurred_at,
                    retain_until=occurred_at + timedelta(days=180),
                    correlation_id=platform_message_id or "",
                    source_key=source_key,
                )
                .on_conflict_do_nothing(index_elements=[m.Message.source_key])
            )
            await session.execute(stmt)
            await session.commit()
        return conversation_id

    # 记录出站消息
    async def record_outbound(self, request: dict, result: dict, ai_id: str) -> str:
        chat = request.get("chat", {})
        platform = str(request.get("channel") or "qq")
        account_id = str(request.get("account_id") or "")
        conversation_id = await self.get_or_create(
            platform,
            account_id,
            str(chat.get("chat_id") or ""),
            str(chat.get("chat_type") or "private"),
        )
        platform_message_id = str(result.get("message_id") or "")
        source_key = (
            f"out:{platform}:{account_id}:{platform_message_id}"
            if platform_message_id
            else None
        )
        content = {
            "type": str(request.get("type") or "text"),
            "text": str(request.get("text") or ""),
            "has_sticker": bool(request.get("sticker")),
            "has_voice": bool(request.get("voice")),
            "platform_message_id": platform_message_id,
        }
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.Message)
                .values(
                    message_id=int(new_snowflake_id()),
                    conversation_id=int(conversation_id),
                    ai_id=ai_id,
                    role="assistant",
                    content=content,
                    occurred_at=datetime.now(timezone.utc),
                    retain_until=datetime.now(timezone.utc) + timedelta(days=180),
                    correlation_id=platform_message_id or "",
                    source_key=source_key,
                )
                .on_conflict_do_nothing(index_elements=[m.Message.source_key])
            )
            await session.execute(stmt)
            await session.commit()
        return conversation_id


# 管理关系存储库持久化
class RelationshipRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 获取联系人
    async def get_person(self, ai_id: str, person_id: str) -> PersonRelationship:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(
                        m.PersonRelationship.familiarity,
                        m.PersonRelationship.affinity,
                        m.PersonRelationship.trust,
                        m.PersonRelationship.importance,
                    ).where(
                        m.PersonRelationship.ai_id == ai_id,
                        m.PersonRelationship.person_id == int(person_id),
                    )
                )
            ).first()
        return PersonRelationship(**row._mapping) if row else PersonRelationship()

    # 保存联系人
    async def save_person(self, ai_id: str, person_id: str, relationship, ceiling_policy: str = "default") -> None:
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.PersonRelationship)
                .values(
                    ai_id=ai_id,
                    person_id=int(person_id),
                    familiarity=relationship.familiarity,
                    affinity=relationship.affinity,
                    trust=relationship.trust,
                    importance=relationship.importance,
                    ceiling_policy=ceiling_policy,
                    last_interaction_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=[
                        m.PersonRelationship.ai_id,
                        m.PersonRelationship.person_id,
                    ],
                    set_={
                        "familiarity": relationship.familiarity,
                        "affinity": relationship.affinity,
                        "trust": relationship.trust,
                        "importance": relationship.importance,
                        "ceiling_policy": ceiling_policy,
                        "last_interaction_at": datetime.now(timezone.utc),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    # 确保联系人
    async def ensure_person(self, ai_id: str, person_id: str, ceiling_policy: str = "default") -> None:
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.PersonRelationship)
                .values(
                    ai_id=ai_id,
                    person_id=int(person_id),
                    familiarity=0,
                    affinity=0,
                    trust=0,
                    importance=0,
                    ceiling_policy=ceiling_policy,
                )
                .on_conflict_do_update(
                    index_elements=[
                        m.PersonRelationship.ai_id,
                        m.PersonRelationship.person_id,
                    ],
                    set_={"ceiling_policy": ceiling_policy},
                )
            )
            await session.execute(stmt)
            await session.commit()

    # 获取群聊
    async def get_group(self, ai_id: str, account_id: str, group_id: str) -> GroupRelationship:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(
                        m.GroupRelationship.familiarity,
                        m.GroupRelationship.belonging,
                        m.GroupRelationship.affinity,
                        m.GroupRelationship.activity_willingness,
                    ).where(
                        m.GroupRelationship.ai_id == ai_id,
                        m.GroupRelationship.account_id == account_id,
                        m.GroupRelationship.platform_group_id == group_id,
                    )
                )
            ).first()
        return GroupRelationship(**row._mapping) if row else GroupRelationship()

    # 保存群聊
    async def save_group(self, ai_id: str, account_id: str, group_id: str, relationship, ceiling_policy: str = "default") -> None:
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.GroupRelationship)
                .values(
                    ai_id=ai_id,
                    account_id=account_id,
                    platform_group_id=group_id,
                    familiarity=relationship.familiarity,
                    belonging=relationship.belonging,
                    affinity=relationship.affinity,
                    activity_willingness=relationship.activity_willingness,
                    ceiling_policy=ceiling_policy,
                    last_interaction_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=[
                        m.GroupRelationship.ai_id,
                        m.GroupRelationship.account_id,
                        m.GroupRelationship.platform_group_id,
                    ],
                    set_={
                        "familiarity": relationship.familiarity,
                        "belonging": relationship.belonging,
                        "affinity": relationship.affinity,
                        "activity_willingness": relationship.activity_willingness,
                        "ceiling_policy": ceiling_policy,
                        "last_interaction_at": datetime.now(timezone.utc),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    # 列出联系人列表
    async def list_people(self, ai_id: str) -> list[dict]:
        latest_user = (
            select(m.PlatformIdentity.platform_user_id)
            .where(m.PlatformIdentity.person_id == m.PersonRelationship.person_id)
            .order_by(m.PlatformIdentity.verified_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        latest_account = (
            select(m.PlatformIdentity.account_id)
            .where(m.PlatformIdentity.person_id == m.PersonRelationship.person_id)
            .order_by(m.PlatformIdentity.verified_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        async with self._db.session() as session:
            rows = await session.execute(
                select(
                    m.PersonRelationship.person_id,
                    m.Person.display_name,
                    latest_user.label("user_id"),
                    latest_account.label("account_id"),
                    m.PersonRelationship.familiarity,
                    m.PersonRelationship.affinity,
                    m.PersonRelationship.trust,
                    m.PersonRelationship.importance,
                    m.PersonRelationship.last_interaction_at,
                )
                .select_from(m.PersonRelationship)
                .join(m.Person, m.Person.person_id == m.PersonRelationship.person_id)
                .where(m.PersonRelationship.ai_id == ai_id)
                .order_by(m.PersonRelationship.last_interaction_at.desc())
            )
            return [
                {
                    "person_id": str(row.person_id),
                    "display_name": row.display_name,
                    "user_id": row.user_id or "",
                    "account_id": row.account_id or "",
                    "familiarity": float(row.familiarity),
                    "affinity": float(row.affinity),
                    "trust": float(row.trust),
                    "importance": float(row.importance),
                    "last_interaction_at": row.last_interaction_at,
                }
                for row in rows
            ]
