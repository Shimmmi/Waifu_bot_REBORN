"""Load equipped legendary bonuses from DB."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_active_legendary_bonuses(
    session: AsyncSession,
    player_id: int,
) -> list[dict[str, Any]]:
    """Return bonus rows with inventory_item_id and slot_type."""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    lb.id,
                    lb.bonus_key,
                    lb.name,
                    lb.description_tpl,
                    lb.trigger_group,
                    lb.params,
                    ii.id AS inventory_item_id,
                    ii.slot_type
                FROM inventory_items ii
                JOIN LATERAL unnest(COALESCE(ii.legendary_bonus_ids, '{}')) AS bid ON TRUE
                JOIN legendary_bonuses lb ON lb.id = bid
                WHERE ii.player_id = :pid
                  AND ii.equipment_slot BETWEEN 1 AND 6
                  AND COALESCE(ii.rarity, 0) = 5
                  AND lb.is_active = TRUE
                """
            ),
            {"pid": int(player_id)},
        )
    ).mappings().all()
    if rows:
        return [dict(r) for r in rows]

    rows2 = (
        await session.execute(
            text(
                """
                SELECT
                    lb.id,
                    lb.bonus_key,
                    lb.name,
                    lb.description_tpl,
                    lb.trigger_group,
                    lb.params,
                    ii.id AS inventory_item_id,
                    ii.slot_type
                FROM inventory_items ii
                JOIN items it ON ii.item_id = it.id
                JOIN item_base_templates ibt
                  ON ibt.name = it.name AND ibt.tier = COALESCE(ii.tier, it.tier)
                JOIN LATERAL unnest(COALESCE(ibt.legendary_bonus_ids, '{}')) AS bid ON TRUE
                JOIN legendary_bonuses lb ON lb.id = bid
                WHERE ii.player_id = :pid
                  AND ii.equipment_slot BETWEEN 1 AND 6
                  AND COALESCE(ii.rarity, 0) = 5
                  AND lb.is_active = TRUE
                """
            ),
            {"pid": int(player_id)},
        )
    ).mappings().all()
    return [dict(r) for r in rows2]


async def count_equipped_legendaries(session: AsyncSession, player_id: int) -> int:
    n = await session.scalar(
        text(
            """
            SELECT COUNT(*) FROM inventory_items
            WHERE player_id = :pid AND equipment_slot BETWEEN 1 AND 6 AND COALESCE(rarity, 0) = 5
            """
        ),
        {"pid": int(player_id)},
    )
    return int(n or 0)


async def fetch_legendary_bonus_payloads(
    session: AsyncSession,
    items: list,
) -> dict[int, list[dict[str, Any]]]:
    """Map inventory_item_id -> UI rows for unique bonuses."""
    ids: set[int] = set()
    for inv in items or []:
        if not getattr(inv, "is_legendary", False) and int(getattr(inv, "rarity", 0) or 0) < 5:
            continue
        raw = getattr(inv, "legendary_bonus_ids", None) or []
        if raw:
            ids.update(int(x) for x in raw)
    if not ids:
        return {}
    rows = (
        await session.execute(
            text(
                """
                SELECT id, bonus_key, name, description_tpl, params
                FROM legendary_bonuses
                WHERE id = ANY(:ids) AND is_active = TRUE
                """
            ),
            {"ids": list(ids)},
        )
    ).mappings().all()
    by_id = {int(r["id"]): dict(r) for r in rows}
    out: dict[int, list[dict[str, Any]]] = {}
    for inv in items or []:
        raw = getattr(inv, "legendary_bonus_ids", None) or []
        if not raw:
            continue
        payload = []
        for bid in raw:
            row = by_id.get(int(bid))
            if row:
                desc_tpl = str(row.get("description_tpl") or "")
                payload.append(
                    {
                        "id": int(row["id"]),
                        "bonus_key": row["bonus_key"],
                        "name": row["name"],
                        "description": desc_tpl,
                        "description_tpl": desc_tpl,
                        "params": row.get("params") or {},
                    }
                )
        if payload:
            out[int(inv.id)] = payload
    return out
