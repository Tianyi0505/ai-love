"""为关系、记忆和称呼证据增加惰性 LFU 状态。

Revision ID: 0005_lazy_lfu_state
Revises: 0004_memory_owner_snowflake
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_lazy_lfu_state"
down_revision = "0004_memory_owner_snowflake"
branch_labels = None
depends_on = None


def _state(counter_sql: str) -> str:
    return (
        "jsonb_build_object("
        f"'counter', {counter_sql}, "
        "'last_decay_at', extract(epoch FROM now()))"
    )


def _has_column(connection, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(connection).get_columns(table_name))


def upgrade() -> None:
    connection = op.get_bind()
    empty_state = sa.text("'{}'::jsonb")
    lfu_tables = (
        "person_relationships",
        "group_relationships",
        "memories",
        "memory_atoms",
        "memory_documents",
    )
    for table_name in lfu_tables:
        if not _has_column(connection, table_name, "lfu_state"):
            op.add_column(
                table_name,
                sa.Column("lfu_state", postgresql.JSONB(), nullable=False, server_default=empty_state),
            )
    if not _has_column(connection, "memory_atoms", "consolidated_at"):
        op.add_column("memory_atoms", sa.Column("consolidated_at", sa.DateTime(timezone=True), nullable=True))

    connection.execute(
        sa.text(
            "UPDATE person_relationships SET lfu_state=jsonb_build_object("
            f"'familiarity', {_state('round(greatest(0, least(1, familiarity)) * 20)::int')},"
            f"'affinity_positive', {_state('round(greatest(0, least(1, affinity)) * 20)::int')},"
            f"'affinity_negative', {_state('round(greatest(0, least(1, -affinity)) * 20)::int')},"
            f"'trust_positive', {_state('round(greatest(0, least(1, trust)) * 20)::int')},"
            f"'trust_negative', {_state('0')},"
            f"'importance', {_state('round(greatest(0, least(1, importance)) * 20)::int')}"
            ")"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE group_relationships SET lfu_state=jsonb_build_object("
            f"'familiarity', {_state('round(greatest(0, least(1, familiarity)) * 20)::int')},"
            f"'belonging', {_state('round(greatest(0, least(1, belonging)) * 20)::int')},"
            f"'affinity_positive', {_state('round(greatest(0, least(1, affinity)) * 20)::int')},"
            f"'affinity_negative', {_state('round(greatest(0, least(1, -affinity)) * 20)::int')},"
            f"'activity_positive', {_state('round(greatest(0, least(1, activity_willingness)) * 20)::int')},"
            f"'activity_negative', {_state('0')}"
            ")"
        )
    )
    connection.execute(
        sa.text(
            f"UPDATE memories SET lfu_state={_state('round(greatest(0, least(1, strength)) * 20)::int')}"
        )
    )
    connection.execute(sa.text(f"UPDATE memory_atoms SET lfu_state={_state('10')}"))
    connection.execute(sa.text(f"UPDATE memory_documents SET lfu_state={_state('10')}"))

    if not sa.inspect(connection).has_table("person_mention_frequencies"):
        op.create_table(
            "person_mention_frequencies",
            sa.Column("person_mention_frequency_id", sa.BigInteger(), nullable=False),
            sa.Column("normalized_mention", sa.Text(), nullable=False),
            sa.Column("person_id", sa.BigInteger(), nullable=False),
            sa.Column("scope_type", sa.Text(), nullable=False),
            sa.Column("scope_id", sa.Text(), nullable=False, server_default=""),
            sa.Column("lfu_state", postgresql.JSONB(), nullable=False, server_default=empty_state),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("person_mention_frequency_id"),
            sa.UniqueConstraint(
                "normalized_mention",
                "person_id",
                "scope_type",
                "scope_id",
                name="uq_person_mention_frequencies_scope",
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_mention_frequencies_lookup "
        "ON person_mention_frequencies (normalized_mention, scope_type, scope_id)"
    )
    connection.execute(
        sa.text(
            "INSERT INTO person_mention_frequencies ("
            "person_mention_frequency_id, normalized_mention, person_id, scope_type, scope_id, lfu_state"
            ") SELECT -row_number() OVER (), normalized_mention, person_id, scope_type, scope_id, "
            f"{_state('least(8, count(*))::int')} FROM person_mentions "
            "GROUP BY normalized_mention, person_id, scope_type, scope_id "
            "ON CONFLICT (normalized_mention, person_id, scope_type, scope_id) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_index("idx_person_mention_frequencies_lookup", table_name="person_mention_frequencies")
    op.drop_table("person_mention_frequencies")
    op.drop_column("memory_documents", "lfu_state")
    op.drop_column("memory_atoms", "consolidated_at")
    op.drop_column("memory_atoms", "lfu_state")
    op.drop_column("memories", "lfu_state")
    op.drop_column("group_relationships", "lfu_state")
    op.drop_column("person_relationships", "lfu_state")
