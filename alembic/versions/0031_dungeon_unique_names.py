"""Replace repeating dungeon names with unique names per act and type.

Revision ID: 0031_dungeon_unique_names
Revises: 0030_monster_slug_images
Create Date: 2026-03-19

Названия больше не повторяются между актами. По типам: пещера/лес/руины/склеп/бездна.
Чем выше акт — тем мрачнее и серьёзнее название.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0031_dungeon_unique_names"
down_revision: Union[str, None] = "0030_monster_slug_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (act, dungeon_number) -> unique name. dungeon_number 1=cave, 2=forest, 3=ruins, 4=crypt, 5=abyss.
DUNGEON_NAMES = {
    (1, 1): "Тёмная пещера",
    (1, 2): "Опушечная чаща",
    (1, 3): "Заброшенные руины",
    (1, 4): "Старый склеп",
    (1, 5): "Глубокая расщелина",
    (2, 1): "Пещеры Гримлоу",
    (2, 2): "Лес Шепчущих Деревьев",
    (2, 3): "Руины Чёрного Креста",
    (2, 4): "Погреб Забытых",
    (2, 5): "Ущелье Теней",
    (3, 1): "Лабиринт Нор",
    (3, 2): "Дремучий Бор",
    (3, 3): "Цитадель Обломков",
    (3, 4): "Некрополь Мёртвых",
    (3, 5): "Пропасть Стихий",
    (4, 1): "Вулканические Гроты",
    (4, 2): "Лес Костей",
    (4, 3): "Проклятый Обелиск",
    (4, 4): "Гробница Лича",
    (4, 5): "Бездна Пламени",
    (5, 1): "Сердце Горы",
    (5, 2): "Гибельная Чаща",
    (5, 3): "Трон Руин",
    (5, 4): "Чертоги Вечности",
    (5, 5): "Врата Ада",
}


def upgrade() -> None:
    import sqlalchemy as sa
    conn = op.get_bind()
    for (act, num), name in DUNGEON_NAMES.items():
        conn.execute(
            sa.text(
                "UPDATE dungeons SET name = :name "
                "WHERE act = :act AND dungeon_number = :num AND dungeon_type = 1"
            ).bindparams(name=name, act=act, num=num),
        )


def downgrade() -> None:
    import sqlalchemy as sa
    # Restore original pattern: "Акт N — {loc} {num}"
    loc_by_num = {
        1: "Пещеры",
        2: "Лес",
        3: "Руины",
        4: "Склеп",
        5: "Бездна",
    }
    conn = op.get_bind()
    for act in range(1, 6):
        for num in range(1, 6):
            loc = loc_by_num[num]
            name = f"Акт {act} — {loc} {num}"
            conn.execute(
                sa.text(
                    "UPDATE dungeons SET name = :name "
                    "WHERE act = :act AND dungeon_number = :num AND dungeon_type = 1"
                ).bindparams(name=name, act=act, num=num),
            )
