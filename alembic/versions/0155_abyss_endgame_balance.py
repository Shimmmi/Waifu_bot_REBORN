"""Seed Abyss endgame HP/reflect/RAGE/checkpoint-heal config.

Revision ID: 0155_abyss_endgame_balance
Revises: 0154_elite_reflect_max_hp
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0155_abyss_endgame_balance"
down_revision: Union[str, None] = "0154_elite_reflect_max_hp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEYS: list[tuple[str, str, str]] = [
    (
        "abyss_hp_piecewise",
        "1",
        "1 = piecewise HP/DMG anchors (F1–F100+); 0 = legacy linear/exp scale",
    ),
    (
        "abyss_modifier_rage_hp",
        "1.5",
        "RAGE: множитель HP монстра (входящий урон без множителя)",
    ),
    (
        "abyss_checkpoint_heal_missing_pct",
        "0.75",
        "Доля недостающего HP, восстанавливаемая на чекпоинте (KO не лечит)",
    ),
    (
        "abyss_reflect_max_hp_frac",
        "0.10",
        "Кап рефлекта за прок: доля max HP ОВ",
    ),
    (
        "abyss_reflect_max_procs_per_fight",
        "3",
        "Максимум проков рефлекта за бой (SPLIT/UNDYING не сбрасывают)",
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for key, value, desc in _KEYS:
        conn.execute(
            sa.text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "v": value, "d": desc},
        )


def downgrade() -> None:
    keys = ", ".join(f"'{k}'" for k, _v, _d in _KEYS)
    op.execute(sa.text(f"DELETE FROM game_config WHERE key IN ({keys})"))
