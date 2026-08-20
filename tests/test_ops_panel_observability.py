from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
import yaml

from ops.panel.backend.observability.people_memory import PeopleMemoryReader
from ops.panel.backend.observability.personality import PersonalityReader
from ops.panel.backend.observability.router import router
from ops.panel.backend.observability.schemas import (
    MemoryDocumentResponse,
    PeopleResponse,
    PersonMemoryResponse,
    PersonalityResponse,
    PersonSummary,
    SelfMemoryResponse,
)
from shared.infrastructure.agent_store import NacosAgentDefinitionStore


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc)


class FileConfigProvider:
    async def get(self, key: str) -> dict:
        path = ROOT / "deploy" / "nacos" / f"{key}.yaml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))


class AlwaysValidSessionStore:
    async def exists(self, token: str) -> bool:
        return token == "valid-session"


class FixedPersonalityReader:
    def __init__(self) -> None:
        self.requested_ai_id = ""

    async def read(self, ai_id: str) -> PersonalityResponse:
        self.requested_ai_id = ai_id
        return PersonalityResponse(
            ai_id=ai_id,
            name="洛雨",
            identity="持续存在的数字 AI",
            traits=["真诚"],
            speaking_style="简短自然",
            catchphrases=[],
            taboos=["泄露凭据"],
            version=1,
            fingerprint="abc",
        )


class FixedSelfMemoryReader:
    async def read(self, ai_id: str) -> SelfMemoryResponse:
        return SelfMemoryResponse(
            ai_id=ai_id,
            memory=MemoryDocumentResponse(
                markdown="# 自我长期认知\n\n- 保持真诚",
                version=3,
                updated_at=NOW,
            ),
        )


class FixedPeopleMemoryReader:
    async def list(self, ai_id: str, query: str) -> PeopleResponse:
        return PeopleResponse(
            ai_id=ai_id,
            people=[
                PersonSummary(
                    person_id="123",
                    display_name="小明",
                    qq="10001",
                    version=2,
                    updated_at=NOW,
                )
            ],
        )

    async def detail(self, ai_id: str, person_id: str) -> PersonMemoryResponse:
        person = PersonSummary(
            person_id=person_id,
            display_name="小明",
            qq="10001",
            version=2,
            updated_at=NOW,
        )
        return PersonMemoryResponse(
            ai_id=ai_id,
            person=person,
            memory=MemoryDocumentResponse(
                markdown="# 联系人长期认知\n\n- 喜欢蓝色",
                version=2,
                updated_at=NOW,
            ),
        )


class FakeResult:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class CapturingSession:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.statement = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def execute(self, statement) -> FakeResult:
        self.statement = statement
        return FakeResult(self.rows)


class CapturingDatabase:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.fake_session = CapturingSession(rows)

    def session(self) -> CapturingSession:
        return self.fake_session


def create_observability_app(personality_reader: FixedPersonalityReader) -> FastAPI:
    app = FastAPI()
    app.state.config = SimpleNamespace(
        ai_id="ai_luoyu",
        nacos_url="/nacos/",
        napcat_url="/webui/",
        napcat_token="secret token",
        k8s_url="/dashboard/",
    )
    app.state.session_store = AlwaysValidSessionStore()
    app.state.personality_reader = personality_reader
    app.state.self_memory_reader = FixedSelfMemoryReader()
    app.state.people_memory_reader = FixedPeopleMemoryReader()
    app.include_router(router)
    return app


class ObservabilityRouteTests(unittest.TestCase):
    def test_routes_use_fixed_ai_and_return_raw_markdown(self) -> None:
        personality_reader = FixedPersonalityReader()
        with TestClient(create_observability_app(personality_reader)) as client:
            client.cookies.set("ai_love_session", "valid-session")

            personality = client.get("/ai-love-api/personality?ai_id=another-ai")
            self_memory = client.get("/ai-love-api/self-memory")
            person_memory = client.get("/ai-love-api/people/123/memory")

            self.assertEqual(200, personality.status_code)
            self.assertEqual("ai_luoyu", personality_reader.requested_ai_id)
            self.assertEqual("# 自我长期认知\n\n- 保持真诚", self_memory.json()["memory"]["markdown"])
            self.assertEqual("# 联系人长期认知\n\n- 喜欢蓝色", person_memory.json()["memory"]["markdown"])

    def test_entries_include_napcat_token_without_exposing_separate_field(self) -> None:
        with TestClient(create_observability_app(FixedPersonalityReader())) as client:
            client.cookies.set("ai_love_session", "valid-session")
            response = client.get("/ai-love-api/entries")

            self.assertEqual(200, response.status_code)
            payload = response.json()
            napcat = next(item for item in payload["entries"] if item["key"] == "napcat")
            self.assertEqual("/webui/?token=secret+token", napcat["url"])
            self.assertNotIn("token", payload)


class ObservabilityReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_personality_reader_uses_merged_real_nacos_definition(self) -> None:
        reader = PersonalityReader(NacosAgentDefinitionStore(FileConfigProvider()))

        result = await reader.read("ai_luoyu")

        self.assertEqual("洛雨", result.name)
        self.assertEqual(["真诚", "活泼", "有自己的判断"], result.traits)
        self.assertIn("泄露私聊内容或账号凭据", result.taboos)
        self.assertNotEqual("", result.fingerprint)

    async def test_people_search_builds_database_ilike_and_returns_qq_identity(self) -> None:
        database = CapturingDatabase(
            [
                SimpleNamespace(
                    owner_id="123",
                    display_name="小明",
                    qq="10001",
                    version=4,
                    updated_at=NOW,
                )
            ]
        )
        reader = PeopleMemoryReader(database)

        result = await reader.list("ai_luoyu", "小明")

        statement = str(
            database.fake_session.statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("ILIKE", statement)
        self.assertIn("memory_documents.owner_type = 'person'", statement)
        self.assertEqual("10001", result.people[0].qq)


if __name__ == "__main__":
    unittest.main()
