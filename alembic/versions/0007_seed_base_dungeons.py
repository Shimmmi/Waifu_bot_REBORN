"""seed base dungeons (act 1-5, dungeon 1-5, SOLO)

Revision ID: 0007_seed_base_dungeons
Revises: 0006_seed_dungeon_content
Create Date: 2026-01-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_seed_base_dungeons"
down_revision: Union[str, None] = "0006_seed_dungeon_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This project historically relied on out-of-band scripts (scripts/seed_dungeons.py)
    # to insert rows into `dungeons`. If prod DB was recreated or the script wasn't run,
    # the game has no dungeons even though pools/templates exist.
    loc_by_num = {
        1: ("cave", "Пещеры"),
        2: ("forest", "Лес"),
        3: ("ruins", "Руины"),
        4: ("crypt", "Склеп"),
        5: ("abyss", "Бездна"),
    }

    conn = op.get_bind()

    for act in range(1, 6):
        for num in range(1, 6):
            loc, loc_title = loc_by_num[num]
            level = (act - 1) * 10 + (num - 1) * 2 + 1  # 1,3,5,7,9... per act baseline
            diff = 80 + (act - 1) * 60 + (num - 1) * 20
            omin = 5 + (act - 1) + (num - 1)
            omax = omin + 3

            name = f"Акт {act} — {loc_title} {num}"
            desc = f"Базовый данж (акт {act}, #{num})."

            conn.execute(
                sa.text(
                    """
                    INSERT INTO dungeons
                      (name, description, act, dungeon_number, dungeon_type, level,
                       location_type, difficulty, obstacle_count, obstacle_min, obstacle_max,
                       base_experience, base_gold, created_at)
                    SELECT
                      :name, :desc, :act, :num, 1, :level,
                      :loc, :diff, :obstacle_count, :omin, :omax,
                      0, 0, CURRENT_TIMESTAMP
                    WHERE NOT EXISTS (
                      SELECT 1 FROM dungeons
                      WHERE act = :act AND dungeon_number = :num AND dungeon_type = 1
                    )
                    """
                ).bindparams(
                    name=name,
                    desc=desc,
                    act=act,
                    num=num,
                    level=level,
                    loc=loc,
                    diff=diff,
                    obstacle_count=omin,
                    omin=omin,
                    omax=omax,
                )
            )


def downgrade() -> None:
    # Remove only our seeded SOLO dungeons (keep user-created/custom content)
    op.execute(
        sa.text(
            """
            DELETE FROM dungeons
            WHERE dungeon_type = 1
              AND act BETWEEN 1 AND 5
              AND dungeon_number BETWEEN 1 AND 5
              AND description LIKE 'Базовый данж (акт %'
            """
        )
    )

