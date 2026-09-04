"""Load equipped legendary bonuses from DB."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.game.legendary_bonuses.describe import format_legendary_description
from waifu_bot.game.legendary_bonuses.tier_scale import deep_merge, roll_bonus_magnitudes


def _rolls_map(raw: Any) -> dict[str, dict]:
    if isinstance(raw, dict):
        return {str(k): (v if isinstance(v, dict) else {}) for k, v in raw.items()}
    return {}


def _overlay_for(
    catalog: dict[str, Any],
    rolls: dict[str, dict],
    bonus_id: int,
    tier: int | None,
) -> dict[str, Any]:
    key = str(int(bonus_id))
    if key in rolls:
        overlay = rolls[key]
        return overlay if isinstance(overlay, dict) else {}
    if tier is None:
        return {}
    return roll_bonus_magnitudes(catalog, int(tier), midpoint=True)


def _merge_row_params(
    row: dict[str, Any],
    rolls: dict[str, dict],
    bonus_id: int,
    *,
    tier: int | None = None,
) -> dict[str, Any]:
    catalog = dict(row.get("params") or {})
    overlay = _overlay_for(catalog, rolls, bonus_id, tier)
    return deep_merge(catalog, overlay)


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
                    ii.slot_type,
                    ii.legendary_bonus_rolls,
                    ii.tier AS item_tier
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
        out = []
        for r in rows:
            row = dict(r)
            rolls = _rolls_map(row.pop("legendary_bonus_rolls", None))
            bid = int(row["id"])
            try:
                item_tier = int(row.get("item_tier") or 1)
            except (TypeError, ValueError):
                item_tier = 1
            row["params"] = _merge_row_params(row, rolls, bid, tier=item_tier)
            out.append(row)
        return out

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
                    ii.slot_type,
                    ii.legendary_bonus_rolls,
                    ii.tier AS item_tier
                FROM inventory_items ii
                JOIN items it ON ii.item_id = it.id
                JOIN item_base_templates ibt
                  ON ibt.name = it.name AND COALESCE(ibt.base_grade, 0) = 0
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
    out = []
    for r in rows2:
        row = dict(r)
        rolls = _rolls_map(row.pop("legendary_bonus_rolls", None))
        bid = int(row["id"])
        try:
            item_tier = int(row.get("item_tier") or 1)
        except (TypeError, ValueError):
            item_tier = 1
        row["params"] = _merge_row_params(row, rolls, bid, tier=item_tier)
        out.append(row)
    return out


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
        rolls = _rolls_map(getattr(inv, "legendary_bonus_rolls", None))
        try:
            item_tier = int(getattr(inv, "tier", None) or 1)
        except (TypeError, ValueError):
            item_tier = 1
        payload = []
        for bid in raw:
            row = by_id.get(int(bid))
            if row:
                merged = _merge_row_params(row, rolls, int(bid), tier=item_tier)
                desc_tpl = str(row.get("description_tpl") or "")
                desc = format_legendary_description(desc_tpl, merged)
                payload.append(
                    {
                        "id": int(row["id"]),
                        "bonus_key": row["bonus_key"],
                        "name": row["name"],
                        "description": desc,
                        "description_tpl": desc_tpl,
                        "params": merged,
                    }
                )
        if payload:
            out[int(inv.id)] = payload
    return out
