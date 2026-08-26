from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared import database_models as m
from shared.contracts.tools import ToolExecutionContext
from shared.database import Database
from shared.global_settings import GroundingSettings
from shared.snowflake_id_generator import snowflake_ids


class GroupMemberRepository:
    def __init__(self, db: Database, settings: GroundingSettings) -> None:
        self._db = db
        self._settings = settings

    async def replace_snapshot(
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
                        "group_member_id": snowflake_ids().next_id(),
                        "platform": platform,
                        "account_id": account_id,
                        "chat_id": chat_id,
                        "platform_user_id": str(member["platform_user_id"]),
                        "person_id": int(member["person_id"]),
                        "nickname": str(member["nickname"]),
                        "group_card": str(member["group_card"]),
                        "role": str(member["role"]),
                        "is_active": True,
                    }
                    statement = (
                        pg_insert(m.GroupMember)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=[
                                m.GroupMember.platform,
                                m.GroupMember.account_id,
                                m.GroupMember.chat_id,
                                m.GroupMember.platform_user_id,
                            ],
                            set_={
                                "person_id": values["person_id"],
                                "nickname": values["nickname"],
                                "group_card": values["group_card"],
                                "role": values["role"],
                                "is_active": values["is_active"],
                                "last_seen_at": func.now(),
                            },
                        )
                    )
                    await session.execute(statement)

    async def names_in_message(
        self,
        context: ToolExecutionContext,
        text: str,
    ) -> dict[str, tuple[str, ...]]:
        async with self._db.session() as session:
            rows = await session.execute(
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
                        func.length(m.GroupMember.group_card) >= self._settings.member_name_min_chars,
                        func.length(m.GroupMember.nickname) >= self._settings.member_name_min_chars,
                    ),
                )
            )
        matches: dict[str, list[str]] = {}
        for row in rows:
            name = str(row.name or "")
            if name and name in text:
                matches.setdefault(name, []).append(str(row.person_id))
        return {name: tuple(dict.fromkeys(person_ids)) for name, person_ids in matches.items()}
