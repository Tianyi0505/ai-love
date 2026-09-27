from types import SimpleNamespace

import pytest

from gateway.gateway_message_handler import GatewayMessageHandler
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender


class _Channel:
    async def hydrate_message(self, message):
        return message


class _Identities:
    async def resolve_or_create(self, platform, account_id, user_id, name):
        return "1", "2"


class _Conversations:
    def __init__(self) -> None:
        self.recorded = None

    async def get_or_create(self, platform, account_id, chat_id, chat_type):
        return "3"

    async def record_inbound(self, message, ai_id):
        self.recorded = (message, ai_id)


class _Router:
    async def route(self, message):
        return SimpleNamespace(ai_id="ai-1")


class _GroupMembers:
    async def sync(self, message):
        raise AssertionError("私聊不应同步群成员")


class _Grounding:
    def __init__(self) -> None:
        self.calls = []

    async def ground_message(self, message, ai_id):
        self.calls.append((message, ai_id))
        return {
            "current_sender": {
                "person_id": message.meta["person_id"],
                "display_name": message.sender.name,
            },
            "references": [],
            "recent_participants": [],
        }


class _Bus:
    def __init__(self) -> None:
        self.published = None

    async def publish_model(self, subject, message):
        self.published = (subject, message)


@pytest.mark.asyncio
async def test_private_message_is_grounded_before_publishing_to_agent(private_database) -> None:
    conversations = _Conversations()
    grounding = _Grounding()
    bus = _Bus()
    handler = GatewayMessageHandler(
        channels={"qq-main": _Channel()},
        identities=_Identities(),
        conversations=conversations,
        router=_Router(),
        group_members=_GroupMembers(),
        grounding=grounding,
        bus=bus,
        live_settings=SimpleNamespace(),
        priority_user_ids=frozenset({"20000"}),
        private_jobs=__import__("shared.private_interaction_repository", fromlist=["PrivateInteractionRepository"]).PrivateInteractionRepository(private_database),
    )
    message = SocialMessage(
        chat=Chat(chat_id="20000", chat_type=ChatType.PRIVATE),
        sender=SocialSender(user_id="20000", name="发送者"),
        type=ContentType.TEXT,
        text="下午好",
        message_id="999",
        account_id="qq-main",
        platform="qq",
    )

    await handler.handle(message)

    message = bus.published[1]
    assert grounding.calls == [(message, "ai-1")]
    assert message.meta["entity_context"] == {
        "current_sender": {"person_id": "2", "display_name": "发送者"},
        "references": [],
        "recent_participants": [],
    }
    assert bus.published == ("social.chat.ai-1", message)
    assert conversations.recorded == (message, "ai-1")
