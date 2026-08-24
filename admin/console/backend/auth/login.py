from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .credentials import CredentialRepository
from .session import RedisSessionStore


class LoginService:
    """只负责面板登录凭据校验与会话签发。"""

    def __init__(
        self,
        repository: CredentialRepository,
        sessions: RedisSessionStore,
        password_hasher: PasswordHasher,
    ) -> None:
        self._repository = repository
        self._sessions = sessions
        self._password_hasher = password_hasher

    async def login(self, username: str, password: str) -> tuple[str, str]:
        credentials = await self._repository.load()
        if credentials is None or credentials.username != username:
            raise InvalidCredentials
        try:
            self._password_hasher.verify(credentials.password_hash, password)
        except VerifyMismatchError as exc:
            raise InvalidCredentials from exc
        return await self._sessions.create(), credentials.username

    async def username(self) -> str:
        credentials = await self._repository.load()
        if credentials is None:
            raise RuntimeError("面板登录凭据未初始化")
        return credentials.username


class InvalidCredentials(ValueError):
    pass
