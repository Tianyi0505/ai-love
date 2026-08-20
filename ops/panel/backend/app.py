from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from v2.nacos import NacosException

from shared.contracts.agent import AgentDefinitionError
from shared.infrastructure.agent_store import NacosAgentDefinitionStore
from shared.infrastructure.config import NacosConfigProvider
from shared.infrastructure.database import Database
from shared.infrastructure.runtime_config import required_value

from .auth.credentials import CredentialRepository, CredentialService
from .auth.login import LoginService
from .auth.router import router as auth_router
from .auth.session import RedisSessionStore
from .observability.people_memory import PeopleMemoryReader
from .observability.personality import PersonalityReader
from .observability.router import router as observability_router
from .observability.self_memory import SelfMemoryReader


logger = logging.getLogger("ailove.panel")


@dataclass(frozen=True)
class PanelConfig:
    ai_id: str
    redis_url: str
    redis_password: str
    initial_username: str
    initial_password: str
    napcat_token: str
    nacos_url: str
    napcat_url: str
    k8s_url: str

    @classmethod
    def load(cls) -> "PanelConfig":
        return cls(
            ai_id=required_value(os.environ.get("PANEL_AI_ID"), "PANEL_AI_ID"),
            redis_url=required_value(os.environ.get("AILOVE_REDIS_URL"), "AILOVE_REDIS_URL"),
            redis_password=required_value(
                os.environ.get("AILOVE_REDIS_PASSWORD"),
                "AILOVE_REDIS_PASSWORD",
            ),
            initial_username=required_value(
                os.environ.get("PANEL_INITIAL_USERNAME"),
                "PANEL_INITIAL_USERNAME",
            ),
            initial_password=required_value(
                os.environ.get("PANEL_INITIAL_PASSWORD"),
                "PANEL_INITIAL_PASSWORD",
            ),
            napcat_token=required_value(
                os.environ.get("PANEL_NAPCAT_TOKEN"),
                "PANEL_NAPCAT_TOKEN",
            ),
            nacos_url=required_value(os.environ.get("PANEL_NACOS_URL"), "PANEL_NACOS_URL"),
            napcat_url=required_value(
                os.environ.get("PANEL_NAPCAT_URL"),
                "PANEL_NAPCAT_URL",
            ),
            k8s_url=required_value(os.environ.get("PANEL_K8S_URL"), "PANEL_K8S_URL"),
        )


def create_app(static_directory: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = PanelConfig.load()
        database = Database()
        redis = Redis.from_url(
            config.redis_url,
            password=config.redis_password,
            decode_responses=True,
        )
        nacos = NacosConfigProvider()
        try:
            await database.connect()
            await redis.ping()
            await nacos.connect()

            agent_store = NacosAgentDefinitionStore(nacos)
            await agent_store.load(config.ai_id)

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
            app.state.session_store = sessions
            app.state.login_service = LoginService(credentials, sessions, password_hasher)
            app.state.credential_service = CredentialService(
                credentials,
                sessions,
                password_hasher,
            )
            app.state.personality_reader = PersonalityReader(agent_store)
            app.state.self_memory_reader = SelfMemoryReader(database)
            app.state.people_memory_reader = PeopleMemoryReader(database)
            logger.info("[panel] ai-love 已就绪，当前 AI: %s", config.ai_id)
            yield
        finally:
            await nacos.close()
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

    for exception_type in (RedisError, SQLAlchemyError, NacosException, AgentDefinitionError):
        app.add_exception_handler(exception_type, dependency_unavailable)
    app.include_router(auth_router)
    app.include_router(observability_router)
    frontend = static_directory or Path(__file__).resolve().parents[1] / "frontend" / "dist"
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
