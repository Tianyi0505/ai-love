from __future__ import annotations

from sqlalchemy import select

from shared.infrastructure.database import Database
from shared.persistence import database_models as m


class AccountOwnershipRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def owner_for_social_account(self, account_id: str) -> str | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(m.AIAccountBinding.ai_id)
                    .select_from(m.AIAccountBinding)
                    .join(m.SocialAccount, m.SocialAccount.account_id == m.AIAccountBinding.account_id)
                    .where(
                        m.AIAccountBinding.account_id == account_id,
                        m.AIAccountBinding.ended_at.is_(None),
                        m.SocialAccount.allows_multi_ai.is_(False),
                    )
                )
            ).first()
            return row.ai_id if row else None

    async def live_candidates(self, account_id: str) -> list[str]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(m.AIAccountBinding.ai_id)
                .where(m.AIAccountBinding.account_id == account_id, m.AIAccountBinding.ended_at.is_(None))
                .order_by(m.AIAccountBinding.ai_id)
            )
            return [row for (row,) in rows]

    async def accounts_for_ai(self, ai_id: str) -> list[str]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(m.AIAccountBinding.account_id)
                .where(m.AIAccountBinding.ai_id == ai_id, m.AIAccountBinding.ended_at.is_(None))
                .order_by(m.AIAccountBinding.bound_at)
            )
            return [row for (row,) in rows]
