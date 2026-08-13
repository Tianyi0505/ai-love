
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from collections import deque

from shared.contracts.behavior import BehaviorSchedule

logger = logging.getLogger("ailove.ai-agent.proactive")


class GroupSession:

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self.active_since = 0.0
        self.last_message_at = 0.0
        self.inactive_until = 0.0
        self.recent_messages: deque[float] = deque()

    def expire(self, now: float, idle_sec: int, max_active_sec: int, rest_sec: int) -> None:
        if not self.active_since:
            return
        idle = self.last_message_at and now - self.last_message_at >= idle_sec
        overtime = now - self.active_since >= max_active_sec
        if idle or overtime:
            self.active_since = 0.0
            if overtime:
                self.inactive_until = now + rest_sec

    @property
    def active(self) -> bool:
        return self.active_since > 0

    def activate(self, now: float) -> None:
        if not self.active:
            self.active_since = now


class GroupChatManager:

    def __init__(self) -> None:
        self._sessions: dict[str, GroupSession] = {}

    def session(self, chat_id: str) -> GroupSession:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = GroupSession(chat_id)
        return self._sessions[chat_id]

    def observe(
        self,
        chat_id: str,
        *,
        join_window_sec: int,
        idle_sec: int,
        max_active_sec: int,
        rest_sec: int,
    ) -> GroupSession:
        now = time.time()
        session = self.session(chat_id)
        session.expire(now, idle_sec, max_active_sec, rest_sec)
        session.recent_messages.append(now)
        cutoff = now - join_window_sec
        while session.recent_messages and session.recent_messages[0] < cutoff:
            session.recent_messages.popleft()
        session.last_message_at = now
        return session

    def ready_to_join(self, chat_id: str, min_messages: int) -> bool:
        session = self.session(chat_id)
        return time.time() >= session.inactive_until and len(session.recent_messages) >= min_messages

    def activate(self, chat_id: str) -> None:
        self.session(chat_id).activate(time.time())


class ProactiveChat:

    def __init__(self, behavior_config: dict) -> None:
        self._config = behavior_config
        self._schedule = BehaviorSchedule.from_config(behavior_config)

    def in_work_hours(self) -> bool:
        return self._schedule.allows_proactive()

    async def run_private(self, personas: list[dict], min_w: float) -> list[dict]:
        if not self.in_work_hours():
            return []
        quiet_period = int(self._config.get("proactive", {}).get("private_quiet_period_sec", 21600))
        now = dt.datetime.now(dt.timezone.utc)
        chosen: list[dict] = []
        for p in personas:
            familiarity = float(p.get("familiarity", 0.0))
            importance = float(p.get("importance", 0.0))
            if familiarity + importance < min_w:
                continue
            if not p.get("user_id") or p.get("waiting_reply", False):
                continue
            last_interaction = p.get("last_interaction_at")
            if last_interaction:
                if isinstance(last_interaction, str):
                    last_interaction = dt.datetime.fromisoformat(last_interaction.replace("Z", "+00:00"))
                if last_interaction.tzinfo is None:
                    last_interaction = last_interaction.replace(tzinfo=dt.timezone.utc)
                if (now - last_interaction.astimezone(dt.timezone.utc)).total_seconds() < quiet_period:
                    continue
            candidate = dict(p)
            candidate["reason"] = p.get("pending_commitment") or "有一段时间没有联系，想自然地问候近况"
            chosen.append(candidate)
        chosen.sort(
            key=lambda item: (
                bool(item.get("priority_contact", False)),
                float(item.get("familiarity", 0.0)) + float(item.get("importance", 0.0)),
            ),
            reverse=True,
        )
        return chosen[:1]

    async def loop(self, agent, private_interval: int, min_w: float) -> None:
        while True:
            try:
                personas = await agent.list_personas()
                for p in await self.run_private(personas, min_w):
                    await agent.send_private(p)
            except Exception as e:
                logger.warning("主动私聊失败: %s", e)
            await asyncio.sleep(private_interval)
