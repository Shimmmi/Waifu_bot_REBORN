"""Curated legendary item_base_templates with unique bonus ids.

Revision ID: 0092_legendary_curated_templates
Revises: 0091_legendary_bonuses_core
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0092_legendary_curated_templates"
down_revision: Union[str, None] = "0091_legendary_bonuses_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (template name, tier, [bonus_key, ...])
_CURATED: list[tuple[str, int, list[str]]] = [
    ("Экскалибур", 10, ["BOSS_SLAYER", "SNIPER_SHOT"]),
    ("Теневое жало", 10, ["MYSTIC_SEVEN", "QUICK_REFLEX"]),
    ("Звёздный лук", 10, ["TYPE_HUNTER", "HUNT_FRENZY"]),
    ("Топор бури", 10, ["WOUND_FURY", "BREAKTHROUGH"]),
    ("Рунный меч", 9, ["GOLD_PULSE", "AFFIX_MASTERY"]),
    ("Серебряная дуга", 9, ["IMMUNITY_BREAKER", "REVENGE_THIRST"]),
    ("Мистерикл", 8, ["PIERCING_SCREAM", "VERBOSITY"]),
    ("Кольцо вечности", 10, ["SURVIVOR_SPIRIT", "RARITY_SYNERGY"]),
    ("Медальон стражника", 5, ["MORNING_RITUAL", "FIRST_DAILY_DUNGEON"]),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name, tier, keys in _CURATED:
        ids = []
        for key in keys:
            row = conn.execute(
                sa.text("SELECT id FROM legendary_bonuses WHERE bonus_key = :k"),
                {"k": key},
            ).fetchone()
            if row:
                ids.append(int(row[0]))
        if not ids:
            continue
        conn.execute(
            sa.text(
                """
                UPDATE item_base_templates
                SET legendary_bonus_ids = :ids
                WHERE name = :name AND tier = :tier
                """
            ),
            {"ids": ids, "name": name, "tier": tier},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name, tier, _ in _CURATED:
        conn.execute(
            sa.text(
                """
                UPDATE item_base_templates
                SET legendary_bonus_ids = '{}'
                WHERE name = :name AND tier = :tier
                """
            ),
            {"name": name, "tier": tier},
        )
