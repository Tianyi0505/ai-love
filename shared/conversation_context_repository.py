from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, func, or_, select

from shared import database_models as m
from shared.contracts.rpc.grounding import HistoryMessage
from shared.contracts.tools import ToolExecutionContext
from shared.database import Database


class ConversationContextRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def matches(self, context: ToolExecutionContext) -> bool:
        if not (
            context.ai_id
            and context.account_id
            and context.conversation_id
            and context.platform
            and context.chat_type
            and context.chat_id
        ):
            return False
        async with self._db.session() as session:
            result = await session.execute(
                select(
                    select(m.Conversation.conversation_id)
                    .where(
                        m.Conversation.conversation_id == int(context.conversation_id),
                        m.Conversation.platform == context.platform,
                        m.Conversation.account_id == context.account_id,
                        m.Conversation.platform_chat_id == context.chat_id,
                        m.Conversation.chat_type == context.chat_type,
                    )
                    .exists()
                )
            )
            return bool(result.scalar())

    async def recent_participants(
        self,
        context: ToolExecutionContext,
        limit: int,
        lookback_sec: float,
    ) -> tuple[dict, ...]:
        if not context.conversation_id or not context.ai_id:
            return ()
        async with self._db.session() as session:
            rows = await session.execute(
                select(
                    m.PlatformIdentity.person_id.label("person_id"),
                    func.coalesce(
                        func.nullif(m.GroupMember.group_card, ""),
                        func.nullif(m.GroupMember.nickname, ""),
                        func.nullif(m.Person.display_name, ""),
                        "",
                    ).label("display_name"),
                    func.nullif(m.GroupMember.group_card, "").label("group_card"),
                    m.GroupMember.role.label("role"),
                    func.max(m.Message.message_id).label("last_message_id"),
                    func.max(m.Message.occurred_at).label("last_seen_at"),
                )
                .select_from(m.Message)
                .join(m.PlatformIdentity, m.PlatformIdentity.identity_id == m.Message.platform_identity_id)
                .join(m.Person, m.Person.person_id == m.PlatformIdentity.person_id)
                .outerjoin(
                    m.GroupMember,
                    and_(
                        m.GroupMember.person_id == m.PlatformIdentity.person_id,
                        m.GroupMember.platform == context.platform,
                        m.GroupMember.account_id == context.account_id,
                        m.GroupMember.chat_id == context.chat_id,
                        m.GroupMember.is_active.is_(True),
                    ),
                )
                .where(
                    m.Message.conversation_id == int(context.conversation_id),
                    m.Message.ai_id == context.ai_id,
                    m.Message.role == "user",
                    m.Message.occurred_at >= datetime.now(timezone.utc) - timedelta(seconds=lookback_sec),
                )
                .group_by(
                    m.PlatformIdentity.person_id,
                    m.Person.display_name,
                    m.GroupMember.group_card,
                    m.GroupMember.nickname,
                    m.GroupMember.role,
                )
                .order_by(desc("last_seen_at"))
                .limit(limit)
            )
            return tuple(
                {
                    "person_id": str(row.person_id),
                    "display_name": row.display_name or "",
                    "group_card": row.group_card or "",
                    "roles": [row.role] if row.role else [],
                    "last_message_id": str(row.last_message_id),
                    "last_seen_at": str(row.last_seen_at),
                }
                for row in rows
            )

    async def search_group_history(
        self,
        context: ToolExecutionContext,
        query: str,
        limit: int,
        lookback_sec: float,
    ) -> list[HistoryMessage]:
        pattern = query.strip()
        async with self._db.session() as session:
            rows = await session.execute(
                select(
                    m.Message.message_id,
                    m.Message.role,
                    m.Message.content,
                    m.Message.occurred_at,
                    m.PlatformIdentity.person_id.label("person_id"),
                    func.coalesce(
                        func.nullif(m.GroupMember.group_card, ""),
                        func.nullif(m.GroupMember.nickname, ""),
                        func.nullif(m.Person.display_name, ""),
                        "",
                    ).label("display_name"),
                )
                .select_from(m.Message)
                .outerjoin(m.PlatformIdentity, m.PlatformIdentity.identity_id == m.Message.platform_identity_id)
                .outerjoin(m.Person, m.Person.person_id == m.PlatformIdentity.person_id)
                .outerjoin(
                    m.GroupMember,
                    and_(
                        m.GroupMember.person_id == m.PlatformIdentity.person_id,
                        m.GroupMember.platform == context.platform,
                        m.GroupMember.account_id == context.account_id,
                        m.GroupMember.chat_id == context.chat_id,
                    ),
                )
                .where(
                    m.Message.conversation_id == int(context.conversation_id),
                    m.Message.ai_id == context.ai_id,
                    m.Message.occurred_at >= datetime.now(timezone.utc) - timedelta(seconds=lookback_sec),
                    or_(
                        pattern == "",
                        func.coalesce(m.Message.content["text"].astext, "").ilike(f"%{pattern}%"),
                    ),
                )
                .order_by(m.Message.occurred_at.desc())
                .limit(limit)
            )
        return [
            HistoryMessage.model_validate(
                {
                    "message_id": str(row.message_id),
                    "sender": {
                        "person_id": str(row.person_id) if row.person_id else "",
                        "display_name": row.display_name or ("AI" if row.role == "assistant" else ""),
                        "role": row.role,
                    },
                    "text": str(row.content["text"]),
                    "occurred_at": row.occurred_at,
                }
            )
            for row in rows
        ]
