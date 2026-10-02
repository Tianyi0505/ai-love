import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml
from agentscope.message import AssistantMsg
from output_fixtures import ResultModel, ValidatingOutputClient

from agent.conversation.conversation_context import ConversationContext
from agent.conversation.multimodal_input import MessageInput
from agent.conversation.response_plan import Action, Emotion, ResponsePlan, Speech
from agent.social.social_message_handler import handle_social
from agent.social.sticker_judge import StickerDecision, StickerJudge
from memory.sticker_service import StickerService
from shared.contracts.entity import EntityContext
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.global_settings import StickerSettings


def sticker_service():
    config_path = Path(__file__).resolve().parents[1] / "deploy/config/ailove.config.yaml"
    settings = StickerSettings.model_validate(yaml.safe_load(config_path.read_text(encoding="utf-8"))["sticker"])
    stickers = [
        {
            "id": "1",
            "image_url": "https://example.com/celebrate.gif",
            "description": "开心庆祝鼓掌",
            "tags": ["开心", "庆祝", "鼓掌"],
            "match_quality": 0.9,
            "usage_strength": settings.initial_usage_strength,
            "boost_count": settings.initial_boost_count,
            "created_at": datetime.now(timezone.utc),
            "last_used_at": None,
        }
    ]
    return StickerService(SimpleNamespace(all=AsyncMock(return_value=stickers)), settings)


@pytest.mark.parametrize("chat_type", [ChatType.PRIVATE, ChatType.GROUP])
@pytest.mark.parametrize(
    ("query", "reply", "image_type", "suitable", "matched"),
    [
        ("开心 庆祝 鼓掌", "太棒啦", "sticker", True, True),
        ("安慰 抱抱 陪伴", "我陪着你", "sticker", True, False),
        ("开心 庆祝 鼓掌", "太棒啦", "screenshot", True, False),
        ("开心 庆祝 鼓掌", "太棒啦", "sticker", False, False),
    ],
)
async def test_social_reply_uses_matching_sticker_and_preserves_text(chat_type, query, reply, image_type, suitable, matched):
    """验证社交回复通过真实检索选择匹配表情并记录发送内容"""
    tasks = []

    def spawn(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    stickers = sticker_service()
    judge_call = AsyncMock(return_value={
        "parsed": StickerDecision(image_type=image_type, suitable=suitable, reason="根据图片和当前场景判断"),
        "raw": AssistantMsg("model", content=""), "parsing_error": None,
    })
    model = ResultModel(judge_call)
    judge = StickerJudge(
        model, "vision", SimpleNamespace(data_urls=AsyncMock(return_value=("data:image/png;base64,YQ==",))),
        "根据图片和当前场景判断", 100, 0,
        SimpleNamespace(include_model_content=False, include_binary_content=False, include_model_request_parameters=False),
        ValidatingOutputClient(),
    )
    plan = ResponsePlan(
        speech=[Speech(text=reply, delivery="text")],
        emotion=Emotion(name="neutral", intensity=0.5),
        actions=[Action(type="sticker", query=query)],
    )
    service = SimpleNamespace(
        ai_id="ai-luoyu",
        settings=SimpleNamespace(social=SimpleNamespace(log_preview_chars=30), qq=SimpleNamespace(voice_reply=False)),
        message_input=SimpleNamespace(build=AsyncMock(return_value=MessageInput("联系人的消息"))),
        persona=SimpleNamespace(name_for=lambda _: "", should_respond_directly=lambda *_: True),
        sessions=SimpleNamespace(mark_replied=AsyncMock()),
        proactive_private=SimpleNamespace(session_key=lambda user_id: f"proactive-private:{user_id}"),
        group_repeat=SimpleNamespace(claim_candidate=AsyncMock(return_value=False)),
        group_participation=SimpleNamespace(
            observe=Mock(), mark_replied=AsyncMock(), begin_turn=AsyncMock(return_value=True),
            activate=Mock(), mark_spoke=AsyncMock(), finish_turn=Mock(),
        ),
        definition=SimpleNamespace(relationship_policy=SimpleNamespace(bounds=SimpleNamespace(neutral_quality=0.5))),
        conversation=ConversationContext(window_size=10),
        bus=SimpleNamespace(request_model=AsyncMock()),
        _timeouts=SimpleNamespace(relationship_update_sec=1, sticker_boost_sec=1),
        spawn=spawn,
        chat_agent=SimpleNamespace(generate_plan=AsyncMock(return_value=plan)),
        prompt_assembler=SimpleNamespace(build_system_prompt=Mock(return_value="system"),
                                         build_user_prompt=Mock(return_value="user")),
        stickers=SimpleNamespace(search=lambda query: stickers.search("ai-luoyu", query)),
        sticker_judge=judge,
        send_response=AsyncMock(),
    )
    message = SocialMessage(
        chat=Chat(chat_id="20000", chat_type=chat_type),
        sender=SocialSender(user_id="20000", name="联系人"),
        type=ContentType.TEXT, text="联系人的消息", account_id="qq-main", platform="qq",
        meta={
            "person_id": "person-1", "conversation_id": "conversation-1",
            "entity_context": EntityContext(current_sender={}, references=(), recent_participants=()).model_dump(),
        },
    )
    with patch("agent.social.social_message_handler.build_social_context", new=AsyncMock(return_value=object())):
        await handle_social(service, message)
    await asyncio.gather(*tasks)

    service.send_response.assert_awaited_once()
    command = service.send_response.await_args.args[0]
    assert command.text == reply
    assert (command.sticker is not None) == matched
    if query == "开心 庆祝 鼓掌":
        judge_call.assert_awaited_once()
    else:
        judge_call.assert_not_awaited()
    remembered = service.conversation.window(chat_type.value, "20000")[-1][1]
    assert reply in remembered
    if matched:
        assert command.sticker["description"] == "开心庆祝鼓掌"
        assert "[表情包] 开心庆祝鼓掌" in remembered
    else:
        assert remembered == reply
