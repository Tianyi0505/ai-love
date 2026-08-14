from __future__ import annotations

import asyncio
import json
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

from agent.application.turn_coordinator import TurnCoordinator
from agent.generation.agent_loop import AgentLoop
from ai.llm.types import ChatMessage, ChatStreamChunk, ToolCall
from shared.contracts.entity import EntityCandidate, EntityContext, EntityReference
from shared.contracts.social import Chat, ChatType, SocialMessage, SocialSender
from shared.contracts.turn import AgentExecutionContext, ResponseCommand
from shared.contracts.tools import ToolExecutionContext
from shared.infrastructure.run_repo import AgentRunRepository


class _Prompts:
    def render(self, key: str, **values) -> str:
        return f"{key}:{values}"


class _StepLLM:
    def __init__(self) -> None:
        self.requests = []

    async def chat(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            yield ChatStreamChunk(tool_call=ToolCall(name="resolve_people", arguments={"mention": "老王"}))
        else:
            yield ChatStreamChunk(content="最终回答")


class _RecordingDB:
    def __init__(self) -> None:
        self.rows = []

    async def execute(self, query, *args):
        self.rows.append((query, args))
        return "OK"


class _FetchDB:
    def __init__(self) -> None:
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return None

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return "OK"


class TurnCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_conversation_serializes(self) -> None:
        coordinator = TurnCoordinator()
        order: list[str] = []

        async def work(lock_key: str, tag: str, delay: float) -> None:
            async with coordinator.lock_for(lock_key):
                order.append(f"{tag}:start")
                await asyncio.sleep(delay)
                order.append(f"{tag}:end")

        await asyncio.gather(
            work("ai\x1fconv", "one", 0.03),
            work("ai\x1fconv", "two", 0.0),
        )
        self.assertEqual(["one:start", "one:end", "two:start", "two:end"], order)

    async def test_different_conversations_run_concurrently(self) -> None:
        coordinator = TurnCoordinator()
        events: list[str] = []
        gate = asyncio.Event()

        async def work(lock_key: str, tag: str) -> None:
            async with coordinator.lock_for(lock_key):
                events.append(f"{tag}:start")
                await gate.wait()
                events.append(f"{tag}:end")

        task_a = asyncio.create_task(work("ai\x1fconv-a", "a"))
        task_b = asyncio.create_task(work("ai\x1fconv-b", "b"))
        await asyncio.sleep(0.02)
        self.assertIn("a:start", events)
        self.assertIn("b:start", events)
        gate.set()
        await asyncio.gather(task_a, task_b)


class AgentExecutionContextTests(unittest.TestCase):
    def test_from_social_message_keeps_gateway_run_id_and_scope(self) -> None:
        message = SocialMessage(
            chat=Chat(chat_id="12345", chat_type=ChatType.GROUP),
            sender=SocialSender(user_id="20000", name="张三"),
            type="text",
            message_id="m-1",
            account_id="qq-main",
            platform="qq",
            meta={
                "run_id": "gateway-run",
                "conversation_id": "11111111-1111-1111-1111-111111111111",
                "person_id": "22222222-2222-2222-2222-222222222222",
            },
        )
        execution = AgentExecutionContext.from_social_message(message, "luoyu")
        self.assertEqual("gateway-run", execution.run_id)
        self.assertEqual("group", execution.chat_type)
        self.assertEqual("12345", execution.chat_id)
        self.assertEqual("22222222-2222-2222-2222-222222222222", execution.tool_context().sender_person_id)

    def test_missing_run_id_is_generated_once(self) -> None:
        message = SocialMessage(
            chat=Chat(chat_id="u1", chat_type=ChatType.PRIVATE),
            sender=SocialSender(user_id="u1"),
            type="text",
            meta={},
        )
        execution = AgentExecutionContext.from_social_message(message, "luoyu")
        self.assertTrue(execution.run_id)
        self.assertEqual(32, len(execution.run_id))


class ResponseCommandTests(unittest.TestCase):
    def test_send_payload_carries_reply_and_media(self) -> None:
        command = ResponseCommand(
            run_id="run-1",
            ai_id="luoyu",
            account_id="qq-main",
            conversation_id="conv-1",
            chat={"chat_id": "12345", "chat_type": "group"},
            reply_to_message_id="987654",
            text="在的",
            sticker={"id": "s1", "image_url": "http://img"},
        )
        payload = command.send_payload()
        self.assertEqual("987654", payload["reply_to_message_id"])
        self.assertEqual("在的", payload["text"])
        self.assertEqual({"id": "s1", "image_url": "http://img"}, payload["sticker"])
        self.assertNotIn("voice", payload)
        self.assertEqual("run-1", payload["run_id"])

    def test_without_sticker_drops_only_sticker(self) -> None:
        command = ResponseCommand(
            run_id="run-1",
            ai_id="luoyu",
            account_id="qq-main",
            conversation_id="conv-1",
            chat={"chat_id": "u1", "chat_type": "private"},
            text="在的",
            sticker={"id": "s1"},
            voice={"audio_path": "/a"},
        )
        retry = command.without_sticker()
        self.assertIsNone(retry.sticker)
        self.assertEqual(command.voice, retry.voice)
        self.assertEqual(command.text, retry.text)
        self.assertNotIn("sticker", retry.send_payload())


class EntityContextTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        context = EntityContext(
            current_sender={"person_id": "p1", "display_name": "饼干罐橘子"},
            references=(EntityReference(
                text="群主",
                status="candidate",
                candidates=(EntityCandidate(person_id="p2", display_name="李四", confidence=0.9),),
            ),),
            recent_participants=(
                {"person_id": "p2", "display_name": "李四", "group_card": "老李", "roles": ["owner"], "last_message_id": "m1", "last_seen_at": "now"},
            ),
        )
        restored = EntityContext.from_dict(json.loads(json.dumps(context.to_dict())))
        self.assertEqual(context.to_dict(), restored.to_dict())
        self.assertEqual("candidate", restored.references[0].status)
        self.assertEqual("p2", restored.references[0].candidates[0].person_id)

    def test_from_dict_tolerates_missing(self) -> None:
        self.assertEqual(EntityContext().to_dict(), EntityContext.from_dict(None).to_dict())


class AgentRunSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_runs_applies_filters(self) -> None:
        db = _FetchDB()
        repo = AgentRunRepository(db)
        await repo.search_runs(
            ai_id="luoyu",
            conversation_id="11111111-1111-1111-1111-111111111111",
            source="social",
            limit=20,
        )
        self.assertEqual(1, len(db.calls))
        query, args = db.calls[0]
        self.assertIn("ai_id=$1", query)
        self.assertIn("conversation_id=$2::uuid", query)
        self.assertIn("source=$3", query)
        self.assertIn("LIMIT $4 OFFSET $5", query)
        self.assertEqual(["luoyu", "11111111-1111-1111-1111-111111111111", "social", 20, 0], list(args))

    async def test_search_runs_rejects_invalid_conversation_id(self) -> None:
        db = _FetchDB()
        repo = AgentRunRepository(db)
        runs = await repo.search_runs(conversation_id="not-a-uuid")
        self.assertEqual([], runs)
        self.assertEqual([], db.calls)


class AgentLoopStepTests(unittest.IsolatedAsyncioTestCase):
    async def test_on_step_receives_tool_and_final(self) -> None:
        loop = AgentLoop(_StepLLM(), _Prompts(), ai_id="ai", max_rounds=3)
        loop.register_tool(
            "resolve_people",
            {"description": "", "parameters": {}},
            lambda arguments, context: "{}",
        )
        steps: list[tuple[int, str, dict]] = []

        async def on_step(index: int, kind: str, data: dict) -> None:
            steps.append((index, kind, data))

        result = await loop.run(
            [ChatMessage(role="user", content="老王是谁")],
            tool_context=ToolExecutionContext(ai_id="ai", chat_type="group", chat_id="真实群"),
            on_step=on_step,
        )
        self.assertEqual("最终回答", result)
        self.assertEqual(2, len(steps))
        self.assertEqual("tool", steps[0][1])
        self.assertEqual("resolve_people", steps[0][2]["tool_name"])
        self.assertEqual("final", steps[1][1])
        self.assertEqual({"text": "最终回答"}, steps[1][2])


if __name__ == "__main__":
    unittest.main()
