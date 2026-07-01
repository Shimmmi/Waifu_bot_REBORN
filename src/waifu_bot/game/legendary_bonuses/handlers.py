"""Legendary bonus handler functions and registry."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from waifu_bot.game.legendary_bonuses.context import BonusContext, BonusResult

Handler = Callable[[BonusContext], BonusResult]

GROUP_ONLY_KEYS = frozenset({"TEAM_SPIRIT", "CROWD_INSPIRATION", "LAST_WORD", "RESONANCE_SERIES"})


def _empty(ctx: BonusContext) -> BonusResult:
    if ctx.is_group_dungeon or ctx.bonus_key in GROUP_ONLY_KEYS:
        return BonusResult()
    return BonusResult()


def _p(ctx: BonusContext, key: str, default=None):
    return (ctx.bonus_params or {}).get(key, default)


def handler_gold_pulse(ctx: BonusContext) -> BonusResult:
    threshold = int(_p(ctx, "gold_threshold", 1000))
    if ctx.waifu_gold <= threshold:
        return BonusResult()
    dmg = float(_p(ctx, "damage_bonus", 0.15))
    drop = float(_p(ctx, "drop_bonus", 0.10))
    return BonusResult(
        damage_multiplier=1.0 + dmg,
        drop_chance_multiplier=1.0 + drop,
    )


def handler_affix_mastery(ctx: BonusContext) -> BonusResult:
    per = float(_p(ctx, "bonus_per_affix", 0.07))
    mult = 1.0 + len(ctx.monster_affixes or []) * per
    return BonusResult(damage_multiplier=mult)


def handler_boss_slayer(ctx: BonusContext) -> BonusResult:
    if not ctx.monster_is_boss:
        return BonusResult()
    return BonusResult(
        damage_multiplier=float(_p(ctx, "damage_multiplier", 2.0)),
        crit_damage_multiplier=float(_p(ctx, "crit_damage_multiplier", 1.5)),
    )


def handler_sniper_shot(ctx: BonusContext) -> BonusResult:
    if ctx.monster_is_first_in_room:
        return BonusResult(force_crit=True)
    return BonusResult()


def handler_breakthrough(ctx: BonusContext) -> BonusResult:
    if ctx.monster_hp_max <= 0:
        return BonusResult()
    pct = ctx.monster_hp_current / max(1, ctx.monster_hp_max)
    if pct <= float(_p(ctx, "hp_threshold_pct", 0.10)):
        return BonusResult(damage_multiplier=float(_p(ctx, "damage_multiplier", 10.0)))
    return BonusResult()


def handler_agony(ctx: BonusContext) -> BonusResult:
    if ctx.waifu_hp_max <= 0:
        return BonusResult()
    if ctx.waifu_hp_current / max(1, ctx.waifu_hp_max) <= float(_p(ctx, "hp_threshold_pct", 0.20)):
        return BonusResult(force_crit=True)
    return BonusResult()


def handler_wound_fury(ctx: BonusContext) -> BonusResult:
    if ctx.waifu_hp_max <= 0:
        return BonusResult()
    lost = 1.0 - ctx.waifu_hp_current / max(1, ctx.waifu_hp_max)
    stacks = int(lost / 0.10)
    bonus = min(
        stacks * float(_p(ctx, "bonus_per_10pct", 0.05)),
        float(_p(ctx, "max_bonus", 0.40)),
    )
    return BonusResult(damage_multiplier=1.0 + bonus)


def handler_hunt_frenzy(ctx: BonusContext) -> BonusResult:
    if ctx.monster_is_first_in_room and int(ctx.battle_state.get("monsters_killed_session", 0) or 0) > 0:
        return BonusResult(damage_multiplier=float(_p(ctx, "damage_multiplier", 2.0)))
    return BonusResult()


def handler_quick_reflex(ctx: BonusContext) -> BonusResult:
    window = float(_p(ctx, "window_seconds", 8))
    if ctx.seconds_since_last_attack < window:
        return BonusResult(damage_multiplier=1.0 + float(_p(ctx, "damage_bonus", 0.30)))
    return BonusResult()


def handler_verbosity(ctx: BonusContext) -> BonusResult:
    base_len = int(_p(ctx, "base_length", 50))
    if ctx.message_type != "text" or ctx.message_length <= base_len:
        return BonusResult()
    extra = (ctx.message_length - base_len) // base_len
    mult = min(
        1.0 + extra * float(_p(ctx, "bonus_per_block", 0.15)),
        float(_p(ctx, "cap_multiplier", 3.0)),
    )
    return BonusResult(damage_multiplier=mult)


def handler_piercing_scream(ctx: BonusContext) -> BonusResult:
    if ctx.message_type == "text" and ctx.message_length == 1:
        return BonusResult(
            damage_multiplier=float(_p(ctx, "damage_multiplier", 0.7)),
            ignore_monster_armor=True,
            ignore_monster_affixes=True,
        )
    return BonusResult()


def handler_mystic_seven(ctx: BonusContext) -> BonusResult:
    n = int(ctx.battle_state.get("total_messages_in_fight", 0) or 0)
    every = int(_p(ctx, "every_n", 7))
    if n > 0 and n % every == 0:
        return BonusResult(
            damage_multiplier=float(_p(ctx, "damage_multiplier", 2.5)),
            notification="✨ Мистическая семёрка!",
        )
    return BonusResult()


def handler_immunity_breaker(ctx: BonusContext) -> BonusResult:
    aff = {str(a).upper() for a in (ctx.monster_affixes or [])}
    if "TEXT_IMMUNE" in aff and ctx.message_type != "text":
        return BonusResult(damage_multiplier=float(_p(ctx, "damage_multiplier", 4.0)))
    return BonusResult()


def handler_survivor_spirit(ctx: BonusContext) -> BonusResult:
    if ctx.waifu_last_dungeon_knocked_out:
        return BonusResult(damage_multiplier=1.0 + float(_p(ctx, "damage_bonus", 0.30)))
    return BonusResult()


def handler_silence_burst(ctx: BonusContext) -> BonusResult:
    threshold = float(_p(ctx, "trigger_minutes", 15)) * 60
    if ctx.seconds_since_last_attack < threshold:
        return BonusResult()
    minutes = ctx.seconds_since_last_attack / 60
    raw = 1.0 + minutes * float(_p(ctx, "damage_per_minute", 0.5))
    final = min(raw, float(_p(ctx, "cap_multiplier", 10.0)))
    return BonusResult(
        damage_multiplier=final,
        notification=f"⚡ Тишина перед бурей! ×{final:.1f}",
    )


def handler_ambush_silence(ctx: BonusContext) -> BonusResult:
    if ctx.message_type == "text":
        return BonusResult()
    threshold = float(_p(ctx, "silence_minutes", 5)) * 60
    if ctx.seconds_since_last_attack < threshold:
        return BonusResult()
    return BonusResult(
        damage_multiplier=float(_p(ctx, "damage_multiplier", 4.0)),
        ignore_monster_death_damage=True,
        notification="🌑 Засада из тишины!",
    )


def handler_morning_ritual(ctx: BonusContext) -> BonusResult:
    threshold = float(_p(ctx, "silence_hours", 6)) * 3600
    if ctx.seconds_since_last_attack < threshold:
        return BonusResult()
    return BonusResult(
        damage_multiplier=float(_p(ctx, "damage_multiplier", 3.0)),
        clear_waifu_debuffs=True,
        ignore_monster_affixes=True,
        battle_state_patch={"morning_ritual_used": True},
        notification="💫 Утренний ритуал!",
    )


def _local_hour(ctx: BonusContext) -> int:
    tz_name = str(_p(ctx, "timezone", "Europe/Moscow"))
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = ctx.message_timestamp or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(tz).hour


def handler_night_serenade(ctx: BonusContext) -> BonusResult:
    if ctx.message_type != "voice":
        return BonusResult()
    h = _local_hour(ctx)
    if int(_p(ctx, "hour_start", 0)) <= h < int(_p(ctx, "hour_end", 6)):
        return BonusResult(
            damage_multiplier=float(_p(ctx, "damage_multiplier", 4.0)),
            ignore_monster_death_damage=True,
            notification="🌙 Ночная серенада!",
        )
    return BonusResult()


def handler_midnight_strike(ctx: BonusContext) -> BonusResult:
    tz_name = str(_p(ctx, "timezone", "Europe/Moscow"))
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = ctx.message_timestamp or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(tz)
    window = int(_p(ctx, "window_minutes", 5))
    if local.hour == 0 and local.minute < window:
        return BonusResult(
            damage_multiplier=float(_p(ctx, "damage_multiplier", 5.0)),
            drop_chance_multiplier=999.0,
            notification="🕛 Полночный удар!",
        )
    return BonusResult()


def handler_first_sticker_of_hour(ctx: BonusContext) -> BonusResult:
    if ctx.message_type != "sticker":
        return BonusResult()
    state = ctx.battle_state
    if state.get("expression_buff_until"):
        try:
            exp = datetime.fromisoformat(str(state["expression_buff_until"]))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < exp:
                return BonusResult(damage_multiplier=1.0 + float(state.get("expression_buff_pct", 0) or 0))
        except (TypeError, ValueError):
            pass
    last_ts = state.get("last_sticker_hour_ts")
    now = datetime.now(timezone.utc)
    if last_ts:
        try:
            last_dt = datetime.fromisoformat(str(last_ts))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if last_dt.astimezone(timezone.utc).hour == now.hour and last_dt.date() == now.date():
                return BonusResult()
        except (TypeError, ValueError):
            pass
    duration = int(_p(ctx, "duration_minutes", 10))
    expires = (now + timedelta(minutes=duration)).isoformat()
    pct = float(_p(ctx, "bonus_pct", 0.40))
    return BonusResult(
        battle_state_patch={
            "last_sticker_hour_ts": now.isoformat(),
            "expression_buff_until": expires,
            "expression_buff_pct": pct,
        },
        notification="✨ Экспрессия! +40% к стикерам на 10 мин.",
    )


def handler_revenge_thirst(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("revenge_ready"):
        return BonusResult(
            force_crit=True,
            battle_state_patch={"revenge_ready": False},
            notification="💢 Жажда мести!",
        )
    return BonusResult()


def handler_counter_dodge(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("counter_dodge_ready"):
        return BonusResult(
            force_crit=True,
            battle_state_patch={"counter_dodge_ready": False},
            notification="↩️ Ответный удар!",
        )
    return BonusResult()


def handler_killing_blow_heal(ctx: BonusContext) -> BonusResult:
    return BonusResult()


def handler_killing_blow_heal_on_death(ctx: BonusContext) -> BonusResult:
    if random.random() >= float(_p(ctx, "proc_chance", 0.60)):
        return BonusResult()
    heal = int(round(ctx.waifu_hp_max * float(_p(ctx, "heal_pct", 0.10))))
    return BonusResult(heal_flat=heal, notification=f"💚 Добивание с выгодой! +{heal} HP")


def handler_thought_stream(ctx: BonusContext) -> BonusResult:
    req = int(_p(ctx, "text_count_required", 10))
    count = int(ctx.battle_state.get("consecutive_text_count", 0) or 0)
    if ctx.message_type == "text" and count >= req:
        total = int(ctx.battle_state.get("total_damage_dealt_fight", 0) or 0)
        bonus = int(round(total * float(_p(ctx, "bonus_pct", 0.15))))
        return BonusResult(damage_flat_bonus=bonus, notification="🧠 Поток сознания!")
    return BonusResult()


def handler_stacking_wrath(ctx: BonusContext) -> BonusResult:
    charges = int(ctx.battle_state.get("anger_charges", 0) or 0)
    max_ch = int(_p(ctx, "max_charges", 5))
    if ctx.message_type == "text":
        return BonusResult(battle_state_patch={"anger_charges": min(charges + 1, max_ch)})
    if charges > 0:
        mult = 1.0 + charges * float(_p(ctx, "bonus_per_charge", 0.5))
        return BonusResult(
            damage_multiplier=mult,
            battle_state_patch={"anger_charges": 0},
            notification=f"💥 Выброс гнева! ×{mult:.1f}",
        )
    return BonusResult()


def handler_hunter_experience(ctx: BonusContext) -> BonusResult:
    per = int(_p(ctx, "damage_per_stack", 100))
    stacks = int(ctx.battle_state.get("total_damage_dealt_fight", 0) or 0) // max(1, per)
    stacks = min(stacks, int(_p(ctx, "max_stacks", 20)))
    drop = 1.0 + stacks * float(_p(ctx, "drop_bonus_per_stack", 0.01))
    return BonusResult(drop_chance_multiplier=drop)


def handler_pain_collector(ctx: BonusContext) -> BonusResult:
    sold = int(ctx.battle_state.get("total_items_sold_session", 0) or 0)
    bonus = min(sold * float(_p(ctx, "bonus_per_sale", 0.01)), float(_p(ctx, "max_bonus", 0.20)))
    return BonusResult(damage_multiplier=1.0 + bonus)


def handler_first_daily_dungeon(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("first_daily_dungeon"):
        return BonusResult(drop_chance_multiplier=float(_p(ctx, "drop_multiplier", 2.0)))
    return BonusResult()


def handler_media_vampire(ctx: BonusContext) -> BonusResult:
    if ctx.message_type == "text":
        return BonusResult()
    if random.random() < float(_p(ctx, "proc_chance", 0.20)):
        return BonusResult(
            heal_pct_of_damage=float(_p(ctx, "heal_pct_of_damage", 0.15)),
            notification="🩸 Медиа-вампир!",
        )
    return BonusResult()


def handler_phantom_double(ctx: BonusContext) -> BonusResult:
    if random.random() < float(_p(ctx, "proc_chance", 0.03)):
        return BonusResult(
            extra_hits=[float(_p(ctx, "phantom_pct", 0.60))],
            notification="👥 Двойник!",
        )
    return BonusResult()


def handler_rarity_synergy(ctx: BonusContext) -> BonusResult:
    if ctx.equipped_legendary_count >= 2:
        return BonusResult(damage_multiplier=1.0 + float(_p(ctx, "damage_bonus", 0.15)))
    return BonusResult()


def handler_long_speech(ctx: BonusContext) -> BonusResult:
    if ctx.message_type != "voice":
        return BonusResult()
    dur = float(ctx.extra_data.get("voice_duration") or ctx.extra_data.get("audio_duration") or 0)
    if dur >= float(_p(ctx, "min_duration_seconds", 10)):
        return BonusResult(ignore_monster_death_damage=True, notification="🎤 Долгая речь!")
    return BonusResult()


def handler_monologue(ctx: BonusContext) -> BonusResult:
    if ctx.message_type != "text":
        return BonusResult()
    if ctx.message_length > int(_p(ctx, "length_threshold", 200)):
        pct = float(_p(ctx, "hit_pct", 0.45))
        hits = int(_p(ctx, "hit_count", 3))
        return BonusResult(damage_multiplier=0.0, extra_hits=[pct] * hits, notification="📜 Монолог!")
    return BonusResult()


def handler_charged_discharge(ctx: BonusContext) -> BonusResult:
    state = ctx.battle_state
    req = int(_p(ctx, "text_count_required", 5))
    if ctx.message_type == "text":
        new_count = int(state.get("consecutive_text_count", 0) or 0)
        patch = {}
        if new_count >= req:
            patch["discharge_ready"] = True
        return BonusResult(battle_state_patch=patch)
    if state.get("discharge_ready") and ctx.message_type != "text":
        return BonusResult(
            damage_multiplier=float(_p(ctx, "discharge_multiplier", 3.0)),
            battle_state_patch={"consecutive_text_count": 0, "discharge_ready": False},
            notification="⚡ Разряд!",
        )
    return BonusResult(battle_state_patch={"consecutive_text_count": 0, "discharge_ready": False})


def handler_media_trio(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("media_trio_active"):
        return BonusResult(damage_multiplier=1.0 + float(_p(ctx, "damage_bonus", 0.25)))
    used = set(ctx.battle_state.get("media_types_used") or [])
    if ctx.message_type in (_p(ctx, "required_types", ["sticker", "photo", "gif"]) or []):
        used.add(ctx.message_type)
    required = set(_p(ctx, "required_types", ["sticker", "photo", "gif"]) or [])
    patch = {"media_types_used": list(used)}
    if required.issubset(used):
        patch["media_trio_active"] = True
        return BonusResult(
            damage_multiplier=1.0 + float(_p(ctx, "damage_bonus", 0.25)),
            battle_state_patch=patch,
            notification="🎭 Медиа-трио!",
        )
    return BonusResult(battle_state_patch=patch)


def handler_crit_chain(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("crit_chain_ready"):
        return BonusResult(
            ignore_monster_dodge=True,
            ignore_monster_affixes=True,
            battle_state_patch={"crit_chain_ready": False, "consecutive_crit_count": 0},
            notification="⛓️ Цепь критов!",
        )
    return BonusResult()


def handler_crit_chain_after_crit(ctx: BonusContext, was_crit: bool) -> dict:
    if not was_crit:
        return {"consecutive_crit_count": 0}
    count = int(ctx.battle_state.get("consecutive_crit_count", 0) or 0) + 1
    req = int(_p(ctx, "crit_count_required", 3))
    patch = {"consecutive_crit_count": count}
    if count >= req:
        patch["crit_chain_ready"] = True
    return patch


def handler_type_hunter(ctx: BonusContext) -> BonusResult:
    used = set(ctx.battle_state.get("media_types_used") or [])
    if ctx.message_type != "text" and ctx.message_type in used:
        pass
    if ctx.message_type != "text":
        used.add(ctx.message_type)
    req = int(_p(ctx, "unique_types_required", 3))
    if len(used) >= req and ctx.battle_state.get("aoe_unlocked"):
        return BonusResult(
            remaining_monsters_damage_multiplier=float(_p(ctx, "aoe_multiplier", 0.6)),
            notification="🎯 Охотник на типы!",
        )
    patch: dict = {"media_types_used": list(used)}
    if len(used) >= req and not ctx.battle_state.get("aoe_unlocked"):
        patch["aoe_unlocked"] = True
    return BonusResult(battle_state_patch=patch)


def handler_double_sticker(ctx: BonusContext) -> BonusResult:
    if ctx.message_type != "sticker":
        return BonusResult()
    fid = str(ctx.extra_data.get("sticker_file_unique_id") or "")
    last = str(ctx.battle_state.get("last_sticker_file_id") or "")
    patch = {"last_sticker_file_id": fid}
    if fid and last and fid == last:
        return BonusResult(
            damage_multiplier=float(_p(ctx, "damage_multiplier", 4.0)),
            battle_state_patch=patch,
            notification="🔄 Настойчивость!",
        )
    return BonusResult(battle_state_patch=patch)


def handler_phoenix_rage(ctx: BonusContext) -> BonusResult:
    until = ctx.battle_state.get("phoenix_active_until")
    if not until:
        return BonusResult()
    try:
        exp = datetime.fromisoformat(str(until))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < exp:
            return BonusResult(damage_multiplier=float(_p(ctx, "damage_multiplier", 2.0)))
    except (TypeError, ValueError):
        pass
    return BonusResult()


def handler_revenge_crystal(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("crystal_discharged"):
        return BonusResult()
    charge = int(ctx.battle_state.get("crystal_charge", 0) or 0)
    if charge <= 0:
        return BonusResult()
    bonus = int(round(charge * float(_p(ctx, "return_multiplier", 1.5))))
    return BonusResult(
        damage_flat_bonus=bonus,
        battle_state_patch={"crystal_charge": 0, "crystal_discharged": True},
        notification=f"💎 Кристалл мести! +{bonus}",
    )


def handler_counter_curse(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("curse_counter_ready"):
        return BonusResult(
            damage_multiplier=1.0 + float(_p(ctx, "damage_bonus", 0.75)),
            clear_waifu_debuffs=True,
            battle_state_patch={"curse_counter_ready": False},
            notification="📿 Контрдеклятие!",
        )
    return BonusResult()


def handler_last_breath_attack(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("last_breath_ready"):
        return BonusResult(
            damage_multiplier=float(_p(ctx, "damage_multiplier", 5.0)),
            battle_state_patch={"last_breath_ready": False},
            notification="🔥 Последний вздох разряжен!",
        )
    return BonusResult()


def handler_kill_echo(ctx: BonusContext) -> BonusResult:
    if ctx.monster_is_first_in_room and int(ctx.battle_state.get("monsters_killed_session", 0) or 0) > 0:
        echo = int(round(int(ctx.battle_state.get("prev_fight_total_damage", 0) or 0) * float(_p(ctx, "echo_pct", 0.20))))
        if echo > 0:
            return BonusResult(damage_flat_bonus=echo, notification=f"👻 Эхо убийства! +{echo}")
    return BonusResult()


def handler_detonator(ctx: BonusContext) -> BonusResult:
    unique = len(set(ctx.battle_state.get("media_types_used") or []))
    if unique >= int(_p(ctx, "unique_media_types_required", 3)) and not ctx.battle_state.get("detonator_triggered"):
        return BonusResult(
            battle_state_patch={"detonator_triggered": True},
            notification="💣 Детонатор!",
        )
    return BonusResult()


def handler_living_artifact(ctx: BonusContext) -> BonusResult:
    result = BonusResult()
    mult = 1.0
    drop = 1.0
    gold = 1.0
    force_crit_chance = 0.0
    for row in _p(ctx, "levels", []) or []:
        try:
            lvl_req = int(row.get("waifu_level", 0))
        except (TypeError, ValueError):
            continue
        if ctx.waifu_level < lvl_req:
            continue
        bonus = str(row.get("bonus") or "")
        val = float(row.get("value", 1.0))
        if bonus == "damage_multiplier":
            mult *= val
        elif bonus == "drop_chance_multiplier":
            drop *= val
        elif bonus == "gold_multiplier":
            gold *= val
        elif bonus == "force_crit_chance" and random.random() < val:
            result.force_crit = True
    result.damage_multiplier = mult
    result.drop_chance_multiplier = drop
    result.gold_multiplier = gold
    return result


BONUS_HANDLERS: dict[str, Handler] = {
    "GOLD_PULSE": handler_gold_pulse,
    "AFFIX_MASTERY": handler_affix_mastery,
    "BOSS_SLAYER": handler_boss_slayer,
    "SNIPER_SHOT": handler_sniper_shot,
    "BREAKTHROUGH": handler_breakthrough,
    "AGONY": handler_agony,
    "WOUND_FURY": handler_wound_fury,
    "HUNT_FRENZY": handler_hunt_frenzy,
    "QUICK_REFLEX": handler_quick_reflex,
    "VERBOSITY": handler_verbosity,
    "PIERCING_SCREAM": handler_piercing_scream,
    "MYSTIC_SEVEN": handler_mystic_seven,
    "IMMUNITY_BREAKER": handler_immunity_breaker,
    "SURVIVOR_SPIRIT": handler_survivor_spirit,
    "SILENCE_BURST": handler_silence_burst,
    "AMBUSH_SILENCE": handler_ambush_silence,
    "MORNING_RITUAL": handler_morning_ritual,
    "NIGHT_SERENADE": handler_night_serenade,
    "MIDNIGHT_STRIKE": handler_midnight_strike,
    "FIRST_STICKER_OF_HOUR": handler_first_sticker_of_hour,
    "REVENGE_THIRST": handler_revenge_thirst,
    "COUNTER_DODGE": handler_counter_dodge,
    "KILLING_BLOW_HEAL": handler_killing_blow_heal,
    "THOUGHT_STREAM": handler_thought_stream,
    "STACKING_WRATH": handler_stacking_wrath,
    "HUNTER_EXPERIENCE": handler_hunter_experience,
    "PAIN_COLLECTOR": handler_pain_collector,
    "FIRST_DAILY_DUNGEON": handler_first_daily_dungeon,
    "MEDIA_VAMPIRE": handler_media_vampire,
    "PHANTOM_DOUBLE": handler_phantom_double,
    "RARITY_SYNERGY": handler_rarity_synergy,
    "LONG_SPEECH": handler_long_speech,
    "MONOLOGUE": handler_monologue,
    "CHARGED_DISCHARGE": handler_charged_discharge,
    "MEDIA_TRIO": handler_media_trio,
    "CRIT_CHAIN": handler_crit_chain,
    "TYPE_HUNTER": handler_type_hunter,
    "DOUBLE_STICKER": handler_double_sticker,
    "PHOENIX_RAGE": handler_phoenix_rage,
    "REVENGE_CRYSTAL": handler_revenge_crystal,
    "COUNTER_CURSE": handler_counter_curse,
    "LAST_BREATH": handler_last_breath_attack,
    "KILL_ECHO": handler_kill_echo,
    "DETONATOR": handler_detonator,
    "LIVING_ARTIFACT": handler_living_artifact,
    "TEAM_SPIRIT": _empty,
    "CROWD_INSPIRATION": _empty,
    "LAST_WORD": _empty,
}

DEATH_HANDLERS = frozenset({"KILLING_BLOW_HEAL"})

INCOMING_BONUS_KEYS = frozenset({"LAST_BREATH", "DAMAGE_MIRROR", "REVENGE_CRYSTAL"})
