from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.infrastructure.database import Database
from shared.infrastructure.snowflake_id_generator import snowflake_ids
from shared.persistence import database_models as m


class QZoneCommentedFeedRepository:
    def __init__(self, db: Database, account_id: str) -> None:
        self._db = db
        self._account_id = account_id

    async def has(self, feed_id: str) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                select(m.QZoneCommentedFeed.feed_id).where(
                    m.QZoneCommentedFeed.account_id == self._account_id,
                    m.QZoneCommentedFeed.feed_id == feed_id,
                )
            )
            return result.first() is not None

    async def add(self, feed_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                pg_insert(m.QZoneCommentedFeed)
                .values(
                    qzone_commented_feed_id=snowflake_ids().next_id(),
                    account_id=self._account_id,
                    feed_id=feed_id,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        m.QZoneCommentedFeed.account_id,
                        m.QZoneCommentedFeed.feed_id,
                    ]
                )
            )
            await session.commit()
