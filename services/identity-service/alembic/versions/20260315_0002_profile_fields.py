"""add username and bio fields

Revision ID: 20260315_0002
Revises: 20260315_0001
Create Date: 2026-03-15 13:10:00
"""

from alembic import op


revision = "20260315_0002"
down_revision = "20260315_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique
        ON users (LOWER(username))
        WHERE username IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_username_unique")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS bio")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS username")
