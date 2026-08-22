"""Delve PQ layer 2: hole drain, 30s tick, readable nodes, trauma, class/traits."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from waifu_bot.game.delve_catalog import (
    HUD_STATUS,
    NODE_BOSS,
    NODE_BRANCH,
    NODE_CITY,
    NODE_COMBAT,
    NODE_LANDMARK,
    NODE_REST,
    NODE_SHOP,
    NODE_SURFACE,
    NODE_TRAVERSE,
    STATE_ASCENDING,
    STATE_DESCENDING,
    STATE_REST,
    T_UP_SEC,
    city_name_ru,
    implied_record,
    is_city_depth,
    split_weighted,
)
from waifu_bot.game.delve_pq import (
    MercState,
    PqParty,
    auto_use_potions,
    compute_power,
    d_max_of,
    merc_gold_cap_day,
    party_power,
    pq_rng,
    resolve_shop,
)

EVENTS_PATH = Path(__file__).resolve().parents[3] / "data" / "delve_node_events.v1.json"

PQ_LAYER_DEFAULT = 2
T_NODE_SEC = 30
T_EFF_MIN = 15
T_EFF_MAX = 50
ARMOR_K = 1.2
COMBAT_FLOOR = 3
BOSS_FLOOR = 6
DRAIN_BASE_FRAC = 0.10
DRAIN_LAMBDA = 2.0
BOSS_FRAC_MULT = 1.6
COMBAT_CAP_FRAC = 0.85
BOSS_CAP_FRAC = 0.90
REST_BASE_FRAC = 0.22
REST_CAP_FRAC = 0.28
HEALER_CLASS_ID = 6
HEALER_AURA = 0.10

KIND_EMPTY = "empty"
KIND_MONSTER = "monster"
KIND_EVENT = "event"
KIND_NPC = "npc"
KIND_FIND = "find"
REGULAR_KINDS = (KIND_EMPTY, KIND_MONSTER, KIND_EVENT, KIND_NPC, KIND_FIND)

KIND_LABEL_RU = {
    KIND_EMPTY: "Ничего",
    KIND_MONSTER: "Монстр",
    KIND_EVENT: "Событие",
    KIND_NPC: "NPC",
    KIND_FIND: "Находка",
    "boss": "Босс",
    "rest": "Костёр",
    "shop": "Лавка",
    "city": "Город",
    "branch": "Вилка",
    "landmark": "Метка",
    "surface": "Лагерь",
}
KIND_GLYPH = {
    KIND_EMPTY: "·",
    KIND_MONSTER: "✕",
    KIND_EVENT: "!",
    KIND_NPC: "◊",
    KIND_FIND: "◇",
}

GRADE_LIGHT = "лёгкая"
GRADE_SERIOUS = "серьёзная"
SEV_FROM_GRADE = {GRADE_LIGHT: "царапина", GRADE_SERIOUS: "рана"}
GRADE_FROM_SEV = {"царапина": GRADE_LIGHT, "рана": GRADE_SERIOUS, "увечье": GRADE_SERIOUS}

CLASS_TO_STANCE = {1: "shield", 2: "shield", 3: "scout", 4: "guide", 5: "scout", 6: "guide", 7: "guide"}

# class_id -> power, drain, tick, injury, rest, monster, event, npc, empty
CLASS_MODS: dict[int, dict[str, float]] = {
    1: {"power": 0.10, "drain": -0.10, "tick": 0.04, "injury": -0.08, "rest": 0.02, "monster": 8, "event": -2, "npc": -2, "empty": -4},
    2: {"power": 0.08, "drain": -0.08, "tick": 0.00, "injury": -0.04, "rest": 0.00, "monster": 10, "event": -4, "npc": -2, "empty": -4},
    3: {"power": 0.02, "drain": 0.02, "tick": -0.06, "injury": 0.02, "rest": 0.00, "monster": 0, "event": 2, "npc": 0, "empty": 6},
    4: {"power": 0.04, "drain": 0.06, "tick": 0.00, "injury": 0.06, "rest": 0.04, "monster": 4, "event": 8, "npc": 0, "empty": -12},
    5: {"power": 0.00, "drain": 0.06, "tick": -0.08, "injury": 0.05, "rest": -0.04, "monster": 6, "event": 0, "npc": -2, "empty": -4},
    6: {"power": -0.04, "drain": -0.06, "tick": 0.06, "injury": -0.05, "rest": 0.25, "monster": -8, "event": 2, "npc": 4, "empty": 2},
    7: {"power": -0.06, "drain": 0.04, "tick": 0.02, "injury": 0.02, "rest": 0.00, "monster": -6, "event": 2, "npc": 12, "empty": -8},
}
STANCE_MODS: dict[str, dict[str, float]] = {
    "scout": {"drain": 0.03, "tick": -0.04, "injury": 0.04, "monster": 2, "empty": 6},
    "shield": {"drain": -0.04, "tick": 0.03, "injury": -0.05, "monster": 4, "empty": 0},
    "guide": {"drain": 0.00, "tick": 0.02, "injury": 0.00, "monster": -4, "empty": -4},
}
TEMPER_MODS: dict[str, dict[str, float]] = {
    "curiosity": {"power": 0.00, "drain": 0.02, "tick": -0.03, "injury": 0.04, "rest": 0.00, "monster": 0, "event": 8, "empty": -6},
    "temper": {"power": 0.02, "drain": 0.05, "tick": -0.04, "injury": 0.06, "rest": -0.04, "monster": 8, "event": 2, "empty": -6},
    "stay": {"power": 0.00, "drain": -0.04, "tick": 0.04, "injury": -0.05, "rest": 0.04, "monster": -4, "event": 0, "empty": 8},
}

# Combat traits only. Others stay tags.
TRAIT_MODS: dict[str, dict[str, float]] = {
    "осторожная": {"injury": -0.16, "drain": -0.08, "tick": 0.14},
    "бесстрашная": {"tick": -0.10, "power": 0.04, "injury": 0.10, "drain": 0.08, "monster": 6},
    "верная": {},
    "одиночка": {},
    "боится_тьмы": {"tick": 0.10},
    "вспыльчивая": {"monster": 8, "power": 0.03, "injury": 0.08, "drain": 0.04},
    "упрямая": {"drain": -0.06, "power": 0.03, "tick": 0.08},
    "тихая": {"injury": -0.04},
}

KIND_WEIGHTS_START = {KIND_EMPTY: 34, KIND_MONSTER: 30, KIND_EVENT: 18, KIND_NPC: 10, KIND_FIND: 8}
KIND_WEIGHTS_BAND1 = {KIND_EMPTY: 26, KIND_MONSTER: 38, KIND_EVENT: 18, KIND_NPC: 10, KIND_FIND: 8}
KIND_WEIGHTS_DEEP = {KIND_EMPTY: 16, KIND_MONSTER: 48, KIND_EVENT: 18, KIND_NPC: 10, KIND_FIND: 8}

TRAUMA_CHANCE = {
    KIND_MONSTER: (0.09, 0.025),
    KIND_EVENT: (0.05, 0.02),
    KIND_NPC: (0.00, 0.03),
    KIND_EMPTY: (0.00, 0.00),
    KIND_FIND: (0.00, 0.00),
    "BOSS": (0.16, 0.07),
}
TRAUMA_GRADE = {
    KIND_MONSTER: (0.80, 0.20),
    KIND_EVENT: (0.88, 0.12),
    KIND_NPC: (0.88, 0.12),
    "BOSS": (0.70, 0.30),
}
FLESH_PART_W = {
    KIND_MONSTER: (("рука", 30), ("рёбра", 28), ("лицо", 18), ("нога", 14), ("глаз", 10)),
    KIND_EVENT: (("нога", 50), ("глаз", 20), ("рука", 15), ("рёбра", 10), ("лицо", 5)),
    "BOSS": (("рёбра", 36), ("рука", 24), ("лицо", 16), ("глаз", 14), ("нога", 10)),
}
PSYCHE_FACET_W = {
    KIND_MONSTER: (("ярость", 40), ("страх", 30), ("боится_тьмы", 20), ("вина", 10)),
    KIND_EVENT: (("боится_тьмы", 40), ("страх", 30), ("вина", 20), ("ярость", 10)),
    KIND_NPC: (("боится_тьмы", 40), ("страх", 30), ("вина", 20), ("ярость", 10)),
    "BOSS": (("страх", 35), ("боится_тьмы", 30), ("ярость", 20), ("вина", 15)),
}

CHIP_BLEED = "bleed"
CHIP_POISON = "poison"
CHIP_WARD = "ward"
CHIP_LIMP = "limp"
CHIP_LABEL = {
    CHIP_BLEED: "кровь",
    CHIP_POISON: "яд",
    CHIP_WARD: "повязка",
    CHIP_LIMP: "хромота",
}

TEMPLATE_STATUS = {
    "hand_slip": "arm_cut",
    "rib_crack": "rib_crack",
    "eye_soot": "eye_soot",
    "leg_twist": "leg_twist",
    "face_cut": "face_cut",
    "fear_dark": "dark_ask",
    "night_scream": "fear_tremor",
    "rage_spark": "rage_spark",
    "guilt_rest": "guilt_prick",
}


@dataclass(frozen=True)
class StatusDef:
    id: str
    name_ru: str
    family: str
    key: str
    bucket: str
    grade: str
    power: float
    tick: float
    drain: float
    returns: int
    line_ru: str


STATUSES: tuple[StatusDef, ...] = (
    StatusDef("arm_graze", "Ссадина ладони", "рука", "рука", "flesh", GRADE_LIGHT, -0.04, 0.00, 0.04, 0, "Держит оружие через боль, бьёт чуть слабее."),
    StatusDef("arm_cut", "Порез руки", "рука", "рука", "flesh", GRADE_SERIOUS, -0.12, 0.04, 0.08, 1, "Рука в плаще: сила ниже, до города не заживёт."),
    StatusDef("leg_twist", "Подворот", "нога", "нога", "flesh", GRADE_LIGHT, -0.02, 0.08, 0.00, 0, "Короче шаг. Колонна чуть медленнее до костра."),
    StatusDef("leg_wound", "Рана ноги", "нога", "нога", "flesh", GRADE_SERIOUS, -0.08, 0.12, 0.06, 1, "Хромает. Спуск медленнее."),
    StatusDef("face_cut", "Порез лица", "лицо", "лицо", "flesh", GRADE_SERIOUS, -0.04, 0.00, 0.04, 1, "Лицо в крови. Шрам на рамке."),
    StatusDef("eye_soot", "Сажа в глазу", "глаз", "глаз", "flesh", GRADE_LIGHT, -0.03, 0.04, 0.00, 0, "Хуже видит до костра."),
    StatusDef("eye_hurt", "Глаз повреждён", "глаз", "глаз", "flesh", GRADE_SERIOUS, -0.10, 0.08, 0.04, 2, "Глаз заплыл."),
    StatusDef("rib_bruise", "Ушиб бока", "рёбра", "рёбра", "flesh", GRADE_LIGHT, -0.03, 0.00, 0.08, 0, "Бок ноет. В бою сток чуть выше."),
    StatusDef("rib_crack", "Трещина ребра", "рёбра", "рёбра", "flesh", GRADE_SERIOUS, -0.10, 0.04, 0.14, 1, "Дышит коротко. Сток сильнее."),
    StatusDef("fear_tremor", "Дрожь", "страх", "страх", "psyche", GRADE_LIGHT, -0.02, 0.06, 0.00, 0, "Руки трясутся. Чуть медленнее."),
    StatusDef("fear_wound", "Страх", "страх", "страх", "psyche", GRADE_SERIOUS, -0.08, 0.10, 0.06, 1, "Боится идти. Сила ниже до города."),
    StatusDef("rage_spark", "Злость", "ярость", "ярость", "psyche", GRADE_LIGHT, 0.04, -0.04, 0.08, 0, "Бьёт злее и быстрее, отряд платит стоком."),
    StatusDef("rage_wound", "Ярость", "ярость", "ярость", "psyche", GRADE_SERIOUS, 0.08, -0.06, 0.12, 1, "Сильнее в бою, жрёт HP."),
    StatusDef("guilt_prick", "Укол", "вина", "вина", "psyche", GRADE_LIGHT, 0.00, 0.00, 0.00, 0, "Молчит у угля."),
    StatusDef("dark_ask", "Просит не гасить", "тьма", "боится_тьмы", "psyche", GRADE_LIGHT, 0.00, 0.08, 0.00, 0, "Просит свет. Во тьме хочет развернуться."),
    StatusDef("dark_wound", "Боится тьмы", "тьма", "боится_тьмы", "psyche", GRADE_SERIOUS, -0.06, 0.12, 0.04, 2, "Во тьме почти не идёт."),
)
STATUS_BY_ID: dict[str, StatusDef] = {s.id: s for s in STATUSES}
STATUS_BY_KEY_GRADE: dict[tuple[str, str], StatusDef] = {(s.key, s.grade): s for s in STATUSES}
FLESH_BY_PART_GRADE: dict[tuple[str, str], str] = {
    (s.key, s.grade): s.id for s in STATUSES if s.bucket == "flesh"
}
ESCALATE = {
    "arm_graze": "arm_cut",
    "leg_twist": "leg_wound",
    "eye_soot": "eye_hurt",
    "rib_bruise": "rib_crack",
    "fear_tremor": "fear_wound",
    "rage_spark": "rage_wound",
    "dark_ask": "dark_wound",
}


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _half_up(value: float) -> int:
    return int(math.floor(float(value) + 0.5))


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    if not rows:
        return 0.0
    return sum(rows) / len(rows)


@lru_cache(maxsize=1)
def load_node_events() -> tuple[dict[str, Any], ...]:
    raw = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    return tuple(dict(row) for row in (raw.get("templates") or []))


def events_by_kind(kind: str) -> list[dict[str, Any]]:
    return [row for row in load_node_events() if str(row.get("kind")) == kind]


def hole(depth: int, party_power_eff: float) -> float:
    threat = max(1, int(depth))
    armor = max(0.01, float(party_power_eff))
    return threat / (threat + ARMOR_K * armor)


def overage_g(depth: int, d_fair: int) -> float:
    fair = max(1, int(d_fair))
    return max(0.0, float(max(0, int(depth))) / float(fair) - 1.0)


def drain_frac(depth: int, d_fair: int) -> float:
    return DRAIN_BASE_FRAC * (DRAIN_LAMBDA ** overage_g(depth, d_fair))


def _clip_hp_frac(raw: float, *, floor: int, cap_frac: float, hp_ref: int) -> int:
    ref = max(1, int(hp_ref))
    cap = max(int(floor), int(math.floor(float(cap_frac) * ref)))
    return int(_clip(_half_up(raw), int(floor), cap))


def combat_drain_hole(depth: int, party_power_eff: float, hp_ref: int = 48, *, d_fair: int | None = None) -> int:
    fair = int(d_fair) if d_fair is not None else d_max_of(max(1, int(round(float(party_power_eff or 1)))))
    frac = drain_frac(depth, fair)
    return _clip_hp_frac(max(1, int(hp_ref)) * frac, floor=COMBAT_FLOOR, cap_frac=COMBAT_CAP_FRAC, hp_ref=hp_ref)


def boss_drain_hole(depth: int, party_power_eff: float, hp_ref: int = 48, *, d_fair: int | None = None) -> int:
    fair = int(d_fair) if d_fair is not None else d_max_of(max(1, int(round(float(party_power_eff or 1)))))
    frac = drain_frac(depth, fair)
    return _clip_hp_frac(
        max(1, int(hp_ref)) * BOSS_FRAC_MULT * frac, floor=BOSS_FLOOR, cap_frac=BOSS_CAP_FRAC, hp_ref=hp_ref
    )


def combat_drain_legacy(depth: int, party_power: int) -> int:
    threat = max(0, int(depth))
    gap = max(0, threat - int(party_power))
    return max(1, int(round(4 + 0.45 * gap)))


def boss_drain_legacy(depth: int, party_power: int) -> int:
    threat = max(0, int(depth))
    gap = max(0, threat - int(party_power))
    return max(2, int(round(10 + 0.7 * gap)))


def living_mercs(mercs: Iterable[MercState]) -> list[MercState]:
    return [m for m in mercs if m.living()]


def has_lamp(mercs: Iterable[MercState]) -> bool:
    for merc in living_mercs(mercs):
        if int(getattr(merc, "class_id", 0) or 0) == HEALER_CLASS_ID:
            return True
        if str(getattr(merc, "stance", "") or "") == "guide":
            return True
    return False


def actor_mods(merc: MercState, *, party_size: int, depth: int = 0, d_max: int = 8, lamp: bool = False) -> dict[str, float]:
    out = {
        "power": 0.0,
        "drain": 0.0,
        "tick": 0.0,
        "injury": 0.0,
        "rest": 0.0,
        KIND_MONSTER: 0.0,
        KIND_EVENT: 0.0,
        KIND_NPC: 0.0,
        KIND_EMPTY: 0.0,
        KIND_FIND: 0.0,
    }
    cid = int(getattr(merc, "class_id", 0) or 0)
    stance = str(getattr(merc, "stance", "") or "")
    class_row = CLASS_MODS.get(cid)
    if class_row:
        for key, val in class_row.items():
            out[key] = out.get(key, 0.0) + float(val)
        expected = CLASS_TO_STANCE.get(cid)
        if stance and expected and stance != expected:
            for key, val in STANCE_MODS.get(stance, {}).items():
                out[key] = out.get(key, 0.0) + float(val)
    elif stance in STANCE_MODS:
        for key, val in STANCE_MODS[stance].items():
            out[key] = out.get(key, 0.0) + float(val)
    temper = str(getattr(merc, "temper", "") or "")
    for key, val in TEMPER_MODS.get(temper, {}).items():
        out[key] = out.get(key, 0.0) + float(val)
    traits = [str(t) for t in (getattr(merc, "traits", None) or [])]
    size = max(1, int(party_size))
    for trait in traits:
        row = dict(TRAIT_MODS.get(trait) or {})
        if trait == "верная":
            row = {"power": 0.04, "drain": -0.04, "injury": -0.04} if size >= 2 else {"drain": 0.06, "tick": 0.06}
        elif trait == "одиночка":
            row = {"power": 0.05, "tick": -0.05} if size == 1 else {"drain": 0.06, "injury": 0.05}
        elif trait == "боится_тьмы":
            if lamp:
                row = {"tick": 0.05}
            else:
                row = {"tick": 0.10}
                if d_max > 0 and depth > 0.70 * d_max:
                    row["power"] = -0.04
                if depth > 0 and depth % 10 == 0:
                    row["injury"] = 0.12
        for key, val in row.items():
            out[key] = out.get(key, 0.0) + float(val)
    for row in list(getattr(merc, "flesh", None) or []) + list(getattr(merc, "psyche", None) or []):
        spec = status_from_row(row)
        if spec is None:
            continue
        out["power"] += spec.power
        out["tick"] += spec.tick
        out["drain"] += spec.drain
    out["tick"] = _clip(out["tick"], -0.28, 0.28)
    out["injury"] = _clip(out["injury"], -0.32, 0.32)
    out["drain"] = _clip(out["drain"], -0.22, 0.22)
    out["power"] = _clip(out["power"], -0.40, 0.25)
    return out


def power_raw_of(merc: MercState) -> int:
    return int(compute_power(merc))


def power_eff_of(merc: MercState, *, party_size: int, depth: int = 0, d_max: int = 8, lamp: bool = False) -> float:
    raw = max(1, power_raw_of(merc))
    bonus = actor_mods(merc, party_size=party_size, depth=depth, d_max=d_max, lamp=lamp)["power"]
    return raw * (1.0 + bonus)


def party_power_eff(mercs: Iterable[MercState], *, depth: int = 0, d_max: int = 8, living_only: bool = True) -> float:
    rows = living_mercs(mercs) if living_only else list(mercs)
    lamp = has_lamp(rows)
    size = max(1, len(rows))
    return float(sum(power_eff_of(m, party_size=size, depth=depth, d_max=d_max, lamp=lamp) for m in rows))


def d_max_eff(mercs: Iterable[MercState], *, depth: int = 0) -> int:
    """Comfort depth from raw party power. depth is unused so it does not oscillate mid-descent."""
    _ = depth
    return d_max_of(party_power(mercs))


def t_eff_of(mercs: Iterable[MercState], *, t_node: int = T_NODE_SEC, depth: int = 0, d_max: int = 8) -> int:
    living = living_mercs(mercs)
    if not living:
        return int(_clip(t_node, T_EFF_MIN, T_EFF_MAX))
    lamp = has_lamp(living)
    size = len(living)
    mean_tick = _mean(
        actor_mods(m, party_size=size, depth=depth, d_max=d_max, lamp=lamp)["tick"] for m in living
    )
    return int(_clip(round(int(t_node) * (1.0 + mean_tick)), T_EFF_MIN, T_EFF_MAX))


def drain_mult_of(mercs: Iterable[MercState], *, depth: int = 0, d_max: int = 8) -> float:
    living = living_mercs(mercs)
    if not living:
        return 1.0
    lamp = has_lamp(living)
    size = len(living)
    mean_drain = _mean(
        actor_mods(m, party_size=size, depth=depth, d_max=d_max, lamp=lamp)["drain"] for m in living
    )
    return _clip(1.0 + mean_drain, 0.75, 1.25)


def injury_mult_of(mercs: Iterable[MercState], *, depth: int = 0, d_max: int = 8) -> float:
    living = living_mercs(mercs)
    if not living:
        return 1.0
    lamp = has_lamp(living)
    size = len(living)
    mean_inj = _mean(
        actor_mods(m, party_size=size, depth=depth, d_max=d_max, lamp=lamp)["injury"] for m in living
    )
    return 1.0 + mean_inj


def kind_weight_base(depth: int) -> dict[str, float]:
    d = max(1, int(depth))
    if d <= 8:
        return dict(KIND_WEIGHTS_START)
    if d <= 20:
        return dict(KIND_WEIGHTS_BAND1)
    return dict(KIND_WEIGHTS_DEEP)


def kind_weights(mercs: Iterable[MercState], depth: int, d_max: int) -> dict[str, float]:
    base = kind_weight_base(depth)
    living = living_mercs(mercs)
    if living:
        lamp = has_lamp(living)
        size = len(living)
        for kind in REGULAR_KINDS:
            extra = _mean(
                actor_mods(m, party_size=size, depth=depth, d_max=d_max, lamp=lamp).get(kind, 0.0)
                for m in living
            )
            base[kind] = max(4.0, float(base[kind]) + extra)
    total = sum(base.values()) or 1.0
    return {k: 100.0 * v / total for k, v in base.items()}


def period_parts_layer(d_max: int, t_eff: int) -> tuple[float, float, float]:
    ceil = max(1, int(d_max))
    t_eff = max(T_EFF_MIN, int(t_eff))
    t_down = float(t_eff * ceil)
    t_rest = 50.0 + 10.0 * math.log(1.0 + ceil)
    return t_down, float(T_UP_SEC), t_rest


def time_at_depth_layer(run_origin: datetime, cycle: int, depth: int, d_max: int, t_eff: int) -> datetime:
    t_down, t_up, t_rest = period_parts_layer(d_max, t_eff)
    period = t_down + t_up + t_rest
    sec = float(cycle) * period + max(1, int(depth)) * float(max(T_EFF_MIN, int(t_eff)))
    return _aware(run_origin) + timedelta(seconds=sec)


def rest_time_layer(run_origin: datetime, cycle: int, d_max: int, t_eff: int) -> datetime:
    t_down, t_up, _t_rest = period_parts_layer(d_max, t_eff)
    period = t_down + t_up + period_parts_layer(d_max, t_eff)[2]
    return _aware(run_origin) + timedelta(seconds=float(cycle) * period + t_down + t_up)


def sawtooth_layer(
    *,
    run_origin: datetime,
    now: datetime,
    d_max: int,
    t_eff: int,
    pb_depth: int = 0,
) -> dict[str, Any]:
    now = _aware(now)
    origin = _aware(run_origin)
    ceil = float(max(1, int(d_max)))
    t_eff = max(T_EFF_MIN, int(t_eff))
    t_down, t_up, t_rest = period_parts_layer(int(ceil), t_eff)
    period = t_down + t_up + t_rest
    elapsed = max(0.0, (now - origin).total_seconds())
    phase = elapsed % period if period > 0 else 0.0
    if phase < t_down:
        depth = min(ceil, math.floor(phase / t_eff) if t_eff else 0)
        state = STATE_DESCENDING
        u = float(depth) / ceil if ceil else 0.0
        if u < 0.35:
            status_key = "DESCENDING_FAST"
            pace = "fast"
        elif u < 0.75:
            status_key = "DESCENDING_MID"
            pace = "mid"
        else:
            status_key = "DESCENDING_HARD"
            pace = "hard"
    elif phase < t_down + t_up:
        v = (phase - t_down) / t_up if t_up > 0 else 1.0
        depth = ceil * (1.0 - v)
        state = STATE_ASCENDING
        status_key = "ASCENDING"
        pace = "up"
        u = 1.0
    else:
        depth = 0.0
        state = STATE_REST
        status_key = "SURFACE_REST"
        pace = "camp"
        u = 0.0
    d_floor = max(0, int(math.floor(depth)))
    return {
        "hours": elapsed / 3600.0,
        "d_ceiling": ceil,
        "depth": float(depth),
        "d": d_floor,
        "state": state,
        "status_key": status_key,
        "status": HUD_STATUS[status_key],
        "pace": pace,
        "t_down": t_down,
        "t_up": t_up,
        "t_rest": t_rest,
        "period": period,
        "phase": phase,
        "elapsed_sec": elapsed,
        "implied_record": max(int(pb_depth or 0), implied_record(elapsed_sec=elapsed, depth=float(depth), ceil=ceil, t_down=t_down)),
        "strain": min(1.0, max(0.0, float(depth) / ceil)) if state == STATE_DESCENDING and ceil else 0.0,
        "u": u if state == STATE_DESCENDING else 0.0,
        "T_eff": t_eff,
    }


def walk_frame(*, last_d: int, d_fair: int, t_eff: int, pb_depth: int = 0) -> dict[str, Any]:
    d = max(0, int(last_d))
    ceil = float(max(1, int(d_fair)))
    tick = max(T_EFF_MIN, int(t_eff))
    t_down, t_up, t_rest = period_parts_layer(int(ceil), tick)
    if d <= 0:
        state = STATE_REST
        status_key = "SURFACE_REST"
        pace = "camp"
        u = 0.0
    else:
        state = STATE_DESCENDING
        u = d / ceil if ceil else 0.0
        if u < 0.35:
            status_key = "DESCENDING_FAST"
            pace = "fast"
        elif u < 1.0:
            status_key = "DESCENDING_MID"
            pace = "mid"
        else:
            status_key = "DESCENDING_HARD"
            pace = "hard"
    return {
        "hours": 0.0,
        "d_ceiling": ceil,
        "depth": float(d),
        "d": d,
        "state": state,
        "status_key": status_key,
        "status": HUD_STATUS[status_key],
        "pace": pace,
        "t_down": t_down,
        "t_up": t_up,
        "t_rest": t_rest,
        "period": t_down + t_up + t_rest,
        "phase": 0.0,
        "elapsed_sec": 0.0,
        "implied_record": max(int(pb_depth or 0), d),
        "strain": min(1.0, max(0.0, u)) if state == STATE_DESCENDING and ceil else 0.0,
        "u": u if state == STATE_DESCENDING else 0.0,
        "T_eff": tick,
    }


def roll_kind(party: PqParty, depth: int, d_max: int) -> str:
    weights = kind_weights(party.mercs, depth, d_max)
    rng = pq_rng("pq-kind", party.seed, party.last_cycle, depth)
    keys = list(REGULAR_KINDS)
    vals = [max(0.01, float(weights.get(k, 4.0))) for k in keys]
    return rng.choices(keys, weights=vals, k=1)[0]


def pick_event_row(party: PqParty, kind: str, depth: int) -> dict[str, Any]:
    pool = events_by_kind(kind)
    if not pool:
        pool = events_by_kind(KIND_EMPTY)
    rng = pq_rng("pq-row", party.seed, party.last_cycle, depth, kind)
    weights = [max(1, int(row.get("weight") or 1)) for row in pool]
    return dict(rng.choices(pool, weights=weights, k=1)[0])


def pick_actor(party: PqParty, row: dict[str, Any]) -> MercState | None:
    living = living_mercs(party.mercs)
    if not living:
        return None
    prefer = str(row.get("prefer_stance") or "")
    prefer_trait = str(row.get("prefer_trait") or "")
    rng = pq_rng("pq-actor", party.seed, party.last_cycle, row.get("id"), living[0].card_id)
    pool = living
    if prefer:
        hit = [m for m in living if str(getattr(m, "stance", "")) == prefer]
        if hit:
            pool = hit
    if prefer_trait:
        hit = [m for m in pool if prefer_trait in [str(t) for t in (getattr(m, "traits", None) or [])]]
        if hit:
            pool = hit
    return rng.choice(pool)


def status_from_row(row: dict[str, Any] | None) -> StatusDef | None:
    if not isinstance(row, dict):
        return None
    sid = str(row.get("id") or "")
    if sid in STATUS_BY_ID:
        return STATUS_BY_ID[sid]
    key = str(row.get("part") or row.get("facet") or "")
    grade = GRADE_FROM_SEV.get(str(row.get("severity") or ""), GRADE_SERIOUS)
    return STATUS_BY_KEY_GRADE.get((key, grade))


def status_tail(row: dict[str, Any]) -> str:
    spec = status_from_row(row)
    if spec is None:
        return ""
    if spec.grade == GRADE_LIGHT:
        return "до костра"
    left = int(row.get("returns_left") or spec.returns or 1)
    if left <= 1:
        return "1 город"
    return f"{left} города"


def public_status(row: dict[str, Any]) -> dict[str, Any]:
    spec = status_from_row(row)
    if spec is None:
        return {}
    return {
        "id": spec.id,
        "name_ru": spec.name_ru,
        "grade": spec.grade,
        "tail": status_tail(row),
        "line_ru": spec.line_ru,
        "bucket": spec.bucket,
    }


def _rows_of(merc: MercState, bucket: str) -> list[dict[str, Any]]:
    raw = getattr(merc, bucket, None) or []
    return [dict(x) for x in raw if isinstance(x, dict)]


def apply_status(merc: MercState, status_id: str, *, rng=None) -> dict[str, Any] | None:
    spec = STATUS_BY_ID.get(status_id)
    if spec is None:
        return None
    bucket = spec.bucket
    rows = _rows_of(merc, bucket)
    for i, old in enumerate(rows):
        old_spec = status_from_row(old)
        if old_spec is None or old_spec.key != spec.key:
            continue
        if spec.grade == GRADE_SERIOUS and old_spec.grade == GRADE_LIGHT:
            rows[i] = _status_row(spec)
            setattr(merc, bucket, rows)
            return rows[i]
        if spec.grade == old_spec.grade and spec.grade == GRADE_LIGHT and ESCALATE.get(old_spec.id):
            if rng is not None and rng.random() < 0.40:
                nxt = STATUS_BY_ID[ESCALATE[old_spec.id]]
                rows[i] = _status_row(nxt)
                setattr(merc, bucket, rows)
                return rows[i]
        return None
    if len(rows) >= 3:
        if spec.grade == GRADE_LIGHT:
            return None
        weakest = min(range(len(rows)), key=lambda i: 1 if status_from_row(rows[i]) and status_from_row(rows[i]).grade == GRADE_LIGHT else 2)
        weak = status_from_row(rows[weakest])
        if weak and weak.grade == GRADE_SERIOUS:
            return None
        rows[weakest] = _status_row(spec)
        setattr(merc, bucket, rows)
        return rows[weakest]
    row = _status_row(spec)
    rows.append(row)
    setattr(merc, bucket, rows)
    return row


def _status_row(spec: StatusDef) -> dict[str, Any]:
    row = {
        "id": spec.id,
        "severity": SEV_FROM_GRADE[spec.grade],
        "permanent": False,
        "returns_left": int(spec.returns),
    }
    if spec.bucket == "flesh":
        row["part"] = spec.key
    else:
        row["facet"] = spec.key
    return row


def heal_light(merc: MercState) -> None:
    for bucket in ("flesh", "psyche"):
        kept = []
        for row in _rows_of(merc, bucket):
            spec = status_from_row(row)
            if spec is None or spec.grade != GRADE_LIGHT:
                kept.append(row)
        setattr(merc, bucket, kept)


def tick_city_return(merc: MercState) -> None:
    heal_light(merc)
    for bucket in ("flesh", "psyche"):
        kept = []
        for row in _rows_of(merc, bucket):
            spec = status_from_row(row)
            if spec is None:
                kept.append(row)
                continue
            if spec.grade != GRADE_SERIOUS:
                kept.append(row)
                continue
            left = int(row.get("returns_left") if row.get("returns_left") is not None else spec.returns) - 1
            if left <= 0:
                continue
            row = dict(row)
            row["returns_left"] = left
            kept.append(row)
        setattr(merc, bucket, kept)


def healer_city_extra(party: PqParty) -> None:
    living = living_mercs(party.mercs)
    if not any(int(getattr(m, "class_id", 0) or 0) == HEALER_CLASS_ID for m in living):
        return
    candidates: list[tuple[MercState, str, int]] = []
    for merc in living:
        for bucket in ("flesh", "psyche"):
            for i, row in enumerate(_rows_of(merc, bucket)):
                spec = status_from_row(row)
                if spec and spec.grade == GRADE_SERIOUS:
                    candidates.append((merc, bucket, i))
    if not candidates:
        return
    merc, bucket, idx = candidates[0]
    rows = _rows_of(merc, bucket)
    row = dict(rows[idx])
    left = int(row.get("returns_left") or 1) - 1
    if left <= 0:
        rows.pop(idx)
    else:
        row["returns_left"] = left
        rows[idx] = row
    setattr(merc, bucket, rows)


def migrate_legacy_status(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("id") in STATUS_BY_ID:
        return row
    key = str(row.get("part") or row.get("facet") or "")
    grade = GRADE_FROM_SEV.get(str(row.get("severity") or ""), GRADE_SERIOUS)
    spec = STATUS_BY_KEY_GRADE.get((key, grade))
    if spec is None:
        return row
    out = _status_row(spec)
    if row.get("permanent"):
        out["permanent"] = True
    return out


def city_return(party: PqParty) -> None:
    for merc in party.mercs:
        tick_city_return(merc)
    healer_city_extra(party)
    party.chips = []


def heal_one_trauma(party: PqParty) -> dict[str, Any] | None:
    for merc in party.mercs:
        for bucket in ("flesh", "psyche"):
            rows = _rows_of(merc, bucket)
            for i, row in enumerate(rows):
                spec = status_from_row(row)
                if spec is None or spec.grade != GRADE_LIGHT:
                    continue
                rows.pop(i)
                setattr(merc, bucket, rows)
                return {"who": merc.name, "id": spec.id, "grade": GRADE_LIGHT, "name_ru": spec.name_ru}
    for merc in party.mercs:
        for bucket in ("flesh", "psyche"):
            rows = _rows_of(merc, bucket)
            for i, row in enumerate(rows):
                spec = status_from_row(row)
                if spec is None or spec.grade != GRADE_SERIOUS:
                    continue
                left = int(row.get("returns_left") if row.get("returns_left") is not None else spec.returns) - 1
                if left <= 0:
                    rows.pop(i)
                else:
                    row = dict(row)
                    row["returns_left"] = left
                    rows[i] = row
                setattr(merc, bucket, rows)
                return {"who": merc.name, "id": spec.id, "grade": GRADE_SERIOUS, "name_ru": spec.name_ru}
    return None


def visit_city(party: PqParty, depth: int, *, band: int) -> dict[str, Any]:
    city_d = int(depth)
    name = city_name_ru(city_d)
    party.checkpoint_d = max(int(getattr(party, "checkpoint_d", 0) or 0), city_d if is_city_depth(city_d) else 0)
    healed = 0
    for merc in party.mercs:
        before = int(merc.hp_current)
        if int(merc.hp_max) > 0:
            merc.hp_current = int(merc.hp_max)
        healed += max(0, int(merc.hp_current) - before)
    bought_here: list[dict[str, Any]] = []
    for merc in party.mercs:
        if not merc.living():
            continue
        buys = resolve_shop(
            merc, depth=city_d, seed=party.seed, cycle=party.last_cycle, band=band
        )
        bought_here.extend(buys)
        party.shop_log.extend(buys)
    trauma = heal_one_trauma(party)
    who = living_mercs(party.mercs)[0].name if living_mercs(party.mercs) else (party.mercs[0].name if party.mercs else "Она")
    line = f"{who} вошла в {name}"
    if bought_here:
        last = bought_here[-1]
        if last.get("kind") in ("gear", "sharpen", "consumable"):
            line = f"{last.get('who') or who} купила {last.get('name') or 'вещь'} в {name}"
            who = str(last.get("who") or who)
    if trauma:
        line = f"{line} · −{trauma.get('name_ru')}"
    phrase = assemble_phrase(kind="city", depth=city_d, line=line, who=who)
    if healed:
        phrase = f"{phrase} (+{healed} HP)"
    return event_dict(
        row=None,
        kind="city",
        depth=city_d,
        who=who,
        phrase=phrase,
        hp_delta=-healed,
        node=NODE_CITY,
    )


def rest_frac_for(merc: MercState, party: PqParty) -> float:
    living = living_mercs(party.mercs)
    lamp = has_lamp(living)
    size = max(1, len(living))
    mods = actor_mods(merc, party_size=size, lamp=lamp)
    aura = sum(HEALER_AURA for other in living if other is not merc and int(getattr(other, "class_id", 0) or 0) == HEALER_CLASS_ID)
    limp = any(c.get("id") == CHIP_LIMP for c in (party.chips or []))
    frac = REST_BASE_FRAC * (1.0 + float(mods.get("rest") or 0.0)) * (1.0 + aura)
    if limp:
        frac *= 0.5
    return _clip(frac, 0.0, REST_CAP_FRAC)


def apply_rest_layer(party: PqParty) -> int:
    healed = 0
    for merc in party.mercs:
        heal_light(merc)
        if not merc.living() and merc.hp_max <= 0:
            continue
        add = max(1, int(round(rest_frac_for(merc, party) * merc.hp_max)))
        before = int(merc.hp_current)
        merc.hp_current = min(int(merc.hp_max), max(0, before) + add)
        healed += int(merc.hp_current) - before
    party.chips = [c for c in (party.chips or []) if c.get("id") != CHIP_LIMP]
    return healed


def apply_drain_named(mercs: list[MercState], amount: int, *, depth: int = 0, d_max: int = 8) -> dict[str, int]:
    living = living_mercs(mercs)
    if not living or amount <= 0:
        return {}
    lamp = has_lamp(living)
    size = len(living)
    weights = [
        max(1, int(round(power_eff_of(m, party_size=size, depth=depth, d_max=d_max, lamp=lamp))))
        for m in living
    ]
    parts = split_weighted(int(amount), weights)
    lost: dict[str, int] = {}
    for merc, share in zip(living, parts):
        take = min(int(merc.hp_current), int(share))
        merc.hp_current = max(0, int(merc.hp_current) - int(share))
        if take:
            lost[merc.name] = lost.get(merc.name, 0) + take
    return lost


def tick_poison(party: PqParty) -> dict[str, int]:
    chips = [c for c in (party.chips or []) if c.get("id") == CHIP_POISON]
    if not chips:
        return {}
    lost = apply_drain_named(party.mercs, len(chips))
    kept = []
    for chip in party.chips or []:
        if chip.get("id") != CHIP_POISON:
            kept.append(chip)
            continue
        left = int(chip.get("left") or 2) - 1
        if left > 0:
            kept.append({**chip, "left": left})
    party.chips = kept
    return lost


def add_chip(party: PqParty, chip_id: str, who: str) -> None:
    if chip_id == CHIP_POISON:
        party.chips.append({"id": chip_id, "who": who, "left": 2})
        return
    if any(c.get("id") == chip_id for c in (party.chips or [])):
        return
    party.chips.append({"id": chip_id, "who": who})


def consume_chip(party: PqParty, chip_id: str) -> bool:
    for i, chip in enumerate(party.chips or []):
        if chip.get("id") == chip_id:
            party.chips.pop(i)
            return True
    return False


def _pick_weighted(rng, pairs: tuple[tuple[str, int], ...]) -> str:
    keys = [p[0] for p in pairs]
    weights = [max(1, int(p[1])) for p in pairs]
    return rng.choices(keys, weights=weights, k=1)[0]


def flesh_id_for(kind: str, part: str, grade: str) -> str | None:
    return FLESH_BY_PART_GRADE.get((part, grade))


def psyche_id_for(facet: str, grade: str) -> str | None:
    spec = STATUS_BY_KEY_GRADE.get((facet, grade))
    return spec.id if spec else None


def roll_trauma(party: PqParty, kind: str, depth: int, d_max: int) -> dict[str, Any] | None:
    flesh_p, mind_p = TRAUMA_CHANCE.get(kind, (0.0, 0.0))
    if flesh_p <= 0 and mind_p <= 0:
        return None
    living = living_mercs(party.mercs)
    if not living:
        return None
    inj = injury_mult_of(party.mercs, depth=depth, d_max=d_max)
    grace = (int(party.wipe_count) == 0 and int(party.nodes_seen) < 20)
    flesh_p = _clip(flesh_p * inj, 0.005, 0.22) if flesh_p else 0.0
    mind_p = _clip(mind_p * inj, 0.005, 0.22) if mind_p else 0.0
    rng = pq_rng("pq-trauma", party.seed, party.last_cycle, depth, kind)
    hit_flesh = flesh_p > 0 and rng.random() < flesh_p
    hit_mind = mind_p > 0 and rng.random() < mind_p
    if not hit_flesh and not hit_mind:
        return None
    light_w, serious_w = TRAUMA_GRADE.get(kind, (0.85, 0.15))
    if grace:
        serious_w *= 0.35
        total = light_w + serious_w
        light_w, serious_w = light_w / total, serious_w / total
    grade = GRADE_LIGHT if rng.random() < light_w else GRADE_SERIOUS
    target = rng.choice(living)
    if grace and int(getattr(target, "nodes_seen", 0) or 0) < 15 and grade == GRADE_SERIOUS and rng.random() > 0.35:
        grade = GRADE_LIGHT
    applied = None
    if hit_flesh:
        part = _pick_weighted(rng, FLESH_PART_W.get(kind, FLESH_PART_W[KIND_MONSTER]))
        sid = flesh_id_for(kind, part, grade)
        if sid:
            applied = apply_status(target, sid, rng=rng)
    if applied is None and hit_mind:
        facet = _pick_weighted(rng, PSYCHE_FACET_W.get(kind, PSYCHE_FACET_W[KIND_EVENT]))
        sid = psyche_id_for(facet, grade)
        if sid:
            applied = apply_status(target, sid, rng=rng)
    if not applied:
        return None
    spec = status_from_row(applied)
    return {"who": target.name, "status": public_status(applied), "id": spec.id if spec else ""}


def grant_event_gold(party: PqParty, merc: MercState | None, delta: int, band: int) -> tuple[int, bool]:
    if merc is None or delta == 0:
        return 0, False
    cap = merc_gold_cap_day(band)
    if int(party.gold_today) >= cap and delta > 0:
        return 0, True
    if delta < 0:
        take = min(int(merc.gold_wallet), abs(int(delta)))
        merc.gold_wallet -= take
        return -take, False
    add = int(delta)
    if int(party.gold_today) + add > cap:
        add = max(0, cap - int(party.gold_today))
        if add <= 0:
            return 0, True
        merc.gold_wallet += add
        return add, True
    merc.gold_wallet += add
    return add, False


def hp_ref_of(mercs: Iterable[MercState]) -> int:
    living = living_mercs(mercs)
    if not living:
        return 48
    return max(1, int(round(sum(max(1, int(m.hp_max)) for m in living) / len(living))))


def assemble_phrase(
    *,
    kind: str,
    depth: int,
    line: str,
    who: str,
    hp_by_name: dict[str, int] | None = None,
    gold_delta: int = 0,
    gold_capped: bool = False,
    status_ru: str = "",
) -> str:
    kind_ru = KIND_LABEL_RU.get(kind, kind)
    text = str(line or "").replace("{who}", who or "Она").replace("{actor}", who or "Она")
    text = text.replace("{name}", who or "Она")
    if not text.endswith((".", "!", "…")):
        pass
    suffix_bits: list[str] = []
    lost = {k: v for k, v in (hp_by_name or {}).items() if v}
    if lost:
        if len(lost) == 1:
            n = next(iter(lost.values()))
            suffix_bits.append(f"(−{n} HP)")
        else:
            bits = [f"{name} −{n}" for name, n in lost.items()]
            suffix_bits.append(f"({', '.join(bits)})")
    if gold_capped and gold_delta == 0:
        suffix_bits.append("(кап дня)")
    elif gold_delta:
        sign = "+" if gold_delta > 0 else ""
        suffix_bits.append(f"({sign}{gold_delta} зол.)")
    extra = " ".join(suffix_bits)
    trauma = f" · {status_ru}" if status_ru else ""
    body = f"{text} {extra}".strip() if extra else text
    return f"[{kind_ru}] Глубина {int(depth)} · {body}{trauma}".strip()


def event_dict(
    *,
    row: dict[str, Any] | None,
    kind: str,
    depth: int,
    who: str,
    phrase: str,
    hp_delta: int = 0,
    hp_by_name: dict[str, int] | None = None,
    gold_delta: int = 0,
    gold_capped: bool = False,
    status: dict[str, Any] | None = None,
    node: str = "",
) -> dict[str, Any]:
    return {
        "id": str((row or {}).get("id") or kind),
        "kind": kind,
        "kind_ru": KIND_LABEL_RU.get(kind, kind),
        "title_ru": str((row or {}).get("title_ru") or KIND_LABEL_RU.get(kind, kind)),
        "d": int(depth),
        "line_ru": str((row or {}).get("line_ru") or ""),
        "phrase": phrase,
        "actor": (row or {}).get("actor"),
        "who": who,
        "hp_delta": int(hp_delta),
        "hp_by_name": dict(hp_by_name or {}),
        "gold_delta": int(gold_delta),
        "gold_capped": bool(gold_capped),
        "status": status,
        "status_ru": str((status or {}).get("name_ru") or ""),
        "node": node,
        "from_llm": False,
        "glyph": KIND_GLYPH.get(kind, "·"),
    }


def resolve_layer_node(party: PqParty, depth: int, node: str, *, band: int) -> dict[str, Any]:
    d_max = max(1, int(d_max_eff(party.mercs, depth=depth)))
    party.nodes_seen = int(getattr(party, "nodes_seen", 0) or 0) + 1
    for merc in party.mercs:
        merc.nodes_seen = int(getattr(merc, "nodes_seen", 0) or 0) + 1
    poison_lost = tick_poison(party)
    who = living_mercs(party.mercs)[0].name if living_mercs(party.mercs) else "Она"

    if node == NODE_SHOP:
        for merc in party.mercs:
            if merc.living():
                buys = resolve_shop(
                    merc, depth=depth, seed=party.seed, cycle=party.last_cycle, band=band
                )
                party.shop_log.extend(buys)
        phrase = assemble_phrase(kind="shop", depth=depth, line=f"{who} зашла в лавку", who=who)
        if party.shop_log:
            last = party.shop_log[-1]
            phrase = assemble_phrase(
                kind="shop",
                depth=depth,
                line=f"{last.get('who') or who} купила {last.get('name') or 'вещь'}",
                who=str(last.get("who") or who),
            )
        return event_dict(row=None, kind="shop", depth=depth, who=who, phrase=phrase, node=node)

    if node == NODE_CITY:
        return visit_city(party, depth, band=band)

    if node == NODE_REST:
        healed = apply_rest_layer(party)
        auto_use_potions(party.mercs)
        phrase = assemble_phrase(
            kind="rest",
            depth=depth,
            line=f"{who} греется у угля",
            who=who,
        )
        if healed:
            phrase = f"{phrase} (+{healed} HP)"
        return event_dict(row=None, kind="rest", depth=depth, who=who, phrase=phrase, hp_delta=-healed, node=node)

    if node in (NODE_BRANCH, NODE_LANDMARK, NODE_SURFACE):
        kind = {NODE_BRANCH: "branch", NODE_LANDMARK: "landmark", NODE_SURFACE: "surface"}[node]
        lines = {
            "branch": f"{who} смотрит на два хода и идёт дальше",
            "landmark": f"{who} трогает метку и запоминает место",
            "surface": f"{who} сидит у стола и снова пойдёт",
        }
        if node == NODE_SURFACE:
            city_return(party)
        phrase = assemble_phrase(kind=kind, depth=depth, line=lines[kind], who=who)
        return event_dict(row=None, kind=kind, depth=depth, who=who, phrase=phrase, node=node)

    if node == NODE_BOSS:
        auto_use_potions(party.mercs, before_boss=True)
        pp = party_power_eff(party.mercs, depth=depth, d_max=d_max, living_only=True)
        raw = boss_drain_hole(depth, pp, hp_ref_of(party.mercs), d_fair=d_max)
        raw = max(BOSS_FLOOR, _half_up(raw * drain_mult_of(party.mercs, depth=depth, d_max=d_max)))
        if consume_chip(party, CHIP_WARD):
            raw = max(BOSS_FLOOR, _half_up(raw * 0.75))
        if consume_chip(party, CHIP_BLEED):
            raw += 1
        lost = apply_drain_named(party.mercs, raw, depth=depth, d_max=d_max)
        if poison_lost:
            for name, n in poison_lost.items():
                lost[name] = lost.get(name, 0) + n
        auto_use_potions(party.mercs)
        trauma = roll_trauma(party, "BOSS", depth, d_max)
        who = next(iter(lost), who)
        phrase = assemble_phrase(
            kind="boss",
            depth=depth,
            line="Хозяин яруса ударил отряд",
            who=who,
            hp_by_name=lost,
            status_ru=str((trauma or {}).get("status", {}).get("name_ru") or ""),
        )
        return event_dict(
            row=None,
            kind="boss",
            depth=depth,
            who=who,
            phrase=phrase,
            hp_delta=-sum(lost.values()),
            hp_by_name=lost,
            status=(trauma or {}).get("status"),
            node=node,
        )

    kind = roll_kind(party, depth, d_max)
    row = pick_event_row(party, kind, depth)
    actor = pick_actor(party, row)
    who = actor.name if actor else who
    line = str(row.get("line_ru") or "").format(who=who)
    hp_mult = float(row.get("hp_mult") or 0)
    lost: dict[str, int] = dict(poison_lost)
    if kind == KIND_MONSTER or hp_mult > 0:
        pp = party_power_eff(party.mercs, depth=depth, d_max=d_max, living_only=True)
        raw = combat_drain_hole(depth, pp, hp_ref_of(party.mercs), d_fair=d_max)
        raw = max(0, _half_up(raw * hp_mult)) if kind != KIND_MONSTER else raw
        if kind == KIND_MONSTER:
            raw = max(COMBAT_FLOOR, _half_up(raw * drain_mult_of(party.mercs, depth=depth, d_max=d_max)))
            if consume_chip(party, CHIP_WARD):
                raw = max(1, _half_up(raw * 0.75))
        else:
            raw = max(0, _half_up(raw * drain_mult_of(party.mercs, depth=depth, d_max=d_max)))
        if raw and consume_chip(party, CHIP_BLEED):
            raw += 1
        if raw:
            for name, n in apply_drain_named(party.mercs, raw, depth=depth, d_max=d_max).items():
                lost[name] = lost.get(name, 0) + n
        if kind == KIND_MONSTER:
            auto_use_potions(party.mercs)
    gold_delta, capped = grant_event_gold(party, actor, int(row.get("gold_delta") or 0), band)
    chip_id = row.get("chip")
    if chip_id in CHIP_LABEL:
        add_chip(party, str(chip_id), who)
    trauma = roll_trauma(party, kind, depth, d_max)
    phrase = assemble_phrase(
        kind=kind,
        depth=depth,
        line=line,
        who=who,
        hp_by_name=lost,
        gold_delta=gold_delta,
        gold_capped=capped,
        status_ru=str((trauma or {}).get("status", {}).get("name_ru") or ""),
    )
    return event_dict(
        row=row,
        kind=kind,
        depth=depth,
        who=who,
        phrase=phrase,
        hp_delta=-sum(lost.values()),
        hp_by_name=lost,
        gold_delta=gold_delta,
        gold_capped=capped,
        status=(trauma or {}).get("status"),
        node=node,
    )


def remember_event(party: PqParty, event: dict[str, Any]) -> None:
    party.last_event = event
    recent = list(party.recent_events or [])
    recent.append(event)
    party.recent_events = recent[-8:]


def layer_state_dump(party: PqParty) -> dict[str, Any]:
    return {
        "armed": True,
        "chips": list(party.chips or []),
        "recent_events": list(party.recent_events or [])[-8:],
        "last_event": party.last_event,
        "nodes_seen": int(party.nodes_seen or 0),
        "t_eff": int(party.t_eff or T_NODE_SEC),
        "nodes_by_card": {str(m.card_id): int(getattr(m, "nodes_seen", 0) or 0) for m in party.mercs},
        "walk_ts": party.walk_ts.isoformat() if getattr(party, "walk_ts", None) else None,
        "checkpoint_d": int(getattr(party, "checkpoint_d", 0) or 0),
    }


def apply_layer_dump(party: PqParty, blob: dict[str, Any] | None) -> None:
    data = blob if isinstance(blob, dict) else {}
    party.chips = [dict(x) for x in (data.get("chips") or []) if isinstance(x, dict)]
    party.recent_events = [dict(x) for x in (data.get("recent_events") or []) if isinstance(x, dict)]
    last = data.get("last_event")
    party.last_event = dict(last) if isinstance(last, dict) else None
    party.nodes_seen = int(data.get("nodes_seen") or 0)
    raw_walk = data.get("walk_ts")
    if raw_walk:
        try:
            party.walk_ts = datetime.fromisoformat(str(raw_walk))
        except ValueError:
            party.walk_ts = None
    party.checkpoint_d = max(0, int(data.get("checkpoint_d") or 0))
    by_card = data.get("nodes_by_card") or {}
    if isinstance(by_card, dict):
        for merc in party.mercs:
            merc.nodes_seen = int(by_card.get(str(merc.card_id)) or merc.nodes_seen or 0)


def special_phrase_fallback(node: str, who: str, depth: int) -> str:
    kind = {
        NODE_SHOP: "shop",
        NODE_CITY: "city",
        NODE_REST: "rest",
        NODE_BOSS: "boss",
        NODE_BRANCH: "branch",
        NODE_LANDMARK: "landmark",
        NODE_SURFACE: "surface",
        NODE_TRAVERSE: KIND_EMPTY,
        NODE_COMBAT: KIND_MONSTER,
    }.get(node, KIND_EMPTY)
    line = {
        "shop": f"{who} зашла в лавку",
        "city": f"{who} вошла в город",
        "rest": f"{who} греется у угля",
        "boss": "Хозяин яруса смотрит на отряд",
        "branch": f"{who} смотрит на два хода и идёт дальше",
        "landmark": f"{who} трогает метку и запоминает место",
        "surface": f"{who} сидит у стола",
        KIND_EMPTY: f"Ход пуст. {who} прошла без встречи",
        KIND_MONSTER: f"Удар пришёлся по {who}",
    }.get(kind, f"{who} идёт дальше")
    return assemble_phrase(kind=kind, depth=depth, line=line, who=who)
