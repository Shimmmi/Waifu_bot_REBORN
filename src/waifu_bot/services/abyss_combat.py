"""Abyss (Бездна) combat: one message = one attack turn.

Reuses the solo-combat building blocks (effective stats, mitigation, level-ups,
item generation) but runs its own floor/monster loop with Abyss-specific floor
modifiers, Graces and checkpoint-boss mechanics.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import MainWaifu, Player
from waifu_bot.game.constants import DODGE_CHANCE_CAP, MediaType
from waifu_bot.game.effective_stats import (
    apply_combined_stat_mult_to_four,
    stat_multipliers_from_passive_hidden,
)
from waifu_bot.game.formulas import (
    calculate_damage_reduction,
    calculate_dodge_chance,
    calculate_message_damage,
    calculate_crit_chance,
    get_crit_multiplier,
)
from waifu_bot.services import abyss_rewards as ar
from waifu_bot.services import abyss_service as absvc
from waifu_bot.services.combat import (
    CombatService,
    apply_main_waifu_levelups,
    compute_incoming_damage_after_mitigation,
)
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
from waifu_bot.services.combat_regen import apply_hp_regen_for_context, is_player_online
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.passive_skills import get_passive_skill_bonuses

logger = logging.getLogger(__name__)

# Reused only for its stateless stat/mitigation helpers (no Redis needed).
_combat = CombatService(redis_client=None)


def _is_text(media_type: MediaType) -> bool:
    return media_type in (MediaType.TEXT, MediaType.LINK)


async def _effective_stats(session: AsyncSession, player_id: int, waifu: MainWaifu) -> dict:
    ps = await get_passive_skill_bonuses(session, player_id)
    hs = await get_hidden_skill_bonuses(session, player_id)
    eff = await _combat._get_effective_combat_profile(session, player_id, waifu, cached_psb=ps)
    _, _, stat_mult = stat_multipliers_from_passive_hidden(ps, hs)
    s, a, i, l = apply_combined_stat_mult_to_four(
        eff["strength"], eff["agility"], eff["intelligence"], eff["luck"], stat_mult
    )
    return {
        "strength": s,
        "agility": a,
        "intelligence": i,
        "luck": l,
        "attack_type": eff.get("attack_type", "melee"),
        "weapon_damage": eff.get("weapon_damage"),
        "min_chars": int(eff.get("min_chars") or 1),
    }


def _apply_grace_to_attack(damage: int, is_text: bool, grace) -> int:
    if not grace:
        return damage
    et = grace.effect_type
    val = float(grace.effect_value or 1.0)
    if et == "TEXT_DMG_BOOST" and is_text:
        damage = round(damage * val)
    elif et == "MEDIA_DMG_BOOST" and not is_text:
        damage = round(damage * val)
    elif et == "DMG_BOOST":
        damage = round(damage * val)
    return damage


def _modifier_blocks_attack(modifier: str | None, media_type: MediaType) -> str | None:
    """Return a block reason if the floor modifier nullifies this attack."""
    if modifier == "CURSED" and media_type == MediaType.STICKER:
        return "CURSED_STICKER"
    if modifier == "DARK" and not _is_text(media_type):
        return "DARK_MEDIA"
    return None


# ---------------------------------------------------------------------------
# Boss mechanics (param-driven so COMBINED bosses compose them)
# ---------------------------------------------------------------------------

def _boss_blocks_text(monster: dict, is_text: bool) -> bool:
    params = monster.get("mechanic_params") or {}
    return bool(params.get("text_immune")) and is_text


def _apply_stone_skin(monster: dict, damage: int) -> int:
    params = monster.get("mechanic_params") or {}
    smax = params.get("stone_skin_max")
    if not smax:
        return damage
    max_hp = max(1, int(monster.get("max_hp") or 1))
    frac = max(0.0, min(1.0, int(monster.get("current_hp") or 0) / max_hp))
    reduction = float(smax) * frac  # full at high HP, 0 at low HP
    return max(1, round(damage * (1.0 - reduction)))


def _maybe_phase_rage(monster: dict) -> None:
    params = monster.get("mechanic_params") or {}
    state = monster.setdefault("mechanic_state", {})
    at = params.get("phase_2_at")
    mult = params.get("rage_dmg_mult")
    if not at or not mult or state.get("rage_applied"):
        return
    max_hp = max(1, int(monster.get("max_hp") or 1))
    if int(monster.get("current_hp") or 0) / max_hp <= float(at):
        monster["damage"] = max(1, round(int(monster.get("damage") or 1) * float(mult)))
        state["rage_applied"] = True


def _roll_reflect(monster: dict, damage_dealt: int, rng: random.Random) -> int:
    params = monster.get("mechanic_params") or {}
    chance = params.get("reflect_chance")
    if not chance:
        return 0
    if rng.random() >= float(chance):
        return 0
    pct = float(params.get("reflect_pct", 0.25))
    return max(0, round(damage_dealt * pct))


def _try_undying(monster: dict) -> bool:
    """Revive the boss once. Returns True if revived (not really dead)."""
    params = monster.get("mechanic_params") or {}
    state = monster.setdefault("mechanic_state", {})
    pct = params.get("revive_hp_pct")
    if not pct or state.get("undying_used"):
        return False
    state["undying_used"] = True
    revive_hp = max(1, round(int(monster.get("max_hp") or 1) * float(pct)))
    monster["current_hp"] = revive_hp
    return True


def _try_split(monster: dict) -> bool:
    """Turn a dying split boss into the first of N weakened copies.

    Subsequent copies are respawned in-place as each copy dies (tracked in
    mechanic_state). Returns True if the fight continues with a copy.
    """
    params = monster.get("mechanic_params") or {}
    state = monster.setdefault("mechanic_state", {})
    copies = int(params.get("copies") or params.get("split_copies") or 0)
    if copies <= 0:
        return False
    hp_pct = float(params.get("copy_hp_pct", 0.4))
    dmg_pct = float(params.get("copy_dmg_pct", 0.4))

    if not state.get("split_started"):
        state["split_started"] = True
        state["copies_left"] = copies
        state["copy_hp"] = max(1, round(int(monster.get("max_hp") or 1) * hp_pct))
        state["copy_dmg"] = max(1, round(int(monster.get("damage") or 1) * dmg_pct))

    if int(state.get("copies_left") or 0) <= 0:
        return False

    state["copies_left"] = int(state["copies_left"]) - 1
    idx = copies - int(state["copies_left"])
    monster["current_hp"] = int(state["copy_hp"])
    monster["max_hp"] = int(state["copy_hp"])
    monster["damage"] = int(state["copy_dmg"])
    monster["is_split_clone"] = True
    base = monster["name"].split("·")[0].strip()
    monster["name"] = f"{base} · копия {idx}"
    return True


# ---------------------------------------------------------------------------
# Exclusive Abyss affix behaviours (ТЗ §10)
# ---------------------------------------------------------------------------

def _affix_flags(monster: dict) -> dict:
    """Map behavior_flag -> params for the elite affixes rolled on this monster."""
    out: dict = {}
    for b in monster.get("affix_behaviors") or []:
        flag = b.get("flag")
        if flag:
            out[flag] = b.get("params") or {}
    return out


def _affix_mirror_reflect(monster: dict, damage: int, behaviors: dict) -> int:
    """ABYSS_MIRROR: every Nth landed hit reflects a share of damage to the waifu."""
    params = behaviors.get("ABYSS_MIRROR")
    if not params or damage <= 0:
        return 0
    every = int(params.get("every_n_hits", 7) or 7)
    if every <= 0:
        return 0
    state = monster.setdefault("mechanic_state", {})
    cnt = int(state.get("mirror_hits", 0)) + 1
    state["mirror_hits"] = cnt
    if cnt % every != 0:
        return 0
    return max(0, round(damage * float(params.get("reflect_pct", 0.3))))


def _affix_chaos_mult(behaviors: dict, rng: random.Random) -> float:
    """CHAOS_DMG: damage type swaps chaotically → random ±30% damage variance."""
    if "CHAOS_DMG" not in behaviors:
        return 1.0
    return rng.uniform(0.7, 1.3)


# ---------------------------------------------------------------------------
# Main attack handler
# ---------------------------------------------------------------------------

async def handle_abyss_attack(
    session: AsyncSession,
    player_id: int,
    media_type: MediaType,
    message_text: str | None = None,
    message_length: int | None = None,
    *,
    rng: random.Random | None = None,
) -> dict:
    """Process one chat message as an Abyss attack. No-ops cleanly if the player
    has no active Abyss session."""
    rng = rng or random
    progress = await absvc.get_progress_for_update(session, player_id)
    if progress is None or not progress.session_active:
        return {"error": "no_session"}
    if progress.pending_grace_choices:
        return {"error": "awaiting_grace"}

    if await absvc.has_active_solo_run(session, player_id):
        return {"error": "solo_dungeon_active"}

    monster = progress.current_monster
    if not monster:
        return {"error": "no_monster"}

    cfg = await get_game_config_map(session)
    waifu = await absvc.get_waifu(session, player_id)
    if not waifu:
        return {"error": "no_waifu"}

    grace = await absvc.get_active_grace(session, progress)
    modifier = progress.current_floor_modifier
    floor = int(progress.current_floor or 0)
    is_text = _is_text(media_type)

    # §10 Бездна-аффиксы: GRACE_STEAL suppresses the active Grace during the fight;
    # ANTI_REGEN blocks the post-kill heal; ABYSS_MIRROR/CHAOS_DMG resolve below.
    behaviors = _affix_flags(monster)
    combat_grace = None if "GRACE_STEAL" in behaviors else grace

    player = await session.get(Player, player_id)
    hs = await get_hidden_skill_bonuses(session, player_id)
    hr_pm = max(0, int(round(float(hs.get("hp_regen_per_active_hour", 0) or 0))))
    now = datetime.now(timezone.utc)
    online = is_player_online(player, now=now)
    apply_hp_regen_for_context(
        waifu, player, context="abyss", extra_hp_per_min=hr_pm, now=now
    )
    if player is not None:
        player.last_combat_action_at = now

    if int(waifu.current_hp or 0) <= 0:
        await session.commit()
        return {
            "damage_dealt": 0,
            "waifu_unconscious": True,
            "waifu_hp_remaining": int(waifu.current_hp or 0),
            "monster_hp_remaining": int(monster.get("current_hp") or 0),
            "monster_killed": False,
        }

    eff = await _effective_stats(session, player_id, waifu)
    msg_len = int(message_length or (len(message_text) if message_text else 0))

    # Gate text attacks by weapon attack speed (min chars).
    if is_text and msg_len < eff["min_chars"]:
        await session.commit()
        return {
            "error": "message_too_short",
            "required_chars": eff["min_chars"],
            "got_chars": msg_len,
        }

    # --- Compute damage ---
    block_reason = _modifier_blocks_attack(modifier, media_type)
    if not block_reason and _boss_blocks_text(monster, is_text):
        block_reason = "BOSS_TEXT_IMMUNE"

    damage = 0
    is_crit = False
    if not block_reason:
        damage = calculate_message_damage(
            media_type,
            strength=eff["strength"],
            agility=eff["agility"],
            intelligence=eff["intelligence"],
            attack_type=eff["attack_type"],
            message_length=msg_len,
            weapon_damage=eff["weapon_damage"],
        )
        crit_chance = calculate_crit_chance(eff["agility"], eff["luck"])
        if rng.random() < crit_chance:
            is_crit = True
            damage = round(damage * get_crit_multiplier(eff["strength"]))
        damage = _apply_grace_to_attack(damage, is_text, combat_grace)
        damage = round(damage * _affix_chaos_mult(behaviors, rng))
        damage = _apply_stone_skin(monster, damage)
        damage = max(1, int(damage))

    # --- Apply to monster ---
    monster["current_hp"] = int(monster.get("current_hp") or 0) - damage
    _maybe_phase_rage(monster)

    # Reflect (boss) + ABYSS_MIRROR affix on a landed hit.
    reflect_dmg = _roll_reflect(monster, damage, rng) if damage > 0 else 0
    reflect_dmg += _affix_mirror_reflect(monster, damage, behaviors)

    result: dict = {
        "damage_dealt": int(damage),
        "damage_blocked": bool(block_reason),
        "block_reason": block_reason,
        "is_crit": is_crit,
        "floor": floor,
        "monster_name": monster.get("name"),
        "is_boss": bool(monster.get("is_boss")),
        "waifu_took_damage": 0,
        "waifu_unconscious": False,
        "monster_killed": False,
        "rewards": None,
        "floor_complete": False,
        "is_checkpoint_complete": False,
        "checkpoint_rewards": None,
        "next_monster": None,
        "next_floor_preview": None,
    }

    # Reflect damage hits the waifu even on a non-killing blow.
    if reflect_dmg > 0:
        reflect_dmg = _apply_incoming_grace(reflect_dmg, combat_grace)
        _damage_waifu(waifu, reflect_dmg)
        result["waifu_took_damage"] += reflect_dmg

    if int(monster.get("current_hp") or 0) > 0:
        # Monster survives this turn.
        result["monster_hp_remaining"] = int(monster["current_hp"])
        result["waifu_hp_remaining"] = int(waifu.current_hp or 0)
        result["waifu_unconscious"] = int(waifu.current_hp or 0) <= 0
        _mark_monster_dirty(progress)
        await session.commit()
        return result

    # --- Monster reached 0 HP: boss revive / split before truly dying ---
    if monster.get("is_boss"):
        if _try_undying(monster):
            result["monster_hp_remaining"] = int(monster["current_hp"])
            result["waifu_hp_remaining"] = int(waifu.current_hp or 0)
            result["boss_revived"] = True
            _mark_monster_dirty(progress)
            await session.commit()
            return result
        if _try_split(monster):
            result["monster_hp_remaining"] = int(monster["current_hp"])
            result["waifu_hp_remaining"] = int(waifu.current_hp or 0)
            result["boss_split"] = True
            result["monster_name"] = monster.get("name")
            _mark_monster_dirty(progress)
            await session.commit()
            return result

    # --- Monster truly dies ---
    result["monster_killed"] = True
    monster["current_hp"] = 0
    progress.total_monsters_killed = int(progress.total_monsters_killed or 0) + 1

    # Monster retaliation (only on kill, like solo dungeons).
    took = await _monster_retaliation(session, player_id, waifu, monster, eff, combat_grace, rng)
    result["waifu_took_damage"] += took
    unconscious = int(waifu.current_hp or 0) <= 0
    result["waifu_unconscious"] = unconscious

    is_cp = ar.is_checkpoint(floor)

    # Rewards for the kill.
    rewards = await _award_monster(
        session, player_id, waifu, monster, floor, modifier, grace, eff, cfg, rng,
        is_checkpoint_boss=is_cp,
    )

    # Between-monster regen (only if still conscious; ANTI_REGEN affix blocks it).
    regen_after = 0
    if not unconscious and "ANTI_REGEN" not in behaviors and online:
        regen_after = _regen_between_monsters(cfg, waifu, grace)
    rewards["hp_regen_after"] = regen_after
    result["rewards"] = rewards

    # Apply level-ups from accumulated EXP.
    try:
        await apply_main_waifu_levelups(session, waifu)
    except Exception:
        logger.debug("abyss levelup failed pid=%s", player_id, exc_info=True)

    # Decrement floor monster count.
    remaining = int(progress.floor_monsters_remaining or 1) - 1
    progress.floor_monsters_remaining = max(0, remaining)

    if remaining > 0:
        # Next monster on the same (non-checkpoint) floor.
        nxt = await absvc.build_normal_monster(
            session, cfg, floor, modifier, rng, player_id=player_id
        )
        progress.current_monster = nxt
        result["next_monster"] = await absvc.serialize_monster(session, nxt)
        result["waifu_hp_remaining"] = int(waifu.current_hp or 0)
        await session.commit()
        return result

    # --- Floor complete ---
    result["floor_complete"] = True
    progress.total_floors_cleared = int(progress.total_floors_cleared or 0) + 1

    if is_cp:
        result["is_checkpoint_complete"] = True
        cp_rewards = await _award_checkpoint(session, player_id, waifu, floor, cfg, progress, rng)
        result["checkpoint_rewards"] = cp_rewards
        progress.current_checkpoint = floor
        progress.revive_scrolls_used_this_block = 0
        progress.current_monster = None
        progress.floor_monsters_remaining = 0
        # Offer Graces; player must choose before continuing.
        choices = await absvc.generate_grace_choices(session, cfg, floor, rng)
        progress.pending_grace_choices = choices or None
        cp_rewards["grace_choices"] = await _serialize_graces(session, choices)
        result["next_floor_preview"] = {
            "floor": floor + 1,
            "is_checkpoint": ar.is_checkpoint(floor + 1),
            "awaiting_grace": bool(choices),
        }
        result["waifu_hp_remaining"] = int(waifu.current_hp or 0)
        await session.commit()
        return result

    # Ordinary floor complete → auto-advance to next floor.
    await absvc.generate_floor(session, cfg, progress, floor + 1, rng)
    nxt_mod = progress.current_floor_modifier
    result["next_monster"] = await absvc.serialize_monster(session, progress.current_monster)
    result["next_floor_preview"] = {
        "floor": floor + 1,
        "modifier": nxt_mod,
        "modifier_label": ar.modifier_label(nxt_mod),
        "is_checkpoint": ar.is_checkpoint(floor + 1),
    }
    result["waifu_hp_remaining"] = int(waifu.current_hp or 0)
    await session.commit()
    return result


# ---------------------------------------------------------------------------
# Helpers: damage to waifu, rewards, regen
# ---------------------------------------------------------------------------

def _mark_monster_dirty(progress) -> None:
    """Force SQLAlchemy to persist the mutated JSONB monster blob."""
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(progress, "current_monster")


def _damage_waifu(waifu: MainWaifu, dmg: int) -> None:
    if dmg <= 0:
        return
    new_hp = max(0, int(waifu.current_hp or 0) - int(dmg))
    waifu.current_hp = new_hp
    if new_hp <= 0:
        waifu.hp_updated_at = datetime.now(timezone.utc)


def _apply_incoming_grace(dmg: int, grace) -> int:
    if grace and grace.effect_type == "DMG_REDUCE":
        return max(0, round(dmg * float(grace.effect_value or 1.0)))
    return dmg


async def _monster_retaliation(
    session: AsyncSession,
    player_id: int,
    waifu: MainWaifu,
    monster: dict,
    eff: dict,
    grace,
    rng: random.Random,
) -> int:
    """Compute and apply monster counter-damage to the waifu. Returns dmg dealt."""
    sec = await _combat._get_waifu_armor_and_secondary(session, player_id)

    # Dodge.
    base_dodge = calculate_dodge_chance(eff["agility"], eff["luck"])
    dodge = min(float(DODGE_CHANCE_CAP), base_dodge + float(sec.get("evade_pct", 0) or 0))
    if grace and grace.effect_type == "DODGE_BOOST":
        dodge = min(0.95, dodge + float(grace.effect_value or 0))
    if rng.random() < dodge:
        return 0

    raw_in = int(monster.get("damage") or 0)
    end_reduce = calculate_damage_reduction(int(getattr(waifu, "endurance", 10) or 10))
    sec_reduce = float(sec.get("dmg_reduce_pct", 0) or 0)
    armor_total = float(sec.get("armor_total", 0) or 0)
    _, _, dmg_after = compute_incoming_damage_after_mitigation(
        raw_in, armor_total, int(waifu.level or 1), end_reduce, sec_reduce
    )
    dmg_after = _apply_incoming_grace(dmg_after, grace)
    _damage_waifu(waifu, dmg_after)
    return int(dmg_after)


def _regen_between_monsters(cfg: dict[str, str], waifu: MainWaifu, grace) -> int:
    pct = cfg_float(cfg, "abyss_between_monster_regen_pct", 0.05)
    if grace and grace.effect_type == "HP_REGEN":
        pct = float(grace.effect_value or pct)
    max_hp = int(waifu.max_hp or 0)
    cur = int(waifu.current_hp or 0)
    if cur <= 0 or cur >= max_hp:
        return 0
    amount = min(round(max_hp * pct), max_hp - cur)
    waifu.current_hp = cur + amount
    return int(amount)


async def _award_monster(
    session: AsyncSession,
    player_id: int,
    waifu: MainWaifu,
    monster: dict,
    floor: int,
    modifier: str | None,
    grace,
    eff: dict,
    cfg: dict[str, str],
    rng: random.Random,
    *,
    is_checkpoint_boss: bool,
) -> dict:
    # Gold.
    gold = rng.randint(int(monster.get("gold_min") or 1), int(monster.get("gold_max") or 1))
    gold = ar.apply_luck_gold_bonus(gold, eff["luck"])
    gold = ar.apply_modifier_to_gold(cfg, gold, modifier)
    if grace and grace.effect_type == "GOLD_MULT":
        gold = round(gold * float(grace.effect_value or 1.0))

    # EXP.
    exp = int(monster.get("exp_reward") or 0)
    exp = ar.apply_int_exp_bonus(exp, eff["intelligence"])
    exp = ar.apply_modifier_to_exp(cfg, exp, modifier)
    if grace and grace.effect_type == "EXP_BOOST":
        exp = round(exp * float(grace.effect_value or 1.0))

    player = await session.get(Player, player_id)
    if player is not None:
        player.gold = int(player.gold or 0) + int(gold)
    waifu.experience = int(waifu.experience or 0) + int(exp)

    # Item drop (skipped for checkpoint boss — handled separately, and skipped
    # entirely while the Алчность/GOLD_MULT Grace is active).
    item = None
    if not is_checkpoint_boss and not (grace and grace.effect_type == "GOLD_MULT"):
        drop_chance = cfg_float(cfg, "abyss_item_drop_base_chance", 0.08)
        if grace and grace.effect_type == "DROP_CHANCE_BOOST":
            drop_chance *= float(grace.effect_value or 1.0)
        if rng.random() < drop_chance:
            item = await _generate_drop(session, player_id, floor, rarity=None)

    return {"gold": int(gold), "exp": int(exp), "item": item}


async def _award_checkpoint(
    session: AsyncSession,
    player_id: int,
    waifu: MainWaifu,
    floor: int,
    cfg: dict[str, str],
    progress,
    rng: random.Random,
) -> dict:
    under_limit = absvc.under_daily_limit(cfg, progress)
    shards = 0
    item = None
    if under_limit:
        shards = ar.calc_checkpoint_shards(cfg, floor)
        progress.abyss_shards = int(progress.abyss_shards or 0) + shards
        progress.checkpoints_today = int(progress.checkpoints_today or 0) + 1
        progress.last_checkpoint_date = absvc.msk_today()
        if cfg_int(cfg, "abyss_checkpoint_item_guaranteed", 1) == 1:
            rarity = rng.choices([2, 3, 4, 5], weights=[30, 40, 20, 10])[0]
            item = await _generate_drop(session, player_id, floor, rarity=rarity)
    return {
        "shards": int(shards),
        "item": item,
        "limit_reached": (not under_limit),
    }


async def _generate_drop(
    session: AsyncSession, player_id: int, floor: int, *, rarity: int | None
) -> dict | None:
    cfg_divisor_level = ar.calc_abyss_item_level({}, floor)
    try:
        inv = await _combat.item_service.generate_inventory_item(
            session=session,
            player_id=player_id,
            act=absvc._act_for_floor(floor),
            rarity=rarity,
            level=cfg_divisor_level,
            is_shop=False,
            plus_level=0,
        )
        await session.flush()
    except Exception:
        logger.debug("abyss item drop failed pid=%s floor=%s", player_id, floor, exc_info=True)
        return None
    name = (
        getattr(inv, "_display_name", None)
        or (inv.item.name if getattr(inv, "item", None) else None)
        or "Предмет"
    )
    return {
        "inventory_item_id": inv.id,
        "name": name,
        "rarity": int(inv.rarity or (rarity or 1)),
        "level": int(inv.level or cfg_divisor_level),
        "tier": int(inv.tier or 1),
    }


async def _serialize_graces(session: AsyncSession, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    from waifu_bot.db.models import AbyssGrace
    from sqlalchemy import select

    res = await session.execute(select(AbyssGrace).where(AbyssGrace.id.in_(ids)))
    by_id = {g.id: g for g in res.scalars().all()}
    out = []
    for gid in ids:
        g = by_id.get(gid)
        if g:
            out.append({
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "icon": g.icon,
                "effect_label": g.effect_label,
            })
    return out
