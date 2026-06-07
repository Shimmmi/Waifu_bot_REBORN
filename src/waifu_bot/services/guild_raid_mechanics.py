"""Mechanical resolution for guild raid v2 daily tactics."""
from __future__ import annotations

import random
from typing import Any

MUSTER_HOURS = 3
TACTIC_POLL_HOURS = 3
RAID_WEEK_DAYS = 7

NEUTRAL_TACTIC = {
    "label": "Осторожный марш",
    "mechanics": {
        "risk": "low",
        "vitality_range": [-8, -2],
        "progress_range": [4, 8],
        "terrain_fit": [],
    },
}

RISK_VITALITY = {
    "low": (-12, -2),
    "medium": (-18, 2),
    "high": (-28, -4),
}

RISK_PROGRESS = {
    "low": (3, 10),
    "medium": (6, 14),
    "high": (10, 20),
}


def mechanics_for_tactic_option(
    *,
    label: str,
    risk: str,
    terrain_fit: list[str] | None = None,
) -> dict[str, Any]:
    risk = (risk or "medium").strip().lower()
    if risk not in RISK_VITALITY:
        risk = "medium"
    v_lo, v_hi = RISK_VITALITY[risk]
    p_lo, p_hi = RISK_PROGRESS[risk]
    return {
        "label": label,
        "mechanics": {
            "risk": risk,
            "vitality_range": [v_lo, v_hi],
            "progress_range": [p_lo, p_hi],
            "terrain_fit": list(terrain_fit or []),
        },
    }


def _lerp_range(rng: list[int] | tuple[int, int]) -> float:
    lo, hi = int(rng[0]), int(rng[1])
    if lo > hi:
        lo, hi = hi, lo
    return random.uniform(lo, hi)


def party_level_modifier(avg_level: float, guild_level: int) -> float:
    expected = max(5.0, float(guild_level) * 2.5)
    diff = (avg_level - expected) / max(expected, 1.0)
    return max(0.9, min(1.1, 1.0 + diff * 0.15))


def resolve_daily_tactic(
    *,
    tactic: dict[str, Any],
    location_archetype_id: str | None,
    party_snapshot: list[dict[str, Any]] | None,
    guild_level: int,
) -> dict[str, Any]:
    mech = dict(tactic.get("mechanics") or {})
    if not mech:
        mech = dict(NEUTRAL_TACTIC["mechanics"])

    vitality_delta = _lerp_range(mech.get("vitality_range") or [-8, -2])
    progress_delta = _lerp_range(mech.get("progress_range") or [4, 8])

    terrain_fit = [str(x).lower() for x in (mech.get("terrain_fit") or [])]
    loc = (location_archetype_id or "").lower()
    terrain_bonus = 1.15 if loc and loc in terrain_fit else 1.0
    progress_delta *= terrain_bonus

    levels = [float(p.get("level") or 1) for p in (party_snapshot or [])]
    avg_level = sum(levels) / max(1, len(levels))
    mod = party_level_modifier(avg_level, guild_level)
    vitality_delta = int(round(vitality_delta * mod)) + random.randint(-5, 5)
    progress_delta = max(1, int(round(progress_delta * mod)))

    return {
        "tactic_label": tactic.get("label") or NEUTRAL_TACTIC["label"],
        "vitality_delta": vitality_delta,
        "progress_delta": progress_delta,
        "terrain_bonus_applied": terrain_bonus > 1.0,
        "party_modifier": round(mod, 3),
    }


def outcome_tier(*, vitality: int, progress: int, day_index: int) -> str:
    if vitality <= 0:
        return "defeat"
    if day_index < RAID_WEEK_DAYS:
        return "ongoing"
    if progress >= 70:
        return "victory"
    if progress >= 40:
        return "partial"
    return "failed"


def gxp_multiplier_for_outcome(outcome: str) -> float:
    return {
        "victory": 1.0,
        "partial": 0.7,
        "failed": 0.35,
        "defeat": 0.4,
    }.get(outcome, 0.0)
