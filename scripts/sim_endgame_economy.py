#!/usr/bin/env python3
"""Endgame economy simulator for P61/P70/P80 launch vs full corridors.

Prints stipend / dust / core / ember / rarity-up / kill-gold-bonus lines.
Phase 0 is not closed unless these corridors print.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

STIPEND = {1: 2000, 2: 3000, 3: 4500, 4: 6500, 5: 9000}
DUST_BONUS = {1: 0, 2: 0, 3: 15, 4: 25, 5: 40}
CORE_CHANCE = {1: 0.0, 2: 0.0, 3: 0.08, 4: 0.12, 5: 0.18}
GOLD_MULT = {1: 1.3, 2: 1.6, 3: 2.0, 4: 2.5, 5: 3.2}
RARITY_STEPS = {1: 0, 2: 0, 3: 1, 4: 1, 5: 2}
REPEAT_DROP_MULT = 0.25

# Dismantle: floor(5 * rarity_mult * 1.20^(tier-1)); rarity_mult_3 typical ~1.0 from live 0094
# Use documented Rare T5 first temper roll ~128 dust from 32 dismantle * 4 salvage.
DISMANTLE_RARE_T4 = 5 * 1.0 * (1.20**3)
DISMANTLE_RARE_T5 = 5 * 1.0 * (1.20**4)
DISMANTLE_EPIC_T5 = 5 * 1.6 * (1.20**4)

CORE_KILL_PLUS = 0.02
CORE_BOSS_MULT = 4
KILLS_SOLO = 10
ABYSS_CORE_KILL = 0.04
ABYSS_ESSENCE_KILL = 0.02
ABYSS_ESSENCE_CP = 0.08
ABYSS_EMBER_CP = 0.05
PITY_N = 8

CORRIDOR_STIPEND_P61 = (8000, 15000)
CORRIDOR_STIPEND_P80_FULL = (18000, 28000)


@dataclass
class Profile:
    name: str
    plus: int
    abyss: int
    solo_per_day: int
    cp_per_day: int
    challenge_tiers: tuple[int, ...]
    dismantle_rare_t4: int = 0
    dismantle_rare_t5: int = 0
    dismantle_epic_t5: int = 0
    gold_bonus_pct: float = 0.0


PROFILES = [
    Profile("P61", plus=3, abyss=15, solo_per_day=2, cp_per_day=0, challenge_tiers=(1, 2, 3), dismantle_rare_t4=1),
    Profile("P70", plus=8, abyss=35, solo_per_day=4, cp_per_day=3, challenge_tiers=(1, 2, 3), dismantle_rare_t5=2),
    Profile("P80", plus=14, abyss=55, solo_per_day=8, cp_per_day=3, challenge_tiers=(1, 2, 3), dismantle_rare_t5=2, dismantle_epic_t5=1),
]


def stipend_day(tiers: tuple[int, ...]) -> int:
    return sum(STIPEND[t] for t in tiers)


def dust_in_day(p: Profile, tiers: tuple[int, ...]) -> dict[str, float]:
    challenge = sum(DUST_BONUS[t] for t in tiers)
    dismantle = (
        p.dismantle_rare_t4 * DISMANTLE_RARE_T4
        + p.dismantle_rare_t5 * DISMANTLE_RARE_T5
        + p.dismantle_epic_t5 * DISMANTLE_EPIC_T5
    )
    return {
        "dismantle": dismantle,
        "challenge": challenge,
        "dust_instant": 0.0,
        "total_base": dismantle + challenge,
    }


def cores_day(p: Profile, tiers: tuple[int, ...]) -> float:
    plus_runs = p.solo_per_day if p.plus >= 6 else 0
    per_run = KILLS_SOLO * CORE_KILL_PLUS + CORE_KILL_PLUS * CORE_BOSS_MULT
    dungeon_plus = plus_runs * per_run
    abyss_kills = max(0, p.abyss) * ABYSS_CORE_KILL  # 1 kill/floor
    challenge = sum(CORE_CHANCE[t] for t in tiers)
    return dungeon_plus + abyss_kills + challenge


def essence_day(p: Profile) -> float:
    if p.abyss < 30:
        return 0.0
    kills = max(0, p.abyss - 29) * ABYSS_ESSENCE_KILL
    cp = p.cp_per_day * ABYSS_ESSENCE_CP if p.abyss >= 30 else 0.0
    return kills + cp


def ember_day(p: Profile) -> dict[str, float]:
    if p.abyss < 50 or p.cp_per_day <= 0:
        return {"drop": 0.0, "pity_days": None, "expected": 0.0}
    drop = p.cp_per_day * ABYSS_EMBER_CP
    pity_days = math.ceil(PITY_N / max(1, p.cp_per_day))
    expected = drop + (1.0 / pity_days)
    return {"drop": drop, "pity_days": pity_days, "expected": expected}


def rarity_up_ev(tiers: tuple[int, ...]) -> float:
    return sum(RARITY_STEPS[t] for t in tiers)


def kill_gold_bonus_line(p: Profile, tiers: tuple[int, ...]) -> float:
    """Separate sim line: player gold_bonus_pct on challenge kills. Not in stipend corridor."""
    # Nominal 10 kills * 80 base gold * gold_mult * gold_bonus_pct
    base_kill = 80
    kills = 10
    return sum(kills * base_kill * GOLD_MULT[t] * p.gold_bonus_pct for t in tiers)


def in_corridor(val: float, lo: int, hi: int) -> str:
    ok = lo <= val <= hi
    return "OK" if ok else "OUT"


def run(gold_bonus_pct: float = 0.0) -> None:
    print("=== Endgame economy sim (daily expected) ===")
    print(f"gold_bonus_pct={gold_bonus_pct} (kill-gold line only; not in stipend corridor)")
    print()
    for p in PROFILES:
        p.gold_bonus_pct = gold_bonus_pct
        launch_tiers = p.challenge_tiers
        full_tiers = (1, 2, 3, 4, 5) if p.name == "P80" else p.challenge_tiers
        for label, tiers in (("launch", launch_tiers), ("full", full_tiers)):
            if label == "full" and p.name != "P80":
                continue
            stip = stipend_day(tiers)
            if p.name in ("P61",) or (p.name == "P80" and label == "launch"):
                lo, hi = CORRIDOR_STIPEND_P61
            elif p.name == "P80" and label == "full":
                lo, hi = CORRIDOR_STIPEND_P80_FULL
            else:
                lo, hi = CORRIDOR_STIPEND_P61
            dust = dust_in_day(p, tiers)
            cores = cores_day(p, tiers)
            ess = essence_day(p)
            ember = ember_day(p)
            print(f"{p.name} {label}  tiers={tiers}")
            print(f"  stipend              {stip}  corridor {lo}-{hi}  [{in_corridor(stip, lo, hi)}]")
            print(f"  dust_in dismantle    {dust['dismantle']:.1f}")
            print(f"  dust_in challenge    {dust['challenge']:.1f}")
            print(f"  dust_instant         {dust['dust_instant']:.1f}  (separate; not in BASE)")
            print(f"  dust_in BASE         {dust['total_base']:.1f}")
            print(f"  cores/day            {cores:.3f}")
            print(f"  essence/day          {ess:.3f}")
            print(
                f"  ember/day drop={ember['drop']:.3f} pity_days={ember['pity_days']} expected={ember['expected']:.3f}"
            )
            print(f"  rarity_steps EV      {rarity_up_ev(tiers)}  (separate rarity-up line)")
            print(f"  challenge kill gold% {kill_gold_bonus_line(p, tiers):.1f}  (separate; not stipend)")
            print()
    print("Repeat drop: base_drop * 0.25; bonus_pct=0; rarity_steps=0; dust/core=0")
    print("Temper dust grows with n to cap 8; ember INT ladder 1/2/3; Dungeon+ curve not nerfed.")


if __name__ == "__main__":
    run()
