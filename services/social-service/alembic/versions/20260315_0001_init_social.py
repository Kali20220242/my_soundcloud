"""init social tables

Revision ID: 20260315_0001
Revises:
Create Date: 2026-03-15 12:32:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "likes",
        sa.Column("track_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("track_id", "user_id"),
    )

    op.create_table(
        "comments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("track_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "follows",
        sa.Column("follower_id", sa.Text(), nullable=False),
        sa.Column("target_user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("follower_id", "target_user_id"),
    )


def downgrade() -> None:
    op.drop_table("follows")
    op.drop_table("comments")
    op.drop_table("likes")
