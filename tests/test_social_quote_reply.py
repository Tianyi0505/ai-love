from __future__ import annotations

import httpx
import pytest
from private_reply_fixtures import build_flow, private_event

from gateway.napcat_message_event import NapCatMessageEvent
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.contracts.turn import AgentExecutionContext


def quoted_event(message_id=101, quoted_id=88):
    return private_event(
        message_id=message_id,
        segments=[
            {"type": "reply", "data": {"id": str(quoted_id)}},
            {"type": "text", "data": {"text": "接着说"}},
        ],
    )


@pytest.mark.asyncio
async def test_private_reply_quotes_current_message_and_keeps_history(private_database):
    flow = await build_flow(private_database)
    requests = []

    def respond(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("/get_msg"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        **private_event(message_id=88, user_id=20001),
                        "message": [{"type": "text", "data": {"text": "历史消息B"}}],
                    },
                },
            )
        return httpx.Response(200, json={"status": "ok", "data": {"message_id": 9001}})

    await flow.client.aclose()
    flow.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    flow.channel._http_client = flow.client
    message = flow.channel._to_message(NapCatMessageEvent.model_validate(quoted_event()))
    await flow.channel._handle_message(message)

    understood = flow.runtime.message_input.build.await_args.args[0]
    assert understood.quote_ref.message_id == "88"
    assert understood.quote_ref.text == "历史消息B"
    assert understood.meta["reply_message_id"] == "88"
    sent = requests[-1].read()
    assert b'"id":101' in sent
    assert b'"id":88' not in sent
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_missing_historical_quote_still_replies_to_current_message(private_database):
    flow = await build_flow(private_database)
    requests = []

    def respond(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("/get_msg"):
            return httpx.Response(200, json={"status": "ok", "data": None})
        return httpx.Response(200, json={"status": "ok", "data": {"message_id": 9002}})

    await flow.client.aclose()
    flow.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    flow.channel._http_client = flow.client
    await flow.channel._handle_message(
        flow.channel._to_message(NapCatMessageEvent.model_validate(quoted_event(message_id=102)))
    )

    understood = flow.runtime.message_input.build.await_args.args[0]
    assert understood.quote_ref is None
    assert understood.meta["reply_message_id"] == "88"
    assert b'"id":102' in requests[-1].read()
    await flow.client.aclose()


def test_nested_quote_never_becomes_reply_target():
    current = SocialMessage(
        chat=Chat(chat_id="20000", chat_type=ChatType.GROUP),
        sender=SocialSender(user_id="20000"),
        type=ContentType.QUOTE,
        text="A",
        message_id="101",
        account_id="qq-main",
        platform="qq",
        meta={"reply_message_id": "88"},
        quote_ref=SocialMessage(
            chat=Chat(chat_id="20000", chat_type=ChatType.GROUP),
            sender=SocialSender(user_id="20001"),
            type=ContentType.QUOTE,
            text="B",
            message_id="88",
            meta={"reply_message_id": "77"},
            quote_ref=SocialMessage(
                chat=Chat(chat_id="20000", chat_type=ChatType.GROUP),
                sender=SocialSender(user_id="20002"),
                type=ContentType.TEXT,
                text="C",
                message_id="77",
            ),
        ),
    )

    assert AgentExecutionContext.from_social_message(current, "ai-1").reply_to_message_id == "101"


def test_plain_and_proactive_messages_do_not_gain_quote():
    message = SocialMessage(
        chat=Chat(chat_id="20000", chat_type=ChatType.PRIVATE),
        sender=SocialSender(user_id="20000"),
        type=ContentType.TEXT,
        text="普通消息",
        message_id="101",
        account_id="qq-main",
        platform="qq",
    )

    assert AgentExecutionContext.from_social_message(message, "ai-1").reply_to_message_id == ""
