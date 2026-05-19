"""Backfill dungeons.tags from location_type where tags is null/empty (cursor_plan_8, act 3 fix).

Revision ID: 0029_dungeon_tags_backfill
Revises: 0028_exp_slot_nullable
Create Date: 2026-03-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0029_dungeon_tags_backfill"
down_revision: Union[str, None] = "0028_exp_slot_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Проставить теги из location_type для подземелий с пустыми tags (cursor_plan_8, акт 3 и др.)
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE dungeons
            SET tags = to_jsonb(ARRAY[location_type])
            WHERE (tags IS NULL OR tags::text IN ('[]', '{}', 'null'))
              AND location_type IS NOT NULL AND trim(location_type) != ''
        """)
    )


def downgrade() -> None:
    # Не откатываем данные — откат только по версии миграции
    pass
