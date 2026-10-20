from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from test_agent_prompt_config import FileConfigProvider
from test_group_work_hours import MemoryRedis

from agent.conversation.conversation_context import ConversationContext
from agent.conversation.multimodal_input import DescribedMessageInputBuilder
from agent.conversation.prompt_assembler import PromptAssembler
from agent.conversation.response_plan import Emotion, ParticipationDecision, ResponsePlan, Speech
from agent.conversation.session_manager import SessionManager
from agent.conversation.social_message_input import SocialMessageInputBuilder
from agent.persona import Persona
from agent.social.group_participation_service import GroupParticipationService
from agent.social.group_repeat_service import GroupRepeatService
from agent.social.social_message_handler import handle_social
from gateway.gateway_message_handler import GatewayMessageHandler
from gateway.qq_channel import QQChannel
from gateway.social_router import SocialRouter
from shared.agent_definition_store import AgentDefinitionStore
from shared.contracts.entity import EntityContext
from shared.contracts.rpc.relationship import (
    GroupRelationshipData,
    GroupRelationshipResponse,
    RelationshipSummaryResponse,
)
from shared.contracts.social import SocialMessage
from shared.global_settings import GlobalSettings


def at(user_id):
    return {"type": "at", "data": {"qq": user_id}}


def reply(message_id):
    return {"type": "reply", "data": {"id": str(message_id)}}


def event(message_id, user_id, segments):
    return {
        "post_type": "message", "message_type": "group", "group_id": 123,
        "self_id": 10000, "user_id": user_id, "message_id": message_id, "time": 1788321000,
        "sender": {"nickname": f"用户{user_id}"},
        "message": [*segments, {"type": "text", "data": {"text": f"讨论话题 {message_id}"}}],
    }


