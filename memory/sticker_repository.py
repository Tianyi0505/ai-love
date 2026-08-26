from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared import database_models as m
from shared.database import Database


class StickerRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_ai_ids(self) -> tuple[str, ...]:
        async with self._db.session() as session:
            rows = await session.execute(select(m.Sticker.ai_id).distinct())
            return tuple(rows.scalars())

    async def count(self, ai_id: str) -> int:
        async with self._db.session() as session:
            return int(
                (
                    await session.execute(select(func.count()).select_from(m.Sticker).where(m.Sticker.ai_id == ai_id))
                ).scalar_one()
            )

    async def exists(self, ai_id: str, sticker_id: str) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                select(m.Sticker.sticker_id).where(
                    m.Sticker.ai_id == ai_id,
                    m.Sticker.sticker_id == int(sticker_id),
                )
            )
            return result.first() is not None

    async def insert(
        self,
        ai_id: str,
        sticker: dict,
        initial_usage_strength: float,
        initial_boost_count: int,
    ) -> None:
        async with self._db.session() as session:
            await session.execute(
                pg_insert(m.Sticker)
                .values(
                    ai_id=ai_id,
                    sticker_id=int(sticker["id"]),
                    image_url=sticker["image_url"],
                    description=sticker["description"],
                    tags=sticker["tags"],
                    match_quality=sticker["match_quality"],
                    usage_strength=initial_usage_strength,
                    boost_count=initial_boost_count,
                )
                .on_conflict_do_nothing(index_elements=[m.Sticker.sticker_id])
            )
            await session.commit()

    async def all(self, ai_id: str) -> list[dict]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(
                    m.Sticker.sticker_id,
                    m.Sticker.image_url,
                    m.Sticker.description,
                    m.Sticker.tags,
                    m.Sticker.match_quality,
                    m.Sticker.usage_strength,
                    m.Sticker.boost_count,
                    m.Sticker.created_at,
                    m.Sticker.last_used_at,
                ).where(m.Sticker.ai_id == ai_id)
            )
            return [
                {
                    "id": str(row.sticker_id),
                    "image_url": row.image_url,
                    "description": row.description,
                    "tags": list(row.tags),
                    "match_quality": float(row.match_quality),
                    "usage_strength": float(row.usage_strength),
                    "boost_count": int(row.boost_count),
                    "created_at": row.created_at,
                    "last_used_at": row.last_used_at,
                }
                for row in rows
            ]

    async def delete(self, ai_id: str, sticker_ids: list[str]) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(m.Sticker).where(
                    m.Sticker.ai_id == ai_id,
                    m.Sticker.sticker_id.in_([int(sticker_id) for sticker_id in sticker_ids]),
                )
            )
            await session.commit()

    async def boost(
        self,
        ai_id: str,
        sticker_id: str,
        delta: float,
        maximum: float,
        count_increment: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            await session.execute(
                update(m.Sticker)
                .where(
                    m.Sticker.ai_id == ai_id,
                    m.Sticker.sticker_id == int(sticker_id),
                )
                .values(
                    usage_strength=func.least(
                        maximum,
                        m.Sticker.usage_strength + delta,
                    ),
                    last_used_at=now,
                    boost_count=m.Sticker.boost_count + count_increment,
                )
            )
            await session.commit()
