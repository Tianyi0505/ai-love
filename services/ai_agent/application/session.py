
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class ChatSession:

    def __init__(self, chat_key: str) -> None:
        self.chat_key = chat_key
        self.active = False
        self.last_active = 0.0


class SessionManager:

    def __init__(self, data_dir: str = "/app/data") -> None:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(Path(data_dir) / "session.db")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS spoke (
                chat_key TEXT PRIMARY KEY,
                last_spoke REAL,
                replied INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()
        self._sessions: dict[str, ChatSession] = {}

    def session(self, chat_key: str) -> ChatSession:
        if chat_key not in self._sessions:
            self._sessions[chat_key] = ChatSession(chat_key)
        return self._sessions[chat_key]

    def can_speak(self, chat_key: str) -> bool:
        row = self._conn.execute(
            "SELECT replied FROM spoke WHERE chat_key=?", (chat_key,)
        ).fetchone()
        if row is None:
            return True
        return bool(row[0])

    def can_initiate(self, chat_key: str, cooldown_sec: int) -> bool:
        row = self._conn.execute(
            "SELECT last_spoke, replied FROM spoke WHERE chat_key=?", (chat_key,)
        ).fetchone()
        if row is None:
            return True
        last_spoke, replied = row
        return bool(replied) and time.time() - float(last_spoke or 0) >= cooldown_sec

    def mark_spoke(self, chat_key: str) -> None:
        self._conn.execute(
            "INSERT INTO spoke (chat_key, last_spoke, replied) VALUES (?,?,0) "
            "ON CONFLICT(chat_key) DO UPDATE SET last_spoke=?, replied=0",
            (chat_key, time.time(), time.time()),
        )
        self._conn.commit()
        self.session(chat_key).last_active = time.time()

    def mark_replied(self, chat_key: str) -> None:
        self._conn.execute(
            "INSERT INTO spoke (chat_key, last_spoke, replied) VALUES (?,0,1) "
            "ON CONFLICT(chat_key) DO UPDATE SET replied=1",
            (chat_key,),
        )
        self._conn.commit()

    def all_sessions(self) -> list[str]:
        return list(self._sessions.keys())
