from __future__ import annotations

import asyncio
import json
import os
import time

import pytest
from private_reply_fixtures import build_flow, private_event
from sqlalchemy import func, select

from gateway.napcat_message_event import NapCatMessageEvent
from shared import database_models as m


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("AILOVE_RUN_PRIVATE_REPLY_LOAD") != "1",
    reason="十分钟持续负载仅在显式验收时运行",
)
async def test_ten_conversations_at_one_message_per_second_for_ten_minutes(private_database):
    flow = await build_flow(private_database)
    latencies = []
    started = time.perf_counter()
    for index in range(600):
        target = started + index
        delay = target - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        event = private_event(message_id=100_000 + index, user_id=20_000 + index % 10)
        received = time.perf_counter()
        message = flow.channel._to_message(NapCatMessageEvent.model_validate(event))
        await flow.channel._handle_message(message)
        latencies.append(time.perf_counter() - received)

    remaining = started + 600 - time.perf_counter()
    if remaining > 0:
        await asyncio.sleep(remaining)

    async with private_database.session() as session:
        jobs = await session.scalar(select(func.count()).select_from(m.PrivateReplyJob))
        sent_jobs = await session.scalar(
            select(func.count()).select_from(m.PrivateReplyJob).where(m.PrivateReplyJob.status == "sent")
        )
        deliveries = await session.scalar(select(func.count()).select_from(m.SocialDelivery))
        unique_runs = await session.scalar(select(func.count(func.distinct(m.SocialDelivery.run_id))))

    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]
    report = {
        "duration_seconds": round(time.perf_counter() - started, 3),
        "messages": jobs,
        "sent": sent_jobs,
        "platform_requests": len(flow.calls),
        "unique_runs": unique_runs,
        "p95_seconds": round(p95, 3),
        "model_calls": flow.runtime.chat_agent.generate_plan.await_count,
        "model_calls_per_message": flow.runtime.chat_agent.generate_plan.await_count / 600,
    }
    print("PRIVATE_REPLY_LOAD=" + json.dumps(report, ensure_ascii=False, sort_keys=True))

    assert jobs == sent_jobs == deliveries == unique_runs == len(flow.calls) == 600
    assert p95 <= 10
    assert flow.runtime.chat_agent.generate_plan.await_count <= 600
    await flow.client.aclose()
