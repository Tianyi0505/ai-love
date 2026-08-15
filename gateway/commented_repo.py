
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import Column, Float, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


_metadata = MetaData()
_commented_table = Table(
    "commented",
    _metadata,
    Column("tid", String, primary_key=True),
    Column("commented_at", Float),
)


# 记录已评论的动态
class CommentedRepo:

    # 初始化当前实例
    def __init__(self, data_dir: str) -> None:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{Path(data_dir) / 'commented.db'}")
        _commented_table.create(self._engine, checkfirst=True)

    # 判断记录是否存在
    def has(self, tid: str) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(_commented_table.c.tid).where(_commented_table.c.tid == tid).limit(1)
            ).first()
        return row is not None

    # 添加数据
    def add(self, tid: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sqlite_insert(_commented_table)
                .values(tid=tid, commented_at=time.time())
                .on_conflict_do_nothing(index_elements=[_commented_table.c.tid])
            )
