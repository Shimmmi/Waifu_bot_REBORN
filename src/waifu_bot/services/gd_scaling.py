"""GD v1: challenge level, HP normalization, activity scoring for rewards.

Соло-статы игрока (STR/AGI/INT/УДЧ с экипом и пассивами) считаются в `waifu_bot.game.effective_stats`;
GD использует отдельный контур боя в `services/gd/`, без дублирования этого модуля.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import MonsterTemplate
from waifu_bot.services.game_config_service import cfg_float

MEDIA_WEIGHT_KEYS = {
    "sticker": "gd_activity_weight_sticker",
    "photo": "gd_activity_weight_photo",
    "gif": "gd_activity_weight_gif",
    "video": "gd_activity_weight_video",
    "voice": "gd_activity_weight_voice",
}

MEDIA_DEFAULTS: dict[str, float] = {
    "sticker": 12.0,
    "photo": 15.0,
    "gif": 14.0,
    "video": 16.0,
    "voice": 28.0,
}


def compute_challenge_level(levels: list[int], cfg: dict[str, str]) -> int:
    """Weighted blend of avg / max / min party level; clamp 1..60."""
    if not levels:
        return 1
    lv = [max(1, min(60, int(x))) for x in levels]
    avg = sum(lv) // len(lv)
    if len(lv) == 1:
        return avg
    mx = max(lv)
    mn = min(lv)
    w_avg = cfg_float(cfg, "gd_cl_w_avg", 1.0)
    w_max = cfg_float(cfg, "gd_cl_w_max", 0.35)
    w_min = cfg_float(cfg, "gd_cl_w_min", 0.15)
    denom = w_avg + w_max + w_min
    if denom <= 0:
        return max(1, min(60, avg))
    val = (w_avg * avg + w_max * mx + w_min * mn) / denom
    return max(1, min(60, int(round(val))))


def ref_hp_trash(
    mt: MonsterTemplate | None,
    level: int,
    n_players: int,
    hp_scale: float,
) -> int:
    """Reference max HP for same template at level (with party scale), for damage normalization."""
    level = max(1, min(60, int(level)))
    n = max(1, int(n_players))
    if mt is None:
        base = 40 + 10 * level
    else:
        base = int(mt.hp_base or 40) + int(mt.hp_per_level or 10) * level
    return max(1, int(base * n * hp_scale))


def ref_hp_boss(mt: MonsterTemplate | None, level: int, boss_mult: float) -> int:
    level = max(1, min(60, int(level)))
    if mt is None:
        base = 40 + 10 * level
    else:
        base = int(mt.hp_base or 40) + int(mt.hp_per_level or 10) * level
    return max(1, int(base * float(boss_mult)))


def normalized_damage_to_global_hp(global_max_hp: int, raw_damage: int, ref_hp: int) -> int:
    """Map raw simulated damage to slice of global pool: H_g * min(1, raw / H_ref(L))."""
    if raw_damage <= 0:
        return 0
    g = max(1, int(global_max_hp))
    r = max(1, int(ref_hp))
    frac = min(1.0, float(raw_damage) / float(r))
    delta = int(g * frac)
    if delta < 1:
        delta = 1
    return min(delta, g)


def activity_score_round_for_user(ubuf: dict[str, Any], cfg: dict[str, str]) -> float:
    """Activity points for one player in one round (buffer user entry)."""
    cap = cfg_float(cfg, "gd_activity_text_effective_cap", 400.0)
    w_text = cfg_float(cfg, "gd_activity_weight_text_per_char", 1.0)
    floor_ns = cfg_float(cfg, "gd_activity_weight_non_silent_floor", 8.0)

    text_len = int(ubuf.get("text_len") or 0)
    eff = min(float(text_len), cap)
    score = eff * w_text
    for mk in ubuf.get("media") or []:
        mk_s = str(mk)
        key = MEDIA_WEIGHT_KEYS.get(mk_s)
        d = MEDIA_DEFAULTS.get(mk_s, 12.0)
        w = cfg_float(cfg, key, d) if key else d
        score += w
    silent = bool(ubuf.get("silent", True))
    if not silent and (eff > 0 or (ubuf.get("media") or [])):
        score += floor_ns
    return float(score)


def merge_activity_totals_from_buffer(
    state: dict[str, Any], buffer: dict[str, Any] | None, cfg: dict[str, str]
) -> None:
    totals: dict[str, float] = state.setdefault("activity_totals", {})
    users = (buffer or {}).get("users") or {}
    for uid, u in users.items():
        if not isinstance(u, dict):
            continue
        sc = activity_score_round_for_user(u, cfg)
        totals[str(uid)] = float(totals.get(str(uid), 0.0)) + sc


async def monster_template_for_state(session: AsyncSession, m: dict[str, Any]) -> MonsterTemplate | None:
    tid = int(m.get("template_id") or 0)
    if tid <= 0:
        return None
    return await session.get(MonsterTemplate, tid)


def reward_level_multiplier(level: int, cfg: dict[str, str]) -> float:
    """Scale reward baseline by waifu level (personal payout)."""
    lv = max(1, min(60, int(level)))
    per = cfg_float(cfg, "gd_reward_scale_per_level", 0.02)
    return 1.0 + float(lv - 1) * per


def power_score_from_contrib(c: dict[str, Any] | None) -> float:
    """Combat power contribution from contribution dict."""
    c = c or {}
    return (
        float(c.get("text") or 0) * 1.0
        + float(c.get("skill") or 0) * 1.5
        + float(c.get("heal") or 0) * 1.2
        + float(c.get("rounds") or 0) * 10.0
        + float(c.get("assists") or 0) * 25.0
    )


def late_join_reward_stage_mult(
    joined_at_round: int,
    total_rounds: int,
    cfg: dict[str, str],
) -> float:
    """Reward multiplier by join stage: earlier join → closer to 1.0.

    stage_mult = clamp(
      1 - (joined_at_round - 1) / max(1, total_rounds) * penalty_scale,
      min_mult,
      1.0,
    )
    """
    jr = max(1, int(joined_at_round or 1))
    tr = max(1, int(total_rounds or 1))
    scale = cfg_float(cfg, "gd_late_join_penalty_scale", 1.0)
    min_m = cfg_float(cfg, "gd_late_join_min_mult", 0.35)
    raw = 1.0 - (float(jr - 1) / float(tr)) * scale
    return max(min_m, min(1.0, raw))


def presence_score_for_uid(
    uid: int,
    activity: dict[str, Any] | None,
    contrib: dict[str, Any] | None,
    *,
    floor: float = 8.0,
    apply_floor: bool = True,
) -> float:
    """Chat presence / engagement score with optional non-zero floor."""
    sc = float((activity or {}).get(str(uid), 0.0) or 0.0)
    if sc < 1.0:
        sc = power_score_from_contrib((contrib or {}).get(str(uid)))
    if apply_floor and sc < floor:
        sc = floor
    return float(sc)


def blend_dual_reward_scores(
    uids: list[int],
    activity: dict[str, Any] | None,
    contrib: dict[str, Any] | None,
    cfg: dict[str, str],
    *,
    joined_at_round_by_uid: dict[int, int] | None = None,
) -> dict[int, float]:
    """Blend presence + power shares into final reward weights.

    Defaults: 0.55 presence + 0.45 power (game_config overridable).
    Presence floor applies only for full-run joiners (joined_at_round==1) or
    players with at least one contrib round.
    """
    w_presence = cfg_float(cfg, "gd_reward_presence_weight", 0.55)
    w_power = cfg_float(cfg, "gd_reward_power_weight", 0.45)
    denom = w_presence + w_power
    if denom <= 0:
        w_presence, w_power, denom = 0.55, 0.45, 1.0
    w_presence /= denom
    w_power /= denom

    jar = joined_at_round_by_uid or {}
    presence: dict[int, float] = {}
    power: dict[int, float] = {}
    for uid in uids:
        c = (contrib or {}).get(str(uid)) or {}
        jr = int(jar.get(uid, 1) or 1)
        rounds = int(c.get("rounds") or 0)
        apply_floor = jr <= 1 or rounds >= 1
        presence[uid] = presence_score_for_uid(
            uid, activity, contrib, apply_floor=apply_floor
        )
        power[uid] = max(0.0, power_score_from_contrib(c))
    sum_p = sum(presence.values()) or 1.0
    sum_pw = sum(power.values()) or 1.0
    out: dict[int, float] = {}
    for uid in uids:
        out[uid] = w_presence * (presence[uid] / sum_p) + w_power * (power[uid] / sum_pw)
    return out



def wipe_reward_multiplier(wipe_count: int, cfg: dict[str, str]) -> float:
    """Penalty mult for party wipes during the cycle (IDLE soft-fail)."""
    n = max(0, int(wipe_count))
    per = cfg_float(cfg, "gd_wipe_penalty_pct", 0.25)
    floor = cfg_float(cfg, "gd_wipe_penalty_floor", 0.40)
    return max(floor, 1.0 - per * n)


def clean_run_bonus_multiplier(wipe_count: int, cfg: dict[str, str]) -> float:
    """Bonus when the party never wiped."""
    if int(wipe_count) > 0:
        return 1.0
    return 1.0 + cfg_float(cfg, "gd_clean_run_bonus_pct", 0.20)


def thematic_class_damage_mult(
    class_id: int,
    thematic_class_ids: list[Any] | None,
    cfg: dict[str, str],
) -> float:
    """Damage mult if waifu class is thematic for the dungeon template."""
    if not thematic_class_ids:
        return 1.0
    try:
        ids = {int(x) for x in thematic_class_ids}
    except (TypeError, ValueError):
        return 1.0
    if int(class_id) not in ids:
        return 1.0
    return cfg_float(cfg, "gd_thematic_bonus_mult", 1.15)


def maybe_grant_hp_break_assist(
    state: dict[str, Any],
    uid: int,
    monster: dict[str, Any],
    hp_before: int,
    hp_after: int,
) -> bool:
    """Grant assist credit when a hit crosses 50%/25%/0% HP thresholds. Returns True if granted."""
    mx = max(1, int(monster.get("max_hp") or 1))
    before_pct = 100.0 * max(0, int(hp_before)) / mx
    after_pct = 100.0 * max(0, int(hp_after)) / mx
    thresholds = (50.0, 25.0, 0.0)
    crossed = any(before_pct > t >= after_pct for t in thresholds)
    if not crossed:
        return False
    assists = state.setdefault("assists", {})
    key = str(uid)
    assists[key] = int(assists.get(key) or 0) + 1
    contrib = state.setdefault("contribution", {})
    c = contrib.setdefault(key, {"text": 0, "skill": 0, "heal": 0, "rounds": 0, "assists": 0})
    c["assists"] = int(c.get("assists") or 0) + 1
    return True
