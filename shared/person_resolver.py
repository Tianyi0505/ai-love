from __future__ import annotations

import re
import time

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared import database_models as m
from shared.contracts.entity import EntityCandidate
from shared.contracts.rpc.grounding import ResolvePeopleResponse
from shared.contracts.tools import ToolExecutionContext
from shared.database import Database
from shared.global_settings import GroundingSettings
from shared.lfu import LazyLFU
from shared.snowflake_id_generator import snowflake_ids


class PersonResolver:
    def __init__(
        self,
        db: Database,
        settings: GroundingSettings,
        lfu: LazyLFU,
    ) -> None:
        self._db = db
        self._settings = settings
        self._lfu = lfu

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
            unique_key = (
                m.PersonMention.normalized_mention == normalized,
                m.PersonMention.person_id == int(person_id),
                m.PersonMention.scope_type == scope_type,
                m.PersonMention.scope_id == scope_id,
                m.PersonMention.evidence_type == evidence_type,
                m.PersonMention.source_message_id == source_message_id,
            )
            insert_evidence = (
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
                .on_conflict_do_nothing(
                    index_elements=[
                        m.PersonMention.normalized_mention,
                        m.PersonMention.person_id,
                        m.PersonMention.scope_type,
                        m.PersonMention.scope_id,
                        m.PersonMention.evidence_type,
                        m.PersonMention.source_message_id,
                    ],
                )
                .returning(m.PersonMention.mention_id)
            )
            inserted_id = (await session.execute(insert_evidence)).scalar_one_or_none()
            if inserted_id is None:
                await session.execute(
                    update(m.PersonMention)
                    .where(*unique_key)
                    .values(
                        confidence=func.greatest(m.PersonMention.confidence, confidence),
                        observed_at=func.now(),
                    )
                )
            else:
                now = time.time()
                initial_state = self._lfu.initial(now).as_dict()
                await session.execute(
                    pg_insert(m.PersonMentionFrequency)
                    .values(
                        person_mention_frequency_id=snowflake_ids().next_id(),
                        normalized_mention=normalized,
                        person_id=int(person_id),
                        scope_type=scope_type,
                        scope_id=scope_id,
                        lfu_state=initial_state,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            m.PersonMentionFrequency.normalized_mention,
                            m.PersonMentionFrequency.person_id,
                            m.PersonMentionFrequency.scope_type,
                            m.PersonMentionFrequency.scope_id,
                        ]
                    )
                )
                frequency = (
                    await session.execute(
                        select(m.PersonMentionFrequency)
                        .where(
                            m.PersonMentionFrequency.normalized_mention == normalized,
                            m.PersonMentionFrequency.person_id == int(person_id),
                            m.PersonMentionFrequency.scope_type == scope_type,
                            m.PersonMentionFrequency.scope_id == scope_id,
                        )
                        .with_for_update()
                    )
                ).scalar_one()
                state = self._lfu.state_from_mapping(frequency.lfu_state, now)
                await session.execute(
                    update(m.PersonMentionFrequency)
                    .where(
                        m.PersonMentionFrequency.person_mention_frequency_id
                        == frequency.person_mention_frequency_id
                    )
                    .values(
                        lfu_state=self._lfu.access(state, now).as_dict(),
                        updated_at=func.now(),
                    )
                )
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

                scope_filter = or_(
                    and_(m.PersonMention.scope_type == "group", m.PersonMention.scope_id == context.chat_id),
                    and_(
                        m.PersonMention.scope_type == "conversation",
                        m.PersonMention.scope_id == context.conversation_id,
                    ),
                    m.PersonMention.scope_type == "global",
                )
                evidence_rows = await session.execute(
                    select(
                        m.PersonMention.person_id,
                        m.Person.display_name,
                        m.PersonMention.scope_type,
                        m.PersonMention.scope_id,
                        func.max(m.PersonMention.confidence).label("confidence"),
                        func.count().label("evidence_count"),
                        func.max(m.PersonMention.observed_at).label("last_seen_at"),
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
                        scope_filter,
                    )
                    .group_by(
                        m.PersonMention.person_id,
                        m.Person.display_name,
                        m.PersonMention.scope_type,
                        m.PersonMention.scope_id,
                    )
                    .order_by(desc("confidence"), desc("evidence_count"), desc("last_seen_at"))
                )
                frequency_scores: dict[tuple[str, str, str], float] = {}
                frequency_scope_filter = or_(
                    and_(
                        m.PersonMentionFrequency.scope_type == "group",
                        m.PersonMentionFrequency.scope_id == context.chat_id,
                    ),
                    and_(
                        m.PersonMentionFrequency.scope_type == "conversation",
                        m.PersonMentionFrequency.scope_id == context.conversation_id,
                    ),
                    m.PersonMentionFrequency.scope_type == "global",
                )
                frequency_rows = await session.execute(
                    select(
                        m.PersonMentionFrequency.person_id,
                        m.PersonMentionFrequency.scope_type,
                        m.PersonMentionFrequency.scope_id,
                        m.PersonMentionFrequency.lfu_state,
                    ).where(
                        m.PersonMentionFrequency.normalized_mention == normalized,
                        frequency_scope_filter,
                    )
                )
                now = time.time()
                for frequency_row in frequency_rows:
                    key = (
                        str(frequency_row.person_id),
                        frequency_row.scope_type,
                        frequency_row.scope_id,
                    )
                    state = self._lfu.state_from_mapping(frequency_row.lfu_state, now)
                    frequency_scores[key] = max(
                        frequency_scores.get(key, 0.0),
                        self._lfu.score(state, now),
                    )
                for row in evidence_rows:
                    frequency_score = frequency_scores.get(
                        (str(row.person_id), row.scope_type, row.scope_id),
                        0.0,
                    )
                    direct_boost = min(
                        self._settings.evidence_boost_max,
                        self._settings.evidence_boost_per_occurrence,
                    )
                    confidence = min(
                        self._settings.evidence_confidence_max,
                        float(row.confidence) * frequency_score + direct_boost,
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
