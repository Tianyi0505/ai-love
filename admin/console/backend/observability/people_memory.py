from __future__ import annotations

from sqlalchemy import String, cast, func, or_, select

from shared.snowflake_id_generator import is_snowflake_id
from shared import database_models as m

from .schemas import (
    MemoryDocumentResponse,
    PeopleResponse,
    PersonMemoryResponse,
    PersonSummary,
)


class PeopleMemoryReader:
    """只负责读取带 QQ 身份的人物长期记忆。"""

    def __init__(self, database, list_limit: int) -> None:
        self._database = database
        self._list_limit = list_limit

    @staticmethod
    def _qq_identity():
        return (
            select(m.PlatformIdentity.platform_user_id)
            .where(
                m.PlatformIdentity.person_id == m.Person.person_id,
                m.PlatformIdentity.platform == "qq",
            )
            .order_by(m.PlatformIdentity.verified_at.desc())
            .limit(1)
            .correlate(m.Person)
            .scalar_subquery()
        )

    async def list(self, ai_id: str, query: str) -> PeopleResponse:
        qq = self._qq_identity()
        display_name = func.coalesce(func.nullif(m.Person.display_name, ""), qq)
        statement = (
            select(
                m.MemoryDocument.owner_id,
                display_name.label("display_name"),
                qq.label("qq"),
                m.MemoryDocument.version,
                m.MemoryDocument.updated_at,
            )
            .select_from(m.MemoryDocument)
            .join(
                m.Person,
                cast(m.Person.person_id, String) == m.MemoryDocument.owner_id,
            )
            .where(
                m.MemoryDocument.ai_id == ai_id,
                m.MemoryDocument.owner_type == "person",
                qq.is_not(None),
            )
            .order_by(m.MemoryDocument.updated_at.desc())
            .limit(self._list_limit)
        )
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(display_name.ilike(pattern), qq.ilike(pattern))
            )
        async with self._database.session() as session:
            rows = await session.execute(statement)
            people = [
                PersonSummary(
                    person_id=row.owner_id,
                    display_name=row.display_name,
                    qq=row.qq,
                    version=row.version,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
        return PeopleResponse(ai_id=ai_id, people=people)

    async def detail(self, ai_id: str, person_id: str) -> PersonMemoryResponse | None:
        if not is_snowflake_id(person_id):
            raise InvalidPersonId
        qq = self._qq_identity()
        display_name = func.coalesce(func.nullif(m.Person.display_name, ""), qq)
        async with self._database.session() as session:
            result = await session.execute(
                select(
                    display_name.label("display_name"),
                    qq.label("qq"),
                    m.MemoryDocument.markdown_content,
                    m.MemoryDocument.version,
                    m.MemoryDocument.updated_at,
                )
                .select_from(m.MemoryDocument)
                .join(
                    m.Person,
                    cast(m.Person.person_id, String) == m.MemoryDocument.owner_id,
                )
                .where(
                    m.MemoryDocument.ai_id == ai_id,
                    m.MemoryDocument.owner_type == "person",
                    m.MemoryDocument.owner_id == person_id,
                    qq.is_not(None),
                )
            )
            row = result.one_or_none()
        if row is None:
            return None
        return PersonMemoryResponse(
            ai_id=ai_id,
            person=PersonSummary(
                person_id=person_id,
                display_name=row.display_name,
                qq=row.qq,
                version=row.version,
                updated_at=row.updated_at,
            ),
            memory=MemoryDocumentResponse(
                markdown=row.markdown_content,
                version=row.version,
                updated_at=row.updated_at,
            ),
        )


class InvalidPersonId(ValueError):
    pass
