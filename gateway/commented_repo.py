
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


# 记录已评论的动态
class CommentedRepo:

    # 初始化当前实例
    def __init__(self, data_dir: str) -> None:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(Path(data_dir) / "commented.db")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS commented (
                tid TEXT PRIMARY KEY,
                commented_at REAL
            )
        """)
        self._conn.commit()

    # 判断记录是否存在
    def has(self, tid: str) -> bool:
        return self._conn.execute("SELECT 1 FROM commented WHERE tid=?", (tid,)).fetchone() is not None

    # 添加数据
    def add(self, tid: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO commented (tid, commented_at) VALUES (?,?)",
            (tid, time.time()),
        )
        self._conn.commit()
