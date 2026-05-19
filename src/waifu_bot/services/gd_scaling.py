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
