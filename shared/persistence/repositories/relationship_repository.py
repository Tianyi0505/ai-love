from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.configuration.global_settings import RelationshipStorageSettings
from shared.contracts.relationship import GroupRelationship, PersonRelationship
from shared.infrastructure.database import Database
from shared.infrastructure.snowflake_id_generator import snowflake_ids
from shared.persistence import database_models as m


class RelationshipRepository:
    def __init__(self, db: Database, settings: RelationshipStorageSettings) -> None:
        self._db = db
        self._settings = settings

    def _new_person(self) -> PersonRelationship:
        score = self._settings.initial_score
        return PersonRelationship(score, score, score, score)

    def _new_group(self) -> GroupRelationship:
        score = self._settings.initial_score
        return GroupRelationship(score, score, score, score)

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
        return PersonRelationship(**row._mapping) if row else self._new_person()

    async def save_person(
        self,
        ai_id: str,
        person_id: str,
        relationship: PersonRelationship,
        ceiling_policy: str,
    ) -> None:
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.PersonRelationship)
                .values(
                    person_relationship_id=snowflake_ids().next_id(),
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
                    index_elements=[m.PersonRelationship.ai_id, m.PersonRelationship.person_id],
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

    async def ensure_person(self, ai_id: str, person_id: str, ceiling_policy: str) -> None:
        initial = self._settings.initial_score
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.PersonRelationship)
                .values(
                    person_relationship_id=snowflake_ids().next_id(),
                    ai_id=ai_id,
                    person_id=int(person_id),
                    familiarity=initial,
                    affinity=initial,
                    trust=initial,
                    importance=initial,
                    ceiling_policy=ceiling_policy,
                )
                .on_conflict_do_update(
                    index_elements=[m.PersonRelationship.ai_id, m.PersonRelationship.person_id],
                    set_={"ceiling_policy": ceiling_policy},
                )
            )
            await session.execute(stmt)
            await session.commit()

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
        return GroupRelationship(**row._mapping) if row else self._new_group()

    async def save_group(
        self,
        ai_id: str,
        account_id: str,
        group_id: str,
        relationship: GroupRelationship,
    ) -> None:
        policy = self._settings.default_ceiling_policy
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.GroupRelationship)
                .values(
                    group_relationship_id=snowflake_ids().next_id(),
                    ai_id=ai_id,
                    account_id=account_id,
                    platform_group_id=group_id,
                    familiarity=relationship.familiarity,
                    belonging=relationship.belonging,
                    affinity=relationship.affinity,
                    activity_willingness=relationship.activity_willingness,
                    ceiling_policy=policy,
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
                        "ceiling_policy": policy,
                        "last_interaction_at": datetime.now(timezone.utc),
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def list_people(self, ai_id: str) -> list[dict]:
        latest_user = (
            select(m.PlatformIdentity.platform_user_id)
            .where(m.PlatformIdentity.person_id == m.PersonRelationship.person_id)
            .order_by(m.PlatformIdentity.verified_at.desc())
            .limit(self._settings.latest_identity_limit)
            .scalar_subquery()
        )
        latest_account = (
            select(m.PlatformIdentity.account_id)
            .where(m.PlatformIdentity.person_id == m.PersonRelationship.person_id)
            .order_by(m.PlatformIdentity.verified_at.desc())
            .limit(self._settings.latest_identity_limit)
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
