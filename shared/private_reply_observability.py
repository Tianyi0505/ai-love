from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from opentelemetry import metrics

logger = logging.getLogger("ailove.private-reply.metrics")
meter = metrics.get_meter("ai-love.private-reply")

_received = meter.create_counter("ailove.private_reply.received")
_result = meter.create_counter("ailove.private_reply.result")
_fallback = meter.create_counter("ailove.private_reply.fallback")
_model_calls = meter.create_counter("ailove.private_reply.model_calls")
_pending_count = meter.create_histogram("ailove.private_reply.pending_count")
_pending_age = meter.create_histogram("ailove.private_reply.oldest_pending_seconds")
_scan_failures = meter.create_counter("ailove.private_reply.scan_failures")
_delivery = meter.create_counter("ailove.social_delivery.result")
_proactive = meter.create_counter("ailove.proactive_private.result")
_failure_streak = 0


def _label(value: object) -> str:
    """限制指标标签为低基数原因码，绝不写入异常正文。"""
    text = str(value or "none")
    return text if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", text) else "other"


def received(*, duplicate: bool) -> None:
    _received.add(1, {"duplicate": str(duplicate).lower()})


def model_call() -> None:
    _model_calls.add(1)


def fallback(reason: object) -> None:
    _fallback.add(1, {"reason": _label(reason)})


def result(status: str, reason: object = "") -> None:
    global _failure_streak
    attributes = {"status": _label(status), "reason": _label(reason)}
    _result.add(1, attributes)
    if status == "sent":
        _failure_streak = 0
    elif status in {"failed", "unknown"}:
        _failure_streak += 1
        if status == "unknown":
            logger.error("private_reply_unknown reason=%s", attributes["reason"])
        if _failure_streak >= 3:
            logger.error("private_reply_failure_streak count=%d", _failure_streak)


def pending(jobs, *, now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc)
    count = len(jobs)
    oldest = max(
        ((current - job.created_at).total_seconds() for job in jobs if job.created_at is not None),
        default=0.0,
    )
    _pending_count.record(count)
    _pending_age.record(max(oldest, 0.0))
    if oldest > 60:
        logger.error("private_reply_pending_alert count=%d oldest_seconds=%.1f", count, oldest)


def scan_failure(component: str, reason: object) -> None:
    _scan_failures.add(1, {"component": _label(component), "reason": _label(reason)})
    logger.error("private_reply_scan_failed component=%s reason=%s", _label(component), _label(reason))


def delivery(status: str, reason: object = "") -> None:
    _delivery.add(1, {"status": _label(status), "reason": _label(reason)})


def proactive(status: str, reason: object = "") -> None:
    _proactive.add(1, {"status": _label(status), "reason": _label(reason)})
