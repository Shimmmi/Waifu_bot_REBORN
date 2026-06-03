"""Rebalance dismantle dust: geometric rarity/tier, no enchant bonus.

Revision ID: 0094_dismantle_dust_rebalance
Revises: 0093_item_base_flavor_ru
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0094_dismantle_dust_rebalance"
down_revision: Union[str, None] = "0093_item_base_flavor_ru"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONFIG_UPDATES: list[tuple[str, str]] = [
    ("dismantle.rarity_mult_1", "1.0"),
    ("dismantle.rarity_mult_2", "1.78"),
    ("dismantle.rarity_mult_3", "3.16"),
    ("dismantle.rarity_mult_4", "5.62"),
    ("dismantle.rarity_mult_5", "10.0"),
    ("dismantle.tier_mult", "1.20"),
    ("dismantle.enchant_plus_mult", "0"),
]

_CONFIG_DOWNGRADE: list[tuple[str, str]] = [
    ("dismantle.rarity_mult_1", "1.0"),
    ("dismantle.rarity_mult_2", "1.3"),
    ("dismantle.rarity_mult_3", "1.7"),
    ("dismantle.rarity_mult_4", "2.2"),
    ("dismantle.rarity_mult_5", "3.0"),
    ("dismantle.tier_mult", "1.08"),
    ("dismantle.enchant_plus_mult", "0.12"),
]


def _apply_updates(updates: list[tuple[str, str]]) -> None:
    conn = op.get_bind()
    for key, val in updates:
        conn.execute(
            sa.text("UPDATE game_config SET value = :val WHERE key = :key"),
            {"key": key, "val": val},
        )


def upgrade() -> None:
    _apply_updates(_CONFIG_UPDATES)


def downgrade() -> None:
    _apply_updates(_CONFIG_DOWNGRADE)
