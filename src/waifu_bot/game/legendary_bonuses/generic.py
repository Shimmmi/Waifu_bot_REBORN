"""Generic parameterized handlers for the legendary bonus pool v2.

Bonus rows seeded by migration 0100 carry ``params["handler"] = <primitive>``.
The engine dispatches keys that have no bespoke handler in ``BONUS_HANDLERS``
to ``GENERIC_HANDLERS[primitive]``. The actual effect of a bonus is described
declaratively in ``params["effects"]`` (see ``build_effects``), so one
primitive serves many bonuses that differ only in trigger config and numbers.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from waifu_bot.game.legendary_bonuses.context import BonusContext, BonusResult

Handler = Callable[[BonusContext], BonusResult]

_PRIMES = frozenset({2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97})
_FIBONACCI = frozenset({1, 2, 3, 5, 8, 13, 21, 34, 55, 89})

# battle_state keys maintained by generic handlers (fight-scoped).
GENERIC_FIGHT_KEYS: tuple[str, ...] = (
    "gen_prev_type",
    "gen_norepeat_streak",
    "gen_fast_streak",
    "gen_last_interval",
    "gen_streak_text",
    "gen_streak_sticker",
    "gen_streak_photo",
    "gen_streak_gif",
    "gen_streak_audio",
    "gen_streak_video",
    "gen_streak_voice",
    "gen_streak_link",
    "gen_streak_media",
)


def _p(ctx: BonusContext, key: str, default=None):
    return (ctx.bonus_params or {}).get(key, default)


def build_effects(ctx: BonusContext, eff: dict[str, Any] | None, *, stacks: float = 1.0) -> BonusResult:
    """Translate a declarative effects dict into a BonusResult.

    ``stacks`` scales additive components (damage_bonus, damage_flat, ...).
    """
    if not eff or stacks <= 0:
        return BonusResult()
    res = BonusResult()
    if eff.get("damage_multiplier") is not None:
        res.damage_multiplier = float(eff["damage_multiplier"])
    if eff.get("damage_bonus") is not None:
        res.damage_multiplier *= 1.0 + float(eff["damage_bonus"]) * stacks
    if eff.get("max_damage_multiplier") is not None:
        res.damage_multiplier = min(res.damage_multiplier, float(eff["max_damage_multiplier"]))
    if eff.get("damage_flat"):
        res.damage_flat_bonus += int(round(float(eff["damage_flat"]) * stacks))
    if eff.get("damage_flat_pct_base"):
        res.damage_flat_bonus += int(round(ctx.base_damage * float(eff["damage_flat_pct_base"]) * stacks))
    if eff.get("replace_with_hits"):
        res.damage_multiplier = 0.0
        res.extra_hits.extend(float(x) for x in eff["replace_with_hits"])
    if eff.get("force_crit"):
        res.force_crit = True
    fcc = eff.get("force_crit_chance")
    if fcc and random.random() < float(fcc):
        res.force_crit = True
    if eff.get("crit_damage_multiplier"):
        res.crit_damage_multiplier = float(eff["crit_damage_multiplier"])
    for flag in (
        "ignore_monster_armor",
        "ignore_monster_affixes",
        "ignore_monster_dodge",
        "ignore_monster_death_damage",
        "clear_waifu_debuffs",
        "prevent_monster_death_spawn",
    ):
        if eff.get(flag):
            setattr(res, flag, True)
    if eff.get("extra_hits"):
        res.extra_hits.extend(float(x) for x in eff["extra_hits"])
    ehc = eff.get("extra_hit_chance")
    if ehc and random.random() < float(ehc):
        res.extra_hits.append(float(eff.get("extra_hit_pct", 0.5)))
    if eff.get("heal_flat"):
        res.heal_flat += int(eff["heal_flat"])
    if eff.get("heal_pct_max_hp"):
        res.heal_flat += int(round(ctx.waifu_hp_max * float(eff["heal_pct_max_hp"])))
    if eff.get("heal_pct_of_damage"):
        res.heal_pct_of_damage += float(eff["heal_pct_of_damage"])
    if eff.get("gold_multiplier"):
        res.gold_multiplier = float(eff["gold_multiplier"])
    if eff.get("gold_bonus"):
        res.gold_multiplier *= 1.0 + float(eff["gold_bonus"]) * stacks
    if eff.get("drop_chance_multiplier"):
        res.drop_chance_multiplier = float(eff["drop_chance_multiplier"])
    if eff.get("drop_bonus"):
        res.drop_chance_multiplier *= 1.0 + float(eff["drop_bonus"]) * stacks
    if eff.get("monster_self_damage_pct_base"):
        res.monster_self_damage = max(
            res.monster_self_damage, int(round(ctx.base_damage * float(eff["monster_self_damage_pct_base"])))
        )
    if eff.get("monster_self_damage"):
        res.monster_self_damage = max(res.monster_self_damage, int(eff["monster_self_damage"]))
    if eff.get("remaining_monsters_damage_multiplier"):
        res.remaining_monsters_damage_multiplier = float(eff["remaining_monsters_damage_multiplier"])
    if eff.get("notification"):
        res.notification = str(eff["notification"])
    return res


def _effects(ctx: BonusContext, *, stacks: float = 1.0) -> BonusResult:
    return build_effects(ctx, _p(ctx, "effects"), stacks=stacks)


def _local_now(ctx: BonusContext) -> datetime:
    tz_name = str(_p(ctx, "timezone", "Europe/Moscow"))
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = ctx.message_timestamp or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(tz)


# ── primitives ────────────────────────────────────────────────


def generic_media(ctx: BonusContext) -> BonusResult:
    """Trigger on message type. params: media_types[], not_in?, effects, else_effects?"""
    types = [str(t) for t in (_p(ctx, "media_types") or [])]
    match = ctx.message_type in types
    if _p(ctx, "not_in", False):
        match = not match
    if match:
        return _effects(ctx)
    return build_effects(ctx, _p(ctx, "else_effects"))


def generic_time_window(ctx: BonusContext) -> BonusResult:
    """Time of day / calendar window.

    params: hour_start?, hour_end? (wrap supported), weekdays? (iso 1-7),
    media_types?, mode? ("window" | "mirror_time"), timezone?, effects.
    """
    mt = _p(ctx, "media_types")
    if mt and ctx.message_type not in [str(t) for t in mt]:
        return BonusResult()
    local = _local_now(ctx)
    weekdays = _p(ctx, "weekdays")
    if weekdays and local.isoweekday() not in [int(x) for x in weekdays]:
        return BonusResult()
    mode = str(_p(ctx, "mode", "window"))
    if mode == "mirror_time":
        if local.hour != local.minute:
            return BonusResult()
    elif mode == "even_hour":
        if local.hour % 2 != 0:
            return BonusResult()
    elif mode == "odd_hour":
        if local.hour % 2 != 1:
            return BonusResult()
    elif mode == "hour_mod":
        if local.hour % max(1, int(_p(ctx, "mod", 3))) != int(_p(ctx, "remainder", 0)):
            return BonusResult()
    else:
        hs, he = _p(ctx, "hour_start"), _p(ctx, "hour_end")
        if hs is not None and he is not None:
            hs, he, h = int(hs), int(he), local.hour
            inside = (hs <= h < he) if hs <= he else (h >= hs or h < he)
            if not inside:
                return BonusResult()
    return _effects(ctx)


def generic_tempo(ctx: BonusContext) -> BonusResult:
    """Message pacing. params: mode, window_seconds / min_seconds / max_seconds,
    media_types?, max_stacks?, effects."""
    mt = _p(ctx, "media_types")
    if mt and ctx.message_type not in [str(t) for t in mt]:
        return BonusResult()
    sec = float(ctx.seconds_since_last_attack)
    mode = str(_p(ctx, "mode", "fast"))
    if mode == "fast":
        if sec < float(_p(ctx, "window_seconds", 5)):
            return _effects(ctx)
        return BonusResult()
    if mode == "pause":
        if sec >= float(_p(ctx, "min_seconds", 60)):
            return _effects(ctx)
        return BonusResult()
    if mode == "band":
        if float(_p(ctx, "min_seconds", 10)) <= sec < float(_p(ctx, "max_seconds", 30)):
            return _effects(ctx)
        return BonusResult()
    if mode == "pause_scaled":
        if sec < float(_p(ctx, "min_seconds", 60)):
            return BonusResult()
        stacks = min(sec / 60.0, float(_p(ctx, "max_stacks", 10)))
        return _effects(ctx, stacks=stacks)
    if mode == "fast_streak":
        window = float(_p(ctx, "window_seconds", 10))
        streak = int(ctx.battle_state.get("gen_fast_streak", 0) or 0)
        streak = streak + 1 if sec < window else 0
        res = _effects(ctx, stacks=min(streak, int(_p(ctx, "max_stacks", 10))))
        res.battle_state_patch = {**res.battle_state_patch, "gen_fast_streak": streak}
        return res
    if mode == "rhythm":
        last = ctx.battle_state.get("gen_last_interval")
        res = BonusResult()
        if last is not None and float(last) > 0:
            tolerance = float(_p(ctx, "tolerance", 0.2))
            if abs(sec - float(last)) <= float(last) * tolerance:
                res = _effects(ctx)
        res.battle_state_patch = {**res.battle_state_patch, "gen_last_interval": round(sec, 2)}
        return res
    return BonusResult()


def generic_text_length(ctx: BonusContext) -> BonusResult:
    """Text length conditions. params: op (gt|lt|eq|between|even|odd),
    length / min_length / max_length, per_block?, max_stacks?, effects."""
    if ctx.message_type != "text":
        return BonusResult()
    n = int(ctx.message_length or 0)
    op = str(_p(ctx, "op", "gt"))
    if op == "gt":
        threshold = int(_p(ctx, "length", 100))
        if n <= threshold:
            return BonusResult()
        block = int(_p(ctx, "per_block", 0) or 0)
        if block > 0:
            stacks = min((n - threshold) // block + 1, int(_p(ctx, "max_stacks", 10)))
            return _effects(ctx, stacks=stacks)
        return _effects(ctx)
    if op == "lt":
        return _effects(ctx) if 0 < n < int(_p(ctx, "length", 5)) else BonusResult()
    if op == "eq":
        return _effects(ctx) if n == int(_p(ctx, "length", 7)) else BonusResult()
    if op == "between":
        if int(_p(ctx, "min_length", 10)) <= n <= int(_p(ctx, "max_length", 20)):
            return _effects(ctx)
        return BonusResult()
    if op == "even":
        return _effects(ctx) if n > 0 and n % 2 == 0 else BonusResult()
    if op == "odd":
        return _effects(ctx) if n % 2 == 1 else BonusResult()
    return BonusResult()


def generic_text_content(ctx: BonusContext) -> BonusResult:
    """Text content conditions (requires extra_data["text"] from the pipeline).

    params: mode (caps|question|exclamation|emoji|digits_only|one_word|
    palindrome|word_count_gt|same_char), word_count?, effects.
    """
    if ctx.message_type != "text":
        return BonusResult()
    txt = ctx.extra_data.get("text")
    if not isinstance(txt, str) or not txt.strip():
        return BonusResult()
    s = txt.strip()
    mode = str(_p(ctx, "mode", "caps"))
    letters = [c for c in s if c.isalpha()]
    triggered = False
    if mode == "caps":
        triggered = len(letters) >= 3 and all(c.isupper() for c in letters)
    elif mode == "question":
        triggered = s.endswith("?")
    elif mode == "exclamation":
        triggered = s.endswith("!")
    elif mode == "emoji":
        triggered = any(ord(c) >= 0x1F000 for c in s)
    elif mode == "digits_only":
        triggered = s.isdigit()
    elif mode == "one_word":
        triggered = len(s.split()) == 1 and len(s) >= 2
    elif mode == "palindrome":
        norm = "".join(c.lower() for c in s if c.isalnum())
        triggered = len(norm) >= 3 and norm == norm[::-1]
    elif mode == "word_count_gt":
        triggered = len(s.split()) > int(_p(ctx, "word_count", 20))
    elif mode == "same_char":
        norm = s.replace(" ", "")
        triggered = len(norm) >= 3 and len(set(norm.lower())) == 1
    return _effects(ctx) if triggered else BonusResult()


def generic_counter(ctx: BonusContext) -> BonusResult:
    """Combo / counter mechanics over battle_state.

    params: mode (every_n|milestone|prime|fibonacci|text_streak|type_streak|
    no_repeat_streak|alternate|unique_media), n?, media_type?, max_stacks?,
    min_stacks?, effects.
    """
    state = ctx.battle_state
    total = int(state.get("total_messages_in_fight", 0) or 0)
    mode = str(_p(ctx, "mode", "every_n"))
    if mode == "every_n":
        n = int(_p(ctx, "n", 5))
        return _effects(ctx) if total > 0 and total % n == 0 else BonusResult()
    if mode == "milestone":
        return _effects(ctx) if total == int(_p(ctx, "n", 25)) else BonusResult()
    if mode == "prime":
        return _effects(ctx) if total in _PRIMES else BonusResult()
    if mode == "fibonacci":
        return _effects(ctx) if total in _FIBONACCI else BonusResult()
    if mode == "text_streak":
        if ctx.message_type != "text":
            return BonusResult()
        streak = int(state.get("consecutive_text_count", 0) or 0)
        if streak < int(_p(ctx, "min_stacks", 2)):
            return BonusResult()
        return _effects(ctx, stacks=min(streak, int(_p(ctx, "max_stacks", 10))))
    if mode == "type_streak":
        target = str(_p(ctx, "media_type", "sticker"))
        key = f"gen_streak_{target}"
        matched = (ctx.message_type != "text") if target == "media" else (ctx.message_type == target)
        streak = int(state.get(key, 0) or 0) + 1 if matched else 0
        res = BonusResult()
        if matched and streak >= int(_p(ctx, "min_stacks", 2)):
            res = _effects(ctx, stacks=min(streak, int(_p(ctx, "max_stacks", 10))))
        res.battle_state_patch = {**res.battle_state_patch, key: streak}
        return res
    if mode == "no_repeat_streak":
        prev = state.get("gen_prev_type")
        streak = int(state.get("gen_norepeat_streak", 0) or 0)
        streak = streak + 1 if (prev and prev != ctx.message_type) else 0
        res = BonusResult()
        if streak >= int(_p(ctx, "min_stacks", 1)):
            res = _effects(ctx, stacks=min(streak, int(_p(ctx, "max_stacks", 10))))
        res.battle_state_patch = {
            **res.battle_state_patch,
            "gen_prev_type": ctx.message_type,
            "gen_norepeat_streak": streak,
        }
        return res
    if mode == "alternate":
        prev = state.get("gen_prev_type")
        res = _effects(ctx) if (prev and prev != ctx.message_type) else BonusResult()
        res.battle_state_patch = {**res.battle_state_patch, "gen_prev_type": ctx.message_type}
        return res
    if mode == "repeat_type":
        prev = state.get("gen_prev_type")
        res = _effects(ctx) if (prev and prev == ctx.message_type) else BonusResult()
        res.battle_state_patch = {**res.battle_state_patch, "gen_prev_type": ctx.message_type}
        return res
    if mode == "unique_media":
        used = len(set(state.get("media_types_used") or []))
        return _effects(ctx) if used >= int(_p(ctx, "n", 3)) else BonusResult()
    return BonusResult()


def generic_hp_state(ctx: BonusContext) -> BonusResult:
    """HP conditions. params: side (waifu|monster), op (below|above|between|
    full|per_missing|david), pct / min_pct / max_pct, per_stack via effects,
    max_stacks?, ratio?, effects."""
    side = str(_p(ctx, "side", "waifu"))
    cur, mx = (ctx.waifu_hp_current, ctx.waifu_hp_max) if side == "waifu" else (
        ctx.monster_hp_current,
        ctx.monster_hp_max,
    )
    if mx <= 0:
        return BonusResult()
    pct = cur / max(1, mx)
    op = str(_p(ctx, "op", "below"))
    if op == "below":
        return _effects(ctx) if pct <= float(_p(ctx, "pct", 0.5)) else BonusResult()
    if op == "above":
        return _effects(ctx) if pct >= float(_p(ctx, "pct", 0.8)) else BonusResult()
    if op == "between":
        if float(_p(ctx, "min_pct", 0.4)) <= pct <= float(_p(ctx, "max_pct", 0.6)):
            return _effects(ctx)
        return BonusResult()
    if op == "full":
        return _effects(ctx) if pct >= 0.999 else BonusResult()
    if op == "per_missing":
        stacks = int((1.0 - pct) / 0.10)
        return _effects(ctx, stacks=min(stacks, int(_p(ctx, "max_stacks", 8))))
    if op == "david":
        if ctx.monster_hp_max >= float(_p(ctx, "ratio", 2.0)) * max(1, ctx.waifu_hp_max):
            return _effects(ctx)
        return BonusResult()
    return BonusResult()


def generic_monster_state(ctx: BonusContext) -> BonusResult:
    """Monster conditions. params: condition (boss|not_boss|elite|clean|
    first_hit|affix_scaled|id_mod|big_hp), mod?, remainder?, value?,
    max_stacks?, effects."""
    cond = str(_p(ctx, "condition", "boss"))
    if cond == "boss":
        return _effects(ctx) if ctx.monster_is_boss else BonusResult()
    if cond == "not_boss":
        return _effects(ctx) if not ctx.monster_is_boss else BonusResult()
    if cond == "elite":
        return _effects(ctx) if ctx.monster_affixes else BonusResult()
    if cond == "clean":
        return _effects(ctx) if not ctx.monster_affixes else BonusResult()
    if cond == "first_hit":
        return _effects(ctx) if ctx.monster_is_first_in_room else BonusResult()
    if cond == "affix_scaled":
        n = len(ctx.monster_affixes or [])
        return _effects(ctx, stacks=min(n, int(_p(ctx, "max_stacks", 5)))) if n else BonusResult()
    if cond == "id_mod":
        mod = int(_p(ctx, "mod", 7))
        if mod > 0 and ctx.monster_id % mod == int(_p(ctx, "remainder", 0)):
            return _effects(ctx)
        return BonusResult()
    if cond == "big_hp":
        return _effects(ctx) if ctx.monster_hp_max >= int(_p(ctx, "value", 500)) else BonusResult()
    return BonusResult()


def generic_session_scale(ctx: BonusContext) -> BonusResult:
    """Run-progress scaling. params: mode (per_kill|echo|fight_damage),
    per_damage?, echo_pct?, require_first_hit?, max_stacks?, effects."""
    state = ctx.battle_state
    mode = str(_p(ctx, "mode", "per_kill"))
    if mode == "per_kill":
        kills = int(state.get("monsters_killed_session", 0) or 0)
        if kills <= 0:
            return BonusResult()
        return _effects(ctx, stacks=min(kills, int(_p(ctx, "max_stacks", 10))))
    if mode == "echo":
        if _p(ctx, "require_first_hit", True) and not ctx.monster_is_first_in_room:
            return BonusResult()
        prev = int(state.get("prev_fight_total_damage", 0) or 0)
        flat = int(round(prev * float(_p(ctx, "echo_pct", 0.10))))
        if flat <= 0:
            return BonusResult()
        res = _effects(ctx)
        res.damage_flat_bonus += flat
        return res
    if mode == "fight_damage":
        per = int(_p(ctx, "per_damage", 200))
        stacks = int(state.get("total_damage_dealt_fight", 0) or 0) // max(1, per)
        if stacks <= 0:
            return BonusResult()
        return _effects(ctx, stacks=min(stacks, int(_p(ctx, "max_stacks", 10))))
    if mode == "session_damage":
        per = int(_p(ctx, "per_damage", 300))
        stacks = int(state.get("total_damage_dealt_session", 0) or 0) // max(1, per)
        if stacks <= 0:
            return BonusResult()
        return _effects(ctx, stacks=min(stacks, int(_p(ctx, "max_stacks", 15))))
    if mode == "received_damage":
        per = int(_p(ctx, "per_damage", 50))
        stacks = int(state.get("received_damage_this_fight", 0) or 0) // max(1, per)
        if stacks <= 0:
            return BonusResult()
        return _effects(ctx, stacks=min(stacks, int(_p(ctx, "max_stacks", 10))))
    if mode == "items_sold":
        sold = int(state.get("total_items_sold_session", 0) or 0)
        if sold <= 0:
            return BonusResult()
        return _effects(ctx, stacks=min(sold, int(_p(ctx, "max_stacks", 20))))
    return BonusResult()


def generic_economy(ctx: BonusContext) -> BonusResult:
    """Gold/MF effects with optional gold conditions.

    params: condition? (gold_above|gold_below), value?, effects."""
    cond = _p(ctx, "condition")
    if cond == "gold_above" and ctx.waifu_gold <= int(_p(ctx, "value", 1000)):
        return BonusResult()
    if cond == "gold_below" and ctx.waifu_gold >= int(_p(ctx, "value", 100)):
        return BonusResult()
    return _effects(ctx)


def generic_meta_scale(ctx: BonusContext) -> BonusResult:
    """Meta/inventory scaling. params: source (legendary_count|waifu_level|stat),
    mode, stat?, value?, per_n?, max_stacks?, effects."""
    source = str(_p(ctx, "source", "legendary_count"))
    mode = str(_p(ctx, "mode", "at_least"))
    if source == "legendary_count":
        count = int(ctx.equipped_legendary_count or 0)
        if mode == "equals":
            return _effects(ctx) if count == int(_p(ctx, "value", 1)) else BonusResult()
        if mode == "at_least":
            return _effects(ctx) if count >= int(_p(ctx, "value", 2)) else BonusResult()
        if mode == "per_item":
            return _effects(ctx, stacks=min(count, int(_p(ctx, "max_stacks", 6)))) if count else BonusResult()
    elif source == "waifu_level":
        lvl = int(ctx.waifu_level or 1)
        if mode == "above":
            return _effects(ctx) if lvl >= int(_p(ctx, "value", 30)) else BonusResult()
        if mode == "below":
            return _effects(ctx) if lvl <= int(_p(ctx, "value", 20)) else BonusResult()
        if mode == "per_n_levels":
            stacks = lvl // max(1, int(_p(ctx, "per_n", 10)))
            return _effects(ctx, stacks=min(stacks, int(_p(ctx, "max_stacks", 5)))) if stacks else BonusResult()
    elif source == "stat":
        stat = str(_p(ctx, "stat", "luck"))
        val = int((ctx.waifu_stats or {}).get(stat, 0) or 0)
        if mode == "above":
            return _effects(ctx) if val >= int(_p(ctx, "value", 50)) else BonusResult()
        if mode == "per_points":
            stacks = val // max(1, int(_p(ctx, "per_n", 20)))
            return _effects(ctx, stacks=min(stacks, int(_p(ctx, "max_stacks", 5)))) if stacks else BonusResult()
    return BonusResult()


def generic_state_flag(ctx: BonusContext) -> BonusResult:
    """Trigger on a truthy battle_state flag (or known ctx flag).

    params: flag, consume? (reset to False after trigger), effects.
    Flags ``counter_dodge_ready`` / ``curse_counter_ready`` are set by the
    retaliation hooks when params contain ``listen_dodge`` / ``listen_debuff``.
    """
    flag = str(_p(ctx, "flag", "revenge_ready"))
    if flag == "waifu_last_dungeon_knocked_out":
        value = ctx.waifu_last_dungeon_knocked_out
    else:
        value = ctx.battle_state.get(flag)
    if not value:
        return BonusResult()
    res = _effects(ctx)
    if _p(ctx, "consume", False):
        res.battle_state_patch = {**res.battle_state_patch, flag: False}
    return res


def generic_random_proc(ctx: BonusContext) -> BonusResult:
    """Random procs. params: media_types?, proc_chance + effects, or outcomes
    [{chance, effects}], or uniform {min_mult, max_mult}."""
    mt = _p(ctx, "media_types")
    if mt and ctx.message_type not in [str(t) for t in mt]:
        return BonusResult()
    uniform = _p(ctx, "uniform")
    if uniform:
        lo, hi = float(uniform.get("min_mult", 0.5)), float(uniform.get("max_mult", 2.0))
        res = _effects(ctx)
        res.damage_multiplier *= random.uniform(lo, hi)
        return res
    outcomes = _p(ctx, "outcomes")
    if outcomes:
        roll = random.random()
        acc = 0.0
        for outcome in outcomes:
            acc += float(outcome.get("chance", 0.0))
            if roll < acc:
                return build_effects(ctx, outcome.get("effects"))
        return BonusResult()
    if random.random() < float(_p(ctx, "proc_chance", 0.1)):
        return _effects(ctx)
    return BonusResult()


def generic_passive(ctx: BonusContext) -> BonusResult:
    """Unconditional effects."""
    return _effects(ctx)


def generic_on_kill(ctx: BonusContext) -> BonusResult:
    """Death-phase effects (dispatched from run_death_handlers).

    params: proc_chance?, effects (heal_flat / heal_pct_max_hp)."""
    chance = float(_p(ctx, "proc_chance", 1.0))
    if chance < 1.0 and random.random() >= chance:
        return BonusResult()
    return _effects(ctx)


GENERIC_HANDLERS: dict[str, Handler] = {
    "media": generic_media,
    "time_window": generic_time_window,
    "tempo": generic_tempo,
    "text_length": generic_text_length,
    "text_content": generic_text_content,
    "counter": generic_counter,
    "hp_state": generic_hp_state,
    "monster_state": generic_monster_state,
    "session_scale": generic_session_scale,
    "economy": generic_economy,
    "meta_scale": generic_meta_scale,
    "state_flag": generic_state_flag,
    "random_proc": generic_random_proc,
    "passive": generic_passive,
}

# Death-phase primitive dispatched separately by the engine.
GENERIC_DEATH_PRIMITIVE = "on_kill"
