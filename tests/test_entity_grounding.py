from __future__ import annotations

import sys
from types import SimpleNamespace
import unittest

try:
    import websockets  # noqa: F401
except ModuleNotFoundError:
    sys.modules["websockets"] = SimpleNamespace()
try:
    import asyncpg  # noqa: F401
except ModuleNotFoundError:
    sys.modules["asyncpg"] = SimpleNamespace()

from agent.clients.extensions import register_tools
from agent.generation.agent_loop import AgentLoop
from ai.llm.types import ChatMessage, ChatStreamChunk, ToolCall
from gateway.channels.qq import QQChannel
from memory.repositories.episode_repo import EpisodeMemoryRepository
from shared.contracts.tools import ToolExecutionContext
from shared.infrastructure.entity_grounding import EntityGroundingRepository


class _Prompts:
    def render(self, key: str, **values) -> str:
        return f"{key}:{values}"


class _RoundLLM:
    def __init__(self) -> None:
        self.requests = []

    async def chat(self, request):
        self.requests.append(request)
        if len(self.requests) <= 3:
            yield ChatStreamChunk(
                tool_call=ToolCall(
                    name="resolve_people",
                    arguments={"mention": "群主", "chat_id": "模型伪造群"},
                )
            )
        else:
            yield ChatStreamChunk(content="最终回答")


class _ExtensionBus:
    def __init__(self) -> None:
        self.execute_request = None

    async def request_json(self, subject, payload, timeout):
        if subject == "tool.list.request":
            return {
                "tools": [
                    {
                        "name": "resolve_people",
                        "description": "解析称呼",
                        "parameters": {"type": "object"},
                    }
                ]
            }
        self.execute_request = payload
        return {"content": "{}"}


class _LoopRegistry:
    def register_tool(self, name, info, executor):
        self.name = name
        self.info = info
        self.executor = executor


class _MemoryDB:
    def __init__(self, member_allowed: bool = True) -> None:
        self.member_allowed = member_allowed
        self.queries = []

    async def fetchrow(self, query, *args):
        self.queries.append(query)
        if "FROM conversations" in query:
            return {"exists": True}
        if "FROM group_members" in query:
            return {"exists": True} if self.member_allowed else None
        if "FROM conversation_summaries" in query:
            return {"summary": "仅当前群摘要"}
        return None

    async def fetch(self, query, *args):
        self.queries.append(query)
        return [
            {
                "content": "群里公开讨论过 Voice Agent",
                "memory_type": "fact",
                "importance": 0.8,
                "confidence": 0.9,
                "created_at": "now",
            }
        ]


class _RoleDB:
    def __init__(self) -> None:
        self.queries = []

    async def fetch(self, query, *args):
        self.queries.append(query)
        return [
            {
                "person_id": "22222222-2222-2222-2222-222222222222",
                "display_name": "当前群主",
                "role": "owner",
            }
        ]


class EntityGroundingTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_owner_is_resolved_from_live_group_members(self) -> None:
        db = _RoleDB()
        repo = EntityGroundingRepository(db, evidence_half_life_sec=2592000)
        context = ToolExecutionContext(
            platform="qq",
            account_id="account",
            chat_type="group",
            chat_id="group",
        )

        result = await repo.resolve_people(context, "群主", 5)

        self.assertEqual(
            "22222222-2222-2222-2222-222222222222",
            result["candidates"][0]["person_id"],
        )
        self.assertEqual("group_role", result["candidates"][0]["evidence"][0]["type"])
        self.assertFalse(any("person_mentions" in query for query in db.queries))

    async def test_three_tool_rounds_still_have_final_generation(self) -> None:
        llm = _RoundLLM()
        loop = AgentLoop(llm, _Prompts(), ai_id="ai", max_rounds=3)
        trusted = ToolExecutionContext(ai_id="ai", chat_type="group", chat_id="真实群")
        received = []

        async def execute(arguments, context):
            received.append((arguments, context))
            return "{}"

        loop.register_tool("resolve_people", {"description": "", "parameters": {}}, execute)
        result = await loop.run(
            [ChatMessage(role="user", content="群主是谁")],
            tool_context=trusted,
        )

        self.assertEqual("最终回答", result)
        self.assertEqual(4, len(llm.requests))
        self.assertEqual([], llm.requests[-1].tools)
        self.assertEqual(["真实群"] * 3, [context.chat_id for _, context in received])
        self.assertTrue(all(arguments["chat_id"] == "模型伪造群" for arguments, _ in received))

    async def test_extension_request_keeps_arguments_and_context_separate(self) -> None:
        bus = _ExtensionBus()
        loop = _LoopRegistry()
        await register_tools(
            loop,
            bus,
            "ai",
            {"tool_list_sec": 1, "tool_execute_sec": 1},
        )
        trusted = ToolExecutionContext(ai_id="ai", chat_type="group", chat_id="真实群")

        await loop.executor({"mention": "群主", "chat_id": "模型伪造群"}, trusted)

        self.assertEqual("真实群", bus.execute_request["execution_context"]["chat_id"])
        self.assertEqual("模型伪造群", bus.execute_request["arguments"]["chat_id"])
        self.assertNotIn("chat_id", {key: value for key, value in bus.execute_request.items() if key != "arguments" and key != "execution_context"})

    async def test_group_person_context_only_reads_current_conversation_atoms(self) -> None:
        db = _MemoryDB()
        repo = EpisodeMemoryRepository(db, history_episode_limit=12)
        context = ToolExecutionContext(
            ai_id="ai",
            account_id="account",
            conversation_id="11111111-1111-1111-1111-111111111111",
            platform="qq",
            chat_type="group",
            chat_id="group",
            sender_person_id="22222222-2222-2222-2222-222222222222",
        )

        result = await repo.person_context(
            context,
            "22222222-2222-2222-2222-222222222222",
            8,
        )

        self.assertEqual("群里公开讨论过 Voice Agent", result["facts"][0]["content"])
        self.assertTrue(any("conversation_episodes" in query for query in db.queries))
        self.assertFalse(any("memory_documents" in query for query in db.queries))

    async def test_group_person_context_rejects_non_member_before_reading_memory(self) -> None:
        db = _MemoryDB(member_allowed=False)
        repo = EpisodeMemoryRepository(db, history_episode_limit=12)
        context = ToolExecutionContext(
            ai_id="ai",
            account_id="account",
            conversation_id="11111111-1111-1111-1111-111111111111",
            platform="qq",
            chat_type="group",
            chat_id="group",
        )

        result = await repo.person_context(
            context,
            "22222222-2222-2222-2222-222222222222",
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
                "reconnect_delay_sec": 1,
            }
        )
        message = channel._to_message(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 123,
                "user_id": 20000,
                "sender": {"nickname": "发送者", "role": "member"},
                "message": [
                    {"type": "at", "data": {"qq": "30000", "name": "老王"}},
                    {"type": "at", "data": {"qq": "10000", "name": "洛雨"}},
                    {"type": "text", "data": {"text": " 群主怎么看"}},
                ],
            }
        )

        self.assertEqual(["30000", "10000"], message.meta["at_user_ids"])
        self.assertEqual("老王", message.meta["at_mentions"][0]["name"])
        self.assertTrue(message.to_ai)


if __name__ == "__main__":
    unittest.main()
