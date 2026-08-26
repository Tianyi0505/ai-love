from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from shared import database_models as m
from shared.database import Database


@dataclass(frozen=True)
class AIProfileRecord:
    ai_id: str
    definition_version: int


class AIProfileRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_active(self) -> list[AIProfileRecord]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(m.AIProfile.ai_id, m.AIProfile.definition_version)
                .where(m.AIProfile.status == "active")
                .order_by(m.AIProfile.ai_id)
            )
            return [AIProfileRecord(row.ai_id, row.definition_version) for row in rows]
