"""dungeon meta + rewards + progress fields

Revision ID: 0004_dungeon_meta_rewards
Revises: c7bbbbf4bd20
Create Date: 2026-01-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_dungeon_meta_rewards"
down_revision: Union[str, None] = "c7bbbbf4bd20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # dungeons: add richer metadata for UI + generation
    op.add_column(
        "dungeons",
        sa.Column("location_type", sa.String(length=32), nullable=False, server_default="dungeon"),
    )
    op.add_column(
        "dungeons",
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )
    op.add_column(
        "dungeons",
        sa.Column("obstacle_min", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "dungeons",
        sa.Column("obstacle_max", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    # Backfill: keep existing behavior (fixed obstacle_count)
    op.execute("UPDATE dungeons SET obstacle_min = obstacle_count, obstacle_max = obstacle_count")

    # monsters: add gold reward + boss marker + difficulty score
    op.add_column(
        "monsters",
        sa.Column("gold_reward", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "monsters",
        sa.Column("is_boss", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "monsters",
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    # dungeon progress: richer progress info for UI and logic
    op.add_column(
        "dungeon_progress",
        sa.Column("total_monsters", sa.Integer(), nullable=True),
    )
    op.add_column(
        "dungeon_progress",
        sa.Column("total_damage_dealt", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("dungeon_progress", "total_damage_dealt")
    op.drop_column("dungeon_progress", "total_monsters")
    op.drop_column("monsters", "difficulty")
    op.drop_column("monsters", "is_boss")
    op.drop_column("monsters", "gold_reward")
    op.drop_column("dungeons", "obstacle_max")
    op.drop_column("dungeons", "obstacle_min")
    op.drop_column("dungeons", "difficulty")
    op.drop_column("dungeons", "location_type")

