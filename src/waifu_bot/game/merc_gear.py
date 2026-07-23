"""Merc gear loot: roll tables for weapon/charm/relic by tier."""

from __future__ import annotations

import random
import uuid
from typing import Any

GEAR_SLOTS = ("weapon", "charm", "relic")

_NAME_POOLS: dict[str, tuple[str, ...]] = {
    "weapon": ("Клинок", "Топор", "Копьё", "Лук", "Кинжал", "Булава"),
    "charm": ("Амулет", "Талисман", "Знак", "Кулон", "Печать"),
    "relic": ("Реликвия", "Осколок", "Тотем", "Свиток", "Эмблема"),
}

_SUFFIX = ("новичка", "наёмника", "ветерана", "капитана", "легенды")


def roll_merc_gear(tier: int, *, rng: random.Random | None = None) -> dict[str, Any]:
    """Roll one unequipped merc gear item for loot box tier 1..3."""
    r = rng or random.Random()
    t = max(1, min(3, int(tier or 1)))
    slot = r.choice(GEAR_SLOTS)
    base = r.choice(_NAME_POOLS[slot])
    suffix = _SUFFIX[min(len(_SUFFIX) - 1, t)]
    # rarity 1..min(5, t+1); score scales with tier
    rarity = max(1, min(5, t + (1 if r.random() < 0.25 else 0)))
    score = t * 3 + rarity + r.randint(0, 2)
    return {
        "id": str(uuid.uuid4()),
        "slot": slot,
        "name": f"{base} {suffix}",
        "rarity": rarity,
        "score": score,
        "tier": t,
    }
