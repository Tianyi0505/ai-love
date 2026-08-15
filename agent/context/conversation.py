
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, create_engine, insert, select

from agent.context.search import Doc, HybridSearch


# 将带归属的会话窗口格式化为提示词片段
def format_entries(entries, ai_name: str = "") -> str:
    blocks: list[str] = []
    for role, text, meta in entries:
        if role == "assistant":
            blocks.append(f"[AI | {ai_name}]\n{text}" if ai_name else f"[AI]\n{text}")
            continue
        name = str(meta.get("speaker_name") or "用户")
        person_id = str(meta.get("speaker_id") or "")
        label = f"[{person_id} | {name}]" if person_id else f"[{name}]"
        quote = meta.get("quote") or {}
        if quote.get("name"):
            blocks.append(f"{label}\n[引用 {quote.get('name')}]\n{text}")
        else:
            blocks.append(f"{label}\n{text}")
    return "\n\n".join(blocks)


_metadata = MetaData()
_messages_table = Table(
    "messages",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("chat_key", String),
    Column("role", String),
    Column("content", String),
    Column("meta", String, server_default=""),
    Column("created_at", Float),
)


# 维护会话上下文
class ConversationContext:

    # 初始化当前实例
    def __init__(self, window_size: int, data_dir: str, search_config: dict) -> None:
        self._window_size = window_size
        self._search_config = search_config
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{Path(data_dir) / 'conversation.db'}")
        _messages_table.create(self._engine, checkfirst=True)
        self._windows: dict[str, deque] = {}
        self._bm25: dict[str, HybridSearch] = {}
        self._load()

    # 加载数据
    def _load(self) -> None:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    _messages_table.c.chat_key,
                    _messages_table.c.role,
                    _messages_table.c.content,
                    _messages_table.c.meta,
                ).order_by(_messages_table.c.id)
            )
            for chat_key, role, content, meta in rows:
                window = self._windows.setdefault(chat_key, deque(maxlen=self._window_size))
                window.append((role, content, self._parse_meta(meta)))
            for chat_key, window in self._windows.items():
                hs = HybridSearch(self._search_config)
                for role, content, _meta in window:
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
    def _persist(self, chat_key: str, role: str, text: str, meta: dict) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(_messages_table).values(
                    chat_key=chat_key,
                    role=role,
                    content=text,
                    meta=json.dumps(meta, ensure_ascii=False),
                    created_at=time.time(),
                )
            )

    # 添加用户
    def add_user(
        self,
        chat_type: str,
        chat_id: str,
        text: str,
        speaker_id: str = "",
        speaker_name: str = "",
        quote: dict | None = None,
    ) -> None:
        key = self._key(chat_type, chat_id)
        meta: dict = {"speaker_id": speaker_id, "speaker_name": speaker_name}
        if quote:
            meta["quote"] = quote
        self.window(chat_type, chat_id).append(("user", text, meta))
        self.remember(chat_type, chat_id, text)
        self._persist(key, "user", text, meta)

    # 添加AI
    def add_ai(self, chat_type: str, chat_id: str, text: str) -> None:
        key = self._key(chat_type, chat_id)
        self.window(chat_type, chat_id).append(("assistant", text, {}))
        self.remember(chat_type, chat_id, text)
        self._persist(key, "assistant", text, {})

    # 获取首条消息
    def first_msg(self, chat_type: str, chat_id: str) -> str:
        key = self._key(chat_type, chat_id)
        with self._engine.connect() as conn:
            row = conn.execute(
                select(_messages_table.c.content)
                .where(_messages_table.c.chat_key == key, _messages_table.c.role == "user")
                .order_by(_messages_table.c.id)
                .limit(1)
            ).first()
        return row[0] if row else ""

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

    # 解析历史元数据
    @staticmethod
    def _parse_meta(raw: str) -> dict:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
