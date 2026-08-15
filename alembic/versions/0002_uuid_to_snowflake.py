"""存量库 uuid 主键迁移为雪花 bigint

Revision ID: 0002_uuid_to_snowflake
Revises: 0001_initial
Create Date: 2026-08-15

"""
from alembic import op
import sqlalchemy as sa

from shared.infrastructure.snowflake import SnowflakeGenerator

revision = "0002_uuid_to_snowflake"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

# 各表需要重建的ID主键映射：(表, 列, 映射表, 排序依据列)
_MAPS = [
    ("persons", "person_id", "_map_person", "created_at"),
    ("conversations", "conversation_id", "_map_conversation", "created_at"),
    ("platform_identities", "identity_id", "_map_identity", "verified_at"),
    ("messages", "message_id", "_map_message", "occurred_at"),
    ("person_mentions", "mention_id", "_map_mention", "observed_at"),
    ("memories", "memory_id", "_map_memory", "created_at"),
    ("memory_revisions", "revision_id", "_map_revision", "created_at"),
    ("conversation_episodes", "episode_id", "_map_episode", "ended_at"),
    ("memory_atoms", "atom_id", "_map_atom", "created_at"),
    ("agent_runs", "run_id", "_map_run", "started_at"),
    ("agent_run_steps", "step_id", "_map_step", "occurred_at"),
    ("ai_account_bindings", "binding_id", "_map_binding", "bound_at"),
    ("audit_log", "audit_id", "_map_audit", "created_at"),
]

# 全部需要更换的ID列：(表, 列, 回填使用的映射表)
_ID_COLUMNS = [
    ("persons", "person_id", "_map_person"),
    ("conversations", "conversation_id", "_map_conversation"),
    ("platform_identities", "identity_id", "_map_identity"),
    ("platform_identities", "person_id", "_map_person"),
    ("messages", "message_id", "_map_message"),
    ("messages", "conversation_id", "_map_conversation"),
    ("messages", "platform_identity_id", "_map_identity"),
    ("group_members", "person_id", "_map_person"),
    ("person_mentions", "mention_id", "_map_mention"),
    ("person_mentions", "person_id", "_map_person"),
    ("person_mentions", "conversation_id", "_map_conversation"),
    ("person_relationships", "person_id", "_map_person"),
    ("memories", "memory_id", "_map_memory"),
    ("memories", "person_id", "_map_person"),
    ("memory_revisions", "revision_id", "_map_revision"),
    ("memory_revisions", "memory_id", "_map_memory"),
    ("memory_revisions", "supersedes_memory_id", "_map_memory"),
    ("conversation_episodes", "episode_id", "_map_episode"),
    ("conversation_episodes", "person_id", "_map_person"),
    ("conversation_episodes", "conversation_id", "_map_conversation"),
    ("memory_atoms", "atom_id", "_map_atom"),
    ("memory_atoms", "person_id", "_map_person"),
    ("memory_atoms", "episode_id", "_map_episode"),
    ("conversation_summaries", "conversation_id", "_map_conversation"),
    ("agent_runs", "run_id", "_map_run"),
    ("agent_runs", "conversation_id", "_map_conversation"),
    ("agent_runs", "sender_person_id", "_map_person"),
    ("agent_run_steps", "step_id", "_map_step"),
    ("agent_run_steps", "run_id", "_map_run"),
    ("ai_account_bindings", "binding_id", "_map_binding"),
    ("audit_log", "audit_id", "_map_audit"),
]

_ARRAYS = [
    ("conversation_episodes", "source_message_ids"),
    ("memory_atoms", "source_message_ids"),
]

# 主键在ID列上的表及其完整主键列
_PRIMARY_KEYS = {
    "persons": ("person_id",),
    "conversations": ("conversation_id",),
    "platform_identities": ("identity_id",),
    "messages": ("message_id",),
    "person_mentions": ("mention_id",),
    "person_relationships": ("ai_id", "person_id"),
    "memories": ("memory_id",),
    "memory_revisions": ("revision_id",),
    "conversation_episodes": ("episode_id",),
    "memory_atoms": ("atom_id",),
    "conversation_summaries": ("ai_id", "conversation_id"),
    "agent_runs": ("run_id",),
    "agent_run_steps": ("step_id",),
    "ai_account_bindings": ("binding_id",),
    "audit_log": ("audit_id",),
}

