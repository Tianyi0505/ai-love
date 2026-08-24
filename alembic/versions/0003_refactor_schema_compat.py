"""补齐重构后 ORM 所需的兼容结构。

Revision ID: 0003_refactor_schema_compat
Revises: 0002_uuid_to_snowflake
"""

import sqlalchemy as sa

from alembic import op
from shared.persistence import database_models as models

revision = "0003_refactor_schema_compat"
down_revision = "0002_uuid_to_snowflake"
branch_labels = None
depends_on = None


_SURROGATE_COLUMNS = {
    "ai_profiles": "profile_id",
    "social_accounts": "social_account_id",
    "group_members": "group_member_id",
    "live_sessions": "live_session_id",
    "live_session_actors": "live_session_actor_id",
    "person_relationships": "person_relationship_id",
    "group_relationships": "group_relationship_id",
    "memory_documents": "memory_document_id",
    "conversation_summaries": "conversation_summary_id",
    "extension_catalog": "extension_catalog_id",
    "ai_extension_bindings": "ai_extension_binding_id",
    "model_profiles": "model_profile_record_id",
    "panel_settings": "panel_setting_id",
    "stickers": "sticker_id",
    "qzone_commented_feeds": "qzone_commented_feed_id",
}


def _has_table(connection, table: str) -> bool:
    return bool(
        connection.execute(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:table)"
            ),
            {"table": table},
        ).scalar()
    )


def _has_column(connection, table: str, column: str) -> bool:
    return bool(
        connection.execute(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:table AND column_name=:column)"
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "CREATE SEQUENCE IF NOT EXISTS ailove_surrogate_id_seq "
            "AS bigint INCREMENT BY -1 START WITH -1 "
            "MINVALUE -9223372036854775807 NO CYCLE"
        )
    )

    # 这两张表是重构后新增的持久化入口。checkfirst 只会补建，不覆盖线上数据。
    models.Sticker.__table__.create(connection, checkfirst=True)
    models.QZoneCommentedFeed.__table__.create(connection, checkfirst=True)

    for table, column in _SURROGATE_COLUMNS.items():
        if not _has_table(connection, table):
            continue
        if not _has_column(connection, table, column):
            connection.execute(
                sa.text(
                    f"ALTER TABLE {table} ADD COLUMN {column} bigint "
                    "DEFAULT nextval('ailove_surrogate_id_seq')"
                )
            )
        connection.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} "
                "SET DEFAULT nextval('ailove_surrogate_id_seq')"
            )
        )
        connection.execute(
            sa.text(
                f"UPDATE {table} SET {column}=nextval('ailove_surrogate_id_seq') "
                f"WHERE {column} IS NULL"
            )
        )
        connection.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"))
        connection.execute(
            sa.text(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{table}_{column} ON {table} ({column})")
        )


def downgrade() -> None:
    # 兼容列可能已经被新版本写入，自动删除会造成数据丢失。
    pass
