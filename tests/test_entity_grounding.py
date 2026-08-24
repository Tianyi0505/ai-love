from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

try:
    import websockets  # noqa: F401
except ModuleNotFoundError:
    sys.modules["websockets"] = SimpleNamespace()
try:
    import asyncpg  # noqa: F401
except ModuleNotFoundError:
    sys.modules["asyncpg"] = SimpleNamespace()

from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from agent.clients.extension_toolset_loader import load_toolset
from gateway.channels.napcat_message_event import NapCatMessageEvent
from gateway.channels.qq_channel import QQChannel
from memory.repositories.episode_memory_repository import EpisodeMemoryRepository
from shared.configuration.global_settings import GlobalSettings
from shared.contracts.tools import ToolExecutionContext
from shared.domain.entity_grounding_facade import EntityGroundingFacade
from shared.utils.lfu import LazyLFU, LFUConfig

ROOT = Path(__file__).resolve().parents[1]


def global_settings():
    config = yaml.safe_load((ROOT / "deploy" / "nacos" / "ailove.config.yaml").read_text(encoding="utf-8"))
    config["qq"]["whitelist"] = []
    return GlobalSettings.model_validate(config)


class _ExtensionBus:
    def __init__(self) -> None:
        self.execute_request = None

    async def request_model(self, subject, request, response_type, timeout):
        if subject == "tool.list.request":
            return response_type.model_validate({
                "tools": [
                    {
                        "name": "resolve_people",
                        "description": "解析称呼",
                        "parameters": {"type": "object"},
                        "provider": "grounding",
                    }
                ]
            })
        self.execute_request = request.model_dump(mode="json")
        return response_type.model_validate({"content": "{}", "data": {}})


class _Rows(list):
    def first(self):
        return self[0] if self else None

    def scalar_one_or_none(self):
        return self[0][0] if self and self[0] else None


class _NapCatResponse:
    def __init__(self, data) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._data


class _NapCatHTTP:
    def __init__(self, message) -> None:
        self.message = message
        self.requests = []

    async def post(self, url, json, timeout):
        self.requests.append((url, json, timeout))
        return _NapCatResponse({"data": self.message})


class _MemoryDB:
    def __init__(self, member_allowed: bool = True) -> None:
        self.member_allowed = member_allowed
        self.queries = []

    def session(self):
        return _FakeSession(self)


class _FakeSession:
    def __init__(self, db) -> None:
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        sql = str(stmt)
        self._db.queries.append(sql)
        lowered = sql.lower()
        if "from conversations" in lowered:
            return _Rows([(True,)])
        if "from messages" in lowered:
            return _Rows([(True,)])
        if "from group_members" in lowered:
            return _Rows([(True,)]) if self._db.member_allowed else _Rows([])
        if "from memory_atoms" in lowered:
            return _Rows(
                [
                    SimpleNamespace(
                        content="群里公开讨论过 Voice Agent",
                        memory_type="fact",
                        importance=0.8,
                        confidence=0.9,
                        created_at="now",
                    )
                ]
            )
        if "from conversation_summaries" in lowered:
            return _Rows([SimpleNamespace(summary="仅当前群摘要")])
        return _Rows([])


class _RoleDB:
    def __init__(self) -> None:
        self.queries = []

    def session(self):
        return _RoleSession(self)


class _RoleSession:
    def __init__(self, db) -> None:
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        sql = str(stmt)
        self._db.queries.append(sql)
        if "group_members" in sql.lower():
            return _Rows(
                [
                    SimpleNamespace(
                        person_id="222222222222222222",
                        display_name="当前群主",
                        role="owner",
                    )
                ]
            )
        return _Rows([])


class EntityGroundingTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_owner_is_resolved_from_live_group_members(self) -> None:
        db = _RoleDB()
        settings = global_settings()
        repo = EntityGroundingFacade(
            db,
            settings.grounding,
            LazyLFU(LFUConfig(**settings.lfu.evidence.model_dump())),
        )
        context = ToolExecutionContext(
            platform="qq",
            account_id="account",
            chat_type="group",
            chat_id="group",
        )

        result = await repo.resolve_people(context, "群主", 5)

        self.assertEqual(
            "222222222222222222",
            result.candidates[0].person_id,
        )
        self.assertEqual("group_role", result.candidates[0].evidence[0]["type"])
        self.assertFalse(any("person_mentions" in query for query in db.queries))

    async def test_extension_request_keeps_arguments_and_context_separate(self) -> None:
        bus = _ExtensionBus()
        toolset = await load_toolset(
            bus,
            "ai",
            SimpleNamespace(tool_list_sec=1, tool_execute_sec=1),
            max_retries=0,
        )
        trusted = ToolExecutionContext(ai_id="ai", chat_type="group", chat_id="真实群")
        context = RunContext(deps=trusted, model=TestModel(), usage=RunUsage())
        tools = await toolset.get_tools(context)
        await toolset.call_tool(
            "resolve_people",
            {"mention": "群主", "chat_id": "模型伪造群"},
            context,
            tools["resolve_people"],
        )

        self.assertEqual("真实群", bus.execute_request["execution_context"]["chat_id"])
        self.assertEqual("模型伪造群", bus.execute_request["arguments"]["chat_id"])
        self.assertNotIn(
            "chat_id",
            {
                key: value
                for key, value in bus.execute_request.items()
                if key != "arguments" and key != "execution_context"
            },
        )

    async def test_group_person_context_only_reads_current_conversation_atoms(self) -> None:
        db = _MemoryDB()
        repo = EpisodeMemoryRepository(db, global_settings().memory)
        context = ToolExecutionContext(
            ai_id="ai",
            account_id="account",
            conversation_id="111111111111111111",
            platform="qq",
            chat_type="group",
            chat_id="group",
            sender_person_id="222222222222222222",
        )

        result = await repo.person_context(
            context,
            "222222222222222222",
            8,
        )

        self.assertEqual("群里公开讨论过 Voice Agent", result["facts"][0]["content"])
        self.assertTrue(any("conversation_episodes" in query for query in db.queries))
        self.assertFalse(any("memory_documents" in query for query in db.queries))

    async def test_group_person_context_rejects_non_member_before_reading_memory(self) -> None:
        db = _MemoryDB(member_allowed=False)
        repo = EpisodeMemoryRepository(db, global_settings().memory)
        context = ToolExecutionContext(
            ai_id="ai",
            account_id="account",
            conversation_id="111111111111111111",
            platform="qq",
            chat_type="group",
            chat_id="group",
        )

        result = await repo.person_context(
            context,
            "222222222222222222",
            8,
        )

        self.assertIsNone(result)
        self.assertFalse(any("memory_atoms" in query for query in db.queries))

    async def test_qq_message_preserves_all_at_targets_for_fast_grounding(self) -> None:
        channel = QQChannel(
            {
                "ws_url": "ws://127.0.0.1",
                "http_url": "http://127.0.0.1",
                "uin": "10000",
                "account_id": "qq-main",
                "message_timeout_sec": 1,
                "forward_timeout_sec": 1,
                "content_strategies": ["quote", "forward", "voice", "image", "file", "at", "text"],
            },
            http_client=object(),
        )
        message = channel._to_message(
            NapCatMessageEvent.model_validate(
                {
                "post_type": "message",
                "message_type": "group",
                "group_id": 123,
                "user_id": 20000,
                "message_id": 999,
                "time": 1,
                "sender": {"nickname": "发送者", "role": "member"},
                "message": [
                    {"type": "at", "data": {"qq": "30000", "name": "老王"}},
                    {"type": "at", "data": {"qq": "10000", "name": "洛雨"}},
                    {"type": "text", "data": {"text": " 群主怎么看"}},
                ],
                }
            )
        )

        self.assertEqual(["30000", "10000"], message.meta["at_user_ids"])
        self.assertTrue(message.to_ai)

    async def test_qq_message_uses_onebot_quote_and_at_contract(self) -> None:
        channel = QQChannel(
            {
                "ws_url": "ws://127.0.0.1",
                "http_url": "http://127.0.0.1",
                "uin": "10000",
                "account_id": "qq-main",
                "message_timeout_sec": 1,
                "forward_timeout_sec": 1,
                "content_strategies": ["quote", "forward", "voice", "image", "file", "at", "text"],
            },
            http_client=object(),
        )

        message = channel._to_message(
            NapCatMessageEvent.model_validate(
                {
                    "post_type": "message",
                    "message_type": "group",
                    "group_id": 123,
                    "group_name": "测试群",
                    "user_id": 20000,
                    "message_id": 999,
                    "time": 1,
                    "sender": {"nickname": "发送者", "card": "发送者", "role": "member"},
                    "message": [
                        {"type": "reply", "data": {"id": "888"}},
                        {"type": "at", "data": {"qq": "30000"}},
                        {"type": "text", "data": {"text": " 你好"}},
                    ],
                }
            )
        )

        self.assertIsNotNone(message)
        self.assertEqual(["30000"], message.meta["at_user_ids"])
        self.assertNotIn("at_mentions", message.meta)
        self.assertEqual("quote", message.type.value)
        self.assertEqual("888", message.meta["reply_message_id"])

    async def test_qq_reply_target_is_resolved_through_get_msg(self) -> None:
        http = _NapCatHTTP(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 123,
                "group_name": "测试群",
                "user_id": 10000,
                "message_id": 888,
                "time": 1,
                "sender": {"nickname": "机器人", "card": "机器人", "role": "member"},
                "message": [{"type": "text", "data": {"text": "原消息"}}],
            }
        )
        channel = QQChannel(
            {
                "ws_url": "ws://127.0.0.1",
                "http_url": "http://127.0.0.1",
                "uin": "10000",
                "account_id": "qq-main",
                "message_timeout_sec": 1,
                "forward_timeout_sec": 1,
                "content_strategies": ["quote", "forward", "voice", "image", "file", "at", "text"],
            },
            http_client=http,
        )
        message = channel._to_message(
            NapCatMessageEvent.model_validate(
                {
                    "post_type": "message",
                    "message_type": "group",
                    "group_id": 123,
                    "group_name": "测试群",
                    "user_id": 20000,
                    "message_id": 999,
                    "time": 2,
                    "sender": {"nickname": "发送者", "card": "发送者", "role": "member"},
                    "message": [
                        {"type": "reply", "data": {"id": "888"}},
                        {"type": "text", "data": {"text": "回复机器人"}},
                    ],
                }
            )
        )

        self.assertFalse(message.to_ai)
        hydrated = await channel.hydrate_message(message)

        self.assertTrue(hydrated.to_ai)
        self.assertEqual("10000", hydrated.quote_ref.sender.user_id)
        self.assertEqual({"message_id": 888}, http.requests[0][1])

    async def test_qq_message_handler_failure_does_not_escape_channel_task(self) -> None:
        channel = QQChannel(
            {
                "ws_url": "ws://127.0.0.1",
                "http_url": "http://127.0.0.1",
                "uin": "10000",
                "account_id": "qq-main",
                "message_timeout_sec": 1,
                "forward_timeout_sec": 1,
                "content_strategies": ["quote", "forward", "voice", "image", "file", "at", "text"],
            },
            http_client=object(),
        )
        message = channel._to_message(
            NapCatMessageEvent.model_validate(
                {
                    "post_type": "message",
                    "message_type": "private",
                    "user_id": 20000,
                    "message_id": 999,
                    "time": 1,
                    "sender": {"nickname": "发送者"},
                    "message": [{"type": "text", "data": {"text": "你好"}}],
                }
            )
        )

        async def failing_handler(_message) -> None:
            raise RuntimeError("下游失败")

        channel.set_message_handler(failing_handler)
        with self.assertLogs("ailove.gateway.qq", level="ERROR"):
            await channel._handle_message(message)


if __name__ == "__main__":
    unittest.main()
