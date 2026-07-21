"""Async Legion Arena 3v3 auto-resolve simulation."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any

from waifu_bot.game.merc_archetypes import stance_edge
from waifu_bot.game.merc_perks import archetype_for_perks, tag_coverage


@dataclass
class ArenaFighter:
    name: str
    cr: int
    perk_ids: list[str]
    stance: str
    archetype_id: str
    hp: float = 0.0

    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = float(max(50, self.cr))


def _seed_rng(seed: str) -> random.Random:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def fighter_from_unit(unit: Any) -> ArenaFighter:
    perks = list(getattr(unit, "perks", None) or [])
    arch = archetype_for_perks([str(p) for p in perks])
    cr = int(getattr(unit, "power", 0) or 0) or 40
    return ArenaFighter(
        name=str(getattr(unit, "name", "Наёмница") or "Наёмница"),
        cr=cr,
        perk_ids=[str(p) for p in perks],
        stance=arch.stance,
        archetype_id=arch.id,
    )


def simulate_3v3(
    attackers: list[ArenaFighter],
    defenders: list[ArenaFighter],
    *,
    match_seed: str,
) -> dict[str, Any]:
    """Deterministic auto-combat. Returns winner side, log lines, rating hint."""
    rng = _seed_rng(match_seed)
    atk = [ArenaFighter(**{**f.__dict__}) for f in attackers[:3]]
    dfn = [ArenaFighter(**{**f.__dict__}) for f in defenders[:3]]
    while len(atk) < 3:
        atk.append(ArenaFighter("Резерв", 30, [], "Assault", "fighter"))
    while len(dfn) < 3:
        dfn.append(ArenaFighter("Резерв", 30, [], "Ward", "defender"))

    log: list[str] = []
    # Pair by index for simplicity (IDLE auto)
    rounds = 0
    while rounds < 12 and any(f.hp > 0 for f in atk) and any(f.hp > 0 for f in dfn):
        rounds += 1
        a = next((f for f in atk if f.hp > 0), None)
        b = next((f for f in dfn if f.hp > 0), None)
        if not a or not b:
            break
        edge = stance_edge(a.stance, b.stance)
        # Tag layer: attacker burst vs defender barrier etc.
        a_cov = tag_coverage(a.perk_ids)
        b_cov = tag_coverage(b.perk_ids)
        a_burst = a_cov.get("burst", 0) + a_cov.get("pressure", 0)
        b_bar = b_cov.get("barrier", 0) + b_cov.get("sustain", 0)
        dmg_mult = 1.0 + edge + 0.15 * a_burst - 0.20 * b_bar
        dmg_mult = max(0.35, min(2.0, dmg_mult))
        base = (a.cr * 0.22) * dmg_mult * rng.uniform(0.9, 1.1)
        b.hp -= base
        log.append(
            f"{a.name} ({a.archetype_id}) бьёт {b.name}: {int(base)} "
            f"[edge {edge:+.2f}] HP {max(0, int(b.hp))}"
        )
        if b.hp <= 0:
            log.append(f"{b.name} выбывает.")
            continue
        # Counter
        edge2 = stance_edge(b.stance, a.stance)
        dmg2 = (b.cr * 0.18) * (1.0 + edge2) * rng.uniform(0.9, 1.1)
        a.hp -= dmg2
        log.append(f"{b.name} отвечает: {int(dmg2)} → {a.name} HP {max(0, int(a.hp))}")
        if a.hp <= 0:
            log.append(f"{a.name} выбывает.")

    atk_alive = sum(1 for f in atk if f.hp > 0)
    dfn_alive = sum(1 for f in dfn if f.hp > 0)
    if atk_alive > dfn_alive:
        winner = "attacker"
    elif dfn_alive > atk_alive:
        winner = "defender"
    else:
        atk_hp = sum(max(0, f.hp) for f in atk)
        dfn_hp = sum(max(0, f.hp) for f in dfn)
        winner = "attacker" if atk_hp >= dfn_hp else "defender"

    log.append("Победа атаки." if winner == "attacker" else "Победа защиты.")
    return {
        "winner": winner,
        "log": log[:16],
        "atk_alive": atk_alive,
        "def_alive": dfn_alive,
        "rounds": rounds,
    }
