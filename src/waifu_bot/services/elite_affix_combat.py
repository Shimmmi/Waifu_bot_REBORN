"""Elite monster affix behavior for solo message combat (DungeonRunMonster)."""

from __future__ import annotations

import random
from typing import Any

from waifu_bot.db.models.dungeon import DungeonRunMonster, MonsterAffix
from waifu_bot.game.constants import CRIT_CHANCE_CAP, MediaType


def _ensure_elite_state(run_monster: DungeonRunMonster) -> dict[str, Any]:
    raw = getattr(run_monster, "elite_state", None)
    if not isinstance(raw, dict):
        raw = {}
    run_monster.elite_state = raw
    return raw


def stone_skin_reduction(max_reduction: float, current_hp: int, max_hp: int) -> float:
    """Reduction fraction: max_reduction * (current_hp / max_hp)."""
    mh = max(1, int(max_hp or 1))
    ch = max(0, int(current_hp or 0))
    return float(max_reduction) * (float(ch) / float(mh))


def aggregate_anti_crit(affix_rows: list[MonsterAffix]) -> float:
    """Sum crit_reduction from ANTI_CRIT debuffs (cap effective reduction at 0.95)."""
    total = 0.0
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "ANTI_CRIT":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if not isinstance(bp, dict):
            continue
        try:
            total += float(bp.get("crit_reduction") or 0.0)
        except (TypeError, ValueError):
            continue
    return min(0.95, max(0.0, total))


def effective_crit_chance_after_anti_crit(base_chance: float, anti_crit_total: float) -> float:
    """Multiply base crit chance by (1 - anti_crit), then cap."""
    ch = float(base_chance) * max(0.0, 1.0 - float(anti_crit_total))
    return min(float(CRIT_CHANCE_CAP), max(0.0, ch))


def apply_curse_to_damage(
    run_monster: DungeonRunMonster,
    affix_rows: list[MonsterAffix],
    damage: int,
    trace,
) -> int:
    """Apply CURSE player damage mult from debuff affixes; persists in elite_state."""
    curse_rows = [
        a
        for a in affix_rows
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() == "CURSE"
    ]
    if not curse_rows or damage <= 0:
        return damage
    st = _ensure_elite_state(run_monster)
    if "curse_player_dmg_mult" not in st:
        curse_mult = 1.0
        for a in curse_rows:
            bp = getattr(a, "behavior_params", None) or {}
            if not isinstance(bp, dict):
                continue
            try:
                dr = float(bp.get("dmg_reduction") or 0.0)
            except (TypeError, ValueError):
                continue
            curse_mult *= max(0.0, 1.0 - dr)
        st["curse_player_dmg_mult"] = float(curse_mult)
    mult = float(st.get("curse_player_dmg_mult") or 1.0)
    if mult >= 0.9999:
        return damage
    nb = damage
    out = max(0, int(round(float(damage) * mult)))
    trace.mult(
        "elite_curse",
        f"Проклятие элита: урон ×{mult:.2f}",
        nb,
        out,
        factor=mult,
    )
    return out


def apply_stone_skin_to_damage(
    run_monster: DungeonRunMonster,
    affix_rows: list[MonsterAffix],
    damage: int,
    trace,
) -> int:
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "STONE_SKIN":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if not isinstance(bp, dict):
            continue
        try:
            mx = float(bp.get("max_reduction") or 0.0)
        except (TypeError, ValueError):
            continue
        red = stone_skin_reduction(mx, int(run_monster.current_hp or 0), int(run_monster.max_hp or 1))
        if red <= 0:
            continue
        nb = damage
        fac = max(0.0, 1.0 - red)
        out = max(0, int(float(damage) * fac))
        trace.mult(
            "elite_stone_skin",
            f"Каменная кожа: снижение входящего ~{red * 100:.0f}%",
            nb,
            out,
            factor=fac,
        )
        return out
    return damage


def media_message_for_block(media_type: MediaType) -> bool:
    return media_type not in (MediaType.TEXT, MediaType.LINK)


def apply_media_block(
    run_monster: DungeonRunMonster,
    affix_rows: list[MonsterAffix],
    media_type: MediaType,
    damage: int,
    trace,
) -> tuple[int, bool]:
    """Increment media counter for non-text/link; block every Nth media hit."""
    if not media_message_for_block(media_type) or damage <= 0:
        return damage, False
    every_n = 0
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "MEDIA_BLOCK":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if not isinstance(bp, dict):
            continue
        try:
            every_n = max(0, int(bp.get("every_n") or 0))
        except (TypeError, ValueError):
            every_n = 0
        if every_n > 0:
            break
    if every_n <= 0:
        return damage, False
    cnt = int(getattr(run_monster, "media_messages_on_monster", 0) or 0) + 1
    run_monster.media_messages_on_monster = cnt
    if cnt % every_n != 0:
        return damage, False
    nb = damage
    trace.result(
        "elite_media_block",
        f"Блок медиа: каждое {every_n}-е медиа не наносит урон",
        nb,
        0,
    )
    return 0, True


