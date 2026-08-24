"""保留已上线的 UUID 到雪花 ID 迁移版本号。

Revision ID: 0002_uuid_to_snowflake
Revises: 0001_initial

生产库已经执行过原始迁移。当前 0001 是合并后的新库基线，因此这里仅保留
历史版本链，避免把已经位于 0002 的生产库错误地重新 stamp 到 0001。
"""

revision = "0002_uuid_to_snowflake"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
