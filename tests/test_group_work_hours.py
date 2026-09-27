from __future__ import annotations

import asyncio
import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from test_agent_prompt_config import FileConfigProvider

from agent.conversation.conversation_context import ConversationContext
from agent.conversation.multimodal_input import DescribedMessageInputBuilder
from agent.conversation.prompt_assembler import PromptAssembler
from agent.conversation.response_plan import Emotion, ParticipationDecision, ResponsePlan, Speech
from agent.conversation.session_manager import SessionManager
from agent.conversation.social_message_input import SocialMessageInputBuilder
from agent.persona import Persona
from agent.social.group_participation_service import GroupParticipationService
from agent.social.social_message_handler import handle_social
from gateway.qq_channel import QQChannel
from shared.agent_definition_store import AgentDefinitionStore
from shared.contracts.behavior import BehaviorSchedule
from shared.contracts.entity import EntityContext
from shared.contracts.rpc.relationship import (
    GroupRelationshipData,
    GroupRelationshipResponse,
    RelationshipSummaryResponse,
)
from shared.global_settings import GlobalSettings


class MemoryRedis:
    def __init__(self):
        self.hashes = {}

    async def hgetall(self, key):
        return self.hashes.get(key, {}).copy()

    def pipeline(self, **_kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    def hset(self, key, field=None, value=None, *, mapping=None):
        self.hashes.setdefault(key, {}).update(mapping or {field: value})

    def expire(self, *_args):
        pass

    async def execute(self):
        pass


@pytest.mark.parametrize(
    "whitelisted,hour,enabled,cooling,message_count,score,model_agrees,expected",
    [
        (True, 1, True, False, 2, 0.5, True, 1),
        (True, 12, True, False, 2, 0.5, True, 1),
        (False, 1, True, False, 2, 0.5, True, 0),
        (False, 12, True, False, 2, 0.5, True, 1),
        (True, 1, False, False, 2, 0.5, True, 0),
        (True, 1, True, True, 2, 0.5, True, 0),
        (True, 1, True, False, 1, 0.5, True, 0),
        (True, 1, True, False, 2, 0.0, True, 0),
        (True, 1, True, False, 2, 0.5, False, 0),
    ],
)
async def test_group_schedule_through_napcat_and_reply_handler(
    whitelisted, hour, enabled, cooling, message_count, score, model_agrees, expected,
):
    provider = FileConfigProvider()
    definition = await AgentDefinitionStore(provider).load("ai_luoyu")
    config = await provider.get("ailove.config")
    config["qq"]["whitelist"] = []
    settings = GlobalSettings.model_validate(config)
    proactive = definition.behavior_policy.proactive.model_copy(update={"enabled": enabled})
    group_id = str(definition.relationship_policy.group_ceiling_whitelist[0]) if whitelisted else "999999999"
    moment = dt.datetime(2026, 9, 27, hour, tzinfo=ZoneInfo("Asia/Shanghai"))

    class FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

    conversation = ConversationContext(10)
    sessions = SessionManager(MemoryRedis(), definition.ai_id, settings.social.session_state_ttl_sec)
    if cooling:
        await sessions.mark_spoke(f"group:{group_id}")
    prompts = PromptAssembler(definition)
    persona = Persona.from_definition(definition, settings.social)
    chat_agent = SimpleNamespace(
        decide_participation=AsyncMock(return_value=ParticipationDecision(participate=model_agrees, reason="群聊判断")),
        generate_plan=AsyncMock(return_value=ResponsePlan(
            speech=[Speech(text="收到啦", delivery="text")], emotion=Emotion(name="neutral", intensity=0.1), actions=[],
        )),
    )

    async def request(subject, *_args, **_kwargs):
        if subject == "relationship.group.request":
            return GroupRelationshipResponse(relationship=GroupRelationshipData(
                familiarity=score, belonging=score, affinity=score, activity_willingness=score,
            ))
        return RelationshipSummaryResponse(summary="")

    tasks = []

    def spawn(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    bus = SimpleNamespace(request_model=AsyncMock(side_effect=request))
    service = SimpleNamespace(
        ai_id=definition.ai_id, settings=settings, definition=definition, persona=persona,
        conversation=conversation, bus=bus, _timeouts=settings.timeouts, spawn=spawn,
        prompt_assembler=prompts, chat_agent=chat_agent, send_response=AsyncMock(),
        group_repeat=SimpleNamespace(claim_candidate=AsyncMock(return_value=False)),
        memory=SimpleNamespace(search=AsyncMock(return_value=[]), person_context=AsyncMock(
            return_value=SimpleNamespace(facts=[], conversation_summary=""))),
        message_input=SocialMessageInputBuilder(
            DescribedMessageInputBuilder(object()), conversation, object(), object(), direct_vision=False,
        ),
    )
    service.group_participation = GroupParticipationService(
        ai_id=definition.ai_id, account_id="qq-main", bus=bus, relationship_timeout_sec=1,
        sessions=sessions, conversation=conversation, persona=persona, prompt_assembler=prompts,
        chat_agent=chat_agent, proactive=proactive,
        behavior_schedule=BehaviorSchedule.from_config(definition.behavior_policy),
        group_whitelist=definition.relationship_policy.group_ceiling_whitelist,
    )
    channel = QQChannel({
        "ws_url": "ws://127.0.0.1", "http_url": "http://127.0.0.1", "uin": "10000", "account_id": "qq-main",
        "message_timeout_sec": 10, "forward_timeout_sec": 1,
        "content_strategies": ["quote", "forward", "voice", "image", "file", "at", "text"],
    }, SimpleNamespace(post=AsyncMock()))

    async def inbound(message):
        assert not message.to_ai
        assert message.chat.chat_id == group_id
        message.meta.update({
            "run_id": "1", "person_id": "person-1", "conversation_id": "conversation-1",
            "entity_context": EntityContext(current_sender={}, references=(), recent_participants=()).model_dump(),
        })
        await handle_social(service, message)

    channel.set_message_handler(inbound)

    async def messages():
        for index in range(message_count):
            yield json.dumps({
                "post_type": "message", "message_type": "group", "group_id": int(group_id),
                "user_id": 20000, "message_id": index + 1, "time": int(moment.timestamp()),
                "sender": {"nickname": "群友"}, "message": [{"type": "text", "data": {"text": f"讨论话题 {index}"}}],
            })

    async def connections():
        yield messages()

    with (
        patch("gateway.qq_channel.websockets.connect", return_value=connections()),
        patch("shared.contracts.behavior.dt.datetime", FixedDatetime),
    ):
        await channel.start()
    await asyncio.gather(*tasks)
    assert service.send_response.await_count == expected
    assert chat_agent.generate_plan.await_count == expected
    if expected:
        assert service.send_response.await_args.args[0].chat["chat_id"] == group_id
    if not whitelisted and hour == 1:
        chat_agent.decide_participation.assert_not_awaited()
