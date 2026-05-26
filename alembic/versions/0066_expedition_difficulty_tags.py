"""Expedition difficulty tags v1.4: affix tags, slot cache, active snapshot.

Revision ID: 0066_expedition_difficulty_tags
Revises: 0065_expedition_paired_perks_canonical
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0066_expedition_difficulty_tags"
down_revision: Union[str, None] = "0065_expedition_paired_perks_canonical"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# name → tag ids (must match expedition_difficulty_tags.DB_AFFIX_NAME_TAGS)
AFFIX_TAG_SEED: dict[str, list[str]] = {
    "Огненная": ["elements"],
    "Ледяная": ["elements"],
    "Ядовитая": ["elements"],
    "Проклятая": ["dark_magic", "curses"],
    "Тёмная": ["dark_magic", "curses"],
    "Заброшенная": ["traps"],
    "Древняя": ["knowledge", "social"],
    "Туманная": ["traps"],
    "Затопленная": ["elements"],
    "Горящая": ["elements"],
    "с гоблинами": ["monsters"],
    "с разбойниками": ["monsters"],
    "с пауками": ["monsters"],
    "со змеями": ["monsters"],
    "с нежитью": ["monsters", "undead"],
    "с демонами": ["monsters", "dark_magic"],
    "с ловушками": ["traps"],
    "с огненными реками": ["traps", "elements"],
    "с призраками": ["monsters", "undead"],
    "с охраной": ["monsters"],
    "с головоломками": ["traps", "knowledge"],
    "с сокровищами": ["knowledge", "social"],
}


def upgrade() -> None:
    op.add_column(
        "expedition_affixes",
        sa.Column("difficulty_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "expedition_slots",
        sa.Column("difficulty_tags", sa.JSON(), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("difficulty_tags_snapshot", sa.JSON(), nullable=True),
    )

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM expedition_affixes")).fetchall()
    for rid, name in rows:
        tags = AFFIX_TAG_SEED.get((name or "").strip(), ["monsters"])
        conn.execute(
            sa.text("UPDATE expedition_affixes SET difficulty_tags = CAST(:j AS JSON) WHERE id = :id"),
            {"j": json.dumps(tags), "id": rid},
        )


def downgrade() -> None:
    op.drop_column("active_expeditions", "difficulty_tags_snapshot")
    op.drop_column("expedition_slots", "difficulty_tags")
    op.drop_column("expedition_affixes", "difficulty_tags")
