from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .contracts import PluginCommand, PluginError


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class PluginStore:
    """A durable local control journal, independent of plugin-owned business data."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS plugins (
                id TEXT PRIMARY KEY, installed INTEGER NOT NULL, enabled INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO metadata VALUES ('revision', 0);
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, request TEXT NOT NULL,
                status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, finished_at TEXT
            );
        """)
        with self.db:
            self.db.execute(
                "UPDATE operations SET status='interrupted', error=?, finished_at=? "
                "WHERE status IN ('accepted', 'running')",
                ("宿主曾退出；已按持久目标状态恢复，请刷新检查实际状态", timestamp()),
            )

    @property
    def revision(self) -> int:
        return int(self.db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0])

    def sync_catalog(self, fingerprint: str) -> None:
        with self.db:
            old = self.db.execute("SELECT value FROM metadata WHERE key='catalog'").fetchone()
            if old is not None and old[0] != fingerprint:
                self.db.execute("UPDATE metadata SET value=value+1 WHERE key='revision'")
            self.db.execute(
                "INSERT INTO metadata VALUES ('catalog', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (fingerprint,),
            )

    def ensure(self, plugin_id: str, enabled: bool, *, installed: bool = True) -> None:
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO plugins VALUES (?, ?, ?)", (plugin_id, installed, enabled))

    def states(self) -> dict[str, dict]:
        return {row["id"]: dict(row) for row in self.db.execute("SELECT * FROM plugins")}

    def operation(self, operation_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["request"] = json.loads(result["request"])
        result.pop("digest")
        return result

    def recent_operations(self) -> list[dict]:
        return [
            self.operation(row[0]) for row in self.db.execute("SELECT id FROM operations ORDER BY rowid DESC LIMIT 30")
        ]

    def existing(self, command: PluginCommand) -> dict | None:
        row = self.db.execute("SELECT digest FROM operations WHERE id=?", (command.operation_id,)).fetchone()
        if row is None:
            return None
        if row[0] != self._digest(command):
            raise PluginError("操作标识已用于另一请求，请刷新后重试")
        return self.operation(command.operation_id)

    def accept(self, command: PluginCommand, changes: dict[str, tuple[bool, bool]]) -> dict:
        with self.db:
            changed = self.db.execute(
                "UPDATE metadata SET value=value+1 WHERE key='revision' AND value=?",
                (command.expected_revision,),
            )
            if changed.rowcount != 1:
                raise PluginError("插件状态已被其他操作修改，请刷新后重试")
            for plugin_id, (installed, enabled) in changes.items():
                self.db.execute(
                    "INSERT INTO plugins VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "installed=excluded.installed, enabled=excluded.enabled",
                    (plugin_id, installed, enabled),
                )
            self.db.execute(
                "INSERT INTO operations VALUES (?, ?, ?, 'accepted', NULL, ?, NULL)",
                (command.operation_id, self._digest(command), command.model_dump_json(), timestamp()),
            )
        return self.operation(command.operation_id)

    def finish(self, operation_id: str, status: str, error: str | None = None) -> None:
        with self.db:
            self.db.execute(
                "UPDATE operations SET status=?, error=?, finished_at=? WHERE id=?",
                (status, error, None if status == "running" else timestamp(), operation_id),
            )

    def close(self) -> None:
        self.db.close()

    def uninstall(self, plugin_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE plugins SET installed=0, enabled=0 WHERE id=?", (plugin_id,))

    @staticmethod
    def _digest(command: PluginCommand) -> str:
        return hashlib.sha256(command.model_dump_json().encode()).hexdigest()
