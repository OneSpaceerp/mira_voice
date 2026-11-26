"""Index of calls in progress (task 1.3)

The ARI event worker looks up the calls with no end time after every (re)connect, to close
the ones that ended while it was not listening.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_calls_open", "calls", ["tenant_id"], postgresql_where=sa.text("ended_at IS NULL")
    )


def downgrade() -> None:
    op.drop_index("ix_calls_open", table_name="calls")
