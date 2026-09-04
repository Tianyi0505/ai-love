from __future__ import annotations

import asyncio
import datetime as dt
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import yaml

from agent.conversation.multimodal_input import MessageInput
from agent.conversation.prompt_assembler import PromptAssembler
from agent.conversation.response_plan import Emotion, ResponsePlan, Speech
from agent.social.proactive_private_service import ProactivePrivateService
from agent.social.social_message_handler import handle_social
from shared.contracts.rpc.memory import MemoryContextResponse
from shared.contracts.rpc.relationship import (
    PersonRelationshipRecord,
    RelationshipListResponse,
    RelationshipSummaryResponse,
)
from shared.contracts.rpc.social import SocialSendResponse
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.nacos_agent_definition_store import NacosAgentDefinitionStore

ROOT = Path(__file__).resolve().parents[1]


class FileConfigProvider:
    async def get(self, key: str) -> dict:
        path = ROOT / "deploy" / "nacos" / f"{key}.yaml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))


class ProactivePrivateServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        self.now = dt.datetime(2026, 8, 30, 12, tzinfo=dt.timezone.utc)

    def relationship(
        self,
        *,
        person_id: str,
        user_id: str,
        name: str,
        priority: bool,
        hours_since_interaction: int = 12,
    ) -> PersonRelationshipRecord:
        return PersonRelationshipRecord(
            person_id=person_id,
            display_name=name,
            user_id=user_id,
            account_id="qq-main",
            familiarity=1.0 if priority else 0.5,
            affinity=1.0 if priority else 0.3,
            trust=0.4,
            importance=0.2,
            last_interaction_at=self.now - dt.timedelta(hours=hours_since_interaction),
            priority_contact=priority,
        )

    def service(self, relationships: list[PersonRelationshipRecord]):
        bus = SimpleNamespace(
            request_model=AsyncMock(return_value=RelationshipListResponse(relationships=relationships))
        )
        sessions = SimpleNamespace(
            can_initiate=AsyncMock(return_value=True),
            mark_spoke=AsyncMock(),
        )
        memory = SimpleNamespace(
            context=AsyncMock(
                return_value=MemoryContextResponse(
                    self_markdown="# 自我长期认知\n- 最近在学烘焙",
                    person_markdown="# 联系人长期认知\n- 正在准备考试",
                    conversation_summary="上次聊到复习计划",
                )
            )
        )
        chat_agent = SimpleNamespace(
            generate_plan=AsyncMock(
                return_value=ResponsePlan(
                    speech=[Speech(text="复习得怎么样啦", delivery="text")],
                    emotion=Emotion(name="neutral", intensity=0.2),
                    actions=[],
                )
            )
        )
        send_response = AsyncMock(return_value=SocialSendResponse(message_id="message-1"))
        conversation = SimpleNamespace(add_ai=Mock())
        service = ProactivePrivateService(
            ai_id=self.definition.ai_id,
            default_account_id="qq-main",
            bus=bus,
            relationship_timeout_sec=1.0,
            sessions=sessions,
            conversation=conversation,
            memory=memory,
            persona=SimpleNamespace(name_for=lambda _user_id: ""),
            prompt_assembler=PromptAssembler(self.definition),
            chat_agent=chat_agent,
            proactive=self.definition.behavior_policy.proactive,
            behavior_schedule=SimpleNamespace(allows_proactive=lambda _now=None: True),
            send_response=send_response,
        )
        return service, bus, sessions, memory, chat_agent, send_response, conversation

    async def test_uses_memory_to_send_to_available_relationship_candidate(self) -> None:
        priority = self.relationship(person_id="person-priority", user_id="10001", name="优先联系人", priority=True)
        other = self.relationship(person_id="person-other", user_id="10002", name="其他联系人", priority=False)
        service, _bus, sessions, memory, chat_agent, send_response, conversation = self.service([other, priority])
        sessions.can_initiate.side_effect = [False, True]

        sent = await service.run_once(self.now)

        self.assertTrue(sent)
        self.assertEqual(
            [
                ("proactive-private:10001", 43200),
                ("proactive-private:10002", 43200),
            ],
            [call.args for call in sessions.can_initiate.await_args_list],
        )
        memory.context.assert_awaited_once_with(person_id="person-other")
        system_prompt, user_prompt = chat_agent.generate_plan.await_args.args
        self.assertNotIn("正在准备考试", system_prompt)
        self.assertNotIn("上次聊到复习计划", system_prompt)
        self.assertLess(user_prompt.index("<retrieved_context>"), user_prompt.index("<user_question>"))
        self.assertIn("正在准备考试", user_prompt)
        self.assertIn("上次聊到复习计划", user_prompt)
        self.assertIn("这不是联系人发来的消息", user_prompt)
        self.assertEqual(False, chat_agent.generate_plan.await_args.kwargs["allow_tools"])
        command = send_response.await_args.args[0]
        self.assertEqual("10002", command.chat["chat_id"])
        self.assertEqual("private", command.chat["chat_type"])
        self.assertEqual("复习得怎么样啦", command.text)
        sessions.mark_spoke.assert_awaited_once_with("proactive-private:10002")
        conversation.add_ai.assert_called_once_with("private", "10002", "复习得怎么样啦")

    async def test_recent_interaction_does_not_enter_generation(self) -> None:
        recent = self.relationship(
            person_id="person-recent",
            user_id="10003",
            name="刚聊过的人",
            priority=True,
            hours_since_interaction=1,
        )
        service, _bus, sessions, memory, chat_agent, send_response, _conversation = self.service([recent])

        sent = await service.run_once(self.now)

        self.assertFalse(sent)
        sessions.can_initiate.assert_not_awaited()
        memory.context.assert_not_awaited()
        chat_agent.generate_plan.assert_not_awaited()
        send_response.assert_not_awaited()


class ProactivePrivateReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_inbound_marks_proactive_session_replied(self) -> None:
        definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        tasks = []

        def spawn(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task

        sessions = SimpleNamespace(mark_replied=AsyncMock())
        service = SimpleNamespace(
            ai_id=definition.ai_id,
            settings=SimpleNamespace(social=SimpleNamespace(log_preview_chars=30)),
            message_input=SimpleNamespace(build=AsyncMock(return_value=MessageInput("你好"))),
            sticker_collector=object(),
            persona=SimpleNamespace(
                name_for=lambda _user_id: "",
                should_respond_directly=lambda *_args: False,
            ),
            sessions=sessions,
            proactive_private=SimpleNamespace(
                session_key=ProactivePrivateService.session_key,
            ),
            definition=definition,
            bus=SimpleNamespace(
                request_model=AsyncMock(return_value=RelationshipSummaryResponse(summary="")),
            ),
            _timeouts=SimpleNamespace(relationship_update_sec=1.0),
            spawn=spawn,
        )
        message = SocialMessage(
            chat=Chat(chat_id="10001", chat_type=ChatType.PRIVATE, chat_name="联系人"),
            sender=SocialSender(user_id="10001", name="联系人"),
            type=ContentType.TEXT,
            text="你好",
            message_id="message-1",
            timestamp=1,
            account_id="qq-main",
            platform="qq",
            meta={"person_id": "person-1", "conversation_id": "conversation-1"},
        )

        await handle_social(service, message)
        await asyncio.gather(*tasks)

        sessions.mark_replied.assert_awaited_once_with("proactive-private:10001")
if __name__ == "__main__":
    unittest.main()
