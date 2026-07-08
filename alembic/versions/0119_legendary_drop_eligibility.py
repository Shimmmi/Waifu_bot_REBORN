"""Legendary drop eligibility columns + clear template-bound bonus ids.

Revision ID: 0119_legendary_drop_eligibility
Revises: 0118_player_solo_dungeon_auto_prefs
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0119_legendary_drop_eligibility"
down_revision: Union[str, None] = "0118_player_solo_dungeon_auto_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "legendary_bonuses",
        sa.Column("min_item_tier", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "legendary_bonuses",
        sa.Column("max_item_tier", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "legendary_bonuses",
        sa.Column(
            "allowed_slot_types",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
            server_default="{weapon_1h,weapon_2h,offhand,costume,ring,amulet}",
        ),
    )
    op.add_column(
        "legendary_bonuses",
        sa.Column("is_drop_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )

    from waifu_bot.game.legendary_bonuses.eligibility import derive_drop_eligibility

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, bonus_key, trigger_group, params, is_active
            FROM legendary_bonuses
            """
        )
    ).mappings().all()

    for row in rows:
        bonus = dict(row)
        elig = derive_drop_eligibility(bonus)
        conn.execute(
            sa.text(
                """
                UPDATE legendary_bonuses
                SET min_item_tier = :min_item_tier,
                    max_item_tier = :max_item_tier,
                    allowed_slot_types = :allowed_slot_types,
                    is_drop_enabled = :is_drop_enabled
                WHERE id = :id
                """
            ),
            {
                "id": int(bonus["id"]),
                "min_item_tier": int(elig["min_item_tier"]),
                "max_item_tier": int(elig["max_item_tier"]),
                "allowed_slot_types": list(elig["allowed_slot_types"]),
                "is_drop_enabled": bool(elig["is_drop_enabled"]),
            },
        )

    conn.execute(
        sa.text(
            """
            UPDATE item_base_templates
            SET legendary_bonus_ids = '{}'
            WHERE COALESCE(base_grade, 0) = 0
            """
        )
    )


def downgrade() -> None:
    op.drop_column("legendary_bonuses", "is_drop_enabled")
    op.drop_column("legendary_bonuses", "allowed_slot_types")
    op.drop_column("legendary_bonuses", "max_item_tier")
    op.drop_column("legendary_bonuses", "min_item_tier")
