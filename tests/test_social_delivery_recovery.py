import pytest
from private_reply_fixtures import build_flow, private_event
from sqlalchemy import select, update

from gateway.napcat_message_event import NapCatMessageEvent
from shared import database_models as m
from shared.contracts.rpc.social import (
    DeliveryConflict,
    DeliveryRejected,
    ReplyUnavailable,
    SocialSendRequest,
    SocialSendResponse,
    SocialSendStatusRequest,
)
from shared.private_interaction_repository import utcnow


@pytest.mark.asyncio
async def test_repeat_request_does_not_send_again(private_database):
    flow = await build_flow(private_database)
    message = flow.channel._to_message(NapCatMessageEvent.model_validate(private_event()))
    await flow.channel._handle_message(message)
    async with private_database.session() as session:
        job = (await session.scalars(select(m.PrivateReplyJob))).one()
    request = SocialSendRequest.model_validate(job.response_snapshot)
    await flow.sender.send(request)
    assert len(flow.calls) == 1
    with pytest.raises(DeliveryConflict):
        await flow.sender.send(request.model_copy(update={'text':'更改文本'}))
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_history_failure_does_not_resend(private_database):
    from unittest.mock import AsyncMock
    flow = await build_flow(private_database)
    flow.sender._conversations.record_outbound = AsyncMock(side_effect=RuntimeError('history failed'))
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event())))
    async with private_database.session() as session:
        job = (await session.scalars(select(m.PrivateReplyJob))).one()
    await flow.sender.send(SocialSendRequest.model_validate(job.response_snapshot))
    assert len(flow.calls) == 1
    assert job.status == 'sent'
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_unknown_send_does_not_retry(private_database):
    import httpx
    flow = await build_flow(private_database)
    attempts=[]
    def timeout(request):
        attempts.append(request)
        raise httpx.ReadTimeout('lost acknowledgement')
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        flow.channel._http_client = client
        await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event())))
        await flow.replies.scan()
    assert len(attempts) == 1
    async with private_database.session() as session:
        assert (await session.scalars(select(m.PrivateReplyJob))).one().status == 'unknown'
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_unavailable_current_quote_is_removed_once(private_database):
    flow = await build_flow(private_database)
    flow.bus.drop_wakeup = True
    await flow.channel._handle_message(
        flow.channel._to_message(NapCatMessageEvent.model_validate(private_event()))
    )
    async with private_database.session() as session:
        job = (await session.scalars(select(m.PrivateReplyJob))).one()
    job = await flow.jobs.claim(job.job_id, job.ai_id)
    request = SocialSendRequest(
        ai_id=job.ai_id,
        account_id=job.account_id,
        conversation_id=str(job.conversation_id),
        channel="qq",
        chat={"chat_id": "20000", "chat_type": "private"},
        type="text",
        text="回复内容",
        run_id=job.run_id,
        reply_to_message_id="101",
        delivery_kind="private_reply",
        source_job_id=str(job.job_id),
        claim_version=job.claim_version,
        person_id=str(job.person_id),
    )
    await flow.jobs.prepare(job.job_id, job.claim_version, request.model_dump(mode="json"))

    class QuoteRejectingChannel:
        def __init__(self):
            self.requests = []

        async def send(self, wire_request):
            self.requests.append(wire_request)
            if len(self.requests) == 1:
                raise ReplyUnavailable("引用消息不存在")
            return SocialSendResponse(message_id="quoted-fallback")

    channel = QuoteRejectingChannel()
    flow.sender._channels["qq-main"] = channel
    response = await flow.sender.send(request)
    repeated = await flow.sender.send(request)

    assert response.message_id == repeated.message_id == "quoted-fallback"
    assert [item.reply_to_message_id for item in channel.requests] == ["101", ""]
    async with private_database.session() as session:
        delivery = (await session.scalars(select(m.SocialDelivery))).one()
        assert delivery.status == "sent"
        assert delivery.revision == 1
        assert delivery.original_digest != delivery.request_digest
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_cleanup_keeps_dedup_and_proactive_count(private_database):
    from datetime import timedelta

    flow = await build_flow(private_database)
    event = private_event()
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(event)))
    async with private_database.session() as session, session.begin():
        job = (await session.scalars(select(m.PrivateReplyJob))).one()
        state = (await session.scalars(select(m.PrivateContactState))).one()
        state.unanswered_count = 2
        job.retain_until = utcnow() - timedelta(days=1)
        await session.execute(
            update(m.SocialDelivery).values(
                updated_at=utcnow() - timedelta(days=181), history_recorded=True
            )
        )

    await flow.jobs.cleanup()
    await flow.deliveries.cleanup()
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(event)))

    async with private_database.session() as session:
        job = (await session.scalars(select(m.PrivateReplyJob))).one()
        delivery = (await session.scalars(select(m.SocialDelivery))).one()
        state = (await session.scalars(select(m.PrivateContactState))).one()
        assert job.message_snapshot == {}
        assert job.response_snapshot is None
        assert delivery.request_snapshot == {}
        assert job.status == delivery.status == "sent"
        assert state.unanswered_count == 2
    assert len(flow.calls) == 1
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_delivery_status_rejects_account_not_owned_by_ai(private_database):
    flow = await build_flow(private_database)
    await flow.channel._handle_message(
        flow.channel._to_message(NapCatMessageEvent.model_validate(private_event()))
    )
    async with private_database.session() as session:
        delivery = (await session.scalars(select(m.SocialDelivery))).one()
    flow.owner.owner_for.return_value = "another-ai"

    with pytest.raises(DeliveryRejected):
        await flow.sender.status(
            SocialSendStatusRequest(
                ai_id=delivery.ai_id,
                account_id=delivery.account_id,
                run_id=delivery.run_id,
            )
        )
    assert len(flow.calls) == 1
    await flow.client.aclose()
