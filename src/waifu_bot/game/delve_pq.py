"""Delve Progress Quest: flat power, shop, HP. Pure functions, no LLM, no I/O besides catalog JSON."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from waifu_bot.game.affix_display_names import resolve_prefix_name_ru, resolve_suffix_name_ru
from waifu_bot.game.delve_catalog import (
    DEPTH_EXP,
    NODE_BOSS,
    NODE_COMBAT,
    NODE_REST,
    NODE_SHOP,
    T_UP_SEC,
    gold_rate_per_sec,
    msk_today,
    period_parts,
    spine_type,
    split_weighted,
    walk_capped_grant,
    xp_rate_per_sec,
)
from waifu_bot.game.item_display_name import guess_gender_ru, inflect_adj_ru

GEAR_PATH = Path(__file__).resolve().parents[3] / "data" / "delve_gear.v1.json"
CONSUMABLE_PATH = Path(__file__).resolve().parents[3] / "data" / "delve_consumables.v1.json"

WIPE_CAP_PER_SYNC = 24
SHARPEN_COST_MULT = 4
PQ_SUFFIX_CHANCE = 0.70
PQ_PREFIX_STATS: tuple[str, ...] = (
    "strength",
    "agility",
    "intelligence",
    "endurance",
    "charm",
    "luck",
    "damage_flat",
    "melee_damage_flat",
    "ranged_damage_flat",
    "magic_damage_flat",
)
PQ_SUFFIX_FAMILIES: tuple[str, ...] = (
    "s_dmg_melee",
    "s_dmg_ranged",
    "s_dmg_magic",
    "s_monster_undead_slayer",
    "s_monster_beast_flat",
    "s_monster_demon_flat",
    "s_monster_dragon_flat",
    "s_monster_undead_flat",
)
POTION_ID = "potion_hp"
SALVE_ID = "salve_party"
POTION_HP_FRAC = 0.40
SALVE_AVG_FRAC = 0.55
REST_REGEN_FRAC = 0.10
POTION_HEAL_FRAC = 0.35
SALVE_HEAL_FRAC = 0.15

SLOT_TYPE_TO_SLOTS: dict[str, tuple[int, ...]] = {
    "weapon_1h": (1, 2),
    "weapon_2h": (1,),
    "offhand": (2,),
    "costume": (3,),
    "ring": (4, 5),
    "amulet": (6,),
}
SLOT_FAMILIES: dict[int, tuple[str, ...]] = {
    1: ("sword", "dagger", "axe", "bow"),
    2: ("shield", "dagger"),
    3: ("costume",),
    4: ("ring",),
    5: ("ring",),
    6: ("amulet",),
}
TWO_HAND = "weapon_2h"


@dataclass(frozen=True)
class GearTemplate:
    id: str
    name: str
    family_key: str
    slot_type: str
    tier: int
    base_ilvl: int


@dataclass(frozen=True)
class ConsumableDef:
    id: str
    name: str
    effect: str
    heal_frac: float
    price_per_band: int
    stack_cap: int
    party: bool


@dataclass
class GearPiece:
    slot: int
    name: str
    slot_type: str
    family_key: str
    template_id: str | None
    base_ilvl: int
    enchant_level: int = 0
    scaled_plus: int = 0
    prefix_stat: str | None = None
    prefix_tier: int = 0
    suffix_family: str | None = None
    suffix_tier: int = 0

    @property
    def ilvl(self) -> int:
        return int(self.base_ilvl) + int(self.enchant_level)

    @property
    def display_name(self) -> str:
        return flavor_display_name(self)

    def to_public(self) -> dict[str, Any]:
        return {
            "slot": int(self.slot),
            "name": self.name,
            "display_name": self.display_name,
            "slot_type": self.slot_type,
            "family_key": self.family_key,
            "template_id": self.template_id,
            "base_ilvl": int(self.base_ilvl),
            "enchant_level": int(self.enchant_level),
            "ilvl": self.ilvl,
            "scaled_plus": int(self.scaled_plus),
            "prefix_stat": self.prefix_stat,
            "prefix_tier": int(self.prefix_tier or 0),
            "suffix_family": self.suffix_family,
            "suffix_tier": int(self.suffix_tier or 0),
        }


@dataclass
class MercState:
    card_id: int
    slot: int
    name: str
    loyalty: int = 50
    level: int = 1
    xp_unspent: int = 0
    gold_wallet: int = 0
    power: int = 1
    hp_current: int = 48
    hp_max: int = 48
    gold_earned: int = 0
    xp_earned: int = 0
    gear: dict[int, GearPiece] = field(default_factory=dict)
    bag: dict[str, int] = field(default_factory=dict)
    last_shop_buy: list[dict[str, Any]] = field(default_factory=list)
    class_id: int = 0
    stance: str = "guide"
    temper: str = "stay"
    traits: list[str] = field(default_factory=list)
    flesh: list[dict[str, Any]] = field(default_factory=list)
    psyche: list[dict[str, Any]] = field(default_factory=list)
    nodes_seen: int = 0

    def living(self) -> bool:
        return int(self.hp_current) > 0


@dataclass
class ShopOffer:
    kind: str
    name: str
    price: int
    slot: int | None = None
    ilvl: int = 0
    template_id: str | None = None
    family_key: str = ""
    slot_type: str = ""
    base_ilvl: int = 0
    scaled_plus: int = 0
    enchant_to: int | None = None
    consumable_id: str | None = None
    item_name: str = ""
    prefix_stat: str | None = None
    prefix_tier: int = 0
    suffix_family: str | None = None
    suffix_tier: int = 0


@dataclass
class PqParty:
    seed: int
    run_origin: datetime
    last_ts: datetime
    wipe_count: int = 0
    last_cycle: int = 0
    last_d: int = 0
    gold_today: int = 0
    xp_today: int = 0
    grant_day: str | None = None
    gold_lifetime: int = 0
    xp_lifetime: int = 0
    mercs: list[MercState] = field(default_factory=list)
    shop_log: list[dict[str, Any]] = field(default_factory=list)
    wipe_log: list[dict[str, Any]] = field(default_factory=list)
    layer: int = 2
    t_node: int = 30
    t_eff: int = 30
    chips: list[dict[str, Any]] = field(default_factory=list)
    last_event: dict[str, Any] | None = None
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    nodes_seen: int = 0
    walk_ts: datetime | None = None


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def pq_rng(*parts: Any) -> random.Random:
    raw = ":".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def xp_to_next(level: int) -> int:
    n = max(0, int(level) - 1)
    return 40 + 20 * n + 3 * n * n


def band_of_depth(depth: int) -> int:
    return max(1, int(math.ceil(max(1, int(depth)) / 20.0)))


def gear_price(base_ilvl: int, band: int) -> int:
    item_tier = max(1, int(math.ceil(max(1, int(base_ilvl)) / 4.0)))
    b = max(1, min(int(band), item_tier))
    return max(1, int(round(12 * int(base_ilvl) * (1.12 ** (b - 1)))))


def sharpen_cost(base_ilvl: int, next_plus: int) -> int:
    n = max(1, int(next_plus))
    return max(1, int(round(SHARPEN_COST_MULT * max(1, int(base_ilvl)) * n)))


def clamp_affix_tier(band: int, delta: int) -> int:
    return max(1, min(10, int(band) + int(delta)))


def flavor_display_name(piece: GearPiece) -> str:
    base = str(piece.name or "").strip() or "Предмет"
    prefix = ""
    if piece.prefix_stat:
        raw = resolve_prefix_name_ru(str(piece.prefix_stat), max(1, int(piece.prefix_tier or 1)))
        prefix = inflect_adj_ru(raw, guess_gender_ru(base))
    suffix = ""
    if piece.suffix_family:
        suffix = resolve_suffix_name_ru(str(piece.suffix_family), max(1, int(piece.suffix_tier or 1)))
    body = " ".join(part for part in (prefix, base, suffix) if part)
    return f"{body} +{int(piece.enchant_level)}"


def roll_flavor_affixes(
    piece: GearPiece,
    *,
    seed: int,
    cycle: int,
    depth: int,
    card_id: int,
    band: int,
) -> GearPiece:
    rng = pq_rng(seed, cycle, depth, card_id, int(piece.slot), "affix")
    piece.prefix_stat = rng.choice(PQ_PREFIX_STATS)
    piece.prefix_tier = clamp_affix_tier(band, rng.choice((-1, 0, 1)))
    if rng.random() < PQ_SUFFIX_CHANCE:
        piece.suffix_family = rng.choice(PQ_SUFFIX_FAMILIES)
        piece.suffix_tier = clamp_affix_tier(band, rng.choice((-1, 0, 1)))
    else:
        piece.suffix_family = None
        piece.suffix_tier = 0
    return piece


def _base_name_from_template(offer: ShopOffer) -> str:
    tid = str(offer.template_id or "")
    if tid:
        for row in load_gear_templates():
            if row.id == tid:
                return row.name
    family = str(offer.family_key or "")
    if family and int(offer.base_ilvl or 0) > 0:
        tier = max(1, int(math.ceil(int(offer.base_ilvl) / 4.0)))
        return piece_for_family_tier(family, tier, int(offer.slot or 1)).name
    return "Предмет"


def consumable_price(price_per_band: int, band: int) -> int:
    return max(1, int(price_per_band) * max(1, int(band)))


def merc_gold_cap_day(band: int) -> int:
    return 80 * max(1, int(band))


def merc_xp_cap_day(band: int) -> int:
    return 60 * max(1, int(band))


def hp_max_of(power: int) -> int:
    return 40 + 8 * max(1, int(power))


D_MAX_BASE = 8.0
D_MAX_LIN = 0.40
D_MAX_QUAD = 0.0038


def d_max_of(party_power: int) -> int:
    """Ceiling from raw party power. Trio targets: 100/7.5d, 500/32d, 3000/95d."""
    p = max(0.0, float(party_power))
    return max(1, int(math.floor(D_MAX_BASE + D_MAX_LIN * p + D_MAX_QUAD * p * p)))


def merc_faucet_band(pb_depth: int) -> int:
    """Daily merc gold/XP band follows the walked record, not theoretical d_max."""
    return band_of_depth(max(0, int(pb_depth)))


def combat_drain(depth: int, party_power: int, hp_ref: int = 48) -> int:
    from waifu_bot.game.delve_pq_layer import combat_drain_hole

    return combat_drain_hole(depth, float(party_power), hp_ref)


def boss_drain(depth: int, party_power: int, hp_ref: int = 48) -> int:
    from waifu_bot.game.delve_pq_layer import boss_drain_hole

    return boss_drain_hole(depth, float(party_power), hp_ref)


def slot_type_of_family(family_key: str) -> str:
    fams = load_families()
    row = fams.get(family_key) or {}
    return str(row.get("slot_type") or "costume")


def abyss_name(family_key: str, tier: int) -> str:
    fams = load_families()
    label = str((fams.get(family_key) or {}).get("abyss") or family_key)
    return f"{label} бездны T{int(tier)}"


def base_ilvl_for_tier(tier: int) -> int:
    t = max(1, int(tier))
    return t * 4


@lru_cache(maxsize=1)
def _gear_pack() -> dict[str, Any]:
    return json.loads(GEAR_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _consumable_pack() -> dict[str, Any]:
    return json.loads(CONSUMABLE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_families() -> dict[str, dict[str, str]]:
    raw = _gear_pack().get("families") or {}
    return {str(k): dict(v) for k, v in raw.items()}


@lru_cache(maxsize=1)
def load_gear_templates() -> tuple[GearTemplate, ...]:
    fams = load_families()
    out: list[GearTemplate] = []
    for row in _gear_pack().get("templates") or []:
        family = str(row["family_key"])
        slot_type = str(fams.get(family, {}).get("slot_type") or "costume")
        tier = int(row["tier"])
        out.append(
            GearTemplate(
                id=str(row["id"]),
                name=str(row["name"]),
                family_key=family,
                slot_type=slot_type,
                tier=tier,
                base_ilvl=base_ilvl_for_tier(tier),
            )
        )
    return tuple(out)


@lru_cache(maxsize=1)
def load_consumables() -> tuple[ConsumableDef, ...]:
    out: list[ConsumableDef] = []
    for row in _consumable_pack().get("consumables") or []:
        out.append(
            ConsumableDef(
                id=str(row["id"]),
                name=str(row["name"]),
                effect=str(row.get("effect") or ""),
                heal_frac=float(row.get("heal_frac") or 0),
                price_per_band=int(row.get("price_per_band") or 1),
                stack_cap=int(row.get("stack_cap") or 1),
                party=bool(row.get("party")),
            )
        )
    return tuple(out)


def consumable_by_id(cid: str) -> ConsumableDef | None:
    for row in load_consumables():
        if row.id == cid:
            return row
    return None


def template_by_family_tier(family_key: str, tier: int) -> GearTemplate | None:
    t = max(1, min(10, int(tier)))
    for row in load_gear_templates():
        if row.family_key == family_key and row.tier == t:
            return row
    return None


def piece_for_family_tier(family_key: str, tier: int, slot: int) -> GearPiece:
    t = max(1, int(tier))
    slot_type = slot_type_of_family(family_key)
    if t <= 10:
        tpl = template_by_family_tier(family_key, t)
        if tpl is not None:
            return GearPiece(
                slot=int(slot),
                name=tpl.name,
                slot_type=tpl.slot_type,
                family_key=tpl.family_key,
                template_id=tpl.id,
                base_ilvl=tpl.base_ilvl,
                enchant_level=0,
                scaled_plus=0,
            )
    return GearPiece(
        slot=int(slot),
        name=abyss_name(family_key, t),
        slot_type=slot_type,
        family_key=family_key,
        template_id=None,
        base_ilvl=base_ilvl_for_tier(t),
        enchant_level=0,
        scaled_plus=max(0, t - 10),
    )


def is_two_hand(piece: GearPiece | None) -> bool:
    return bool(piece and piece.slot_type == TWO_HAND)


def equipped_ilvl(merc: MercState, slot: int) -> int:
    piece = merc.gear.get(1) if int(slot) == 2 and is_two_hand(merc.gear.get(1)) else merc.gear.get(int(slot))
    if int(slot) == 2 and is_two_hand(merc.gear.get(1)):
        return 0
    if piece is None:
        return 0
    return piece.ilvl


def gear_power(merc: MercState) -> int:
    total = 0
    for slot, piece in merc.gear.items():
        if int(slot) == 2 and is_two_hand(merc.gear.get(1)):
            continue
        total += piece.ilvl
    return int(total)


def compute_power(merc: MercState) -> int:
    return max(1, int(merc.level) + gear_power(merc))


def party_power(mercs: Iterable[MercState], *, living_only: bool = False) -> int:
    total = 0
    for merc in mercs:
        if living_only and not merc.living():
            continue
        total += compute_power(merc)
    return int(total)


def refresh_derived(merc: MercState, *, fill_if_full: bool = False) -> None:
    power = compute_power(merc)
    hmax = hp_max_of(power)
    full = int(merc.hp_current) >= int(merc.hp_max)
    merc.power = power
    merc.hp_max = hmax
    if fill_if_full and full:
        merc.hp_current = hmax
    else:
        merc.hp_current = max(0, min(int(merc.hp_current), hmax))


def apply_levelups(merc: MercState) -> int:
    gained = 0
    guard = 0
    while merc.xp_unspent >= xp_to_next(merc.level) and guard < 400:
        need = xp_to_next(merc.level)
        merc.xp_unspent -= need
        merc.level += 1
        gained += 1
        guard += 1
    if gained:
        refresh_derived(merc)
    return gained


def install_piece(merc: MercState, piece: GearPiece) -> None:
    slot = int(piece.slot)
    if piece.slot_type == TWO_HAND:
        merc.gear.pop(2, None)
        piece.slot = 1
        merc.gear[1] = piece
    elif slot == 2 and is_two_hand(merc.gear.get(1)):
        merc.gear.pop(1, None)
        merc.gear[2] = piece
    else:
        merc.gear[slot] = piece
    refresh_derived(merc)


def buy_increases_power(merc: MercState, piece: GearPiece) -> bool:
    before = compute_power(merc)
    snapshot = dict(merc.gear)
    install_piece(merc, piece)
    after = compute_power(merc)
    merc.gear = snapshot
    refresh_derived(merc)
    return after > before


def offer_from_piece(piece: GearPiece, band: int) -> ShopOffer:
    return ShopOffer(
        kind="gear",
        name=piece.display_name,
        price=gear_price(piece.base_ilvl, band),
        slot=piece.slot,
        ilvl=piece.ilvl,
        template_id=piece.template_id,
        family_key=piece.family_key,
        slot_type=piece.slot_type,
        base_ilvl=piece.base_ilvl,
        scaled_plus=piece.scaled_plus,
        item_name=piece.name,
        prefix_stat=piece.prefix_stat,
        prefix_tier=int(piece.prefix_tier or 0),
        suffix_family=piece.suffix_family,
        suffix_tier=int(piece.suffix_tier or 0),
    )


def shop_offers(
    merc: MercState, *, depth: int, seed: int, cycle: int, band: int | None = None
) -> list[ShopOffer]:
    node_band = band_of_depth(depth)
    if band is None:
        band = node_band
    else:
        band = max(node_band, max(1, int(band)))
    rng = pq_rng(seed, cycle, depth, merc.card_id)
    offers: list[ShopOffer] = []
    slots = [1, 2, 3, 4, 5, 6]
    rng.shuffle(slots)
    for slot in slots:
        if len([o for o in offers if o.kind == "gear"]) >= 3:
            break
        if slot == 2 and is_two_hand(merc.gear.get(1)):
            continue
        families = list(SLOT_FAMILIES.get(slot) or ())
        if not families:
            continue
        family = rng.choice(families)
        tier = max(1, band + rng.choice((-1, 0, 1)))
        piece = piece_for_family_tier(family, tier, slot)
        if piece.ilvl <= equipped_ilvl(merc, slot):
            piece = piece_for_family_tier(family, max(tier + 1, band + 1), slot)
        if piece.ilvl <= equipped_ilvl(merc, slot):
            continue
        roll_flavor_affixes(
            piece, seed=seed, cycle=cycle, depth=depth, card_id=merc.card_id, band=band
        )
        if not buy_increases_power(merc, piece):
            continue
        offers.append(offer_from_piece(piece, band))
    if not any(o.kind == "gear" for o in offers):
        for slot in (1, 3, 4, 6):
            families = list(SLOT_FAMILIES.get(slot) or ())
            if not families:
                continue
            family = families[0]
            cur = equipped_ilvl(merc, slot)
            need_ilvl = cur + 1
            tier = max(1, int(math.ceil(need_ilvl / 4.0)))
            tier = min(tier, max(1, band + 1))
            piece = piece_for_family_tier(family, tier, slot)
            roll_flavor_affixes(
                piece, seed=seed, cycle=cycle, depth=depth, card_id=merc.card_id, band=band
            )
            if piece.ilvl > cur and buy_increases_power(merc, piece):
                offers.append(offer_from_piece(piece, band))
                break
    for slot in (1, 2, 3, 4, 5, 6):
        if equipped_ilvl(merc, slot) > 0:
            continue
        if slot == 2 and is_two_hand(merc.gear.get(1)):
            continue
        families = list(SLOT_FAMILIES.get(slot) or ())
        if not families:
            continue
        piece = piece_for_family_tier(families[0], 1, slot)
        roll_flavor_affixes(
            piece, seed=seed, cycle=cycle, depth=depth, card_id=merc.card_id, band=band
        )
        if buy_increases_power(merc, piece):
            offers.append(offer_from_piece(piece, band))
    sharpen = best_sharpen_offer(merc, band)
    if sharpen is not None:
        offers.append(sharpen)
    for spec in load_consumables():
        offers.append(
            ShopOffer(
                kind="consumable",
                name=spec.name,
                price=consumable_price(spec.price_per_band, band),
                consumable_id=spec.id,
            )
        )
    return offers


def best_sharpen_offer(merc: MercState, band: int) -> ShopOffer | None:
    best: ShopOffer | None = None
    for slot, piece in merc.gear.items():
        if int(slot) == 2 and is_two_hand(merc.gear.get(1)):
            continue
        nxt = int(piece.enchant_level) + 1
        cost = sharpen_cost(piece.base_ilvl, nxt)
        preview = GearPiece(
            slot=piece.slot,
            name=piece.name,
            slot_type=piece.slot_type,
            family_key=piece.family_key,
            template_id=piece.template_id,
            base_ilvl=piece.base_ilvl,
            enchant_level=nxt,
            scaled_plus=piece.scaled_plus,
            prefix_stat=piece.prefix_stat,
            prefix_tier=piece.prefix_tier,
            suffix_family=piece.suffix_family,
            suffix_tier=piece.suffix_tier,
        )
        offer = ShopOffer(
            kind="sharpen",
            name=preview.display_name,
            price=cost,
            slot=int(slot),
            ilvl=piece.ilvl + 1,
            template_id=piece.template_id,
            family_key=piece.family_key,
            slot_type=piece.slot_type,
            base_ilvl=piece.base_ilvl,
            enchant_to=nxt,
            prefix_stat=piece.prefix_stat,
            prefix_tier=int(piece.prefix_tier or 0),
            suffix_family=piece.suffix_family,
            suffix_tier=int(piece.suffix_tier or 0),
        )
        if best is None or offer.ilvl < best.ilvl or (offer.ilvl == best.ilvl and offer.price < best.price):
            best = offer
    return best


def _apply_sharpen(
    merc: MercState,
    band: int,
    bought: list[dict[str, Any]],
    *,
    reserve: int = 0,
) -> bool:
    offer = best_sharpen_offer(merc, band)
    if not offer or not offer.slot or int(offer.price) > merc.gold_wallet - max(0, int(reserve)):
        return False
    piece = merc.gear.get(int(offer.slot))
    if piece is None:
        return False
    before = compute_power(merc)
    piece.enchant_level = int(piece.enchant_level) + 1
    refresh_derived(merc)
    if compute_power(merc) <= before:
        piece.enchant_level -= 1
        refresh_derived(merc)
        return False
    merc.gold_wallet -= int(offer.price)
    bought.append(
        {
            "kind": "sharpen",
            "name": piece.display_name,
            "slot": piece.slot,
            "ilvl": piece.ilvl,
            "price": offer.price,
            "power": compute_power(merc),
            "power_delta": compute_power(merc) - before,
            "who": merc.name,
        }
    )
    return True


def _worth_replacing(merc: MercState, offer: ShopOffer) -> bool:
    slot = int(offer.slot or 0)
    if slot <= 0 or int(offer.ilvl) <= equipped_ilvl(merc, slot):
        return False
    cur = merc.gear.get(slot)
    if cur is None:
        return True
    if int(cur.enchant_level) >= 12 and int(offer.base_ilvl) <= cur.ilvl:
        return False
    return True


def resolve_shop(
    merc: MercState, *, depth: int, seed: int, cycle: int, band: int | None = None
) -> list[dict[str, Any]]:
    apply_levelups(merc)
    offers = shop_offers(merc, depth=depth, seed=seed, cycle=cycle, band=band)
    bought: list[dict[str, Any]] = []
    gear_offers = [
        o
        for o in offers
        if o.kind == "gear"
        and o.slot
        and o.price <= merc.gold_wallet
        and _worth_replacing(merc, o)
    ]
    if gear_offers:
        pick = max(gear_offers, key=lambda o: (o.ilvl, -o.price))
        piece = GearPiece(
            slot=int(pick.slot or 1),
            name=pick.item_name or _base_name_from_template(pick),
            slot_type=pick.slot_type,
            family_key=pick.family_key,
            template_id=pick.template_id,
            base_ilvl=pick.base_ilvl,
            enchant_level=0,
            scaled_plus=pick.scaled_plus,
            prefix_stat=pick.prefix_stat,
            prefix_tier=int(pick.prefix_tier or 0),
            suffix_family=pick.suffix_family,
            suffix_tier=int(pick.suffix_tier or 0),
        )
        before = compute_power(merc)
        if buy_increases_power(merc, piece) and merc.gold_wallet >= pick.price:
            merc.gold_wallet -= pick.price
            install_piece(merc, piece)
            bought.append(
                {
                    "kind": "gear",
                    "name": piece.display_name,
                    "slot": piece.slot,
                    "ilvl": piece.ilvl,
                    "price": pick.price,
                    "power": compute_power(merc),
                    "power_delta": compute_power(merc) - before,
                    "who": merc.name,
                }
            )
    shop_band = max(band_of_depth(depth), max(1, int(band or band_of_depth(depth))))
    bought_gear = any(b.get("kind") == "gear" for b in bought)
    if not bought_gear:
        _apply_sharpen(merc, shop_band, bought)
    upgrade_reserve = _shop_save_reserve(
        merc, shop_offers(merc, depth=depth, seed=seed, cycle=cycle, band=shop_band), bought
    )
    day_cap = merc_gold_cap_day(shop_band)
    if upgrade_reserve > merc.gold_wallet + day_cap:
        upgrade_reserve = 0
    extra = 0
    while extra < 16 and _apply_sharpen(merc, shop_band, bought, reserve=upgrade_reserve):
        extra += 1
    offers = shop_offers(merc, depth=depth, seed=seed, cycle=cycle, band=shop_band)
    reserve = _shop_save_reserve(merc, offers, bought)
    for offer in offers:
        if offer.kind != "consumable" or not offer.consumable_id:
            continue
        spec = consumable_by_id(offer.consumable_id)
        if spec is None:
            continue
        have = int(merc.bag.get(spec.id, 0))
        while have < spec.stack_cap and merc.gold_wallet - offer.price >= reserve:
            merc.gold_wallet -= offer.price
            have += 1
            merc.bag[spec.id] = have
            bought.append(
                {
                    "kind": "consumable",
                    "name": spec.name,
                    "consumable_id": spec.id,
                    "price": offer.price,
                    "qty": have,
                    "who": merc.name,
                }
            )
    merc.last_shop_buy = list(bought)
    return bought


def _shop_save_reserve(merc: MercState, offers: list[ShopOffer], bought: list[dict[str, Any]]) -> int:
    """Keep gold for the next gear/sharpen so potions cannot empty the wallet."""
    pending: list[int] = []
    bought_gear_slots = {int(b["slot"]) for b in bought if b.get("kind") == "gear" and b.get("slot")}
    bought_sharpen = any(b.get("kind") == "sharpen" for b in bought)
    for offer in offers:
        if offer.kind == "gear" and offer.slot and int(offer.slot) not in bought_gear_slots:
            if offer.ilvl > equipped_ilvl(merc, int(offer.slot)):
                pending.append(int(offer.price))
        if offer.kind == "sharpen" and not bought_sharpen and offer.price > 0:
            pending.append(int(offer.price))
    return min(pending) if pending else 0


def _heal(merc: MercState, frac: float) -> int:
    add = max(1, int(round(float(frac) * merc.hp_max)))
    before = int(merc.hp_current)
    merc.hp_current = min(int(merc.hp_max), before + add)
    return int(merc.hp_current) - before


def auto_use_potions(mercs: list[MercState], *, before_boss: bool = False) -> list[dict[str, Any]]:
    used: list[dict[str, Any]] = []
    living = [m for m in mercs if m.living()]
    if not living:
        return used
    low = [m for m in living if m.hp_max > 0 and (m.hp_current / m.hp_max) < POTION_HP_FRAC]
    avg = sum(m.hp_current / max(1, m.hp_max) for m in living) / len(living)
    need_salve = len(low) >= 2 or (before_boss and avg < SALVE_AVG_FRAC)
    if need_salve:
        holder = next((m for m in mercs if int(m.bag.get(SALVE_ID, 0)) > 0), None)
        if holder is not None:
            holder.bag[SALVE_ID] = int(holder.bag.get(SALVE_ID, 0)) - 1
            for merc in living:
                _heal(merc, SALVE_HEAL_FRAC)
            used.append({"kind": "salve", "who": holder.name})
            living = [m for m in mercs if m.living()]
            low = [m for m in living if m.hp_max > 0 and (m.hp_current / m.hp_max) < POTION_HP_FRAC]
    for _ in range(12):
        living = [m for m in mercs if m.living()]
        if not living:
            break
        target = min(living, key=lambda m: m.hp_current / max(1, m.hp_max))
        if target.hp_max <= 0 or (target.hp_current / target.hp_max) >= POTION_HP_FRAC:
            break
        holder = next((m for m in mercs if int(m.bag.get(POTION_ID, 0)) > 0), None)
        if holder is None:
            break
        holder.bag[POTION_ID] = int(holder.bag.get(POTION_ID, 0)) - 1
        _heal(target, POTION_HEAL_FRAC)
        used.append({"kind": "potion", "who": holder.name, "target": target.name})
    return used


def apply_drain(mercs: list[MercState], amount: int) -> None:
    living = [m for m in mercs if m.living()]
    if not living or amount <= 0:
        return
    weights = [max(1, compute_power(m)) for m in living]
    parts = split_weighted(int(amount), weights)
    for merc, share in zip(living, parts):
        merc.hp_current = max(0, int(merc.hp_current) - int(share))


def apply_rest(mercs: list[MercState]) -> None:
    for merc in mercs:
        if not merc.living() and merc.hp_max <= 0:
            continue
        add = max(1, int(round(REST_REGEN_FRAC * merc.hp_max)))
        merc.hp_current = min(int(merc.hp_max), max(0, int(merc.hp_current)) + add)


def all_down(mercs: list[MercState]) -> bool:
    living = [m for m in mercs if m.living()]
    return not living


def do_wipe(party: PqParty, *, now: datetime, depth: int) -> None:
    party.wipe_count += 1
    party.run_origin = _aware(now)
    party.last_cycle = 0
    party.last_d = 0
    party.walk_ts = _aware(now)
    party.wipe_log.append({"kind": "wipe", "d": int(depth), "n": party.wipe_count})
    for merc in party.mercs:
        refresh_derived(merc)
        merc.hp_current = int(merc.hp_max)
    if int(getattr(party, "layer", 2) or 2) >= 2:
        from waifu_bot.game.delve_pq_layer import city_return

        city_return(party)


def grant_merc_faucet(party: PqParty, *, now: datetime, band: int) -> tuple[int, int]:
    cap_g = merc_gold_cap_day(band)
    cap_x = merc_xp_cap_day(band)
    gold, day_g, today_g = walk_capped_grant(
        party.last_ts,
        now,
        rate=gold_rate_per_sec(cap_g),
        cap=cap_g,
        day_key=party.grant_day,
        granted_today=party.gold_today,
    )
    xp, day_x, today_x = walk_capped_grant(
        party.last_ts,
        now,
        rate=xp_rate_per_sec(cap_x),
        cap=cap_x,
        day_key=party.grant_day,
        granted_today=party.xp_today,
    )
    party.grant_day = day_g or day_x or msk_today(now)
    party.gold_today = int(today_g)
    party.xp_today = int(today_x)
    party.gold_lifetime += int(gold)
    party.xp_lifetime += int(xp)
    if party.mercs and (gold or xp):
        weights = [max(1, max(0, min(100, int(m.loyalty)))) for m in party.mercs]
        gold_parts = split_weighted(int(gold), weights)
        xp_parts = split_weighted(int(xp), weights)
        for merc, g, x in zip(party.mercs, gold_parts, xp_parts):
            merc.gold_wallet += int(g)
            merc.xp_unspent += int(x)
            merc.gold_earned += int(g)
            merc.xp_earned += int(x)
            apply_levelups(merc)
    return int(gold), int(xp)


def _ceil(party: PqParty) -> float:
    if int(getattr(party, "layer", 2) or 2) >= 2:
        from waifu_bot.game.delve_pq_layer import d_max_eff

        return float(max(1, d_max_eff(party.mercs)))
    return float(max(1, d_max_of(party_power(party.mercs))))


def time_at_depth(run_origin: datetime, cycle: int, depth: int, ceil: float, *, t_eff: int | None = None) -> datetime:
    if t_eff is not None:
        from waifu_bot.game.delve_pq_layer import time_at_depth_layer

        return time_at_depth_layer(run_origin, cycle, depth, int(max(1, math.floor(ceil))), int(t_eff))
    t_down, _t_up, _t_rest = period_parts(ceil)
    c = max(1.0, float(ceil))
    d = max(1.0, float(depth))
    if d >= c:
        u = 1.0
    else:
        u = ((d - 1.0) / (c - 1.0)) ** (1.0 / DEPTH_EXP)
    u = min(1.0, max(0.0, u))
    period = t_down + T_UP_SEC + (50.0 + 10.0 * math.log(1.0 + c))
    sec = float(cycle) * period + u * t_down
    return _aware(run_origin) + timedelta(seconds=sec)


def rest_time(run_origin: datetime, cycle: int, ceil: float, *, t_eff: int | None = None) -> datetime:
    if t_eff is not None:
        from waifu_bot.game.delve_pq_layer import rest_time_layer

        return rest_time_layer(run_origin, cycle, int(max(1, math.floor(ceil))), int(t_eff))
    t_down, t_up, t_rest = period_parts(ceil)
    period = t_down + t_up + t_rest
    return _aware(run_origin) + timedelta(seconds=float(cycle) * period + t_down + t_up)


def simulate_pq(party: PqParty, now: datetime, *, pb_depth: int = 0) -> PqParty:
    now = _aware(now)
    party.run_origin = _aware(party.run_origin)
    party.last_ts = _aware(party.last_ts)
    layer = int(getattr(party, "layer", 2) or 2)
    if party.last_ts >= now:
        for merc in party.mercs:
            apply_levelups(merc)
            refresh_derived(merc)
        if layer >= 2:
            from waifu_bot.game.delve_pq_layer import t_eff_of

            party.t_eff = t_eff_of(party.mercs, t_node=int(party.t_node or 30), depth=int(party.last_d or 0), d_max=int(_ceil(party)))
        return party
    band = merc_faucet_band(pb_depth)
    grant_merc_faucet(party, now=now, band=band)
    for merc in party.mercs:
        apply_levelups(merc)
        refresh_derived(merc)
    if party.walk_ts is None:
        party.walk_ts = party.last_ts
    party.walk_ts = _aware(party.walk_ts)
    wipes = 0
    steps = 0
    while wipes < WIPE_CAP_PER_SYNC and steps < 8000:
        steps += 1
        ceil = _ceil(party)
        floor_ceil = max(1, int(math.floor(ceil)))
        t_eff = None
        if layer >= 2:
            from waifu_bot.game.delve_pq_layer import (
                apply_rest_layer,
                city_return,
                period_parts_layer,
                remember_event,
                resolve_layer_node,
                t_eff_of,
            )

            t_eff = t_eff_of(party.mercs, t_node=int(party.t_node or 30), depth=int(party.last_d or 0), d_max=floor_ceil)
            party.t_eff = t_eff
            _t_down, t_up, t_rest = period_parts_layer(floor_ceil, t_eff)
            tick = max(1, int(t_eff))
            if party.last_d >= floor_ceil:
                ready = party.walk_ts + timedelta(seconds=float(t_up + t_rest))
                if ready > now:
                    break
                healed = apply_rest_layer(party)
                city_return(party)
                auto_use_potions(party.mercs)
                who = party.mercs[0].name if party.mercs else "Она"
                remember_event(
                    party,
                    {
                        "id": "surface_rest",
                        "kind": "surface",
                        "kind_ru": "Лагерь",
                        "d": 0,
                        "phrase": f"[Лагерь] Глубина 0 · {who} сидит у стола (+{healed} HP)",
                        "who": who,
                        "hp_delta": -healed,
                        "from_llm": False,
                    },
                )
                party.last_cycle = party.last_cycle + 1
                party.last_d = 0
                party.walk_ts = ready
                continue
            nxt_t = party.walk_ts + timedelta(seconds=tick)
            if nxt_t > now:
                break
            party.walk_ts = nxt_t
            nxt = party.last_d + 1
            party.last_d = nxt
            node = spine_type(nxt, ceil)
            event = resolve_layer_node(party, nxt, node, band=band)
            remember_event(party, event)
            if all_down(party.mercs):
                do_wipe(party, now=party.walk_ts, depth=nxt)
                party.walk_ts = party.walk_ts + timedelta(seconds=t_rest)
                wipes += 1
            continue
        t_down, t_up, t_rest = period_parts(ceil)
        period = t_down + t_up + t_rest
        elapsed = max(0.0, (now - party.run_origin).total_seconds())
        cur_cycle = int(elapsed // period) if period > 0 else 0
        if party.last_ts >= now:
            break
        if party.last_d >= floor_ceil:
            t_rest_at = rest_time(party.run_origin, party.last_cycle, ceil, t_eff=t_eff)
            if t_rest_at > now:
                break
            if t_rest_at >= party.last_ts:
                apply_rest(party.mercs)
                auto_use_potions(party.mercs)
            party.last_cycle = party.last_cycle + 1
            party.last_d = 0
            party.last_ts = max(party.last_ts, t_rest_at + timedelta(seconds=t_rest))
            continue
        nxt = party.last_d + 1
        if nxt > floor_ceil:
            party.last_d = floor_ceil
            continue
        t_at = time_at_depth(party.run_origin, party.last_cycle, nxt, ceil, t_eff=t_eff)
        if t_at > now:
            break
        if t_at < party.last_ts and nxt <= party.last_d:
            party.last_d = nxt
            continue
        party.last_ts = max(party.last_ts, t_at)
        party.last_d = nxt
        node = spine_type(nxt, ceil)
        if node == NODE_SHOP:
            for merc in party.mercs:
                if not merc.living():
                    continue
                buys = resolve_shop(
                    merc, depth=nxt, seed=party.seed, cycle=party.last_cycle, band=band
                )
                party.shop_log.extend(buys)
        elif node == NODE_BOSS:
            auto_use_potions(party.mercs, before_boss=True)
            apply_drain(party.mercs, boss_drain(nxt, party_power(party.mercs, living_only=True)))
            auto_use_potions(party.mercs)
        elif node == NODE_COMBAT:
            apply_drain(party.mercs, combat_drain(nxt, party_power(party.mercs, living_only=True)))
            auto_use_potions(party.mercs)
        elif node == NODE_REST:
            apply_rest(party.mercs)
            auto_use_potions(party.mercs)
        if all_down(party.mercs):
            do_wipe(party, now=party.last_ts, depth=nxt)
            _t_down, _t_up, t_rest_w = period_parts(_ceil(party))
            party.last_ts = party.last_ts + timedelta(seconds=t_rest_w)
            wipes += 1
            continue
        if party.last_cycle < cur_cycle and nxt >= floor_ceil:
            continue
    party.last_ts = now
    for merc in party.mercs:
        apply_levelups(merc)
        refresh_derived(merc)
    if layer >= 2:
        from waifu_bot.game.delve_pq_layer import t_eff_of

        party.t_eff = t_eff_of(party.mercs, t_node=int(party.t_node or 30), depth=int(party.last_d or 0), d_max=int(_ceil(party)))
    return party


def public_bag(bag: dict[str, int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in load_consumables():
        qty = int(bag.get(spec.id, 0) or 0)
        if qty <= 0:
            continue
        out.append({"id": spec.id, "name": spec.name, "qty": qty, "stack_cap": spec.stack_cap})
    return out


def empty_gear_slots(gear: dict[int, GearPiece]) -> list[dict[str, Any] | None]:
    rows: list[dict[str, Any] | None] = []
    for slot in range(1, 7):
        piece = gear.get(slot)
        if slot == 2 and is_two_hand(gear.get(1)):
            rows.append({"slot": 2, "blocked": True, "name": "двуручник"})
            continue
        rows.append(piece.to_public() if piece else None)
    return rows
