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

# Potential star fodder cost (commons-equivalent): key = target star after upgrade
STAR_FODDER_COST: dict[int, int] = {
    1: 2,
    2: 4,
    3: 7,
    4: 12,
    5: 18,
}

# Perk level hard cap by stars
PERK_LEVEL_CAP_BY_STARS: dict[int, int] = {
    0: 1,
    1: 2,
    2: 3,
    3: 4,
    4: 5,
    5: 6,
}

# Soft cap: max perk level reachable with each consumable tier at given ★
# rows: stars -> (t1_max, t2_max, t3_max)
PERK_SOFT_CAP_BY_STARS: dict[int, tuple[int, int, int]] = {
    0: (1, 1, 1),
    1: (1, 2, 2),
    2: (2, 3, 3),
    3: (2, 3, 4),
    4: (3, 4, 5),
    5: (3, 5, 6),
}

MANUAL_TYPES = ("ATK", "DEF", "SUP")


def bench_cap_for_main_level(level: int) -> int:
    lvl = max(1, int(level or 1))
    for min_lvl, cap in BENCH_CAP_BY_LEVEL:
        if lvl >= min_lvl:
            return cap
    return 8


def perk_level_cap(stars: int) -> int:
    s = max(0, min(5, int(stars or 0)))
    return PERK_LEVEL_CAP_BY_STARS.get(s, 1)


def perk_soft_cap(stars: int, tier: int) -> int:
    s = max(0, min(5, int(stars or 0)))
    t = max(1, min(3, int(tier or 1)))
    caps = PERK_SOFT_CAP_BY_STARS.get(s, (1, 1, 1))
    return caps[t - 1]


def fodder_cost_for_next_star(current_stars: int) -> int:
    nxt = max(0, min(5, int(current_stars or 0) + 1))
    if nxt > 5 or int(current_stars or 0) >= 5:
        return 0
    return STAR_FODDER_COST.get(nxt, 99)


def empty_manual_wallet() -> dict[str, dict[str, int]]:
    return {t: {"t1": 0, "t2": 0, "t3": 0} for t in MANUAL_TYPES}


def normalize_drill_manuals(raw: dict | None) -> dict[str, dict[str, int]]:
    """Accept legacy `{ATK: n}` or nested `{ATK:{t1,t2,t3}}` → nested ints."""
    out = empty_manual_wallet()
    if not isinstance(raw, dict):
        return out
    for ptype in MANUAL_TYPES:
        val = raw.get(ptype)
        if isinstance(val, dict):
            out[ptype] = {
                "t1": max(0, int(val.get("t1", 0) or 0)),
                "t2": max(0, int(val.get("t2", 0) or 0)),
                "t3": max(0, int(val.get("t3", 0) or 0)),
            }
        elif val is not None:
            # legacy flat count → T2 textbooks
            out[ptype]["t2"] = max(0, int(val or 0))
    # tolerate lowercase keys
    for k, v in raw.items():
        ku = str(k).upper()
        if ku not in MANUAL_TYPES:
            continue
        if isinstance(v, dict):
            out[ku] = {
                "t1": max(0, int(v.get("t1", 0) or 0)),
                "t2": max(0, int(v.get("t2", 0) or 0)),
                "t3": max(0, int(v.get("t3", 0) or 0)),
            }
    return out


def add_manual(wallet: dict, perk_type: str, tier: int, amount: int = 1) -> dict:
    w = normalize_drill_manuals(wallet)
    pt = str(perk_type or "ATK").upper()
    if pt not in MANUAL_TYPES:
        pt = "ATK"
    t = max(1, min(3, int(tier or 2)))
    key = f"t{t}"
    w[pt][key] = max(0, int(w[pt].get(key, 0) or 0) + int(amount))
    return w


def consume_manual(wallet: dict, perk_type: str, tier: int, amount: int = 1) -> tuple[dict | None, str | None]:
    w = normalize_drill_manuals(wallet)
    pt = str(perk_type or "ATK").upper()
    if pt not in MANUAL_TYPES:
        return None, "bad_type"
    t = max(1, min(3, int(tier or 2)))
    key = f"t{t}"
    have = int(w[pt].get(key, 0) or 0)
    if have < amount:
        return None, "no_manual"
    w[pt][key] = have - amount
    return w, None
