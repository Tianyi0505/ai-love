
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.infrastructure.runtime_config import ConfigKey, required_setting


# 管理数据库引擎与会话
class Database:
    # 初始化当前实例
    def __init__(self) -> None:
        self._url = self._async_url(
            required_setting(None, ConfigKey.AILOVE_DATABASE_URL)
        )
        self._pool_min_size = int(
            required_setting(None, ConfigKey.AILOVE_DATABASE_POOL_MIN_SIZE)
        )
        self._pool_max_size = int(
            required_setting(None, ConfigKey.AILOVE_DATABASE_POOL_MAX_SIZE)
        )
        self._engine = None
        self._session_factory = None

    # 转换为异步驱动URL
    @staticmethod
    def _async_url(url: str) -> str:
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://"):]
        return url

    # 建立连接
    async def connect(self) -> None:
        self._engine = create_async_engine(
            self._url,
            pool_size=self._pool_min_size,
            max_overflow=max(0, self._pool_max_size - self._pool_min_size),
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    # 关闭资源
    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    # 返回会话工厂
    @property
    def session(self):
        if self._session_factory is None:
            raise RuntimeError("Database 未 connect")
        return self._session_factory

    # 返回异步引擎
    @property
    def engine(self):
        if self._engine is None:
            raise RuntimeError("Database 未 connect")
        return self._engine
