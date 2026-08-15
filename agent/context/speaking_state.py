
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


# 维护单个聊天会话状态
class ChatSession:

    # 初始化当前实例
    def __init__(self, chat_key: str) -> None:
        self.chat_key = chat_key
        self.active = False
        self.last_active = 0.0


_metadata = MetaData()
_spoke_table = Table(
    "spoke",
    _metadata,
    Column("chat_key", String, primary_key=True),
    Column("last_spoke", Float),
    Column("replied", Integer, server_default="0"),
)


# 管理聊天会话与发言状态
class SessionManager:

    # 初始化当前实例
    def __init__(self, data_dir: str) -> None:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{Path(data_dir) / 'session.db'}")
        _spoke_table.create(self._engine, checkfirst=True)
        self._sessions: dict[str, ChatSession] = {}

    # 获取会话
    def session(self, chat_key: str) -> ChatSession:
        if chat_key not in self._sessions:
            self._sessions[chat_key] = ChatSession(chat_key)
        return self._sessions[chat_key]

    # 判断是否可以发言
    def can_speak(self, chat_key: str) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(_spoke_table.c.replied).where(_spoke_table.c.chat_key == chat_key)
            ).first()
        if row is None:
            return True
        return bool(row[0])

    # 判断是否可以发起会话
    def can_initiate(self, chat_key: str, cooldown_sec: int) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(_spoke_table.c.last_spoke, _spoke_table.c.replied).where(
                    _spoke_table.c.chat_key == chat_key
                )
            ).first()
        if row is None:
            return True
        last_spoke, replied = row
        return bool(replied) and time.time() - float(last_spoke or 0) >= cooldown_sec

    # 标记已发言状态
    def mark_spoke(self, chat_key: str) -> None:
        now = time.time()
        with self._engine.begin() as conn:
            conn.execute(
                sqlite_insert(_spoke_table)
                .values(chat_key=chat_key, last_spoke=now, replied=0)
                .on_conflict_do_update(
                    index_elements=[_spoke_table.c.chat_key],
                    set_={"last_spoke": now, "replied": 0},
                )
            )
        self.session(chat_key).last_active = now

    # 标记已回复状态
    def mark_replied(self, chat_key: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sqlite_insert(_spoke_table)
                .values(chat_key=chat_key, last_spoke=0, replied=1)
                .on_conflict_do_update(
                    index_elements=[_spoke_table.c.chat_key],
                    set_={"replied": 1},
                )
            )

    # 列出全部会话
    def all_sessions(self) -> list[str]:
        return list(self._sessions.keys())
