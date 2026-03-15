"""add external source fields for imported tracks

Revision ID: 20260315_0003
Revises: 20260315_0002
Create Date: 2026-03-15 14:25:00
"""

from alembic import op


revision = "20260315_0003"
down_revision = "20260315_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'local'")
    op.execute("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS source_track_id TEXT")
    op.execute("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS source_url TEXT")
    op.execute("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS artwork_url TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tracks_source ON tracks (source)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_source_track_unique
        ON tracks (owner_id, source, source_track_id)
        WHERE source_track_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tracks_source_track_unique")
    op.execute("DROP INDEX IF EXISTS idx_tracks_source")
    op.execute("ALTER TABLE tracks DROP COLUMN IF EXISTS artwork_url")
    op.execute("ALTER TABLE tracks DROP COLUMN IF EXISTS source_url")
    op.execute("ALTER TABLE tracks DROP COLUMN IF EXISTS source_track_id")
    op.execute("ALTER TABLE tracks DROP COLUMN IF EXISTS source")
