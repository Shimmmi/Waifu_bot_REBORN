"""Async Legion Arena 3v3 auto-resolve simulation."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Literal

from waifu_bot.game.merc_archetypes import stance_edge
from waifu_bot.game.merc_perks import archetype_for_perks, tag_coverage

Side = Literal["attacker", "defender"]

# Relative CR gap above which the favorite is heavily favored (~≥80% WR).
_CR_GAP_FAIRNESS = 0.25
_PROC_CHANCE = 0.20
_MAX_ROUNDS = 12
_LOG_CAP = 24


@dataclass
class ArenaFighter:
    name: str
    cr: int
    perk_ids: list[str]
    stance: str
    archetype_id: str
    hp: float = 0.0
    max_hp: float = 0.0
    barrier_charges: int = 0
    side: Side = "attacker"

    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = float(max(50, self.cr))
        if self.max_hp <= 0:
            self.max_hp = float(self.hp)


def _seed_rng(seed: str) -> random.Random:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def fighter_from_unit(unit: Any, *, side: Side = "attacker") -> ArenaFighter:
    perks = list(getattr(unit, "perks", None) or [])
    arch = archetype_for_perks([str(p) for p in perks])
    cr = int(getattr(unit, "power", 0) or 0) or 40
    return ArenaFighter(
        name=str(getattr(unit, "name", "Наёмница") or "Наёмница"),
        cr=cr,
        perk_ids=[str(p) for p in perks],
        stance=arch.stance,
        archetype_id=arch.id,
        side=side,
    )


def _clone(f: ArenaFighter, *, side: Side | None = None) -> ArenaFighter:
    return ArenaFighter(
        name=f.name,
        cr=f.cr,
        perk_ids=list(f.perk_ids),
        stance=f.stance,
        archetype_id=f.archetype_id,
        hp=f.hp if f.hp > 0 else 0.0,
        max_hp=f.max_hp,
        barrier_charges=0,
        side=side or f.side,
    )


def _alive(team: list[ArenaFighter]) -> list[ArenaFighter]:
    return [f for f in team if f.hp > 0]


def _pick_target(enemies: list[ArenaFighter], rng: random.Random) -> ArenaFighter:
    """50% lowest-HP, 30% highest-CR, 20% random."""
    roll = rng.random()
    if roll < 0.50:
        return min(enemies, key=lambda f: f.hp)
    if roll < 0.80:
        return max(enemies, key=lambda f: f.cr)
    return rng.choice(enemies)


def _initiative_order(
    atk: list[ArenaFighter],
    dfn: list[ArenaFighter],
    rng: random.Random,
    *,
    gap: float,
    favorite: Side,
) -> list[ArenaFighter]:
    """Sort living fighters: score = CR*0.01 + noise (underdog noise damped if gap large)."""
    living = _alive(atk) + _alive(dfn)

    def score(f: ArenaFighter) -> float:
        noise = rng.random()
        if gap > _CR_GAP_FAIRNESS and f.side != favorite:
            noise *= 0.45
        return f.cr * 0.01 + noise

    return sorted(living, key=score, reverse=True)


def _pick_proc(
    cov: dict[str, float],
    rng: random.Random,
    *,
    underdog: bool,
    gap: float,
) -> str | None:
    chance = _PROC_CHANCE
    if gap > _CR_GAP_FAIRNESS and underdog:
        chance *= 0.5
    if rng.random() > chance:
        return None
    candidates: list[str] = []
    if cov.get("burst", 0) > 0 or cov.get("pressure", 0) > 0:
        candidates.append("burst")
    if cov.get("barrier", 0) > 0:
        candidates.append("barrier")
    if cov.get("sustain", 0) > 0:
        candidates.append("sustain")
    if not candidates:
        return None
    return rng.choice(candidates)


def _fairness_mult(side: Side, *, gap: float, favorite: Side) -> float:
    if gap <= _CR_GAP_FAIRNESS:
        return 1.0
    return 1.12 if side == favorite else 0.82


def _apply_damage(
    target: ArenaFighter,
    raw: float,
    log: list[str],
) -> float:
    if target.barrier_charges > 0:
        target.barrier_charges -= 1
        log.append(f"Барьер {target.name} поглощает удар.")
        return 0.0
    target.hp -= raw
    return raw


def simulate_3v3(
    attackers: list[ArenaFighter],
    defenders: list[ArenaFighter],
    *,
    match_seed: str,
) -> dict[str, Any]:
    """Deterministic auto-combat with initiative, targeting, and rare perk procs."""
    rng = _seed_rng(match_seed)
    atk = [_clone(f, side="attacker") for f in attackers[:3]]
    dfn = [_clone(f, side="defender") for f in defenders[:3]]
    while len(atk) < 3:
        atk.append(ArenaFighter("Резерв", 30, [], "Assault", "fighter", side="attacker"))
    while len(dfn) < 3:
        dfn.append(ArenaFighter("Резерв", 30, [], "Ward", "defender", side="defender"))
    for f in atk + dfn:
        if f.max_hp <= 0:
            f.max_hp = float(max(50, f.cr)) if f.hp <= 0 else float(f.hp)
        if f.hp <= 0:
            f.hp = float(f.max_hp)

    atk_cr = sum(f.cr for f in atk) or 1
    dfn_cr = sum(f.cr for f in dfn) or 1
    gap = abs(atk_cr - dfn_cr) / max(atk_cr, dfn_cr)
    favorite: Side = "attacker" if atk_cr >= dfn_cr else "defender"

    log: list[str] = []
    if gap > _CR_GAP_FAIRNESS:
        log.append(
            f"Перевес CR {favorite}: {atk_cr} vs {dfn_cr} (gap {gap:.0%})."
        )

    rounds = 0
    while rounds < _MAX_ROUNDS and _alive(atk) and _alive(dfn):
        rounds += 1
        order = _initiative_order(atk, dfn, rng, gap=gap, favorite=favorite)
        if rounds == 1 or rounds % 3 == 1:
            names = ", ".join(f.name for f in order[:4])
            log.append(f"Инициатива р{rounds}: {names}")

        for actor in order:
            if actor.hp <= 0:
                continue
            enemies = _alive(dfn) if actor.side == "attacker" else _alive(atk)
            if not enemies:
                break

            cov = tag_coverage(actor.perk_ids)
            underdog = actor.side != favorite
            proc = _pick_proc(cov, rng, underdog=underdog, gap=gap)

            if proc == "sustain":
                heal = actor.max_hp * 0.12
                before = actor.hp
                actor.hp = min(actor.max_hp, actor.hp + heal)
                log.append(
                    f"{actor.name} sustain +{int(actor.hp - before)} HP "
                    f"→ {int(actor.hp)}"
                )
            elif proc == "barrier":
                actor.barrier_charges = max(1, actor.barrier_charges)
                log.append(f"{actor.name} ставит барьер.")

            target = _pick_target(enemies, rng)
            edge = stance_edge(actor.stance, target.stance)
            t_cov = tag_coverage(target.perk_ids)
            a_burst = cov.get("burst", 0) + cov.get("pressure", 0)
            b_bar = t_cov.get("barrier", 0) + t_cov.get("sustain", 0)
            dmg_mult = 1.0 + edge + 0.15 * a_burst - 0.20 * b_bar
            if proc == "burst":
                dmg_mult *= 1.6
                log.append(f"{actor.name} прок burst!")
            dmg_mult *= _fairness_mult(actor.side, gap=gap, favorite=favorite)
            dmg_mult = max(0.35, min(2.4, dmg_mult))
            # Base strike weight: attackers slightly higher than defenders historically
            coeff = 0.22 if actor.side == "attacker" else 0.18
            raw = (actor.cr * coeff) * dmg_mult * rng.uniform(0.85, 1.15)
            dealt = _apply_damage(target, raw, log)
            if dealt > 0:
                log.append(
                    f"{actor.name} ({actor.archetype_id}) бьёт {target.name}: "
                    f"{int(dealt)} [edge {edge:+.2f}] HP {max(0, int(target.hp))}"
                )
            if target.hp <= 0:
                log.append(f"{target.name} выбывает.")

    atk_alive = len(_alive(atk))
    dfn_alive = len(_alive(dfn))
    if atk_alive > dfn_alive:
        winner: Side = "attacker"
    elif dfn_alive > atk_alive:
        winner = "defender"
    else:
        atk_hp = sum(max(0.0, f.hp) for f in atk)
        dfn_hp = sum(max(0.0, f.hp) for f in dfn)
        winner = "attacker" if atk_hp >= dfn_hp else "defender"

    # Hard fairness: huge CR gap must not flip too often — bias final call if needed.
    if gap > _CR_GAP_FAIRNESS and winner != favorite and rng.random() < 0.75:
        winner = favorite
        log.append(f"Перевес силы удерживает победу ({favorite}).")

    log.append("Победа атаки." if winner == "attacker" else "Победа защиты.")
    return {
        "winner": winner,
        "log": log[:_LOG_CAP],
        "atk_alive": atk_alive,
        "def_alive": dfn_alive,
        "rounds": rounds,
        "cr_gap": round(gap, 3),
        "favorite": favorite,
    }
