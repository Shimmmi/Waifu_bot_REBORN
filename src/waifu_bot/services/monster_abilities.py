"""Solo dungeon: monster ability templates (DoT, shock, weakness) on DungeonRun.active_waifu_debuffs."""
from __future__ import annotations

import random
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import BattleLog, MonsterAbilityTemplate, MonsterTemplate
from waifu_bot.db.models.dungeon import DungeonRun
from waifu_bot.db.models.waifu import MainWaifu
from waifu_bot.services.combat_damage_trace import DamageTrace


def get_active_debuffs(run: DungeonRun) -> list[dict[str, Any]]:
    raw = getattr(run, "active_waifu_debuffs", None)
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def set_active_debuffs(run: DungeonRun, debuffs: list[dict[str, Any]]) -> None:
    run.active_waifu_debuffs = debuffs


def clear_debuffs_from_source_monster(run: DungeonRun, position: int) -> None:
    pos = int(position)
    debuffs = [d for d in get_active_debuffs(run) if int(d.get("source_position", -1)) != pos]
    set_active_debuffs(run, debuffs)


def process_debuffs_start_of_player_turn(run: DungeonRun, waifu: MainWaifu) -> tuple[int, bool]:
    """Apply DoT to waifu; roll shock for this turn. Returns (dot_damage_total, shock_skips_attack)."""
    debuffs = get_active_debuffs(run)
    if not debuffs:
        return 0, False

    dot_total = 0
    rest: list[dict[str, Any]] = []
    for d in debuffs:
        if (d.get("kind") or "") == "dot_poison":
            tick = int(d.get("damage_per_tick", 0) or 0)
            left = int(d.get("ticks_left", 0) or 0)
            if left > 0 and tick > 0:
                cur = int(waifu.current_hp or 0)
                waifu.current_hp = max(0, cur - tick)
                run.waifu_hp_lost = int(run.waifu_hp_lost or 0) + tick
                dot_total += tick
                left -= 1
            if left > 0:
                nd = dict(d)
                nd["ticks_left"] = left
                rest.append(nd)
        else:
            rest.append(dict(d))

    shock_skip = False
    final: list[dict[str, Any]] = []
    for d in rest:
        if (d.get("kind") or "") == "shock":
            ch = int(d.get("charges", 0) or 0)
            sc = float(d.get("skip_chance", 0) or 0)
            if ch > 0 and random.random() < sc:
                shock_skip = True
                ch -= 1
            nd = dict(d)
            nd["charges"] = ch
            if ch > 0:
                final.append(nd)
        else:
            final.append(d)

    set_active_debuffs(run, final)
    return dot_total, shock_skip


def apply_weakness_to_outgoing_damage(damage: int, run: DungeonRun, trace: DamageTrace) -> int:
    """Multiply outgoing damage; consumes one hit from each active weakness debuff."""
    debuffs = get_active_debuffs(run)
    if not debuffs or damage <= 0:
        return damage

    mult = 1.0
    new_list: list[dict[str, Any]] = []
    for d in debuffs:
        if (d.get("kind") or "") == "weakness":
            hl = int(d.get("hits_left", 0) or 0)
            if hl > 0:
                mult *= float(d.get("player_dmg_mult", 1.0) or 1.0)
                nd = dict(d)
                nd["hits_left"] = hl - 1
                if nd["hits_left"] > 0:
                    new_list.append(nd)
        else:
            new_list.append(dict(d))

    set_active_debuffs(run, new_list)
    if mult != 1.0:
        nb = damage
        damage = max(1, int(round(damage * mult)))
        trace.mult(
            "monster_ability_weakness",
            f"Ослабление от монстра: ×{mult:.2f}",
            nb,
            damage,
            factor=mult,
        )
    return damage


async def maybe_apply_first_player_hit_ability(
    session: AsyncSession,
    run: DungeonRun,
    run_monster,
    waifu: MainWaifu,
) -> None:
    tid = getattr(run_monster, "template_id", None)
    if not tid:
        return
    tmpl = await session.get(MonsterTemplate, int(tid))
    if not tmpl or not getattr(tmpl, "monster_ability_template_id", None):
        return
    ab = await session.get(MonsterAbilityTemplate, int(tmpl.monster_ability_template_id))
    if not ab or (str(ab.trigger or "").strip() != "first_player_hit"):
        return
    eff = ab.effect_json if isinstance(ab.effect_json, dict) else {}
    kind = str(eff.get("kind") or "").strip()
    pos = int(run_monster.position)
    debuffs = get_active_debuffs(run)

    if kind == "dot_poison":
        debuffs.append(
            {
                "slug": ab.slug,
                "kind": "dot_poison",
                "ticks_left": max(1, int(eff.get("ticks", 5))),
                "damage_per_tick": max(1, int(eff.get("damage_per_tick", 8))),
                "source_position": pos,
            }
        )
    elif kind == "shock":
        debuffs.append(
            {
                "slug": ab.slug,
                "kind": "shock",
                "charges": max(1, int(eff.get("charges", 5))),
                "skip_chance": min(0.95, max(0.0, float(eff.get("skip_chance", 0.12)))),
                "source_position": pos,
            }
        )
    elif kind == "weakness":
        debuffs.append(
            {
                "slug": ab.slug,
                "kind": "weakness",
                "hits_left": max(1, int(eff.get("hits", 4))),
                "player_dmg_mult": min(1.0, max(0.1, float(eff.get("player_dmg_mult", 0.88)))),
                "source_position": pos,
            }
        )
    else:
        return

    set_active_debuffs(run, debuffs)


async def log_dot_tick_if_any(
    session: AsyncSession,
    *,
    player_id: int,
    dungeon_id: int,
    dot_total: int,
    hp_before: int,
    hp_after: int,
) -> None:
    if dot_total <= 0:
        return
    session.add(
        BattleLog(
            player_id=player_id,
            dungeon_id=dungeon_id,
            event_type="waifu_debuff_dot",
            event_data={
                "dot_damage": dot_total,
                "summary_ru": f"Дебафф монстра: {dot_total} урона по основной вайфу (яд/DoT).",
            },
            player_hp_before=hp_before,
            player_hp_after=hp_after,
        )
    )
