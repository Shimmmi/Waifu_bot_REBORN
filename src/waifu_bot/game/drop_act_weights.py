"""Boss-chest rarity weights (DropRule). Early acts include a small legendary weight."""

from __future__ import annotations

# Integer weights; rarity 5 = legendary. Shop still caps at Rare separately.
ACT_RARITY_WEIGHTS: dict[int, dict[str, int]] = {
    1: {"1": 70, "2": 25, "3": 4, "5": 1},
    2: {"1": 55, "2": 30, "3": 12, "4": 2, "5": 1},
    3: {"1": 45, "2": 32, "3": 18, "4": 4, "5": 1},
    4: {"1": 35, "2": 30, "3": 22, "4": 11, "5": 2},
    5: {"1": 28, "2": 30, "3": 24, "4": 14, "5": 4},
}

PREV_ACT_RARITY_WEIGHTS: dict[int, dict[str, int]] = {
    1: {"1": 70, "2": 25, "3": 5},
    2: {"1": 55, "2": 30, "3": 12, "4": 3},
    3: {"1": 45, "2": 32, "3": 18, "4": 5},
    4: {"1": 35, "2": 30, "3": 22, "4": 11, "5": 2},
    5: {"1": 28, "2": 30, "3": 24, "4": 14, "5": 4},
}
