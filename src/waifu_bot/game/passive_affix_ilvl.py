"""Согласование аффиксов «+уровень к пассивному узлу» с уровнем предмета (ilvl)."""

from __future__ import annotations

# Ряд дерева passive_skill_nodes.tier (0037_passive_skill_tree); id → tier
PASSIVE_NODE_TREE_TIER: dict[str, int] = {
    "w_bash": 1,
    "w_tough": 1,
    "w_cry": 1,
    "w_heavy": 2,
    "w_iron": 2,
    "w_blood": 2,
    "w_berserk": 3,
    "w_fort": 3,
    "w_last": 3,
    "w_wrath": 4,
    "w_imm": 4,
    "s_keen": 1,
    "s_nimble": 1,
    "s_media": 1,
    "s_crit_m": 2,
    "s_shadow": 2,
    "s_exploit": 2,
    "s_nth": 3,
    "s_ghost": 3,
    "s_amp": 3,
    "s_lethal": 4,
    "s_phantom": 4,
    "m_arcane": 1,
    "m_wisdom": 1,
    "m_trade": 1,
    "m_media_m": 2,
    "m_lore": 2,
    "m_bargain": 2,
    "m_surge": 3,
    "m_cmd": 3,
    "m_rune": 3,
    "m_trans": 4,
    "m_arch": 4,
}

_PREFIX = "passive_node_level_add:"


def max_passive_tree_tier_for_item_level(ilvl: int) -> int:
    """
    Максимальный ряд дерева пассивов (1..4), который может давать предмет данного ilvl.

    1–10: tier 1; 11–20: 1–2; 21–39: 1–3; 40+: 1–4.
    """
    lv = max(1, int(ilvl))
    if lv <= 10:
        return 1
    if lv <= 20:
        return 2
    if lv <= 39:
        return 3
    return 4


def passive_node_id_from_effect_key(effect_key: str | None) -> str | None:
    ek = str(effect_key or "").strip()
    if not ek.startswith(_PREFIX):
        return None
    nid = ek[len(_PREFIX) :].strip()
    return nid or None


def passive_node_level_add_allowed(effect_key: str | None, ilvl: int) -> bool:
    """True, если аффикс passive_node_level_add:<node> допустим для ilvl предмета."""
    nid = passive_node_id_from_effect_key(effect_key)
    if nid is None:
        return True
    tree_tier = PASSIVE_NODE_TREE_TIER.get(nid)
    if tree_tier is None:
        return True
    return int(tree_tier) <= max_passive_tree_tier_for_item_level(ilvl)


def split_ilvl_bands(tier_min_ilvl: int, n_tiers: int = 10, cap: int = 50) -> list[tuple[int, int]]:
    """
    Разбивает [tier_min_ilvl, cap] на n_tiers непрерывных полос (min, max включительно).
    Остаток от деления распределяется по первым полосам.
    """
    lo = max(1, int(tier_min_ilvl))
    hi = max(lo, int(cap))
    total = hi - lo + 1
    nt = max(1, int(n_tiers))
    base = total // nt
    rem = total % nt
    widths = [base + (1 if i < rem else 0) for i in range(nt)]
    out: list[tuple[int, int]] = []
    cur = lo
    for w in widths:
        if w <= 0:
            continue
        mn, mx = cur, cur + w - 1
        cur = mx + 1
        out.append((mn, mx))
    return out
