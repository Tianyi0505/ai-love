
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import asyncpg
import yaml

from shared.infrastructure.runtime_config import ConfigKey, required_config, required_setting
from shared.infrastructure.snowflake import new_snowflake_id


with Path(__file__).with_name("migrate_legacy_sqlite.yaml").open(encoding="utf-8") as config_file:
    MIGRATION_CONFIG = yaml.safe_load(config_file)
if not isinstance(MIGRATION_CONFIG, dict):
    raise RuntimeError("deploy.migrate_legacy_sqlite 配置必须是对象")
MEMORY_CONFIG = dict(required_config(MIGRATION_CONFIG, "memory", "deploy.migrate_legacy_sqlite.memory"))
CONVERSATION_CONFIG = dict(required_config(MIGRATION_CONFIG, "conversation", "deploy.migrate_legacy_sqlite.conversation"))


# 将数值限制在单位区间
def unit(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1:
        number /= 100.0
    return max(0.0, min(1.0, number))


# 读取数据表记录
def rows(path: Path, table: str) -> list[dict]:
    if not path.is_file():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"')]
    finally:
        conn.close()


# 迁移记忆
async def migrate_memories(conn, data_dir: Path, ai_id: str) -> int:
    imported = 0
    for item in rows(data_dir / "memory.db", "memories"):
        result = await conn.execute(
            "INSERT INTO memories(memory_id,owner_ai_id,scope,memory_type,content,importance,strength,"
            "confidence,source,consolidated,created_at,last_strength_at,last_recalled_at,recall_count) "
            "VALUES($1::bigint,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,to_timestamp($11),"
            "to_timestamp($12),to_timestamp($12),$13) ON CONFLICT(memory_id) DO NOTHING",
            int(new_snowflake_id()),
            ai_id,
            str(MEMORY_CONFIG["scope"]),
            str(item.get("kind") or MEMORY_CONFIG["default_type"]),
            str(item.get("content") or ""),
            unit(item.get("importance"), float(MEMORY_CONFIG["default_importance"])),
            float(MEMORY_CONFIG["strength"]),
            float(MEMORY_CONFIG["confidence"]),
            json.dumps({"migration": "legacy-sqlite", "channel": item.get("channel", "")}),
            bool(MEMORY_CONFIG["consolidated"]),
            float(item.get("created_at") or 0),
            float(item.get("last_access_at") or item.get("created_at") or 0),
            int(item.get("access_count") or 0),
        )
        imported += int(result.endswith("1"))
    return imported


# 迁移会话记录
async def migrate_conversations(conn, data_dir: Path, ai_id: str) -> int:
    imported = 0
    agent_path = data_dir / "agents" / ai_id / "conversation.db"
    source_path = agent_path if agent_path.is_file() else data_dir / "conversation.db"
    persons: dict[str, tuple[int, int]] = {}
    for item in rows(source_path, "messages"):
        chat_key = str(item.get("chat_key") or "")
        chat_type, separator, chat_id = chat_key.partition(":")
        if not separator or chat_type not in {"private", "group"} or not chat_id:
            continue
        conversation_row = await conn.fetchrow(
            "INSERT INTO conversations(conversation_id,platform,account_id,platform_chat_id,chat_type) "
            "VALUES($1::bigint,'qq','qq-main',$2,$3) "
            "ON CONFLICT(platform,account_id,platform_chat_id) DO NOTHING "
            "RETURNING conversation_id",
            int(new_snowflake_id()),
            chat_id,
            chat_type,
        )
        conversation_id = int(conversation_row["conversation_id"])
        identity_id = None
        if chat_type == "private":
            if chat_id not in persons:
                person_id = int(new_snowflake_id())
                identity_id_new = int(new_snowflake_id())
                await conn.execute(
                    "INSERT INTO persons(person_id,display_name) VALUES($1::bigint,'') "
                    "ON CONFLICT(person_id) DO NOTHING",
                    person_id,
                )
                await conn.execute(
                    "INSERT INTO platform_identities(identity_id,person_id,platform,account_id,"
                    "platform_user_id,verified_by) VALUES($1::bigint,$2::bigint,'qq','qq-main',$3,'legacy-chat') "
                    "ON CONFLICT(identity_id) DO NOTHING",
                    identity_id_new,
                    person_id,
                    chat_id,
                )
                persons[chat_id] = (person_id, identity_id_new)
            identity_id = persons[chat_id][1]
        role = str(item.get("role") or CONVERSATION_CONFIG["default_role"])
        occurred_at = float(item.get("created_at") or 0)
        result = await conn.execute(
            "INSERT INTO messages(message_id,conversation_id,ai_id,platform_identity_id,role,content,"
            "occurred_at,retain_until,correlation_id,source_key) VALUES($1::bigint,$2::bigint,$3,$4::bigint,"
            "$5,$6::jsonb,to_timestamp($7),to_timestamp($7)+$8*interval '1 day',$9,$10) "
            "ON CONFLICT(source_key) DO NOTHING",
            int(new_snowflake_id()),
            conversation_id,
            ai_id if role == CONVERSATION_CONFIG["assistant_role"] else None,
            identity_id if role != CONVERSATION_CONFIG["assistant_role"] else None,
            role,
            json.dumps({"text": str(item.get("content") or ""), "migration": "legacy-sqlite"}, ensure_ascii=False),
            occurred_at,
            int(CONVERSATION_CONFIG["retention_days"]),
            f"legacy-sqlite:{item.get('id')}",
            f"legacy-sqlite:{item.get('id')}",
        )
        imported += int(result.endswith("1"))
    return imported


# 启动程序入口
async def main() -> None:
    database_url = required_setting(None, ConfigKey.AILOVE_DATABASE_URL)
    data_dir = Path(required_setting(None, ConfigKey.AILOVE_LEGACY_DATA_DIR))
    ai_id = required_setting(None, ConfigKey.AILOVE_AI_ID)
    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            memories = await migrate_memories(conn, data_dir, ai_id)
            messages = await migrate_conversations(conn, data_dir, ai_id)
            await conn.execute(
                "INSERT INTO audit_log(audit_id,actor_type,actor_id,action,target_type,target_id,reason,result) "
                "VALUES($1::bigint,'system','deploy','legacy.sqlite.import','dataset',$2,"
                "'preserve meaningful legacy data',$3::jsonb) ON CONFLICT(audit_id) DO NOTHING",
                int(new_snowflake_id()),
                str(data_dir),
                json.dumps({"memories_imported": memories, "messages_imported": messages}),
            )
        print(f"legacy migration complete: memories={memories}, messages={messages}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
