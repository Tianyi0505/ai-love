import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from private_reply_fixtures import Clock, build_flow, private_event
from sqlalchemy import select

from agent.social.proactive_private_service import ProactivePrivateService
from gateway.napcat_message_event import NapCatMessageEvent
from shared import database_models as m
from shared.contracts.rpc.relationship import PersonRelationshipRecord, RelationshipListResponse
from shared.private_interaction_repository import utcnow
from shared.relationship_repository import RelationshipRepository


async def proactive_flow(db):
    from unittest.mock import AsyncMock
    flow = await build_flow(db)
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event())))
    async with db.session() as session:
        job = (await session.scalars(select(m.PrivateReplyJob))).one()
    clock = Clock(utcnow()+timedelta(hours=7))
    flow.jobs.clock = clock
    flow.deliveries.clock = clock
    flow.deliveries.interactions.clock = clock
    relation = PersonRelationshipRecord(person_id=str(job.person_id),display_name='联系人',user_id='20000',account_id='qq-main',
        familiarity=1,affinity=.5,trust=.5,importance=1,last_interaction_at=clock()-timedelta(hours=12),priority_contact=True)
    flow.bus.handlers['relationship.list.request'] = AsyncMock(return_value=RelationshipListResponse(relationships=[relation]))
    async def send(command):
        return await flow.sender.send(command.send_request())
    service = ProactivePrivateService(ai_id=flow.runtime.ai_id,default_account_id='qq-main',bus=flow.bus,
        relationship_timeout_sec=1,interactions=flow.jobs,allowed_account_ids=('qq-main',),
        conversation=flow.runtime.conversation,memory=flow.runtime.memory,persona=flow.runtime.persona,
        prompt_assembler=flow.runtime.prompt_assembler,chat_agent=flow.runtime.chat_agent,
        proactive=flow.runtime.definition.behavior_policy.proactive,
        behavior_schedule=SimpleNamespace(allows_proactive=lambda *_:True),send_response=send)
    return flow,service,clock,job

@pytest.mark.asyncio
async def test_three_unanswered_contacts_then_stop(private_database):
    flow,service,clock,job = await proactive_flow(private_database)
    for _ in range(3):
        assert await service.run_once(clock())
        clock.now += timedelta(minutes=31)
    assert not await service.run_once(clock())
    assert (await flow.jobs.state(job.ai_id,job.person_id)).unanswered_count == 3
    assert len(flow.calls) == 4
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_reply_resets_but_duplicate_and_restart_do_not(private_database):
    flow,service,clock,job = await proactive_flow(private_database)
    for _ in range(3):
        assert await service.run_once(clock())
        clock.now += timedelta(minutes=31)
    clock.now += timedelta(days=2)
    assert not await service.run_once(clock())
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event())))
    assert (await flow.jobs.state(job.ai_id,job.person_id)).unanswered_count == 3
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event(102))))
    assert (await flow.jobs.state(job.ai_id,job.person_id)).unanswered_count == 0
    clock.now += timedelta(hours=7)
    assert await service.run_once(clock())
    from shared.private_interaction_repository import PrivateInteractionRepository
    reopened = PrivateInteractionRepository(private_database,clock=clock)
    assert (await reopened.state(job.ai_id,job.person_id)).unanswered_count == 1
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_competing_schedulers_share_last_slot(private_database):
    flow,service,clock,job = await proactive_flow(private_database)
    for _ in range(2):
        assert await service.run_once(clock())
        clock.now += timedelta(minutes=31)
    results = await asyncio.gather(service.run_once(clock()), service.run_once(clock()))
    assert sum(results) == 1
    assert (await flow.jobs.state(job.ai_id,job.person_id)).unanswered_count == 3
    assert len(flow.calls) == 4
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_inbound_during_generation_cancels_old_topic(private_database):
    flow,service,clock,job = await proactive_flow(private_database)
    plan = flow.runtime.chat_agent.generate_plan.return_value
    async def generate(*args,**kwargs):
        # 在真实私信入口并发接收，测试发送前的版本复核。
        flow.bus.drop_wakeup=True
        await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event(102))))
        return plan
    flow.runtime.chat_agent.generate_plan.side_effect = generate
    assert not await service.run_once(clock())
    assert len(flow.calls) == 1
    await flow.client.aclose()

@pytest.mark.asyncio
async def test_send_unknown_blocks_only_proactive(private_database):
    import httpx
    flow,service,clock,job = await proactive_flow(private_database)
    attempts=[]
    def timeout(request):
        attempts.append(request)
        raise httpx.ReadTimeout('lost')
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        flow.channel._http_client=client
        assert not await service.run_once(clock())
    flow.channel._http_client=flow.client
    clock.now += timedelta(days=1)
    assert not await service.run_once(clock())
    await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(private_event(102))))
    state=await flow.jobs.state(job.ai_id,job.person_id)
    assert state.status == 'unknown' and state.unanswered_count == 0
    assert len(flow.calls) == 2
    assert len(attempts) == 1
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_rpc_failure_before_gateway_freezes_reserved_contact(private_database):
    flow, service, clock, job = await proactive_flow(private_database)

    async def unavailable(_command):
        raise TimeoutError("gateway unavailable")

    service._send_response = unavailable
    assert not await service.run_once(clock())

    state = await flow.jobs.state(job.ai_id, job.person_id)
    assert state.status == "unknown"
    assert state.pending_run_id
    assert state.reason_code == "TimeoutError"
    assert len(flow.calls) == 1
    await flow.client.aclose()


@pytest.mark.asyncio
async def test_relationship_route_comes_from_one_bound_identity(private_database):
    async with private_database.session() as session, session.begin():
        session.add_all(
            [
                m.Person(person_id=501, display_name="联系人"),
                m.PlatformIdentity(
                    identity_id=601,
                    person_id=501,
                    platform="qq",
                    account_id="qq-other",
                    platform_user_id="wrong-user",
                    verified_by="test",
                ),
                m.PlatformIdentity(
                    identity_id=602,
                    person_id=501,
                    platform="qq",
                    account_id="qq-main",
                    platform_user_id="right-user",
                    verified_by="test",
                ),
                m.AIAccountBinding(
                    binding_id=701,
                    account_id="qq-main",
                    ai_id="ai-bound",
                ),
                m.PersonRelationship(
                    person_relationship_id=801,
                    ai_id="ai-bound",
                    person_id=501,
                    ceiling_policy="priority",
                ),
            ]
        )

    repository = RelationshipRepository(private_database, SimpleNamespace(initial_score=0))
    rows = await repository.list_people("ai-bound")

    assert len(rows) == 1
    assert rows[0]["person_id"] == "501"
    assert (rows[0]["account_id"], rows[0]["user_id"]) == ("qq-main", "right-user")
