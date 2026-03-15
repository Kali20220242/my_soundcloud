"""upload service baseline revision

Revision ID: 20260315_0001
Revises:
Create Date: 2026-03-15 12:33:00
"""

from alembic import op


revision = "20260315_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upload service currently has no SQL schema.
    pass


def downgrade() -> None:
    pass
