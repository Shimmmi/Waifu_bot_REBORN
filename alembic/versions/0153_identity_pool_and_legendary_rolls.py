"""Identity pool extras, legendary bonus snapshots, early-act legendary weights.

Revision ID: 0153_identity_pool_and_legendary_rolls
Revises: 0152_companion_memory
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0153_identity_pool_and_legendary_rolls"
down_revision: Union[str, None] = "0152_companion_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE inventory_items "
            "ADD COLUMN IF NOT EXISTS legendary_bonus_rolls JSONB"
        )
    )

    from waifu_bot.game.drop_act_weights import ACT_RARITY_WEIGHTS
    from waifu_bot.game.item_art_identities import extra_identity_seed_rows
    from waifu_bot.game.legendary_bonuses.tier_scale import roll_bonus_magnitudes

    conn = op.get_bind()

    insert_sql = sa.text(
        """
        INSERT INTO item_base_templates (
            name, item_type, subtype, attack_type, tier, level_min, level_max,
            dmg_min, dmg_max, attack_speed, armor_base, stat1_type, stat1_value,
            stat2_type, stat2_value, base_price, boss_allowed, weight, base_grade, family_key
        )
        SELECT
            CAST(:name AS varchar(128)),
            CAST(:item_type AS varchar(32)),
            CAST(:subtype AS varchar(32)),
            CAST(:attack_type AS varchar(16)),
            :tier, :level_min, :level_max,
            :dmg_min, :dmg_max, :attack_speed, :armor_base,
            CAST(:stat1_type AS varchar(8)),
            :stat1_value,
            CAST(:stat2_type AS varchar(8)),
            :stat2_value, :base_price, :boss_allowed, :weight, :base_grade,
            CAST(:family_key AS varchar(64))
        WHERE NOT EXISTS (
            SELECT 1 FROM item_base_templates x WHERE x.name = CAST(:name AS varchar(128))
        )
        """
    )
    for row in extra_identity_seed_rows():
        conn.execute(insert_sql, row)

    for act, weights in ACT_RARITY_WEIGHTS.items():
        if act > 3:
            continue
        conn.execute(
            sa.text(
                """
                UPDATE drop_rules
                SET rarity_weights = CAST(:w AS json)
                WHERE act = :act AND boss_only = TRUE
                """
            ),
            {"w": json.dumps(weights), "act": int(act)},
        )

    bonus_rows = conn.execute(sa.text("SELECT id, params FROM legendary_bonuses")).mappings().all()
    by_id: dict[int, dict] = {}
    for br in bonus_rows:
        params = br.get("params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (TypeError, ValueError, json.JSONDecodeError):
                params = {}
        if not isinstance(params, dict):
            params = {}
        by_id[int(br["id"])] = params

    items = conn.execute(
        sa.text(
            """
            SELECT id, COALESCE(tier, 1) AS tier, legendary_bonus_ids
            FROM inventory_items
            WHERE legendary_bonus_ids IS NOT NULL
              AND cardinality(legendary_bonus_ids) > 0
              AND legendary_bonus_rolls IS NULL
            """
        )
    ).mappings().all()

    upd = sa.text(
        """
        UPDATE inventory_items
        SET legendary_bonus_rolls = CAST(:rolls AS jsonb)
        WHERE id = :id
        """
    )
    for inv in items:
        rolls: dict[str, dict] = {}
        for bid in inv.get("legendary_bonus_ids") or []:
            try:
                bonus_id = int(bid)
            except (TypeError, ValueError):
                continue
            catalog = by_id.get(bonus_id) or {}
            rolls[str(bonus_id)] = roll_bonus_magnitudes(
                catalog, int(inv.get("tier") or 1), midpoint=True
            )
        conn.execute(upd, {"rolls": json.dumps(rolls, ensure_ascii=False), "id": int(inv["id"])})


def downgrade() -> None:
    from waifu_bot.game.drop_act_weights import PREV_ACT_RARITY_WEIGHTS
    from waifu_bot.game.item_art_identities import extra_identity_seed_rows

    conn = op.get_bind()
    names = [r["name"] for r in extra_identity_seed_rows() if r.get("name")]
    if names:
        conn.execute(
            sa.text(
                "DELETE FROM item_base_templates WHERE name = ANY(:names) AND COALESCE(base_grade, 0) = 0"
            ).bindparams(sa.bindparam("names", type_=ARRAY(sa.String()))),
            {"names": names},
        )
    for act, weights in PREV_ACT_RARITY_WEIGHTS.items():
        if act > 3:
            continue
        conn.execute(
            sa.text(
                """
                UPDATE drop_rules
                SET rarity_weights = CAST(:w AS json)
                WHERE act = :act AND boss_only = TRUE
                """
            ),
            {"w": json.dumps(weights), "act": int(act)},
        )
    op.execute(sa.text("ALTER TABLE inventory_items DROP COLUMN IF EXISTS legendary_bonus_rolls"))
