from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from private_reply_fixtures import build_flow, private_event

from gateway.napcat_message_event import NapCatMessageEvent
from shared import private_reply_observability as metrics


class Recorder:
    def __init__(self):
        self.values = []

    def add(self, value, attributes=None):
        self.values.append((value, attributes or {}))

    def record(self, value, attributes=None):
        self.values.append((value, attributes or {}))


def test_metric_labels_exclude_exception_text_and_message_content(monkeypatch):
    result = Recorder()
    fallback = Recorder()
    monkeypatch.setattr(metrics, "_result", result)
    monkeypatch.setattr(metrics, "_fallback", fallback)

    metrics.fallback("模型失败：用户正文=银行卡密码123456")
    metrics.result("failed", "远端错误：Authorization=secret-token")

    rendered = repr(result.values + fallback.values)
    assert "银行卡密码" not in rendered
    assert "secret-token" not in rendered
    assert len(result.values[0][1]["reason"]) <= 64


def test_pending_and_failure_alerts_have_only_aggregate_fields(caplog, monkeypatch):
    pending_count = Recorder()
    pending_age = Recorder()
    result = Recorder()
    monkeypatch.setattr(metrics, "_pending_count", pending_count)
    monkeypatch.setattr(metrics, "_pending_age", pending_age)
    monkeypatch.setattr(metrics, "_result", result)
    monkeypatch.setattr(metrics, "_failure_streak", 0)
    now = datetime.now(timezone.utc)

    with caplog.at_level(logging.ERROR, logger="ailove.private-reply.metrics"):
        metrics.pending([SimpleNamespace(created_at=now - timedelta(seconds=61))], now=now)
        for _ in range(3):
            metrics.result("failed", "ModelUnavailable")

    assert pending_count.values == [(1, {})]
    assert pending_age.values == [(61.0, {})]
    assert "private_reply_pending_alert count=1 oldest_seconds=61.0" in caplog.text
    assert "private_reply_failure_streak count=3" in caplog.text


@pytest.mark.asyncio
async def test_private_failure_logs_do_not_include_inbound_or_exception_body(private_database, caplog):
    flow = await build_flow(private_database)
    flow.runtime.chat_agent.generate_plan.side_effect = RuntimeError(
        "Authorization=secret-token; 用户正文=不可记录"
    )
    event = private_event(segments=[{"type": "text", "data": {"text": "身份证号不可记录"}}])

    with caplog.at_level(logging.WARNING):
        await flow.channel._handle_message(flow.channel._to_message(NapCatMessageEvent.model_validate(event)))

    assert "secret-token" not in caplog.text
    assert "身份证号不可记录" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert len(flow.calls) == 1
    await flow.client.aclose()
