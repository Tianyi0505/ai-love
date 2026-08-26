from __future__ import annotations

import time
from collections import deque


# 维护群聊会话状态
class GroupSession:
    # 初始化当前实例
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self.active_since: float | None = None
        self.last_message_at: float | None = None
        self.inactive_until: float | None = None
        self.recent_messages: deque[float] = deque()

    # 更新过期状态
    def expire(self, now: float, idle_sec: int, max_active_sec: int, rest_sec: int) -> None:
        if self.active_since is None:
            return
        idle = self.last_message_at is not None and now - self.last_message_at >= idle_sec
        overtime = now - self.active_since >= max_active_sec
        if idle or overtime:
            self.active_since = None
            if overtime:
                self.inactive_until = now + rest_sec

    # 返回是否处于活跃状态
    @property
    def active(self) -> bool:
        return self.active_since is not None

    # 激活群聊会话
    def activate(self, now: float) -> None:
        if not self.active:
            self.active_since = now


# 管理群聊会话生命周期
class GroupChatManager:
    # 初始化当前实例
    def __init__(self) -> None:
        self._sessions: dict[str, GroupSession] = {}

    # 获取会话
    def session(self, chat_id: str) -> GroupSession:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = GroupSession(chat_id)
        return self._sessions[chat_id]

    # 记录观察事件
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

    # 判断是否可以加入群聊
    def ready_to_join(self, chat_id: str, min_messages: int) -> bool:
        session = self.session(chat_id)
        rest_complete = session.inactive_until is None or time.time() >= session.inactive_until
        return rest_complete and len(session.recent_messages) >= min_messages

    # 激活群聊会话
    def activate(self, chat_id: str) -> None:
        self.session(chat_id).activate(time.time())
