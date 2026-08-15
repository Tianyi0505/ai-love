
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    func,
    inspect,
    or_,
    select,
    update,
)

_metadata = MetaData()
_stickers_table = Table(
    "stickers",
    _metadata,
    Column("id", String, primary_key=True),
    Column("image_url", String),
    Column("description", String),
    Column("tags", String),
    Column("value", Float),
    Column("importance", Float),
    Column("boost_count", Integer, server_default="0"),
    Column("last_boost_at", Float),
    Column("created_at", Float),
    Column("match_quality", Float),
    Column("usage_strength", Float),
    Column("last_used_at", Float),
)

_REQUIRED_COLUMNS = {
    "id", "image_url", "description", "tags", "value", "importance",
    "boost_count", "last_boost_at", "created_at", "match_quality", "usage_strength", "last_used_at",
}


# 对检索文本分词
def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for ch in text:
        if "一" <= ch <= "鿿":
            tokens.append(ch)
    return tokens


# 管理表情存储库持久化
class StickerRepo:

    # 初始化当前实例
    def __init__(self, ai_id: str, data_dir: str, config: dict) -> None:
        self._ai_id = ai_id
        self._config = config
        db_dir = Path(data_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_dir / f'stickers_{ai_id}.db'}")
        self._init_db()

    # 初始化表情数据库
    def _init_db(self) -> None:
        inspector = inspect(self._engine)
        if inspector.has_table("stickers"):
            existing = {col["name"] for col in inspector.get_columns("stickers")}
            if not _REQUIRED_COLUMNS.issubset(existing):
                _stickers_table.drop(self._engine)
        _stickers_table.create(self._engine, checkfirst=True)
        with self._engine.begin() as conn:
            rows = conn.execute(select(_stickers_table)).all()
            for row in rows:
                if row.match_quality is None:
                    conn.execute(
                        update(_stickers_table)
                        .where(_stickers_table.c.id == row.id)
                        .values(
                            match_quality=max(
                                0.0,
                                min(
                                    1.0,
                                    float(
                                        row.value
                                        or float(self._config["initial_match_quality"])
                                        * float(self._config["legacy_value_divisor"])
                                    )
                                    / float(self._config["legacy_value_divisor"]),
                                ),
                            )
                        )
                    )

    # 将数据行转换为字典
    def _row_to_dict(self, row) -> dict:
        data = dict(row._mapping)
        data["tags"] = json.loads(data.get("tags") or "[]")
        data["freshness"] = self._freshness(data)
        data["retention_score"] = self._retention_score(data)
        data.pop("value", None)
        data.pop("importance", None)
        return data

    # 计算记忆新鲜度
    def _freshness(self, row: dict) -> float:
        anchor = row.get("last_used_at") or row.get("created_at") or time.time()
        elapsed = max(0.0, time.time() - anchor)
        return 0.5 ** (elapsed / float(self._config["half_life_sec"]))

    # 计算记忆保留分数
    def _retention_score(self, row: dict) -> float:
        return (
            float(row.get("match_quality") or 0.0) * float(self._config["retention_weights"]["match_quality"])
            + float(row.get("usage_strength") or 0.0) * float(self._config["retention_weights"]["usage_strength"])
            + self._freshness(row) * float(self._config["retention_weights"]["freshness"])
        )

    # 返回记录数量
    def count(self) -> int:
        with self._engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(_stickers_table)).scalar_one()

    # 判断记录是否存在
    def exists(self, sticker_id: str) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(_stickers_table.c.id).where(_stickers_table.c.id == sticker_id).limit(1)
            ).first()
        return row is not None

    # 插入数据
    def insert(self, sticker: dict) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                _stickers_table.insert().values(
                    id=sticker["id"],
                    image_url=sticker["image_url"],
                    description=sticker["description"],
                    tags=json.dumps(sticker.get("tags", [])),
                    value=None,
                    importance=None,
                    boost_count=0,
                    last_boost_at=None,
                    created_at=time.time(),
                    match_quality=self._unit(
                        sticker.get("match_quality", self._config["initial_match_quality"])
                    ),
                    usage_strength=self._config["initial_usage_strength"],
                    last_used_at=None,
                )
            )

    # 删除最低项
    def delete_lowest(self) -> str:
        with self._engine.connect() as conn:
            rows = conn.execute(select(_stickers_table)).all()
            if not rows:
                return ""
            lowest = min(rows, key=lambda row: self._retention_score(dict(row._mapping)))
            conn.execute(delete(_stickers_table).where(_stickers_table.c.id == lowest.id))
            conn.commit()
            return lowest.description

    # 删除不可用项
    def delete_unusable(self, min_quality: float) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                delete(_stickers_table).where(
                    or_(
                        func.coalesce(_stickers_table.c.match_quality, 0) < self._unit(min_quality),
                        func.trim(_stickers_table.c.description).like("```%"),
                    )
                )
            )
            return max(0, result.rowcount)

    # 列出全部数据
    def all(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(_stickers_table)).all()
        return [self._row_to_dict(row) for row in rows]

    # 增强记忆强度
    def boost(self, sticker_id: str, boost_delta: float) -> None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(_stickers_table).where(_stickers_table.c.id == sticker_id)
            ).first()
            if row:
                new_strength = min(1.0, float(row.usage_strength or 0.0) + self._unit(boost_delta))
                now = time.time()
                conn.execute(
                    update(_stickers_table)
                    .where(_stickers_table.c.id == sticker_id)
                    .values(
                        usage_strength=new_strength,
                        last_used_at=now,
                        last_boost_at=now,
                        boost_count=_stickers_table.c.boost_count + 1,
                    )
                )
                conn.commit()

    # 清理过期数据
    def cleanup(self, threshold: float) -> int:
        normalized_threshold = self._unit(threshold)
        with self._engine.connect() as conn:
            rows = conn.execute(select(_stickers_table)).all()
            removed = [
                row.id for row in rows if self._retention_score(dict(row._mapping)) < normalized_threshold
            ]
            if removed:
                conn.execute(delete(_stickers_table).where(_stickers_table.c.id.in_(removed)))
                conn.commit()
            return len(removed)

    # 获取数据
    def get(self, sticker_id: str) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(_stickers_table).where(_stickers_table.c.id == sticker_id)
            ).first()
        return self._row_to_dict(row) if row else None

    # 关闭资源
    def close(self) -> None:
        self._engine.dispose()

    # 将数值限制在单位区间
    @staticmethod
    def _unit(value) -> float:
        number = float(value)
        if number > 1.0:
            number /= 100.0
        return max(0.0, min(1.0, number))
