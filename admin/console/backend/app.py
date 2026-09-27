from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from plugin_runtime.control import PluginControlClient
from shared.agent_definition_store import AgentDefinitionStore
from shared.config_provider import ConfigurationError
from shared.contracts.agent import AgentDefinitionError
from shared.database import Database
from shared.mounted_config_provider import MountedConfigProvider
from shared.nats_bus import create_bus

from .auth.credentials import CredentialRepository, CredentialService
from .auth.login import LoginService
from .auth.router import router as auth_router
from .auth.session import RedisSessionStore
from .observability.people_memory import PeopleMemoryReader
from .observability.personality import PersonalityReader
from .observability.router import router as observability_router
from .observability.self_memory import SelfMemoryReader
from .plugins.router import router as plugins_router

logger = logging.getLogger("ailove.panel")


class PanelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PANEL_", extra="ignore", frozen=True)

    port: int
    ai_id: str
    people_memory_limit: int
    initial_username: str
    initial_password: str
    napcat_token: str
    napcat_url: str
    k8s_url: str
    k8s_internal_url: str = "https://127.0.0.1:30443"
    k8s_service_account_token_path: Path = Path(
        "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )
    redis_url: str = Field(validation_alias="AILOVE_REDIS_URL")
    redis_password: str = Field(validation_alias="AILOVE_REDIS_PASSWORD")
    bus_url: str = Field(default="nats://nats:4222", validation_alias="AILOVE_BUS_URL")
    bus_token: str | None = Field(default=None, validation_alias="AILOVE_BUS_TOKEN")
    plugin_hosts: tuple[str, ...] = ("gateway", "ai-agent", "extension-host", "mcp", "gptsovits", "director", "live-edge")


def create_app(
    static_directory: Path | None = None,
    panel_config: PanelConfig | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = panel_config or PanelConfig()
        database = Database()
        redis = Redis.from_url(
            config.redis_url,
            password=config.redis_password,
            decode_responses=True,
        )
        config_provider = MountedConfigProvider()
        plugin_control = PluginControlClient(create_bus(config.bus_url, config.bus_token), config.plugin_hosts)
        try:
            await database.connect()
            await redis.ping()
            await config_provider.connect()

            agent_store = AgentDefinitionStore(config_provider)

            password_hasher = PasswordHasher()
            sessions = RedisSessionStore(redis)
            credentials = CredentialRepository(database)
            await credentials.create_table()
            stored = await credentials.load()
            if stored is None or not stored.password_hash.startswith("$argon2"):
                if stored is not None:
                    logger.info("[panel] 将旧面板凭据迁移为 Argon2")
                await credentials.save(
                    config.initial_username,
                    password_hasher.hash(config.initial_password),
                )

            app.state.config = config
            app.state.plugin_control = plugin_control
            app.state.session_store = sessions
            app.state.login_service = LoginService(credentials, sessions, password_hasher)
            app.state.credential_service = CredentialService(
                credentials,
                sessions,
                password_hasher,
            )
            app.state.personality_reader = PersonalityReader(agent_store)
            app.state.self_memory_reader = SelfMemoryReader(database)
            app.state.people_memory_reader = PeopleMemoryReader(
                database,
                config.people_memory_limit,
            )
            logger.info("[panel] ai-love 已就绪，当前 AI: %s", config.ai_id)
            yield
        finally:
            await plugin_control.close()
            await config_provider.close()
            await redis.aclose()
            await database.close()

    app = FastAPI(title="ai-love", lifespan=lifespan, docs_url=None, redoc_url=None)

    async def dependency_unavailable(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "[panel] 外部依赖运行期错误: %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(status_code=503, content={"detail": "依赖服务暂时不可用"})

    for exception_type in (RedisError, SQLAlchemyError, ConfigurationError, AgentDefinitionError):
        app.add_exception_handler(exception_type, dependency_unavailable)
    app.include_router(auth_router)
    app.include_router(observability_router)
    app.include_router(plugins_router)
    frontend = static_directory or Path(__file__).resolve().parents[1] / "frontend" / "dist"
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
