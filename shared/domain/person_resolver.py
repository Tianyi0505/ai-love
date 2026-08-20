from __future__ import annotations

import re

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.configuration.global_settings import GroundingSettings
from shared.contracts.entity import EntityCandidate
from shared.contracts.rpc.grounding import ResolvePeopleResponse
from shared.contracts.tools import ToolExecutionContext
from shared.infrastructure.database import Database
from shared.infrastructure.snowflake_id_generator import snowflake_ids
from shared.persistence import database_models as m


class PersonResolver:
    def __init__(self, db: Database, settings: GroundingSettings) -> None:
        self._db = db
        self._settings = settings

    @staticmethod
    def normalize(value: str) -> str:
        return re.sub(r"[\s@，,。.!！?？:：]+", "", value).casefold()

    async def record_evidence(
        self,
        *,
        mention_text: str,
        person_id: str,
        scope_type: str,
        scope_id: str,
        conversation_id: str,
        source_message_id: str,
        evidence_type: str,
        confidence: float,
    ) -> None:
        normalized = self.normalize(mention_text)
        if not self._settings.confidence_min <= confidence <= self._settings.confidence_max:
            raise ValueError("称呼证据置信度超出配置范围")
        async with self._db.session() as session:
            statement = (
                pg_insert(m.PersonMention)
                .values(
                    mention_id=snowflake_ids().next_id(),
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
            await session.execute(statement)
            await session.commit()

    async def resolve(
        self,
        context: ToolExecutionContext,
        mention: str,
        limit: int,
    ) -> ResolvePeopleResponse:
        normalized = self.normalize(mention)
        candidates: dict[str, dict] = {}
        roles = self._settings.role_names.get(normalized)
        async with self._db.session() as session:
            display_name = func.coalesce(
                func.nullif(m.GroupMember.group_card, ""),
                func.nullif(m.GroupMember.nickname, ""),
                m.Person.display_name,
                "",
            )
            if roles:
                rows = list(
                    await session.execute(
                        select(
                            m.GroupMember.person_id,
                            display_name.label("display_name"),
                            m.GroupMember.role,
                        )
                        .select_from(m.GroupMember)
                        .join(m.Person, m.Person.person_id == m.GroupMember.person_id)
                        .where(
                            m.GroupMember.platform == context.platform,
                            m.GroupMember.account_id == context.account_id,
                            m.GroupMember.chat_id == context.chat_id,
                            m.GroupMember.is_active.is_(True),
                            m.GroupMember.role.in_(roles),
                        )
                        .order_by(m.GroupMember.role)
                    )
                )
                for row in rows:
                    self._add_candidate(
                        candidates,
                        row.person_id,
                        row.display_name,
                        self._settings.role_unique_confidence
                        if len(rows) == self._settings.primary_candidate_limit
                        else self._settings.role_ambiguous_confidence,
                        {"type": "group_role", "role": row.role},
                    )
            else:
                stripped = mention.strip()
                platform_user_id = stripped.lstrip("@")
                rows = await session.execute(
                    select(
                        m.GroupMember.person_id,
                        display_name.label("display_name"),
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
                            func.lower(m.GroupMember.platform_user_id) == platform_user_id.casefold(),
                            func.lower(m.GroupMember.nickname) == stripped.casefold(),
                            func.lower(m.GroupMember.group_card) == stripped.casefold(),
                            func.lower(m.Person.display_name) == stripped.casefold(),
                        ),
                    )
                )
                for row in rows:
                    if row.platform_user_id.casefold() == platform_user_id.casefold():
                        confidence = self._settings.platform_identity_confidence
                        evidence_type = "platform_identity"
                    elif str(row.group_card).casefold() == stripped.casefold():
                        confidence = self._settings.group_card_confidence
                        evidence_type = "group_card"
                    else:
                        confidence = self._settings.display_name_confidence
                        evidence_type = "display_name"
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
                        func.extract("epoch", func.now() - func.max(m.PersonMention.observed_at)).label("age_sec"),
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
                            and_(m.PersonMention.scope_type == "group", m.PersonMention.scope_id == context.chat_id),
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
                    recency = self._settings.recency_base ** (
                        max(self._settings.confidence_min, float(row.age_sec))
                        / self._settings.mention_evidence_half_life_sec
                    )
                    confidence = min(
                        self._settings.evidence_confidence_max,
                        float(row.confidence) * recency
                        + min(
                            self._settings.evidence_boost_max,
                            int(row.evidence_count) * self._settings.evidence_boost_per_occurrence,
                        ),
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
        return ResolvePeopleResponse(
            mention=mention,
            candidates=[EntityCandidate.model_validate(candidate) for candidate in ordered],
        )

    def _add_candidate(
        self,
        candidates: dict[str, dict],
        person_id: str,
        display_name: str,
        confidence: float,
        evidence: dict,
    ) -> None:
        key = str(person_id)
        if key not in candidates:
            candidates[key] = {
                "person_id": key,
                "display_name": str(display_name or ""),
                "confidence": self._settings.confidence_min,
                "evidence": [],
            }
        candidate = candidates[key]
        candidate["confidence"] = max(float(candidate["confidence"]), confidence)
        candidate["evidence"].append(evidence)
