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

GEAR_PATH = Path(__file__).resolve().parents[3] / "data" / "delve_gear.v1.json"
CONSUMABLE_PATH = Path(__file__).resolve().parents[3] / "data" / "delve_consumables.v1.json"

SAFE_ENCHANT_MAX = 7
WIPE_CAP_PER_SYNC = 24
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

    @property
    def ilvl(self) -> int:
        return int(self.base_ilvl) + int(self.enchant_level)

    def to_public(self) -> dict[str, Any]:
        return {
            "slot": int(self.slot),
            "name": self.name,
            "slot_type": self.slot_type,
            "family_key": self.family_key,
            "template_id": self.template_id,
            "base_ilvl": int(self.base_ilvl),
            "enchant_level": int(self.enchant_level),
            "ilvl": self.ilvl,
            "scaled_plus": int(self.scaled_plus),
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
    b = max(1, int(band))
    return max(1, int(round(12 * int(base_ilvl) * (1.12 ** (b - 1)))))


def sharpen_cost(ilvl: int, next_plus: int) -> int:
    n = max(1, int(next_plus))
    return max(1, int(round(8 * max(1, int(ilvl)) * (1.35 ** (n - 1)))))


def consumable_price(price_per_band: int, band: int) -> int:
    return max(1, int(price_per_band) * max(1, int(band)))


def merc_gold_cap_day(band: int) -> int:
    return 80 * max(1, int(band))


def merc_xp_cap_day(band: int) -> int:
    return 60 * max(1, int(band))


def hp_max_of(power: int) -> int:
    return 40 + 8 * max(1, int(power))


def d_max_of(party_power: int) -> int:
    return max(1, int(math.floor(8.0 + 0.35 * max(0, int(party_power)))))


def combat_drain(depth: int, party_power: int) -> int:
    threat = max(0, int(depth))
    gap = max(0, threat - int(party_power))
    return max(1, int(round(4 + 0.45 * gap)))


def boss_drain(depth: int, party_power: int) -> int:
    threat = max(0, int(depth))
    gap = max(0, threat - int(party_power))
    return max(2, int(round(10 + 0.7 * gap)))


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
        name=piece.name,
        price=gear_price(piece.base_ilvl, band),
        slot=piece.slot,
        ilvl=piece.ilvl,
        template_id=piece.template_id,
        family_key=piece.family_key,
        slot_type=piece.slot_type,
        base_ilvl=piece.base_ilvl,
        scaled_plus=piece.scaled_plus,
    )


def shop_offers(merc: MercState, *, depth: int, seed: int, cycle: int) -> list[ShopOffer]:
    band = band_of_depth(depth)
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
            piece = piece_for_family_tier(family, tier, slot)
            if piece.ilvl > cur and buy_increases_power(merc, piece):
                offers.append(offer_from_piece(piece, band))
                break
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
        if int(piece.enchant_level) >= SAFE_ENCHANT_MAX:
            continue
        nxt = int(piece.enchant_level) + 1
        cost = sharpen_cost(piece.ilvl, nxt)
        offer = ShopOffer(
            kind="sharpen",
            name=f"{piece.name} +{nxt}",
            price=cost,
            slot=int(slot),
            ilvl=piece.ilvl + 1,
            template_id=piece.template_id,
            family_key=piece.family_key,
            slot_type=piece.slot_type,
            base_ilvl=piece.base_ilvl,
            enchant_to=nxt,
        )
        if best is None or offer.ilvl < best.ilvl or (offer.ilvl == best.ilvl and offer.price < best.price):
            best = offer
    return best


