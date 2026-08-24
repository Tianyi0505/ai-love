"""将人物记忆 owner_id 中遗留的 UUID 回填为雪花 ID。

Revision ID: 0004_memory_owner_snowflake
Revises: 0003_refactor_schema_compat
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_memory_owner_snowflake"
down_revision = "0003_refactor_schema_compat"
branch_labels = None
depends_on = None


_UUID_PATTERN = (
    "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "CREATE TEMP TABLE uuid_owner_map ON COMMIT DROP AS "
            "SELECT owner_id AS old_id, min(person_id)::text AS new_id "
            "FROM memory_atoms "
            "WHERE owner_type='person' AND owner_id ~ :uuid_pattern AND person_id IS NOT NULL "
            "GROUP BY owner_id HAVING count(DISTINCT person_id)=1"
        ),
        {"uuid_pattern": _UUID_PATTERN},
    )

    unmapped = connection.execute(
        sa.text(
            "SELECT count(*) FROM memory_documents d "
            "LEFT JOIN uuid_owner_map m ON m.old_id=d.owner_id "
            "WHERE d.owner_type='person' AND d.owner_id ~ :uuid_pattern AND m.old_id IS NULL"
        ),
        {"uuid_pattern": _UUID_PATTERN},
    ).scalar_one()
    missing_person = connection.execute(
        sa.text(
            "SELECT count(*) FROM uuid_owner_map m "
            "LEFT JOIN persons p ON p.person_id::text=m.new_id WHERE p.person_id IS NULL"
        )
    ).scalar_one()
    if unmapped or missing_person:
        raise RuntimeError(
            f"人物记忆 UUID 映射不完整: unmapped={unmapped}, missing_person={missing_person}"
        )

    connection.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS memory_documents_uuid_backup_20260824 AS "
            "SELECT d.*, m.new_id AS mapped_owner_id, now() AS backed_up_at "
            "FROM memory_documents d JOIN uuid_owner_map m ON m.old_id=d.owner_id "
            "WHERE d.owner_type='person' AND d.owner_id ~ :uuid_pattern"
        ),
        {"uuid_pattern": _UUID_PATTERN},
    )
    connection.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS memory_atoms_uuid_backup_20260824 AS "
            "SELECT a.*, a.person_id::text AS mapped_owner_id, now() AS backed_up_at "
            "FROM memory_atoms a "
            "WHERE a.owner_type='person' AND a.owner_id ~ :uuid_pattern"
        ),
        {"uuid_pattern": _UUID_PATTERN},
    )

    # 同一人物已有雪花文档时保留当前规范记录，旧 UUID 文档已进入备份表。
    connection.execute(
        sa.text(
            "DELETE FROM memory_documents legacy USING uuid_owner_map m "
            "WHERE legacy.owner_type='person' AND legacy.owner_id=m.old_id "
            "AND EXISTS (SELECT 1 FROM memory_documents current "
            "WHERE current.ai_id=legacy.ai_id AND current.owner_type=legacy.owner_type "
            "AND current.owner_id=m.new_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE memory_documents d SET owner_id=m.new_id FROM uuid_owner_map m "
            "WHERE d.owner_type='person' AND d.owner_id=m.old_id"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE memory_atoms SET owner_id=person_id::text "
            "WHERE owner_type='person' AND owner_id ~ :uuid_pattern AND person_id IS NOT NULL"
        ),
        {"uuid_pattern": _UUID_PATTERN},
    )


def downgrade() -> None:
    # 回退会重新引入已淘汰的 UUID 标识，因此仅保留备份表供人工恢复。
    pass