@pytest.mark.parametrize(
    "segments,references,addressed",
    [
        pytest.param([at("30000")], {}, False, id="mention-other"),
        pytest.param([at("all")], {}, False, id="mention-everyone"),
        pytest.param([at("30000"), {"type": "image", "data": {
            "url": "https://example.com/image.png", "summary": "图片",
        }}], {}, False, id="mention-other-with-image"),
        pytest.param([reply(88)], {88: event(88, 30000, [])}, False, id="reply-other"),
        pytest.param([reply(88), at("30000")], {88: event(88, 30000, [])},
                     False, id="reply-and-mention-other"),
        pytest.param([reply(88)], {}, False, id="unresolved-reply"),
        pytest.param([reply(88)], {88: event(88, 30000, [reply(77)]), 77: event(77, 10000, [])},
                     False, id="nested-reply-to-self-is-not-current-target"),
        pytest.param([reply(88)], {88: event(88, 30000, [at("10000")])},
                     False, id="quoted-mention-is-not-current-target"),
        pytest.param([at(10000)], {}, True, id="mention-self"),
        pytest.param([at("30000"), at("10000")], {}, True, id="mention-self-among-others"),
        pytest.param([reply(88)], {88: event(88, 10000, [])}, True, id="reply-self"),
        pytest.param([reply(88), at("10000")], {88: event(88, 30000, [])},
                     True, id="mention-self-while-replying-other"),
        pytest.param([reply(88), at("30000")], {88: event(88, 10000, [])},
                     True, id="reply-self-while-mentioning-other"),
        pytest.param([reply(88), at("10000")], {}, True, id="mention-self-with-unresolved-reply"),
        pytest.param([], {}, False, id="ordinary-group-participation"),
    ],
)
@pytest.mark.parametrize("policy", ["eligible", "disabled", "cooling", "not-ready", "model-declines"])
async def test_group_reply_target_through_napcat_gateway_and_agent(segments, references, addressed, policy):
    provider = FileConfigProvider()
    definition = await AgentDefinitionStore(provider).load("ai_luoyu")
    config = await provider.get("ailove.config")
    config["qq"]["whitelist"] = []
    settings = GlobalSettings.model_validate(config)
    conversation = ConversationContext(10)
    sessions = SessionManager(MemoryRedis(), definition.ai_id, settings.social.session_state_ttl_sec)
    if policy == "cooling":
        await sessions.mark_spoke("group:123")
    persona = Persona.from_definition(definition, settings.social)
    prompts = PromptAssembler(definition)
    chat_agent = SimpleNamespace(
        decide_participation=AsyncMock(return_value=ParticipationDecision(
            participate=policy != "model-declines", reason="群聊判断",
        )),
        generate_plan=AsyncMock(return_value=ResponsePlan(
            speech=[Speech(text="收到啦", delivery="text")], emotion=Emotion(name="neutral", intensity=0.1), actions=[],
        )),
    )

    async def request(subject, *_args, **_kwargs):
        if subject == "relationship.group.request":
            return GroupRelationshipResponse(relationship=GroupRelationshipData(
                familiarity=0.5, belonging=0.5, affinity=0.5, activity_willingness=0.5,
            ))
        return RelationshipSummaryResponse(summary="")

    tasks = []

    def spawn(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    received = []

    async def publish(subject, message):
        assert subject == f"social.chat.{definition.ai_id}"
        # Exercise the same contract serialization used between gateway and agent.
        decoded = SocialMessage.model_validate_json(message.model_dump_json())
        received.append(decoded)
        await handle_social(service, decoded)

    bus = SimpleNamespace(request_model=AsyncMock(side_effect=request), publish_model=AsyncMock(side_effect=publish))
    service = SimpleNamespace(
        ai_id=definition.ai_id, settings=settings, definition=definition, persona=persona,
        conversation=conversation, bus=bus, _timeouts=settings.timeouts, spawn=spawn,
        prompt_assembler=prompts, chat_agent=chat_agent, send_response=AsyncMock(),
        group_repeat=GroupRepeatService(SimpleNamespace(eval=AsyncMock(return_value=0)), definition.ai_id, 3600),
        sticker_collector=SimpleNamespace(collect=AsyncMock()),
        memory=SimpleNamespace(search=AsyncMock(return_value=[]), person_context=AsyncMock(
            return_value=SimpleNamespace(facts=[], conversation_summary=""))),
        message_input=SocialMessageInputBuilder(
            DescribedMessageInputBuilder(object()), conversation, object(), object(), direct_vision=False,
        ),
    )
    service.group_participation = GroupParticipationService(
        ai_id=definition.ai_id, account_id="qq-main", bus=bus, relationship_timeout_sec=1,
        sessions=sessions, conversation=conversation, persona=persona, prompt_assembler=prompts,
        chat_agent=chat_agent, proactive=definition.behavior_policy.proactive.model_copy(
            update={"enabled": policy != "disabled"},
        ),
        behavior_schedule=SimpleNamespace(allows_proactive=lambda: True), group_whitelist=(),
    )
    participation = service.group_participation
    participation.begin_turn = AsyncMock(wraps=participation.begin_turn)
    participation.should_join = AsyncMock(wraps=participation.should_join)

    sent = []

    def respond(request):
        if request.url.path == "/send_group_msg":
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok", "data": {"message_id": 9001}})
        assert request.url.path == "/get_msg"
        message_id = json.loads(request.content)["message_id"]
        return httpx.Response(200, json={"status": "ok", "data": references.get(message_id)})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        channel = QQChannel({
            "ws_url": "ws://127.0.0.1", "http_url": "http://127.0.0.1", "uin": "10000", "account_id": "qq-main",
            "message_timeout_sec": 10, "forward_timeout_sec": 1,
            "content_strategies": ["quote", "forward", "voice", "image", "file", "at", "text"],
        }, client)

        async def send(command):
            await channel.send(command.send_request())

        service.send_response.side_effect = send
        conversations = SimpleNamespace(get_or_create=AsyncMock(return_value="3"), record_inbound=AsyncMock())
        handler = GatewayMessageHandler(
            channels={"qq-main": channel},
            identities=SimpleNamespace(resolve_or_create=AsyncMock(return_value=("1", "2"))),
            conversations=conversations,
            router=SocialRouter(SimpleNamespace(owner_for_social_account=AsyncMock(return_value=definition.ai_id))),
            group_members=SimpleNamespace(sync=AsyncMock()),
            grounding=SimpleNamespace(ground_message=AsyncMock(return_value=EntityContext(
                current_sender={}, references=(), recent_participants=(),
            ).model_dump(mode="json"))),
            bus=bus, live_settings=SimpleNamespace(), priority_user_ids=frozenset(), private_jobs=object(),
        )
        channel.set_message_handler(handler.handle)

        async def messages():
            # Two real incoming messages make the built-in proactive policy eligible.
            if policy != "not-ready":
                yield json.dumps(event(1, 20000, []))
            yield json.dumps(event(2, 20000, segments))

        async def connections():
            yield messages()

        with patch("gateway.qq_channel.websockets.connect", return_value=connections()):
            await channel.start()
        await asyncio.gather(*tasks)

    message_count = 1 if policy == "not-ready" else 2
    responds = (addressed or policy == "eligible") and policy != "model-declines"
    assert len(received) == message_count
    assert received[-1].to_ai is addressed
    assert conversations.record_inbound.await_count == message_count
    assert sum(entry[0] == "user" for entry in conversation.window("group", "123")) == message_count
    participation.begin_turn.assert_awaited_with("123", force=addressed)
    if addressed or policy != "cooling":
        participation.should_join.assert_awaited_with("123", explicitly_addressed=addressed, images=())
    else:
        participation.should_join.assert_not_awaited()
    assert service.send_response.await_count == int(responds)
    assert chat_agent.generate_plan.await_count == int(responds)
    assert chat_agent.decide_participation.await_count == int(addressed or policy in {"eligible", "model-declines"})
    if chat_agent.decide_participation.await_count:
        prompt = json.loads(chat_agent.decide_participation.await_args.args[1])
        assert prompt["retrieved_context"]["参与判断"]["提及状态"] == (
            "当前真实消息明确 @ 了你或回复了你的消息" if addressed else "当前群聊消息"
        )
    assert len(sent) == int(responds)
    if responds:
        quoted_ids = [part["data"]["id"] for part in sent[0]["message"] if part["type"] == "reply"]
        assert quoted_ids == ([2] if addressed and any(part["type"] == "reply" for part in segments) else [])