def resolve_shop(merc: MercState, *, depth: int, seed: int, cycle: int) -> list[dict[str, Any]]:
    apply_levelups(merc)
    offers = shop_offers(merc, depth=depth, seed=seed, cycle=cycle)
    bought: list[dict[str, Any]] = []
    gear_offers = [o for o in offers if o.kind == "gear" and o.price <= merc.gold_wallet and o.ilvl > equipped_ilvl(merc, int(o.slot or 0))]
    gear_offers = [o for o in gear_offers if o.slot]
    if gear_offers:
        pick = max(gear_offers, key=lambda o: (o.ilvl, -o.price))
        piece = GearPiece(
            slot=int(pick.slot or 1),
            name=pick.name,
            slot_type=pick.slot_type,
            family_key=pick.family_key,
            template_id=pick.template_id,
            base_ilvl=pick.base_ilvl,
            enchant_level=0,
            scaled_plus=pick.scaled_plus,
        )
        before = compute_power(merc)
        if buy_increases_power(merc, piece) and merc.gold_wallet >= pick.price:
            merc.gold_wallet -= pick.price
            install_piece(merc, piece)
            bought.append(
                {
                    "kind": "gear",
                    "name": piece.name,
                    "slot": piece.slot,
                    "ilvl": piece.ilvl,
                    "price": pick.price,
                    "power": compute_power(merc),
                    "power_delta": compute_power(merc) - before,
                    "who": merc.name,
                }
            )
    if not bought:
        sharpen = next((o for o in offers if o.kind == "sharpen"), None)
        if sharpen and sharpen.slot and sharpen.price <= merc.gold_wallet:
            piece = merc.gear.get(int(sharpen.slot))
            if piece and int(piece.enchant_level) < SAFE_ENCHANT_MAX:
                before = compute_power(merc)
                piece.enchant_level = int(piece.enchant_level) + 1
                refresh_derived(merc)
                if compute_power(merc) > before:
                    merc.gold_wallet -= sharpen.price
                    bought.append(
                        {
                            "kind": "sharpen",
                            "name": f"{piece.name} +{piece.enchant_level}",
                            "slot": piece.slot,
                            "ilvl": piece.ilvl,
                            "price": sharpen.price,
                            "power": compute_power(merc),
                            "power_delta": compute_power(merc) - before,
                            "who": merc.name,
                        }
                    )
                else:
                    piece.enchant_level -= 1
                    refresh_derived(merc)
    for offer in offers:
        if offer.kind != "consumable" or not offer.consumable_id:
            continue
        spec = consumable_by_id(offer.consumable_id)
        if spec is None:
            continue
        have = int(merc.bag.get(spec.id, 0))
        while have < spec.stack_cap and merc.gold_wallet >= offer.price:
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
    party.wipe_log.append({"kind": "wipe", "d": int(depth), "n": party.wipe_count})
    for merc in party.mercs:
        refresh_derived(merc)
        merc.hp_current = int(merc.hp_max)


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
    return float(max(1, d_max_of(party_power(party.mercs))))


def time_at_depth(run_origin: datetime, cycle: int, depth: int, ceil: float) -> datetime:
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


def rest_time(run_origin: datetime, cycle: int, ceil: float) -> datetime:
    t_down, t_up, t_rest = period_parts(ceil)
    period = t_down + t_up + t_rest
    return _aware(run_origin) + timedelta(seconds=float(cycle) * period + t_down + t_up)


def simulate_pq(party: PqParty, now: datetime, *, pb_depth: int = 0) -> PqParty:
    now = _aware(now)
    party.run_origin = _aware(party.run_origin)
    party.last_ts = _aware(party.last_ts)
    if party.last_ts >= now:
        for merc in party.mercs:
            apply_levelups(merc)
            refresh_derived(merc)
        return party
    band = max(band_of_depth(pb_depth), band_of_depth(d_max_of(party_power(party.mercs))))
    grant_merc_faucet(party, now=now, band=band)
    for merc in party.mercs:
        apply_levelups(merc)
        refresh_derived(merc)
    wipes = 0
    steps = 0
    while party.last_ts < now and wipes < WIPE_CAP_PER_SYNC and steps < 8000:
        steps += 1
        ceil = _ceil(party)
        floor_ceil = max(1, int(math.floor(ceil)))
        t_down, t_up, t_rest = period_parts(ceil)
        period = t_down + t_up + t_rest
        elapsed = max(0.0, (now - party.run_origin).total_seconds())
        cur_cycle = int(elapsed // period) if period > 0 else 0
        if party.last_d >= floor_ceil:
            t_rest_at = rest_time(party.run_origin, party.last_cycle, ceil)
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
        t_node = time_at_depth(party.run_origin, party.last_cycle, nxt, ceil)
        if t_node > now:
            break
        if t_node < party.last_ts and nxt <= party.last_d:
            party.last_d = nxt
            continue
        party.last_ts = max(party.last_ts, t_node)
        party.last_d = nxt
        node = spine_type(nxt, ceil)
        if node == NODE_SHOP:
            for merc in party.mercs:
                if not merc.living():
                    continue
                buys = resolve_shop(merc, depth=nxt, seed=party.seed, cycle=party.last_cycle)
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
