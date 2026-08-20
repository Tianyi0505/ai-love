from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from shared.configuration.connection_settings import DatabaseURLSettings
from shared.persistence import database_models as m


# 转换为异步驱动URL
def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def run_migrations_online() -> None:
    url = _async_url(DatabaseURLSettings().url)
    engine = create_async_engine(url)

    def do_run(connection) -> None:
        context.configure(
            connection=connection,
            target_metadata=m.Base.metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    async def run() -> None:
        async with engine.connect() as connection:
            await connection.run_sync(do_run)
        await engine.dispose()

    asyncio.run(run())


run_migrations_online()
