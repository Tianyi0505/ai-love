from __future__ import annotations

import asyncio
import sys
import unittest
from types import SimpleNamespace

try:
    import websockets  # noqa: F401
except ModuleNotFoundError:
    sys.modules["websockets"] = SimpleNamespace()
try:
    import asyncpg  # noqa: F401
except ModuleNotFoundError:
    sys.modules["asyncpg"] = SimpleNamespace()

from agent.conversation.response_plan import Emotion, ResponsePlan, Speech
from agent.conversation.turn_coordinator import TurnCoordinator
from shared.contracts.entity import EntityCandidate, EntityContext, EntityReference
from shared.contracts.social import Chat, ChatType, SocialMessage, SocialSender
from shared.contracts.turn import AgentExecutionContext, ResponseCommand


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
        self.assertTrue(execution.run_id.isdecimal())


class ResponseCommandTests(unittest.TestCase):
    def test_send_payload_carries_reply_and_media(self) -> None:
        command = ResponseCommand(
            run_id="run-1",
            ai_id="luoyu",
            account_id="qq-main",
            conversation_id="conv-1",
            platform="qq",
            chat={"chat_id": "12345", "chat_type": "group"},
            reply_to_message_id="987654",
            text="在的",
            sticker={"id": "s1", "image_url": "http://img"},
            voice=None,
        )
        payload = command.send_request().model_dump(mode="json", exclude_none=True)
        self.assertEqual("987654", payload["reply_to_message_id"])
        self.assertEqual("在的", payload["text"])
        self.assertEqual({"id": "s1", "image_url": "http://img"}, payload["sticker"])
        self.assertNotIn("voice", payload)
        self.assertEqual("run-1", payload["run_id"])

class EntityContextTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        context = EntityContext(
            current_sender={"person_id": "p1", "display_name": "饼干罐橘子"},
            references=(
                EntityReference(
                    text="群主",
                    status="candidate",
                    person_id="",
                    display_name="",
                    candidates=(
                        EntityCandidate(
                            person_id="p2",
                            display_name="李四",
                            confidence=0.9,
                            evidence=(),
                        ),
                    ),
                    evidence=(),
                ),
            ),
            recent_participants=(
                {
                    "person_id": "p2",
                    "display_name": "李四",
                    "group_card": "老李",
                    "roles": ["owner"],
                    "last_message_id": "m1",
                    "last_seen_at": "now",
                },
            ),
        )
        restored = EntityContext.model_validate_json(context.model_dump_json())
        self.assertEqual(context, restored)
        self.assertEqual("candidate", restored.references[0].status)
        self.assertEqual("p2", restored.references[0].candidates[0].person_id)

    def test_invalid_entity_context_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EntityContext.model_validate(None)


class ResponsePlanTextTests(unittest.TestCase):
    def test_markdown_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Speech(text="**嘿嘿** `好耶` [链接](http://x) 来了", delivery="text")

    def test_plain_text_keeps_normal_content(self) -> None:
        plan = ResponsePlan(
            speech=[Speech(text="好耶，就这么办", delivery="text")],
            emotion=Emotion(name="happy", intensity=0.5),
            actions=[],
        )
        self.assertEqual("好耶，就这么办", plan.text)


if __name__ == "__main__":
    unittest.main()
