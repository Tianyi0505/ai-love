import asyncio

import pytest
from private_reply_fixtures import build_flow, private_event
from sqlalchemy import select

from gateway.napcat_message_event import NapCatMessageEvent
from shared import database_models as m


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [None, 'empty', 'model', 'input'])
async def test_private_reply_entry(private_database, failure):
    flow = await build_flow(private_database)
    if failure == 'empty':
        flow.runtime.chat_agent.generate_plan.return_value.speech = []
    elif failure == 'model':
        flow.runtime.chat_agent.generate_plan.side_effect = RuntimeError('model down')
    elif failure == 'input':
        flow.runtime.message_input.build.side_effect = RuntimeError('media down')
    try:
        for _ in range(2):
            message = flow.channel._to_message(NapCatMessageEvent.model_validate(private_event()))
            await flow.channel._handle_message(message)
        assert len(flow.calls) == 1
        async with private_database.session() as session:
            job = (await session.scalars(select(m.PrivateReplyJob))).one()
            assert job.status == 'sent'
            assert job.response_snapshot['text'].strip()
        assert flow.runtime.chat_agent.generate_plan.await_count <= 1
    finally:
        await asyncio.gather(*flow.background, return_exceptions=True)
        await flow.client.aclose()

@pytest.mark.asyncio
async def test_lost_wakeup_recovers(private_database):
    flow = await build_flow(private_database)
    flow.bus.drop_wakeup = True
    message = flow.channel._to_message(NapCatMessageEvent.model_validate(private_event()))
    await flow.channel._handle_message(message)
    assert not flow.calls
    await flow.replies.scan()
    assert len(flow.calls) == 1
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_concurrent_private_messages_are_ordered(private_database):
    flow = await build_flow(private_database)
    flow.bus.drop_wakeup = True
    for message_id in (101,102,103):
        await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event(message_id))))
    for _ in range(3):
        await asyncio.gather(flow.replies.scan(),flow.replies.scan())
    assert len(flow.calls) == 3
    async with private_database.session() as session:
        assert [j.status for j in (await session.scalars(select(m.PrivateReplyJob).order_by(m.PrivateReplyJob.received_seq))).all()] == ['sent']*3
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_self_private_event_is_not_reprocessed(private_database):
    flow = await build_flow(private_database)
    await flow.channel._handle_message(
        flow.channel._to_message(NapCatMessageEvent.model_validate(private_event(user_id=10000)))
    )
    assert flow.calls == []
    assert flow.runtime.chat_agent.generate_plan.await_count == 0
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_non_priority_private_sender_still_gets_reply(private_database):
    flow = await build_flow(private_database)
    await flow.channel._handle_message(
        flow.channel._to_message(NapCatMessageEvent.model_validate(private_event(user_id=99999)))
    )

    assert len(flow.calls) == 1
    assert flow.runtime.chat_agent.generate_plan.await_count == 1
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_duplicate_after_account_rebind_keeps_original_job(private_database):
    flow = await build_flow(private_database)
    event = private_event()
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(event)))
    flow.owner.route.return_value.ai_id = "ai-after-rebind"
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(event)))

    async with private_database.session() as session:
        jobs = (await session.scalars(select(m.PrivateReplyJob))).all()
    assert len(jobs) == 1
    assert jobs[0].ai_id == flow.runtime.ai_id
    assert len(flow.calls) == 1
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_expired_processing_does_not_replay_generation(private_database):
    from datetime import timedelta

    from sqlalchemy import update

    from shared.private_interaction_repository import utcnow
    flow = await build_flow(private_database)
    flow.bus.drop_wakeup = True
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event())))
    job = (await flow.jobs.pending(('ready',)))[0]
    old_claim = await flow.jobs.claim(job.job_id,flow.runtime.ai_id)
    async with private_database.session() as session, session.begin():
        await session.execute(update(m.PrivateReplyJob).values(lease_until=utcnow()-timedelta(seconds=1)))
    await flow.replies.scan()
    assert len(flow.calls) == 1
    assert flow.runtime.chat_agent.generate_plan.await_count == 0
    assert not await flow.jobs.heartbeat(old_claim.job_id,old_claim.claim_version,120)
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_model_deadline_uses_fallback(private_database):
    from shared.service_settings import PrivateReplySettings
    flow = await build_flow(private_database)
    flow.replies.settings = PrivateReplySettings(processing_budget_sec=.02)
    async def slow(*args,**kwargs):
        await asyncio.sleep(1)
    flow.runtime.chat_agent.generate_plan.side_effect = slow
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event())))
    assert len(flow.calls) == 1
    await flow.client.aclose()

@pytest.mark.asyncio
@pytest.mark.parametrize('segments', [
    [{'type':'image','data':{'url':'http://local.invalid/image','summary':'图片'}}],
    [{'type':'record','data':{'url':'http://local.invalid/audio'}}],
    [{'type':'file','data':{'name':'test.txt','url':'http://local.invalid/file'}}],
    [{'type':'reply','data':{'id':'7'}},{'type':'text','data':{'text':'引用内容'}}],
    [{'type':'forward','data':{'id':'7'}}],
])
async def test_supported_media_entry_replies(private_database,segments):
    flow = await build_flow(private_database)
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event(segments=segments))))
    async with private_database.session() as session:
        job = (await session.scalars(select(m.PrivateReplyJob))).one()
        assert job.status == 'sent'
        assert job.response_snapshot['text'].strip()
    await flow.client.aclose()
