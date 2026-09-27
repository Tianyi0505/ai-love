from __future__ import annotations

from sqlalchemy import literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from shared import database_models as m
from shared.database import Database
from shared.snowflake_id_generator import snowflake_ids


class IdentityRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

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

    async def resolve_or_create(
        self,
        platform: str,
        account_id: str,
        platform_user_id: str,
        display_name: str,
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
                person = m.Person(person_id=snowflake_ids().next_id(), display_name=display_name)
                session.add(person)
                await session.flush()
                identity = m.PlatformIdentity(
                    identity_id=snowflake_ids().next_id(),
                    person_id=person.person_id,
                    platform=platform,
                    account_id=account_id,
                    platform_user_id=platform_user_id,
                    verified_by="platform-observed",
                )
                session.add(identity)
                await self._initialize_private_contact(session, person.person_id, account_id)
                await session.flush()
                result = str(identity.identity_id), str(person.person_id)
        return result

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
                result = {str(row.platform_user_id): (str(row.identity_id), str(row.person_id)) for row in rows}
                for person in people:
                    user_id = str(person.get("platform_user_id") or "")
                    if not user_id or user_id in result:
                        continue
                    display_name = str(person.get("group_card") or person.get("nickname") or user_id)
                    person_row = m.Person(person_id=snowflake_ids().next_id(), display_name=display_name)
                    session.add(person_row)
                    await session.flush()
                    identity = m.PlatformIdentity(
                        identity_id=snowflake_ids().next_id(),
                        person_id=person_row.person_id,
                        platform=platform,
                        account_id=account_id,
                        platform_user_id=user_id,
                        verified_by="platform-observed",
                    )
                    session.add(identity)
                    await self._initialize_private_contact(session, person_row.person_id, account_id)
                    await session.flush()
                    result[user_id] = (str(identity.identity_id), str(person_row.person_id))
        return result

    async def _initialize_private_contact(self, session, person_id, account_id):
        await session.execute(insert(m.PrivateContactState).from_select(
            ["ai_id", "person_id", "status", "reason_code"],
            select(m.AIAccountBinding.ai_id, literal(person_id), literal("active"), literal(""))
            .where(m.AIAccountBinding.account_id == account_id, m.AIAccountBinding.ended_at.is_(None))
        ).on_conflict_do_nothing())
