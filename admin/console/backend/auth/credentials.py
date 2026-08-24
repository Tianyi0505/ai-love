from __future__ import annotations

from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.persistence import database_models as m

from .session import RedisSessionStore


@dataclass(frozen=True)
class CredentialRecord:
    username: str
    password_hash: str


class CredentialRepository:
    """只负责 panel_settings 中的登录凭据持久化。"""

    def __init__(self, database) -> None:
        self._database = database

    async def create_table(self) -> None:
        async with self._database.engine.begin() as connection:
            await connection.run_sync(
                lambda sync: m.PanelSetting.__table__.create(sync, checkfirst=True)
            )

    async def load(self) -> CredentialRecord | None:
        async with self._database.session() as session:
            result = await session.execute(
                select(m.PanelSetting.key, m.PanelSetting.value).where(
                    m.PanelSetting.key.in_(("username", "password_hash"))
                )
            )
            settings = {row.key: row.value for row in result}
        if "username" not in settings or "password_hash" not in settings:
            return None
        return CredentialRecord(
            username=settings["username"],
            password_hash=settings["password_hash"],
        )

    async def save(self, username: str, password_hash: str) -> None:
        async with self._database.session() as session:
            for key, value in (("username", username), ("password_hash", password_hash)):
                statement = (
                    pg_insert(m.PanelSetting)
                    .values(key=key, value=value)
                    .on_conflict_do_update(
                        index_elements=[m.PanelSetting.key],
                        set_={"value": value},
                    )
                )
                await session.execute(statement)
            await session.commit()


class CredentialService:
    """只负责校验当前密码并更新登录凭据。"""

    def __init__(
        self,
        repository: CredentialRepository,
        sessions: RedisSessionStore,
        password_hasher: PasswordHasher,
    ) -> None:
        self._repository = repository
        self._sessions = sessions
        self._password_hasher = password_hasher

    async def update(
        self,
        current_password: str,
        username: str,
        password: str,
    ) -> None:
        credentials = await self._repository.load()
        if credentials is None:
            raise RuntimeError("面板登录凭据未初始化")
        try:
            self._password_hasher.verify(credentials.password_hash, current_password)
        except VerifyMismatchError as exc:
            raise CurrentPasswordMismatch from exc
        await self._repository.save(
            username,
            self._password_hasher.hash(password),
        )
        await self._sessions.delete_all()


class CurrentPasswordMismatch(ValueError):
    pass
