"""Normalize drill_manuals to nested T1/T2/T3 wallet; points→T1 is runtime.

Revision ID: 0130_drill_manuals_tier_wallet
Revises: 0129_merc_overhaul_v7
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0130_drill_manuals_tier_wallet"
down_revision: Union[str, None] = "0129_merc_overhaul_v7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MANUAL_TYPES = ("ATK", "DEF", "SUP")


def _normalize(raw: Any) -> dict[str, dict[str, int]]:
    out = {t: {"t1": 0, "t2": 0, "t3": 0} for t in MANUAL_TYPES}
    if not isinstance(raw, dict):
        return out
    for ptype in MANUAL_TYPES:
        val = raw.get(ptype)
        if isinstance(val, dict):
            out[ptype] = {
                "t1": max(0, int(val.get("t1", 0) or 0)),
                "t2": max(0, int(val.get("t2", 0) or 0)),
                "t3": max(0, int(val.get("t3", 0) or 0)),
            }
        elif val is not None:
            out[ptype]["t2"] = max(0, int(val or 0))
    return out


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT player_id, drill_manuals FROM tavern_states")).fetchall()
    for player_id, manuals in rows:
        if isinstance(manuals, str):
            try:
                manuals = json.loads(manuals)
            except Exception:
                manuals = {}
        norm = _normalize(manuals)
        # Fold leftover perk_upgrade_points into T1 ATK (type refined at runtime per unit)
        pts = conn.execute(
            sa.text(
                "SELECT COALESCE(SUM(perk_upgrade_points), 0) FROM hired_waifus WHERE player_id = :pid"
            ),
            {"pid": player_id},
        ).scalar()
        pts_i = int(pts or 0)
        if pts_i > 0:
            norm["ATK"]["t1"] = int(norm["ATK"]["t1"]) + pts_i
            conn.execute(
                sa.text("UPDATE hired_waifus SET perk_upgrade_points = 0 WHERE player_id = :pid"),
                {"pid": player_id},
            )
        conn.execute(
            sa.text("UPDATE tavern_states SET drill_manuals = CAST(:m AS json) WHERE player_id = :pid"),
            {"m": json.dumps(norm), "pid": player_id},
        )


def downgrade() -> None:
    # Flatten nested wallet back to legacy T2-only ints (lossy for T1/T3).
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT player_id, drill_manuals FROM tavern_states")).fetchall()
    for player_id, manuals in rows:
        if isinstance(manuals, str):
            try:
                manuals = json.loads(manuals)
            except Exception:
                manuals = {}
        flat: dict[str, int] = {}
        if isinstance(manuals, dict):
            for ptype in MANUAL_TYPES:
                val = manuals.get(ptype)
                if isinstance(val, dict):
                    flat[ptype] = max(0, int(val.get("t2", 0) or 0))
                elif val is not None:
                    flat[ptype] = max(0, int(val or 0))
        conn.execute(
            sa.text("UPDATE tavern_states SET drill_manuals = CAST(:m AS json) WHERE player_id = :pid"),
            {"m": json.dumps(flat), "pid": player_id},
        )
