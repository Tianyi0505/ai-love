from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from agent.conversation.conversation_context import ConversationContext, format_entries
from agent.conversation.social_context_builder import build_social_context
from shared.contracts.entity import EntityContext
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender


def test_formats_each_message_with_local_timestamp() -> None:
    context = ConversationContext(window_size=4, timezone="Asia/Shanghai")
    moment = datetime(2026, 9, 2, 6, 30, tzinfo=timezone.utc)

    context.add_user(
        "group",
        "123",
        "你好",
        speaker_id="person-1",
        speaker_name="甲",
        timestamp=moment,
    )
    context.add_ai("group", "123", "你好呀", timestamp=moment)

    rendered = format_entries(context.window("group", "123"), ai_name="洛雨")
    assert rendered == (
        "[2026-09-02 周三 14:30] [person-1 | 甲]\n你好\n\n"
        "[2026-09-02 周三 14:30] [AI | 洛雨]\n你好呀"
    )


def test_accepts_millisecond_event_timestamp() -> None:
    context = ConversationContext(window_size=1, timezone="Asia/Shanghai")
    timestamp_ms = int(datetime(2026, 9, 2, 6, 30, tzinfo=timezone.utc).timestamp() * 1000)

    assert context.format_timestamp(timestamp_ms) == "2026-09-02 周三 14:30"


async def test_current_social_message_also_carries_timestamp() -> None:
    moment = datetime(2026, 9, 2, 6, 30, tzinfo=timezone.utc)
    message = SocialMessage(
        chat=Chat(chat_id="100", chat_type=ChatType.PRIVATE),
        sender=SocialSender(user_id="200", name="甲"),
        type=ContentType.TEXT,
        text="现在几点",
        timestamp=int(moment.timestamp()),
    )
    conversation = ConversationContext(window_size=4, timezone="Asia/Shanghai")
    service = SimpleNamespace(
        ai_id="ai-luoyu",
        settings=SimpleNamespace(social=SimpleNamespace(prompt_history_messages=3)),
        conversation=conversation,
        persona=SimpleNamespace(name="洛雨"),
        prompt_assembler=SimpleNamespace(render=Mock(return_value="发送者身份")),
        memory=SimpleNamespace(
            search=AsyncMock(return_value=()),
            context=AsyncMock(
                return_value=SimpleNamespace(
                    self_markdown="",
                    person_markdown="",
                    conversation_summary="",
                )
            ),
        ),
        bus=SimpleNamespace(request_model=AsyncMock(return_value=SimpleNamespace(summary=""))),
        _timeouts=SimpleNamespace(relationship_summary_sec=1.0),
    )
    execution = SimpleNamespace(
        chat_type="private",
        sender_person_id="person-1",
        conversation_id="conversation-1",
        tool_context=lambda: None,
    )

    context = await build_social_context(
        service,
        message,
        message.text,
        execution,
        sender_name="甲",
        entity_context=EntityContext(current_sender={}, references=(), recent_participants=()),
    )

    assert context.user_input == "[2026-09-02 周三 14:30]\n现在几点"
