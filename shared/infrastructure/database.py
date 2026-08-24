from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AILOVE_DATABASE_", extra="ignore")

    url: str
    pool_min_size: int
    pool_max_size: int
    pool_recycle_sec: int
    pool_timeout_sec: float

    @model_validator(mode="after")
    def validate_pool_range(self) -> "DatabaseSettings":
        if self.pool_max_size < self.pool_min_size:
            raise ValueError("数据库连接池最大容量不能小于基础容量")
        return self


# 管理数据库引擎与会话
class Database:
    # 初始化当前实例
    def __init__(self) -> None:
        self._settings = DatabaseSettings()
        self._engine = None
        self._session_factory = None

    # 转换为异步驱动URL
    @staticmethod
    def _async_url(url: str) -> str:
        return make_url(url).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)

    # 建立连接
    async def connect(self) -> None:
        self._engine = create_async_engine(
            self._async_url(self._settings.url),
            pool_size=self._settings.pool_min_size,
            max_overflow=self._settings.pool_max_size - self._settings.pool_min_size,
            pool_pre_ping=True,
            pool_recycle=self._settings.pool_recycle_sec,
            pool_timeout=self._settings.pool_timeout_sec,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

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
