"""GD v1: 15-минутные этапы + конфиг мульти-циклового раунда.

Revision ID: 0085_gd_15min_round
Revises: 0084_shop_offers_per_player
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0085_gd_15min_round"
down_revision: Union[str, None] = "0084_shop_offers_per_player"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Новые ключи конфигурации (вставляются, если отсутствуют).
NEW_CONFIG_SEED: list[tuple[str, str, str]] = [
    ("gd_registration_window_minutes", "15", "GD v1 окно регистрации от первого /gd_join (мин)"),
    ("gd_round_cycle_cap", "8", "GD v1 макс. число циклов реплея в одном раунде"),
    ("gd_max_actions_per_round", "8", "GD v1 макс. отдельных действий игрока за раунд (анти-спам)"),
    ("gd_series_window_seconds", "8", "GD v1 окно склейки сообщений одного типа в серию (сек)"),
]


def upgrade() -> None:
    conn = op.get_bind()
    # Раунд: 30 -> 15 минут (обновляем существующее значение).
    conn.execute(
        sa.text("UPDATE game_config SET value = '15' WHERE key = 'gd_round_duration_minutes'")
    )
    for key, val, desc in NEW_CONFIG_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO game_config (key, value, description)
                VALUES (:k, :v, :d)
                ON CONFLICT (key) DO NOTHING"""
            ),
            {"k": key, "v": val, "d": desc},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE game_config SET value = '30' WHERE key = 'gd_round_duration_minutes'")
    )
    for key, _val, _desc in NEW_CONFIG_SEED:
        conn.execute(sa.text("DELETE FROM game_config WHERE key = :k"), {"k": key})