# 迁移后需要重建的索引
_INDEXES = [
    ("person_mentions", "person_mentions_uidx", "UNIQUE",
     ["normalized_mention", "person_id", "scope_type", "scope_id", "evidence_type", "source_message_id"]),
    ("group_members", "idx_group_members_person", "INDEX", ["person_id", "last_seen_at DESC"]),
    ("conversation_episodes", "idx_conversation_episodes_owner", "INDEX",
     ["ai_id", "person_id", "conversation_id", "ended_at DESC"]),
    ("agent_runs", "idx_agent_runs_conversation", "INDEX", ["ai_id", "conversation_id", "started_at DESC"]),
    ("agent_run_steps", "idx_agent_run_steps_run", "INDEX", ["run_id", "step_index"]),
]


def _has_table(conn, name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:name"
        ),
        {"name": name},
    ).scalar()
    return bool(row)


def _has_uuid_columns(conn) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='messages' "
            "AND column_name='message_id' AND data_type='uuid'"
        )
    ).scalar()
    return bool(row)


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "messages") or not _has_uuid_columns(conn):
        return

    # 按时间顺序为每个表分配雪花ID并写入映射表
    generator = SnowflakeGenerator(worker_id=0)
    created_maps = set()
    for table, column, map_table, order_by in _MAPS:
        if not _has_table(conn, table):
            continue
        rows = conn.execute(
            sa.text(f"SELECT {column} AS old_id FROM {table} ORDER BY {order_by}, {column}")
        ).fetchall()
        conn.execute(
            sa.text(f"CREATE TEMP TABLE {map_table} (old_id uuid PRIMARY KEY, new_id bigint NOT NULL)")
        )
        created_maps.add(map_table)
        for row in rows:
            conn.execute(
                sa.text(f"INSERT INTO {map_table}(old_id,new_id) VALUES(:old,:new)"),
                {"old": row[0], "new": generator.next_id()},
            )

    # 逐列更换为 bigint 并按映射表回填
    for table, column, map_table in _ID_COLUMNS:
        if not _has_table(conn, table):
            continue
        new_col = f"{column}_new"
        conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {new_col} bigint"))
        if map_table in created_maps:
            conn.execute(
                sa.text(
                    f"UPDATE {table} t SET {new_col}=mp.new_id "
                    f"FROM {map_table} mp WHERE mp.old_id=t.{column}"
                )
            )
        conn.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        conn.execute(sa.text(f"ALTER TABLE {table} RENAME COLUMN {new_col} TO {column}"))

    # 消息ID数组逐元素重映射
    for table, column in _ARRAYS:
        if not _has_table(conn, table):
            continue
        new_col = f"{column}_new"
        conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {new_col} bigint[]"))
        conn.execute(
            sa.text(
                f"UPDATE {table} t SET {new_col}=ARRAY("
                f"SELECT mp.new_id FROM _map_message mp "
                f"JOIN unnest(t.{column}) WITH ORDINALITY AS u(old_id, ord) ON u.old_id=mp.old_id "
                f"ORDER BY u.ord)"
            )
        )
        conn.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        conn.execute(sa.text(f"ALTER TABLE {table} RENAME COLUMN {new_col} TO {column}"))

    # 重建主键（DROP COLUMN 时已被连带删除）
    for table, columns in _PRIMARY_KEYS.items():
        if not _has_table(conn, table):
            continue
        cols = ", ".join(columns)
        conn.execute(sa.text(f"ALTER TABLE {table} ADD PRIMARY KEY ({cols})"))

    # 重建受影响的索引与唯一约束
    for table, index_name, kind, columns in _INDEXES:
        if not _has_table(conn, table):
            continue
        cols = ", ".join(columns)
        if kind == "UNIQUE":
            conn.execute(sa.text(f"CREATE UNIQUE INDEX {index_name} ON {table} ({cols})"))
        else:
            conn.execute(sa.text(f"CREATE INDEX {index_name} ON {table} ({cols})"))

    # 消息去重键列
    conn.execute(sa.text("ALTER TABLE messages ADD COLUMN source_key text"))
    conn.execute(sa.text("CREATE UNIQUE INDEX messages_source_key_uq ON messages(source_key)"))


def downgrade() -> None:
    pass
