
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for ch in text:
        if "一" <= ch <= "鿿":
            tokens.append(ch)
    return tokens


class StickerRepo:

    def __init__(self, ai_id: str, data_dir: str, config: dict) -> None:
        self._ai_id = ai_id
        self._config = config
        db_dir = Path(data_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_dir / f"stickers_{ai_id}.db")
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS stickers (
                id TEXT PRIMARY KEY,
                image_url TEXT,
                description TEXT,
                tags TEXT,
                value REAL,
                importance REAL,
                boost_count INTEGER DEFAULT 0,
                last_boost_at REAL,
                created_at REAL,
                match_quality REAL DEFAULT {float(self._config['initial_match_quality'])},
                usage_strength REAL DEFAULT {float(self._config['initial_usage_strength'])},
                last_used_at REAL
            )
        """)
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(stickers)")}
        added_match_quality = "match_quality" not in columns
        if added_match_quality:
            self._conn.execute(
                f"ALTER TABLE stickers ADD COLUMN match_quality REAL DEFAULT {float(self._config['initial_match_quality'])}"
            )
        if "usage_strength" not in columns:
            self._conn.execute(
                f"ALTER TABLE stickers ADD COLUMN usage_strength REAL DEFAULT {float(self._config['initial_usage_strength'])}"
            )
        if "last_used_at" not in columns:
            self._conn.execute("ALTER TABLE stickers ADD COLUMN last_used_at REAL")
        if added_match_quality:
            self._conn.execute(
                "UPDATE stickers SET match_quality=MAX(0.0, MIN(1.0, "
                f"COALESCE(value, {float(self._config['initial_match_quality']) * float(self._config['legacy_value_divisor'])}) "
                f"/ {float(self._config['legacy_value_divisor'])}))"
            )
        self._conn.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["tags"] = json.loads(d.get("tags") or "[]")
        d["freshness"] = self._freshness(row)
        d["retention_score"] = self._retention_score(row)
        d.pop("value", None)
        d.pop("importance", None)
        return d

    def _freshness(self, row: sqlite3.Row) -> float:
        anchor = row["last_used_at"] or row["created_at"] or time.time()
        elapsed = max(0.0, time.time() - anchor)
        return 0.5 ** (elapsed / float(self._config["half_life_sec"]))

    def _retention_score(self, row: sqlite3.Row) -> float:
        return (
            float(row["match_quality"] or 0.0) * float(self._config["retention_weights"]["match_quality"])
            + float(row["usage_strength"] or 0.0) * float(self._config["retention_weights"]["usage_strength"])
            + self._freshness(row) * float(self._config["retention_weights"]["freshness"])
        )

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM stickers").fetchone()[0]

    def exists(self, sticker_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM stickers WHERE id=?", (sticker_id,)).fetchone() is not None

    def insert(self, sticker: dict) -> None:
        self._conn.execute(
            "INSERT INTO stickers (id, image_url, description, tags, value, importance, boost_count, "
            "last_boost_at, created_at, match_quality, usage_strength, last_used_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sticker["id"], sticker["image_url"], sticker["description"], json.dumps(sticker.get("tags", [])),
             None, None, 0, None, time.time(), self._unit(sticker.get("match_quality", self._config["initial_match_quality"])), self._config["initial_usage_strength"], None),
        )
        self._conn.commit()

    def delete_lowest(self) -> str:
        rows = self._conn.execute("SELECT * FROM stickers").fetchall()
        if not rows:
            return ""
        lowest = min(rows, key=self._retention_score)
        self._conn.execute("DELETE FROM stickers WHERE id=?", (lowest["id"],))
        self._conn.commit()
        return lowest["description"]

    def delete_unusable(self, min_quality: float) -> int:
        cursor = self._conn.execute(
            "DELETE FROM stickers WHERE COALESCE(match_quality, 0) < ? OR TRIM(description) LIKE '```%'",
            (self._unit(min_quality),),
        )
        self._conn.commit()
        return max(0, cursor.rowcount)

    def all(self) -> list[dict]:
        return [self._row_to_dict(r) for r in self._conn.execute("SELECT * FROM stickers").fetchall()]

    def boost(self, sticker_id: str, boost_delta: float) -> None:
        cur = self._conn.execute("SELECT * FROM stickers WHERE id=?", (sticker_id,))
        row = cur.fetchone()
        if row:
            new_strength = min(1.0, float(row["usage_strength"] or 0.0) + self._unit(boost_delta))
            now = time.time()
            self._conn.execute(
                "UPDATE stickers SET usage_strength=?, last_used_at=?, last_boost_at=?, "
                "boost_count=boost_count+1 WHERE id=?",
                (new_strength, now, now, sticker_id),
            )
            self._conn.commit()

    def cleanup(self, threshold: float) -> int:
        rows = self._conn.execute("SELECT * FROM stickers").fetchall()
        normalized_threshold = self._unit(threshold)
        removed = [r["id"] for r in rows if self._retention_score(r) < normalized_threshold]
        for rid in removed:
            self._conn.execute("DELETE FROM stickers WHERE id=?", (rid,))
        if removed:
            self._conn.commit()
        return len(removed)

    def get(self, sticker_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM stickers WHERE id=?", (sticker_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _unit(value) -> float:
        number = float(value)
        if number > 1.0:
            number /= 100.0
        return max(0.0, min(1.0, number))
