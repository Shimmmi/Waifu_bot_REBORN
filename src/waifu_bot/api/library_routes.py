"""Library / Codex API: the monster bestiary (pokedex).

Returns the full monster catalog joined with the player's per-monster discovery
progress. Information is *redacted on the server* based on the discovery tier so
the payload itself never leaks hidden stats (anti-datamining).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db import models as m
from waifu_bot.game import bestiary as bcfg

logger = logging.getLogger(__name__)

router = APIRouter()

_HIDDEN_NAME = "???"
_HIDDEN_TYPE = "???"


def _tier_catalog() -> list[dict]:
    """Public description of every discovery tier (for the UI legend)."""
    out: list[dict] = []
    for t in bcfg.BESTIARY_TIERS:
        bonuses: list[str] = []
        if t.exp_pct:
            bonuses.append(f"+{round(t.exp_pct * 100)}% опыта")
        if t.gold_pct:
            bonuses.append(f"+{round(t.gold_pct * 100)}% золота")
        if t.dmg_pct:
            bonuses.append(f"+{round(t.dmg_pct * 100)}% урона")
        if t.dmg_taken_pct:
            bonuses.append(f"{round(t.dmg_taken_pct * 100)}% получаемого урона")
        reveals: list[str] = []
        if t.reveals_name:
            reveals.append("имя")
        if t.reveals_hp:
            reveals.append("HP")
        if t.reveals_type:
            reveals.append("тип")
        if t.reveals_damage:
            reveals.append("урон")
        if t.reveals_rewards:
            reveals.append("награды")
        if t.reveals_abilities:
            reveals.append("способности")
        if t.reveals_lore:
            reveals.append("лор")
        out.append(
            {
                "tier": t.tier,
                "kills_required": t.kills_required,
                "name": t.name,
                "bonuses": bonuses,
                "reveals": reveals,
                "title": t.title,
            }
        )
    return out


def _build_entry(tmpl: m.MonsterTemplate, kills: int, seen: bool, *, detailed: bool) -> dict:
    """Build a redacted bestiary entry for one template + player progress."""
    tier = bcfg.tier_for_kills(kills)
    reveal = bcfg.reveal_flags_for_tier(tier)
    bonuses = bcfg.cumulative_bonuses_for_tier(tier)
    next_threshold = bcfg.next_tier_threshold(kills)
    tier_def = bcfg.get_tier_def(tier)

    name = tmpl.name if reveal["name"] else _HIDDEN_NAME
    family = (tmpl.family or "") if reveal["type"] else None

    entry: dict = {
        "template_id": tmpl.id,
        "tier": tier,
        "tier_name": tier_def.name,
        "max_tier": bcfg.MAX_TIER,
        "kills": int(kills),
        "seen": bool(seen),
        "name": name,
        "name_known": reveal["name"],
        # Image hints: family/slug/monster-tier are needed to render art. These are
        # gated by "seen" (the monster has appeared in front of the player), not by
        # kill-tier: once encountered we show the real art, before that a silhouette.
        "family": (tmpl.family or "unknown") if seen else None,
        "slug": tmpl.slug if seen else None,
        "monster_tier": tmpl.tier,
        "has_image": bool(tmpl.has_image) if seen else False,
        "image_updated_at": (
            tmpl.image_updated_at.isoformat()
            if (seen and tmpl.image_updated_at)
            else None
        ),
        "emoji": tmpl.emoji if seen else None,
        # Where the monster can be found (always available for filtering/goals).
        "act_min": tmpl.act_min,
        "act_max": tmpl.act_max,
        # Progress to the next tier.
        "next_tier_kills": next_threshold,
        # Active per-monster bonuses at the current tier.
        "bonuses": {
            "dmg_pct": bonuses.dmg_pct,
            "dmg_taken_pct": bonuses.dmg_taken_pct,
            "exp_pct": bonuses.exp_pct,
            "gold_pct": bonuses.gold_pct,
        },
    }

    # Type/family text label (revealed at tier 3).
    entry["type"] = family if reveal["type"] else (_HIDDEN_TYPE if seen else None)

    # Stat curves are only revealed at the relevant tiers.
    if reveal["hp"]:
        entry["hp_base"] = tmpl.hp_base
        entry["hp_per_level"] = tmpl.hp_per_level
    if reveal["damage"]:
        entry["dmg_base"] = tmpl.dmg_base
        entry["dmg_per_level"] = tmpl.dmg_per_level
    if reveal["rewards"]:
        entry["exp_base"] = tmpl.exp_base
        entry["exp_per_level"] = tmpl.exp_per_level
        entry["gold_base"] = tmpl.gold_base
        entry["gold_per_level"] = tmpl.gold_per_level
        entry["level_min"] = tmpl.level_min
        entry["level_max"] = tmpl.level_max

    if detailed and reveal["lore"]:
        entry["lore_known"] = True

    return entry


@router.get("/library/bestiary", tags=["library"])
async def bestiary_catalog(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Full monster catalog with the player's (redacted) discovery progress."""
    try:
        templates = list(
            (await session.execute(select(m.MonsterTemplate))).scalars().all()
        )
        codex_rows = list(
            (
                await session.execute(
                    select(m.PlayerMonsterCodex).where(
                        m.PlayerMonsterCodex.player_id == player_id
                    )
                )
            )
            .scalars()
            .all()
        )
        kills_by_tmpl = {int(r.monster_template_id): int(r.kills) for r in codex_rows}
        seen_set = set(kills_by_tmpl.keys())

        entries = [
            _build_entry(
                t,
                kills_by_tmpl.get(int(t.id), 0),
                int(t.id) in seen_set,
                detailed=False,
            )
            for t in templates
        ]
        entries.sort(key=lambda e: (e["act_min"], e["template_id"]))

        total = len(templates)
        seen_count = len(seen_set)
        completed = sum(1 for e in entries if e["tier"] >= bcfg.MAX_TIER)
        return {
            "monsters": entries,
            "tiers": _tier_catalog(),
            "summary": {
                "total": total,
                "seen": seen_count,
                "completed": completed,
                "seen_pct": round(100.0 * seen_count / total) if total else 0,
            },
        }
    except Exception as e:
        logger.exception("Failed /library/bestiary for player_id=%s: %s", player_id, e)
        return {"monsters": [], "tiers": _tier_catalog(), "summary": {"total": 0, "seen": 0, "completed": 0, "seen_pct": 0}}


@router.get("/library/bestiary/{template_id}", tags=["library"])
async def bestiary_monster(
    template_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Detailed (redacted) page for a single monster template."""
    tmpl = await session.get(m.MonsterTemplate, int(template_id))
    if tmpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monster_not_found")
    row = await session.get(m.PlayerMonsterCodex, (int(player_id), int(template_id)))
    kills = int(row.kills) if row is not None else 0
    seen = row is not None
    entry = _build_entry(tmpl, kills, seen, detailed=True)
    entry["tiers"] = _tier_catalog()
    return entry
