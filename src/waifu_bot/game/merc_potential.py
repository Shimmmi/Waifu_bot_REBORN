"""Bench capacity and potential-star helpers."""
from __future__ import annotations

# Main waifu level → max hired pool (plan §1)
BENCH_CAP_BY_LEVEL: tuple[tuple[int, int], ...] = (
    (40, 24),
    (30, 20),
    (20, 16),
    (10, 12),
    (1, 8),
)

# Potential star fodder cost (commons-equivalent)
STAR_FODDER_COST: dict[int, int] = {
    1: 2,
    2: 4,
    3: 7,
    4: 12,
    5: 18,
}

# Perk level cap by stars
PERK_LEVEL_CAP_BY_STARS: dict[int, int] = {
    0: 1,
    1: 2,
    2: 3,
    3: 4,
    4: 5,
    5: 6,
}


def bench_cap_for_main_level(level: int) -> int:
    lvl = max(1, int(level or 1))
    for min_lvl, cap in BENCH_CAP_BY_LEVEL:
        if lvl >= min_lvl:
            return cap
    return 8


def perk_level_cap(stars: int) -> int:
    s = max(0, min(5, int(stars or 0)))
    return PERK_LEVEL_CAP_BY_STARS.get(s, 1)


def fodder_cost_for_next_star(current_stars: int) -> int:
    nxt = max(0, min(5, int(current_stars or 0) + 1))
    if nxt > 5 or int(current_stars or 0) >= 5:
        return 0
    return STAR_FODDER_COST.get(nxt, 99)
