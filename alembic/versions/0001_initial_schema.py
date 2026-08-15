"""初始雪花ID表结构

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-15

"""
from alembic import op

from shared.infrastructure import models as m

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    m.Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    m.Base.metadata.drop_all(bind=op.get_bind())
