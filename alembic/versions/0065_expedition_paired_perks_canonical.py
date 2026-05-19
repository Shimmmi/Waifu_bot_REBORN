"""Normalize expedition_affixes/slots paired_perks to canonical PERKS ids.

Revision ID: 0065_expedition_paired_perks_canonical
Revises: 0064_monster_power_and_abilities
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0065_expedition_paired_perks_canonical"
down_revision: Union[str, None] = "0064_monster_power_and_abilities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from waifu_bot.game.expedition_perk_resolve import normalize_expedition_paired_perk_ids

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, paired_perks FROM expedition_affixes")).fetchall()
    for rid, pp in rows:
        new_pp = normalize_expedition_paired_perk_ids(pp or [])
        conn.execute(
            sa.text("UPDATE expedition_affixes SET paired_perks = CAST(:j AS JSON) WHERE id = :id"),
            {"j": json.dumps(new_pp), "id": rid},
        )

    srows = conn.execute(
        sa.text("SELECT id, paired_perks FROM expedition_slots WHERE paired_perks IS NOT NULL")
    ).fetchall()
    for sid, pp in srows:
        new_pp = normalize_expedition_paired_perk_ids(pp or [])
        conn.execute(
            sa.text("UPDATE expedition_slots SET paired_perks = CAST(:j AS JSON) WHERE id = :id"),
            {"j": json.dumps(new_pp), "id": sid},
        )


def downgrade() -> None:
    pass
