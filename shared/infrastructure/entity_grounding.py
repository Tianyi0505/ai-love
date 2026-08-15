from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.contracts.entity import EntityCandidate, EntityContext, EntityReference
from shared.contracts.tools import ToolExecutionContext
from shared.infrastructure.database import Database
from shared.infrastructure import models as m
from shared.infrastructure.snowflake import new_snowflake_id


_ROLE_NAMES = {
    "群主": ("owner",),
    "管理员": ("admin",),
    "群管理员": ("admin",),
}


def normalize_mention(value: str) -> str:
    return re.sub(r"[\s@，,。.!！?？:：]+", "", value).casefold()


# 管理群成员快照与称呼证据
class EntityGroundingRepository:
    def __init__(self, db: Database, evidence_half_life_sec: float) -> None:
        self._db = db
        self._evidence_half_life_sec = evidence_half_life_sec

    async def context_matches(self, context: ToolExecutionContext) -> bool:
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
            row = await session.execute(
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
            return bool(row.scalar())

    async def sync_group_members(
        self,
        platform: str,
        account_id: str,
        chat_id: str,
        members: list[dict],
    ) -> None:
        async with self._db.session() as session:
            async with session.begin():
                await session.execute(
                    update(m.GroupMember)
                    .where(
                        m.GroupMember.platform == platform,
                        m.GroupMember.account_id == account_id,
                        m.GroupMember.chat_id == chat_id,
                    )
                    .values(is_active=False)
                )
                for member in members:
                    values = {
                        "platform": platform,
                        "account_id": account_id,
                        "chat_id": chat_id,
                        "platform_user_id": str(member["platform_user_id"]),
                        "person_id": int(member["person_id"]),
                        "nickname": str(member.get("nickname") or ""),
                        "group_card": str(member.get("group_card") or ""),
                        "role": str(member.get("role") or "member"),
                        "is_active": True,
                    }
                    stmt = pg_insert(m.GroupMember).values(**values).on_conflict_do_update(
                        index_elements=[
                            m.GroupMember.platform,
                            m.GroupMember.account_id,
                            m.GroupMember.chat_id,
                            m.GroupMember.platform_user_id,
                        ],
                        set_={**values, "last_seen_at": func.now()},
                    )
                    await session.execute(stmt)

    async def record_mention_evidence(
        self,
        *,
        mention_text: str,
        person_id: str,
        scope_type: str,
        scope_id: str,
        conversation_id: str = "",
        source_message_id: str = "",
        evidence_type: str,
        confidence: float,
    ) -> None:
        normalized = normalize_mention(mention_text)
        if not normalized or not person_id:
            return
        confidence = max(0.0, min(1.0, confidence))
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.PersonMention)
                .values(
                    mention_id=int(new_snowflake_id()),
                    mention_text=mention_text.strip(),
                    normalized_mention=normalized,
                    person_id=int(person_id),
                    scope_type=scope_type,
                    scope_id=scope_id,
                    conversation_id=int(conversation_id) if conversation_id else None,
                    source_message_id=source_message_id,
                    evidence_type=evidence_type,
                    confidence=confidence,
                )
                .on_conflict_do_update(
                    index_elements=[
                        m.PersonMention.normalized_mention,
                        m.PersonMention.person_id,
                        m.PersonMention.scope_type,
                        m.PersonMention.scope_id,
                        m.PersonMention.evidence_type,
                        m.PersonMention.source_message_id,
                    ],
                    set_={
                        "confidence": func.greatest(m.PersonMention.confidence, confidence),
                        "observed_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def resolve_people(
        self,
        context: ToolExecutionContext,
        mention: str,
        limit: int,
    ) -> dict:
        normalized = normalize_mention(mention)
        if not normalized:
            return {"mention": mention, "candidates": []}

        candidates: dict[str, dict] = {}
        roles = _ROLE_NAMES.get(normalized)
        async with self._db.session() as session:
            display_name_expr = func.coalesce(
                func.nullif(m.GroupMember.group_card, ""),
                func.nullif(m.GroupMember.nickname, ""),
                m.Person.display_name,
                "",
            )
            if roles:
                rows = await session.execute(
                    select(
                        m.GroupMember.person_id,
                        display_name_expr.label("display_name"),
                        m.GroupMember.role,
                    )
                    .select_from(m.GroupMember)
                    .join(m.Person, m.Person.person_id == m.GroupMember.person_id)
                    .where(
                        m.GroupMember.platform == context.platform,
                        m.GroupMember.account_id == context.account_id,
                        m.GroupMember.chat_id == context.chat_id,
                        m.GroupMember.is_active.is_(True),
                        m.GroupMember.role.in_(list(roles)),
                    )
                    .order_by(m.GroupMember.role, display_name_expr)
                )
                role_rows = list(rows)
                for row in role_rows:
                    self._add_candidate(
                        candidates,
                        row.person_id,
                        row.display_name,
                        1.0 if len(role_rows) == 1 else 0.9,
                        {"type": "group_role", "role": row.role},
                    )
            else:
                rows = await session.execute(
                    select(
                        m.GroupMember.person_id,
                        display_name_expr.label("display_name"),
                        m.GroupMember.platform_user_id,
                        m.GroupMember.nickname,
                        m.GroupMember.group_card,
                    )
                    .select_from(m.GroupMember)
                    .join(m.Person, m.Person.person_id == m.GroupMember.person_id)
                    .where(
                        m.GroupMember.platform == context.platform,
                        m.GroupMember.account_id == context.account_id,
                        m.GroupMember.chat_id == context.chat_id,
                        m.GroupMember.is_active.is_(True),
                        or_(
                            func.lower(m.GroupMember.platform_user_id)
                            == func.lower(mention.strip().lstrip("@")),
                            func.lower(m.GroupMember.nickname) == func.lower(mention.strip()),
                            func.lower(m.GroupMember.group_card) == func.lower(mention.strip()),
                            func.lower(m.Person.display_name) == func.lower(mention.strip()),
                        ),
                    )
                )
                for row in rows:
                    if row.platform_user_id.casefold() == mention.strip().lstrip("@").casefold():
                        confidence, evidence_type = 1.0, "platform_identity"
                    elif str(row.group_card).casefold() == mention.strip().casefold():
                        confidence, evidence_type = 0.98, "group_card"
                    else:
                        confidence, evidence_type = 0.95, "display_name"
                    self._add_candidate(
                        candidates,
                        row.person_id,
                        row.display_name,
                        confidence,
                        {"type": evidence_type},
                    )

                evidence_rows = await session.execute(
                    select(
                        m.PersonMention.person_id,
                        m.Person.display_name,
                        func.max(m.PersonMention.confidence).label("confidence"),
                        func.count().label("evidence_count"),
                        func.max(m.PersonMention.observed_at).label("last_seen_at"),
                        func.extract(
                            "epoch", func.now() - func.max(m.PersonMention.observed_at)
                        ).label("age_sec"),
                    )
                    .select_from(m.PersonMention)
                    .join(m.Person, m.Person.person_id == m.PersonMention.person_id)
                    .join(
                        m.GroupMember,
                        and_(
                            m.GroupMember.person_id == m.PersonMention.person_id,
                            m.GroupMember.platform == context.platform,
                            m.GroupMember.account_id == context.account_id,
                            m.GroupMember.chat_id == context.chat_id,
                            m.GroupMember.is_active.is_(True),
                        ),
                    )
                    .where(
                        m.PersonMention.normalized_mention == normalized,
                        or_(
                            and_(
                                m.PersonMention.scope_type == "group",
                                m.PersonMention.scope_id == context.chat_id,
                            ),
                            and_(
                                m.PersonMention.scope_type == "conversation",
                                m.PersonMention.scope_id == context.conversation_id,
                            ),
                            m.PersonMention.scope_type == "global",
                        ),
                    )
                    .group_by(m.PersonMention.person_id, m.Person.display_name)
                    .order_by(desc("confidence"), desc("evidence_count"), desc("last_seen_at"))
                    .limit(limit)
                )
                for row in evidence_rows:
                    recency = 0.5 ** (
                        max(0.0, float(row.age_sec or 0.0)) / self._evidence_half_life_sec
                    )
                    confidence = min(
                        0.99,
                        float(row.confidence) * recency
                        + min(0.12, int(row.evidence_count) * 0.02),
                    )
                    self._add_candidate(
                        candidates,
                        row.person_id,
                        row.display_name,
                        confidence,
                        {
                            "type": "mention_evidence",
                            "count": int(row.evidence_count),
                            "last_seen_at": str(row.last_seen_at),
                        },
                    )

        ordered = sorted(
            candidates.values(),
            key=lambda item: (-item["confidence"], item["display_name"], item["person_id"]),
        )[:limit]
        return {"mention": mention, "candidates": ordered}

    async def fast_ground(
        self,
        context: ToolExecutionContext,
        message,
        recent_participants_limit: int = 6,
        recent_lookback_sec: int = 86400,
    ) -> EntityContext:
        sender = (
            {
                "person_id": context.sender_person_id,
                "display_name": message.sender.name or message.sender.user_id,
            }
            if context.sender_person_id
            else {}
        )
        references: list[EntityReference] = []
        seen = {context.sender_person_id}

        for target in message.meta.get("at_user_ids", []):
            if message.to_ai and str(target) == message.at_user_id:
                continue
            result = await self.resolve_people(context, str(target), 2)
            references.append(self._mention_from_result(f"@{target}", "explicit_at", result))
            for candidate in result["candidates"][:1]:
                seen.add(candidate["person_id"])

        if message.quote_ref and message.quote_ref.sender.user_id:
            result = await self.resolve_people(context, message.quote_ref.sender.user_id, 2)
            references.append(self._mention_from_result("引用消息发送者", "reply_to", result))

        text = message.text or ""
        matched_roles: list[str] = []
        for role_name in sorted(_ROLE_NAMES, key=len, reverse=True):
            if role_name not in text:
                continue
            if any(role_name in existing for existing in matched_roles):
                continue
            result = await self.resolve_people(context, role_name, 3)
            references.append(self._mention_from_result(role_name, "group_role", result))
            matched_roles.append(role_name)

        async with self._db.session() as session:
            name_rows = await session.execute(
                select(
                    m.GroupMember.person_id,
                    func.coalesce(
                        func.nullif(m.GroupMember.group_card, ""),
                        func.nullif(m.GroupMember.nickname, ""),
                        "",
                    ).label("name"),
                ).where(
                    m.GroupMember.platform == context.platform,
                    m.GroupMember.account_id == context.account_id,
                    m.GroupMember.chat_id == context.chat_id,
                    m.GroupMember.is_active.is_(True),
                    or_(
                        func.length(m.GroupMember.group_card) >= 2,
                        func.length(m.GroupMember.nickname) >= 2,
                    ),
                )
            )
            matched_names: dict[str, list[str]] = {}
            for row in name_rows:
                name = str(row.name or "")
                if name and name in text:
                    matched_names.setdefault(name, []).append(str(row.person_id))
        selected_names: list[str] = []
        for name in sorted(matched_names, key=len, reverse=True):
            if any(name in existing for existing in selected_names):
                continue
            selected_names.append(name)
            person_ids = matched_names[name]
            unique_ids = tuple(dict.fromkeys(person_ids))
            if len(unique_ids) == 1 and unique_ids[0] not in seen:
                references.append(
                    EntityReference(
                        text=name,
                        status="resolved",
                        person_id=unique_ids[0],
                        evidence=({"type": "group_card_match", "name": name},),
                    )
                )
                seen.add(unique_ids[0])
            elif len(unique_ids) > 1:
                references.append(
                    EntityReference(
                        text=name,
                        status="candidate",
                        candidates=tuple(
                            EntityCandidate(person_id=person_id, confidence=0.7)
                            for person_id in unique_ids
                        ),
                    )
                )
        participants = await self._recent_participants(
            context,
            recent_participants_limit,
            recent_lookback_sec,
        )
        if context.sender_person_id and all(
            item["person_id"] != context.sender_person_id for item in participants
        ):
            participants = (
                {
                    "person_id": context.sender_person_id,
                    "display_name": message.sender.name or "",
                    "group_card": "",
                    "roles": [],
                    "last_message_id": "",
                    "last_seen_at": "now",
                },
            ) + participants
        return EntityContext(
            current_sender=sender,
            references=tuple(references),
            recent_participants=participants,
        )

    # 读取会话近期发言者快照
    async def _recent_participants(
        self,
        context: ToolExecutionContext,
        limit: int,
        lookback_sec: int,
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
                .join(
                    m.PlatformIdentity,
                    m.PlatformIdentity.identity_id == m.Message.platform_identity_id,
                )
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
                    m.Message.occurred_at
                    >= datetime.now(timezone.utc) - timedelta(seconds=int(lookback_sec)),
                )
                .group_by(
                    m.PlatformIdentity.person_id,
                    m.Person.display_name,
                    m.GroupMember.group_card,
                    m.GroupMember.nickname,
                    m.GroupMember.role,
                )
                .order_by(desc("last_seen_at"))
                .limit(int(limit))
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
        lookback_sec: int,
    ) -> list[dict]:
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
                .outerjoin(
                    m.PlatformIdentity,
                    m.PlatformIdentity.identity_id == m.Message.platform_identity_id,
                )
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
                    m.Message.occurred_at
                    >= datetime.now(timezone.utc) - timedelta(seconds=int(lookback_sec)),
                    or_(
                        pattern == "",
                        func.coalesce(m.Message.content["text"].astext, "").ilike(
                            f"%{pattern}%"
                        ),
                    ),
                )
                .order_by(m.Message.occurred_at.desc())
                .limit(int(limit))
            )
            return [
                {
                    "message_id": str(row.message_id),
                    "sender": {
                        "person_id": str(row.person_id) if row.person_id else "",
                        "display_name": row.display_name
                        or ("AI" if row.role == "assistant" else ""),
                        "role": row.role,
                    },
                    "text": self._message_text(row.content),
                    "occurred_at": str(row.occurred_at),
                }
                for row in rows
            ]

    @staticmethod
    def _message_text(content) -> str:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return content
        return str((content or {}).get("text") or "")

    @staticmethod
    def _add_candidate(
        candidates: dict[str, dict],
        person_id: str,
        display_name: str,
        confidence: float,
        evidence: dict,
    ) -> None:
        item = candidates.setdefault(
            str(person_id),
            {
                "person_id": str(person_id),
                "display_name": str(display_name or ""),
                "confidence": 0.0,
                "evidence": [],
            },
        )
        item["confidence"] = max(float(item["confidence"]), confidence)
        item["evidence"].append(evidence)

    @staticmethod
    def _mention_from_result(text: str, resolution_type: str, result: dict) -> EntityReference:
        raw = list(result.get("candidates") or [])
        candidates = tuple(
            EntityCandidate(
                person_id=str(item.get("person_id") or ""),
                display_name=str(item.get("display_name") or ""),
                confidence=float(item.get("confidence") or 0.0),
                evidence=tuple(item.get("evidence") or []),
            )
            for item in raw
            if item.get("person_id")
        )
        if len(candidates) == 1 and candidates[0].confidence >= 0.9:
            return EntityReference(
                text=text,
                status="resolved",
                person_id=candidates[0].person_id,
                display_name=candidates[0].display_name,
                evidence=({"type": resolution_type},),
            )
        if candidates:
            return EntityReference(text=text, status="candidate", candidates=candidates)
        return EntityReference(text=text, status="unresolved")
