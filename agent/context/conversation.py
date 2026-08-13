
from __future__ import annotations

import sqlite3
import time
from collections import deque
from pathlib import Path

from agent.context.search import Doc, HybridSearch


# 维护会话上下文
class ConversationContext:

    # 初始化当前实例
    def __init__(self, window_size: int, data_dir: str, search_config: dict) -> None:
        self._window_size = window_size
        self._search_config = search_config
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(Path(data_dir) / "conversation.db")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_key TEXT,
                role TEXT,
                content TEXT,
                created_at REAL
            )
        """)
        self._conn.commit()
        self._windows: dict[str, deque] = {}
        self._bm25: dict[str, HybridSearch] = {}
        self._load()

    # 加载数据
    def _load(self) -> None:
        rows = self._conn.execute(
            "SELECT chat_key, role, content FROM messages ORDER BY id"
        ).fetchall()
        for chat_key, role, content in rows:
            window = self._windows.setdefault(chat_key, deque(maxlen=self._window_size))
            window.append((role, content))
        for chat_key, window in self._windows.items():
            hs = HybridSearch(self._search_config)
            for role, content in window:
                hs.add(Doc(id=f"{chat_key}:{len(hs._docs)}", text=content))
            self._bm25[chat_key] = hs

    # 生成状态存储键
    def _key(self, chat_type: str, chat_id: str) -> str:
        return f"{chat_type}:{chat_id}"

    # 获取会话窗口
    def window(self, chat_type: str, chat_id: str) -> deque:
        key = self._key(chat_type, chat_id)
        return self._windows.setdefault(key, deque(maxlen=self._window_size))

    # 记录会话内容
    def remember(self, chat_type: str, chat_id: str, text: str) -> None:
        key = self._key(chat_type, chat_id)
        hs = self._bm25.setdefault(key, HybridSearch(self._search_config))
        hs.add(Doc(id=f"{key}:{len(hs._docs)}", text=text))

    # 持久化会话上下文
    def _persist(self, chat_key: str, role: str, text: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (chat_key, role, content, created_at) VALUES (?,?,?,?)",
            (chat_key, role, text, time.time()),
        )
        self._conn.commit()

    # 添加用户
    def add_user(self, chat_type: str, chat_id: str, text: str) -> None:
        key = self._key(chat_type, chat_id)
        self.window(chat_type, chat_id).append(("user", text))
        self.remember(chat_type, chat_id, text)
        self._persist(key, "user", text)

    # 添加AI
    def add_ai(self, chat_type: str, chat_id: str, text: str) -> None:
        key = self._key(chat_type, chat_id)
        self.window(chat_type, chat_id).append(("assistant", text))
        self.remember(chat_type, chat_id, text)
        self._persist(key, "assistant", text)

    # 获取首条消息
    def first_msg(self, chat_type: str, chat_id: str) -> str:
        key = self._key(chat_type, chat_id)
        rows = self._conn.execute(
            "SELECT content FROM messages WHERE chat_key=? AND role='user' ORDER BY id LIMIT 1",
            (key,),
        ).fetchone()
        return rows[0] if rows else ""

    # 执行BM25文本检索
    def bm25_search(self, chat_type: str, chat_id: str, query: str) -> list[str]:
        key = self._key(chat_type, chat_id)
        hs = self._bm25.get(key)
        if hs is None:
            return []
        hits = hs.search(query)
        return [hs.get(doc_id).text for doc_id, _ in hits if hs.get(doc_id)]

    # 列出全部会话窗口
    def all_windows(self) -> list[tuple[str, deque]]:
        return list(self._windows.items())
