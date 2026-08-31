from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from agent.conversation.multimodal_input import MessageInput
from agent.social.group_repeat_service import GroupRepeatService
from agent.social.social_message_handler import handle_social
from gateway.qq_channel import QQChannel
from shared.contracts.rpc.social import SocialSendRequest
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int, nx: bool):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


class _HTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _NapCatHTTP:
    def __init__(self, source_message: dict) -> None:
        self.source_message = source_message
        self.requests: list[tuple[str, dict, float]] = []

    async def post(self, url: str, json: dict, timeout: float) -> _HTTPResponse:
        self.requests.append((url, json, timeout))
        if url.endswith("/get_msg"):
            return _HTTPResponse({"status": "ok", "data": self.source_message})
        return _HTTPResponse({"status": "ok", "data": {"message_id": 1000}})


def _message(*, chat_id: str = "123", message_id: str = "999") -> SocialMessage:
    return SocialMessage(
        chat=Chat(chat_id=chat_id, chat_type=ChatType.GROUP, chat_name="测试群"),
        sender=SocialSender(user_id="20000", name="发送者"),
        type=ContentType.TEXT,
        text="今天吃什么",
        message_id=message_id,
        timestamp=1,
        account_id="qq-main",
        platform="qq",
        meta={
            "person_id": "person-1",
            "conversation_id": "conversation-1",
        },
    )


class GroupRepeatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeats_second_identical_content_only_once_per_group(self) -> None:
        service = GroupRepeatService(_Redis(), "ai-luoyu", 3600)

        self.assertFalse(await service.should_repeat(_message(message_id="1")))
        self.assertTrue(await service.should_repeat(_message(message_id="2")))
        self.assertFalse(await service.should_repeat(_message(message_id="3")))

    async def test_same_content_in_another_group_has_independent_state(self) -> None:
        service = GroupRepeatService(_Redis(), "ai-luoyu", 3600)

        self.assertFalse(await service.should_repeat(_message(chat_id="group-a", message_id="1")))
        self.assertFalse(await service.should_repeat(_message(chat_id="group-b", message_id="2")))
        self.assertTrue(await service.should_repeat(_message(chat_id="group-a", message_id="3")))
        self.assertTrue(await service.should_repeat(_message(chat_id="group-b", message_id="4")))

    async def test_message_without_platform_id_is_not_eligible(self) -> None:
        service = GroupRepeatService(_Redis(), "ai-luoyu", 3600)

        self.assertFalse(await service.should_repeat(_message(message_id="")))


class GroupRepeatHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_group_message_repeats_before_model_policy(self) -> None:
        message = _message(message_id="2")
        repeat = GroupRepeatService(_Redis(), "ai-luoyu", 3600)
        self.assertFalse(await repeat.should_repeat(_message(message_id="1")))
        tasks: list[asyncio.Task] = []

        def spawn(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task

        group_participation = SimpleNamespace(
            observe=Mock(),
            mark_replied=AsyncMock(),
            activate=Mock(),
            mark_spoke=AsyncMock(),
            begin_turn=AsyncMock(side_effect=AssertionError("+1 不应进入模型回合")),
        )
        chat_agent = SimpleNamespace(
            generate_plan=AsyncMock(side_effect=AssertionError("+1 不应请求模型")),
        )
        send_response = AsyncMock()
        conversation = SimpleNamespace(add_user=Mock(), add_ai=Mock())
        service = SimpleNamespace(
            ai_id="ai-luoyu",
            settings=SimpleNamespace(social=SimpleNamespace(log_preview_chars=30)),
            message_input=SimpleNamespace(build=AsyncMock(return_value=MessageInput("今天吃什么"))),
            sticker_collector=object(),
            persona=SimpleNamespace(name_for=lambda _user_id: ""),
            conversation=conversation,
            group_participation=group_participation,
            group_repeat=repeat,
            definition=SimpleNamespace(
                relationship_policy=SimpleNamespace(bounds=SimpleNamespace(neutral_quality=0.5)),
            ),
            bus=SimpleNamespace(request_model=AsyncMock()),
            _timeouts=SimpleNamespace(relationship_update_sec=1.0),
            spawn=spawn,
            send_response=send_response,
            chat_agent=chat_agent,
        )

        await handle_social(service, message)
        await asyncio.gather(*tasks)

        command = send_response.await_args.args[0]
        self.assertEqual("2", command.repeat_message_id)
        self.assertEqual("repeat", command.send_request().type)
        group_participation.begin_turn.assert_not_awaited()
        chat_agent.generate_plan.assert_not_awaited()
        conversation.add_ai.assert_called_once_with("group", "123", "今天吃什么")


class QQGroupRepeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_fetches_and_resends_original_message_segments(self) -> None:
        source = {
            "message": [
                {"type": "at", "data": {"qq": "30000"}},
                {"type": "text", "data": {"text": " 今天吃什么"}},
            ],
        }
        http = _NapCatHTTP(source)
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
        request = SocialSendRequest(
            ai_id="ai-luoyu",
            account_id="qq-main",
            conversation_id="conversation-1",
            channel="qq",
            chat=Chat(chat_id="123", chat_type=ChatType.GROUP),
            type="repeat",
            text="今天吃什么",
            run_id="run-1",
            repeat_message_id="999",
        )

        response = await channel.send(request)

        self.assertEqual("1000", response.message_id)
        self.assertEqual(("http://127.0.0.1/get_msg", {"message_id": 999}, 1.0), http.requests[0])
        self.assertEqual(
            (
                "http://127.0.0.1/send_group_msg",
                {"message": source["message"], "group_id": 123},
                1.0,
            ),
            http.requests[1],
        )


if __name__ == "__main__":
    unittest.main()
