"""init tracks table

Revision ID: 20260315_0001
Revises:
Create Date: 2026-03-15 12:31:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracks",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False, server_default="private"),
        sa.Column("status", sa.Text(), nullable=False, server_default="processing"),
        sa.Column("raw_object_key", sa.Text(), nullable=False),
        sa.Column("processed_object_key", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("loudness_lufs", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_tracks_owner", "tracks", ["owner_id"])
    op.create_index("idx_tracks_status", "tracks", ["status"])


def downgrade() -> None:
    op.drop_index("idx_tracks_status", table_name="tracks")
    op.drop_index("idx_tracks_owner", table_name="tracks")
    op.drop_table("tracks")
