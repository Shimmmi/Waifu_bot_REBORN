"""Legendary bonus engine: run handlers, aggregate, apply."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from waifu_bot.game.constants import MediaType
from waifu_bot.game.legendary_bonuses.context import BonusContext, BonusResult
from waifu_bot.game.legendary_bonuses.handlers import (
    BONUS_HANDLERS,
    DEATH_HANDLERS,
    handler_crit_chain_after_crit,
    handler_killing_blow_heal_on_death,
)
from waifu_bot.game.legendary_bonuses.state import merge_battle_state


@dataclass
class AggregatedLegendaryResult:
    damage_multiplier: float = 1.0
    damage_flat_bonus: int = 0
    force_crit: bool = False
    crit_damage_multiplier: float = 1.0
    ignore_monster_armor: bool = False
    ignore_monster_affixes: bool = False
    ignore_monster_dodge: bool = False
    ignore_monster_death_damage: bool = False
    extra_hits: list[float] = field(default_factory=list)
    remaining_monsters_damage_multiplier: float = 0.0
    heal_flat: int = 0
    heal_pct_of_damage: float = 0.0
    drop_chance_multiplier: float = 1.0
    gold_multiplier: float = 1.0
    clear_waifu_debuffs: bool = False
    battle_state_patch: dict[str, Any] = field(default_factory=dict)
    notifications: list[str] = field(default_factory=list)
    prevent_monster_death_spawn: bool = False
    monster_self_damage: int = 0
    detonator_pending: bool = False


def media_type_to_str(media_type: MediaType | str | None) -> str:
    if media_type is None:
        return "text"
    if isinstance(media_type, str):
        return media_type.lower()
    mapping = {
        MediaType.TEXT: "text",
        MediaType.STICKER: "sticker",
        MediaType.PHOTO: "photo",
        MediaType.GIF: "gif",
        MediaType.AUDIO: "audio",
        MediaType.VIDEO: "video",
        MediaType.VOICE: "voice",
        MediaType.LINK: "link",
    }
    return mapping.get(media_type, "text")


def _aggregate(results: list[BonusResult], *, max_mult: float) -> AggregatedLegendaryResult:
    agg = AggregatedLegendaryResult()
    mult = 1.0
    for r in results:
        mult *= float(r.damage_multiplier or 1.0)
        agg.damage_flat_bonus += int(r.damage_flat_bonus or 0)
        agg.force_crit = agg.force_crit or bool(r.force_crit)
        agg.crit_damage_multiplier *= float(r.crit_damage_multiplier or 1.0)
        agg.ignore_monster_armor = agg.ignore_monster_armor or bool(r.ignore_monster_armor)
        agg.ignore_monster_affixes = agg.ignore_monster_affixes or bool(r.ignore_monster_affixes)
        agg.ignore_monster_dodge = agg.ignore_monster_dodge or bool(r.ignore_monster_dodge)
        agg.ignore_monster_death_damage = agg.ignore_monster_death_damage or bool(r.ignore_monster_death_damage)
        agg.extra_hits.extend(list(r.extra_hits or []))
        agg.remaining_monsters_damage_multiplier = max(
            agg.remaining_monsters_damage_multiplier,
            float(r.remaining_monsters_damage_multiplier or 0.0),
        )
        agg.heal_flat += int(r.heal_flat or 0)
        agg.heal_pct_of_damage += float(r.heal_pct_of_damage or 0.0)
        agg.drop_chance_multiplier *= float(r.drop_chance_multiplier or 1.0)
        agg.gold_multiplier *= float(r.gold_multiplier or 1.0)
        agg.clear_waifu_debuffs = agg.clear_waifu_debuffs or bool(r.clear_waifu_debuffs)
        agg.prevent_monster_death_spawn = agg.prevent_monster_death_spawn or bool(r.prevent_monster_death_spawn)
        if r.monster_self_damage:
            agg.monster_self_damage = max(agg.monster_self_damage, int(r.monster_self_damage))
        if r.notification:
            agg.notifications.append(str(r.notification))
        agg.battle_state_patch = merge_battle_state(agg.battle_state_patch, r.battle_state_patch or {})
        if r.battle_state_patch.get("detonator_triggered"):
            agg.detonator_pending = True
    agg.damage_multiplier = min(mult, max_mult)
    return agg


def run_outgoing_handlers(
    active_rows: list[dict[str, Any]],
    ctx_base: BonusContext,
    *,
    max_mult: float = 10.0,
    skip_keys: frozenset[str] | None = None,
    phase: str = "full",
) -> AggregatedLegendaryResult:
    skip = skip_keys or frozenset()
    results: list[BonusResult] = []
    working_state = dict(ctx_base.battle_state or {})
    for row in active_rows:
        key = str(row.get("bonus_key") or "")
        if not key or key in skip or key in DEATH_HANDLERS:
            continue
        handler = BONUS_HANDLERS.get(key)
        if not handler:
            continue
        ctx = BonusContext(
            player_id=ctx_base.player_id,
            waifu_id=ctx_base.waifu_id,
            session_id=ctx_base.session_id,
            is_group_dungeon=ctx_base.is_group_dungeon,
            message_type=ctx_base.message_type,
            message_length=ctx_base.message_length,
            message_timestamp=ctx_base.message_timestamp,
            seconds_since_last_attack=ctx_base.seconds_since_last_attack,
            monster_id=ctx_base.monster_id,
            monster_hp_current=ctx_base.monster_hp_current,
            monster_hp_max=ctx_base.monster_hp_max,
            monster_affixes=list(ctx_base.monster_affixes),
            monster_is_boss=ctx_base.monster_is_boss,
            monster_is_first_in_room=ctx_base.monster_is_first_in_room,
            waifu_hp_current=ctx_base.waifu_hp_current,
            waifu_hp_max=ctx_base.waifu_hp_max,
            waifu_gold=ctx_base.waifu_gold,
            waifu_level=ctx_base.waifu_level,
            waifu_stats=dict(ctx_base.waifu_stats),
            waifu_last_dungeon_knocked_out=ctx_base.waifu_last_dungeon_knocked_out,
            battle_state=working_state,
            item_id=int(row.get("inventory_item_id") or 0),
            bonus_key=key,
            bonus_params=dict(row.get("params") or {}),
            group_last_attacker_id=ctx_base.group_last_attacker_id,
            group_messages_since_last_ov_attack=ctx_base.group_messages_since_last_ov_attack,
            base_damage=ctx_base.base_damage,
            extra_data=dict(ctx_base.extra_data),
            equipped_legendary_count=ctx_base.equipped_legendary_count,
            slot_type=row.get("slot_type"),
        )
        res = handler(ctx)
        if phase == "pre_crit":
            res = BonusResult(force_crit=res.force_crit, crit_damage_multiplier=res.crit_damage_multiplier)
        elif phase == "post_crit":
            res.force_crit = False
        results.append(res)
        working_state = merge_battle_state(working_state, res.battle_state_patch or {})
    agg = _aggregate(results, max_mult=max_mult if phase != "pre_crit" else 999.0)
    if phase == "full":
        agg.battle_state_patch = merge_battle_state(ctx_base.battle_state, working_state)
    else:
        agg.battle_state_patch = merge_battle_state({}, working_state)
    return agg


def run_death_handlers(
    active_rows: list[dict[str, Any]],
    ctx_base: BonusContext,
) -> AggregatedLegendaryResult:
    results: list[BonusResult] = []
    for row in active_rows:
        key = str(row.get("bonus_key") or "")
        if key != "KILLING_BLOW_HEAL":
            continue
        ctx = BonusContext(
            **{
                **ctx_base.__dict__,
                "bonus_key": key,
                "bonus_params": dict(row.get("params") or {}),
            }
        )
        results.append(handler_killing_blow_heal_on_death(ctx))
    return _aggregate(results, max_mult=999.0)


def apply_outgoing_to_damage(damage: int, agg: AggregatedLegendaryResult) -> int:
    if agg.extra_hits and agg.damage_multiplier <= 0:
        total = 0
        for pct in agg.extra_hits:
            total += int(round(damage * float(pct)))
        return total + int(agg.damage_flat_bonus)
    out = int(round(damage * agg.damage_multiplier)) + int(agg.damage_flat_bonus)
    for pct in agg.extra_hits:
        out += int(round(damage * float(pct)))
    return max(0, out)


def post_crit_patches(
    active_rows: list[dict[str, Any]],
    ctx_base: BonusContext,
    was_crit: bool,
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for row in active_rows:
        if str(row.get("bonus_key") or "") != "CRIT_CHAIN":
            continue
        ctx = BonusContext(
            **{
                **ctx_base.__dict__,
                "bonus_key": "CRIT_CHAIN",
                "bonus_params": dict(row.get("params") or {}),
            }
        )
        patch = merge_battle_state(patch, handler_crit_chain_after_crit(ctx, was_crit))
    return patch


def try_incoming_last_breath(
    active_rows: list[dict[str, Any]],
    ctx_base: BonusContext,
    incoming_damage: int,
) -> tuple[int, dict[str, Any], str | None]:
    """Returns (damage_to_apply, patch, notification)."""
    for row in active_rows:
        if str(row.get("bonus_key") or "") != "LAST_BREATH":
            continue
        if ctx_base.battle_state.get("last_breath_used"):
            continue
        if ctx_base.waifu_hp_current - incoming_damage > 0:
            continue
        applied = max(0, int(ctx_base.waifu_hp_current) - 1)
        return (
            applied,
            {"last_breath_used": True, "last_breath_ready": True},
            "😤 Последний вздох!",
        )
    return incoming_damage, {}, None


def try_incoming_damage_mirror(
    active_rows: list[dict[str, Any]],
    ctx_base: BonusContext,
    incoming_damage: int,
) -> tuple[int, int, str | None]:
    """Returns (waifu_incoming, monster_reflect_damage, notification)."""
    import random

    for row in active_rows:
        if str(row.get("bonus_key") or "") != "DAMAGE_MIRROR":
            continue
        chance = float((row.get("params") or {}).get("proc_chance", 0.25))
        if random.random() < chance:
            return 0, incoming_damage, "🪞 Зеркало ответа!"
    return incoming_damage, 0, None


def charge_revenge_crystal(active_rows: list[dict[str, Any]], damage_received: int) -> dict[str, Any]:
    for row in active_rows:
        if str(row.get("bonus_key") or "") != "REVENGE_CRYSTAL":
            continue
        if damage_received <= 0:
            return {}
        st = {}
        return {
            "crystal_charge": int(damage_received),
            "crystal_discharged": False,
        }
    return {}


def on_retaliation_dodge(active_rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in active_rows:
        if str(row.get("bonus_key") or "") == "COUNTER_DODGE":
            return {"counter_dodge_ready": True}
    return {}


def on_retaliation_damage(active_rows: list[dict[str, Any]], damage: int) -> dict[str, Any]:
    patch: dict[str, Any] = {"received_damage_this_fight": damage, "revenge_ready": True}
    patch.update(charge_revenge_crystal(active_rows, damage))
    return patch


def on_phoenix_revive(active_rows: list[dict[str, Any]], params_by_key: dict[str, dict]) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    if not any(str(r.get("bonus_key") or "") == "PHOENIX_RAGE" for r in active_rows):
        return {}
    p = params_by_key.get("PHOENIX_RAGE") or {"duration_minutes": 5}
    until = (datetime.now(timezone.utc) + timedelta(minutes=int(p.get("duration_minutes", 5)))).isoformat()
    return {"phoenix_active_until": until}


def on_monster_debuff_applied(active_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if any(str(r.get("bonus_key") or "") == "COUNTER_CURSE" for r in active_rows):
        return {"curse_counter_ready": True}
    return {}


def on_monster_kill_state(
    battle_state: dict[str, Any],
    total_damage_fight: int,
) -> dict[str, Any]:
    return {
        "prev_fight_total_damage": int(total_damage_fight),
        "monsters_killed_session": int(battle_state.get("monsters_killed_session", 0) or 0) + 1,
    }