def regen_amount_and_params(affix_rows: list[MonsterAffix]) -> tuple[int, int]:
    """Best REGEN affix: (regen_pct, every_n)."""
    best = (0, 1)
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "REGEN":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if not isinstance(bp, dict):
            continue
        try:
            rp = int(bp.get("regen_pct") or 0)
            en = max(1, int(bp.get("every_n") or 1))
        except (TypeError, ValueError):
            continue
        if rp > best[0]:
            best = (rp, en)
    return best


def apply_regen_after_hit(
    run_monster: DungeonRunMonster,
    affix_rows: list[MonsterAffix],
    messages_after_hit: int,
    damage_dealt: int,
) -> None:
    if damage_dealt <= 0 or int(run_monster.current_hp or 0) <= 0:
        return
    rp, every_n = regen_amount_and_params(affix_rows)
    if rp <= 0 or every_n <= 0:
        return
    if messages_after_hit <= 0 or messages_after_hit % every_n != 0:
        return
    mx = max(1, int(run_monster.max_hp or 1))
    heal = max(1, int(mx * rp / 100.0))
    cur = int(run_monster.current_hp or 0)
    run_monster.current_hp = min(mx, cur + heal)


def reflect_params(affix_rows: list[MonsterAffix]) -> tuple[float, float]:
    """Max chance / reflect_pct from REFLECT affixes."""
    ch = 0.0
    pct = 0.0
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "REFLECT":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if not isinstance(bp, dict):
            continue
        try:
            c = float(bp.get("chance") or 0.0)
            p = float(bp.get("reflect_pct") or 0.0)
        except (TypeError, ValueError):
            continue
        if c > ch:
            ch, pct = c, p
    return ch, pct


def berserk_multiplier(affix_rows: list[MonsterAffix]) -> tuple[float, float]:
    """(threshold, dmg_bonus) from BERSERK — first matching row."""
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "BERSERK":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if not isinstance(bp, dict):
            continue
        try:
            th = float(bp.get("threshold") or 0.5)
            db = float(bp.get("dmg_bonus") or 1.0)
        except (TypeError, ValueError):
            continue
        return th, db
    return 1.0, 1.0


def update_berserk_elite_state(
    run_monster: DungeonRunMonster,
    affix_rows: list[MonsterAffix],
    hp_after_damage: int,
) -> None:
    th, _ = berserk_multiplier(affix_rows)
    if th >= 1.0:
        return
    mx = max(1, int(run_monster.max_hp or 1))
    ratio = float(max(0, int(hp_after_damage))) / float(mx)
    if ratio <= th and int(hp_after_damage) > 0:
        st = _ensure_elite_state(run_monster)
        st["berserk_active"] = True


def undying_revive_fraction(affix_rows: list[MonsterAffix]) -> float | None:
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "UNDYING":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if not isinstance(bp, dict):
            continue
        try:
            return float(bp.get("revive_hp_pct") or 0.1)
        except (TypeError, ValueError):
            return 0.1
    return None


def split_behavior_params(affix_rows: list[MonsterAffix]) -> dict[str, Any] | None:
    for a in affix_rows:
        if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "SPLIT":
            continue
        bp = getattr(a, "behavior_params", None) or {}
        if isinstance(bp, dict):
            return bp
    return None


def buff_next_multipliers_for_new_monster(
    earlier_monsters: list[DungeonRunMonster],
    affix_by_id: dict[int, MonsterAffix],
    new_position: int,
) -> tuple[float, float]:
    """Aggregate hp_mult, dmg_mult from alive elites with position < new_position (BUFF_NEXT)."""
    hp_m = 1.0
    dmg_m = 1.0
    for m in earlier_monsters:
        if int(m.position or 0) >= int(new_position):
            continue
        if int(m.current_hp or 0) <= 0:
            continue
        if not getattr(m, "is_elite", False):
            continue
        ids = getattr(m, "applied_affix_ids", None) or []
        if not ids:
            continue
        for aid in ids:
            a = affix_by_id.get(int(aid))
            if not a:
                continue
            if str(getattr(a, "behavior_flag", None) or "").strip().upper() != "BUFF_NEXT":
                continue
            bp = getattr(a, "behavior_params", None) or {}
            if not isinstance(bp, dict):
                continue
            try:
                if bp.get("hp_mult") is not None:
                    hp_m *= float(bp["hp_mult"])
                if bp.get("dmg_mult") is not None:
                    dmg_m *= float(bp["dmg_mult"])
            except (TypeError, ValueError):
                continue
    return hp_m, dmg_m


def roll_reflect(chance: float, reflect_pct: float, damage_to_monster: int) -> int:
    if damage_to_monster <= 0 or chance <= 0 or reflect_pct <= 0:
        return 0
    if random.random() >= float(chance):
        return 0
    return max(0, int(float(damage_to_monster) * float(reflect_pct)))
