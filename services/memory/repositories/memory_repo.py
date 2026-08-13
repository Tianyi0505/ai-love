
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class MemoryRepo:

    def __init__(self, data_dir: str) -> None:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(Path(data_dir) / "memory.db")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ai_id TEXT,
                content TEXT,
                importance REAL,
                layer TEXT,
                kind TEXT,
                channel TEXT,
                created_at REAL,
                last_access_at REAL,
                access_count INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ai ON memories(ai_id)")
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(memories)")}
        if "person_id" not in columns:
            self._conn.execute("ALTER TABLE memories ADD COLUMN person_id TEXT")
        self._conn.commit()

    async def write(self, ai_id: str, entries: list[dict]) -> None:
        for e in entries:
            self._conn.execute(
                "INSERT INTO memories (ai_id, person_id, content, importance, layer, kind, channel, created_at, last_access_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (ai_id, e.get("person_id") or None, e.get("content", ""),
                 e["importance"],
                 e.get("layer", "long_term"), e["memory_type"],
                 e.get("channel", ""), time.time(), time.time()),
            )
        self._conn.commit()

    async def search(self, ai_id: str, query: str, top_k: int, person_id: str = "", **_) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE ai_id=? AND (?='' OR person_id IS NULL OR person_id=?) "
            "ORDER BY importance DESC LIMIT ?",
            (ai_id, person_id, person_id, top_k * 3),
        ).fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM memories LIMIT 0").description]
        results = []
        for r in rows:
            d = dict(zip(cols, r))
            if query and not self._match(d["content"], query):
                continue
            results.append(d)
            self._conn.execute(
                "UPDATE memories SET access_count=access_count+1, last_access_at=? WHERE id=?",
                (time.time(), d["id"]),
            )
            if len(results) >= top_k:
                break
        self._conn.commit()
        return results

    async def cleanup(self) -> dict[str, int]:
        return {"dormant": 0, "deleted": 0}

    def _match(self, content: str, query: str) -> bool:
        content_l = content.lower()
        if query.lower() in content_l:
            return True
        q_chars = set(query.lower())
        return sum(1 for c in q_chars if c in content_l) >= max(1, len(q_chars) // 2)
