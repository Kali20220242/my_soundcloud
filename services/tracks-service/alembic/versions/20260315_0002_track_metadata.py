"""add track metadata and counters

Revision ID: 20260315_0002
Revises: 20260315_0001
Create Date: 2026-03-15 13:11:00
"""

from alembic import op


revision = "20260315_0002"
down_revision = "20260315_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS description TEXT")
    op.execute("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS genre TEXT")
    op.execute("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS plays_count INTEGER NOT NULL DEFAULT 0")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tracks_visibility ON tracks (visibility)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tracks_created ON tracks (created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tracks_created")
    op.execute("DROP INDEX IF EXISTS idx_tracks_visibility")
    op.execute("ALTER TABLE tracks DROP COLUMN IF EXISTS plays_count")
    op.execute("ALTER TABLE tracks DROP COLUMN IF EXISTS genre")
    op.execute("ALTER TABLE tracks DROP COLUMN IF EXISTS description")
