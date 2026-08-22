"""Persist and resolve Delve Progress Quest on living cards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.delve_pq import (
    GearPiece,
    MercState,
    PqParty,
    compute_power,
    d_max_of,
    empty_gear_slots,
    hp_max_of,
    load_consumables,
    load_families,
    load_gear_templates,
    party_power,
    public_bag,
    refresh_derived,
    simulate_pq,
)
from waifu_bot.game.delve_pq_layer import (
    PQ_LAYER_DEFAULT,
    T_NODE_SEC,
    apply_layer_dump,
    d_max_eff,
    layer_state_dump,
    migrate_legacy_status,
    party_power_eff,
    public_status,
)
from waifu_bot.services.game_config_service import cfg_bool, cfg_int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_pq_enabled(cfg: dict[str, str] | None) -> bool:
    return cfg_bool(cfg or {}, "delve.pq_enabled", True)


def pq_layer_of(cfg: dict[str, str] | None) -> int:
    return max(1, cfg_int(cfg or {}, "delve.pq_layer", PQ_LAYER_DEFAULT))


def pq_t_node_of(cfg: dict[str, str] | None) -> int:
    return max(15, min(50, cfg_int(cfg or {}, "delve.pq_t_node", T_NODE_SEC)))


def card_loyalty(card: m.CompanionCard) -> int:
    look = card.look_card or {}
    try:
        return max(0, min(100, int(look.get("loyalty", 50))))
    except (TypeError, ValueError):
        return 50


def _piece_from_row(row: m.DelveCompanionGear) -> GearPiece:
    return GearPiece(
        slot=int(row.equipment_slot),
        name=str(row.name),
        slot_type=str(row.slot_type),
        family_key=str(row.family_key),
        template_id=str(row.template_id) if row.template_id else None,
        base_ilvl=int(row.base_ilvl or 0),
        enchant_level=int(row.enchant_level or 0),
        scaled_plus=int(row.scaled_plus or 0),
        prefix_stat=str(row.prefix_stat) if row.prefix_stat else None,
        prefix_tier=int(row.prefix_tier or 0),
        suffix_family=str(row.suffix_family) if row.suffix_family else None,
        suffix_tier=int(row.suffix_tier or 0),
    )


def merc_from_card(
    card: m.CompanionCard,
    gear_rows: list[m.DelveCompanionGear],
    bag_rows: list[m.DelveCompanionBag],
) -> MercState:
    gear = {int(r.equipment_slot): _piece_from_row(r) for r in gear_rows}
    bag = {str(r.consumable_id): int(r.qty or 0) for r in bag_rows if int(r.qty or 0) > 0}
    look = card.look_card if isinstance(card.look_card, dict) else {}
    try:
        class_id = int(look.get("class_id") or 0)
    except (TypeError, ValueError):
        class_id = 0
    traits = [str(t) for t in (card.traits or []) if str(t).strip()]
    flesh = [migrate_legacy_status(x) for x in (card.flesh or []) if isinstance(x, dict)]
    psyche = [migrate_legacy_status(x) for x in (card.psyche or []) if isinstance(x, dict)]
    merc = MercState(
        card_id=int(card.id),
        slot=int(card.slot or 0),
        name=str(card.name or ""),
        loyalty=card_loyalty(card),
        level=max(1, int(getattr(card, "level", 1) or 1)),
        xp_unspent=max(0, int(getattr(card, "xp_unspent", 0) or 0)),
        gold_wallet=max(0, int(getattr(card, "gold_wallet", 0) or 0)),
        power=max(1, int(getattr(card, "power", 1) or 1)),
        hp_current=int(getattr(card, "hp_current", 48) or 0),
        hp_max=max(1, int(getattr(card, "hp_max", 48) or 48)),
        gold_earned=int(card.gold_earned or 0),
        xp_earned=int(card.xp_earned or 0),
        gear=gear,
        bag=bag,
        class_id=class_id,
        stance=str(card.stance or "guide"),
        temper=str(card.temper or "stay"),
        traits=traits,
        flesh=flesh,
        psyche=psyche,
        nodes_seen=int(look.get("pq_nodes") or 0),
    )
    refresh_derived(merc, fill_if_full=int(merc.hp_current) >= int(getattr(card, "hp_max", 48) or 48))
    return merc


def apply_merc_to_card(card: m.CompanionCard, merc: MercState) -> None:
    card.level = int(merc.level)
    card.xp_unspent = int(merc.xp_unspent)
    card.gold_wallet = int(merc.gold_wallet)
    card.power = int(compute_power(merc))
    card.hp_max = int(hp_max_of(card.power))
    card.hp_current = max(0, min(int(merc.hp_current), int(card.hp_max)))
    card.gold_earned = int(merc.gold_earned)
    card.xp_earned = int(merc.xp_earned)
    card.flesh = list(merc.flesh or [])
    card.psyche = list(merc.psyche or [])
    look = dict(card.look_card or {})
    look["pq_nodes"] = int(getattr(merc, "nodes_seen", 0) or 0)
    card.look_card = look


def apply_merc_to_delve(row: m.DelveCompanion, merc: MercState) -> None:
    row.level = int(merc.level)
    row.xp_unspent = int(merc.xp_unspent)
    row.gold_wallet = int(merc.gold_wallet)
    row.power = int(compute_power(merc))
    row.hp_max = int(hp_max_of(row.power))
    row.hp_current = max(0, min(int(merc.hp_current), int(row.hp_max)))
    row.gold_earned = max(int(row.gold_earned or 0), int(merc.gold_earned))
    row.xp_earned = max(int(row.xp_earned or 0), int(merc.xp_earned))


def merc_public(merc: MercState) -> dict[str, Any]:
    chips = []
    for row in list(merc.flesh or []) + list(merc.psyche or []):
        pub = public_status(row)
        if pub:
            chips.append(pub)
    return {
        "card_id": merc.card_id,
        "level": int(merc.level),
        "power": int(compute_power(merc)),
        "gold_wallet": int(merc.gold_wallet),
        "xp_unspent": int(merc.xp_unspent),
        "hp_current": int(merc.hp_current),
        "hp_max": int(merc.hp_max),
        "gear": empty_gear_slots(merc.gear),
        "bag": public_bag(merc.bag),
        "last_shop_buy": list(merc.last_shop_buy or []),
        "trauma": chips[:2],
        "class_id": int(getattr(merc, "class_id", 0) or 0),
        "traits": list(getattr(merc, "traits", None) or []),
    }


async def _load_rows(
    session: AsyncSession, card_ids: list[int]
) -> tuple[dict[int, list[m.DelveCompanionGear]], dict[int, list[m.DelveCompanionBag]]]:
    gear_map: dict[int, list[m.DelveCompanionGear]] = {i: [] for i in card_ids}
    bag_map: dict[int, list[m.DelveCompanionBag]] = {i: [] for i in card_ids}
    if not card_ids:
        return gear_map, bag_map
    gear_rows = (
        await session.execute(select(m.DelveCompanionGear).where(m.DelveCompanionGear.card_id.in_(card_ids)))
    ).scalars().all()
    bag_rows = (
        await session.execute(select(m.DelveCompanionBag).where(m.DelveCompanionBag.card_id.in_(card_ids)))
    ).scalars().all()
    for row in gear_rows:
        gear_map.setdefault(int(row.card_id), []).append(row)
    for row in bag_rows:
        bag_map.setdefault(int(row.card_id), []).append(row)
    return gear_map, bag_map


async def persist_merc_items(session: AsyncSession, player_id: int, merc: MercState) -> None:
    await session.execute(delete(m.DelveCompanionGear).where(m.DelveCompanionGear.card_id == int(merc.card_id)))
    await session.execute(delete(m.DelveCompanionBag).where(m.DelveCompanionBag.card_id == int(merc.card_id)))
    for piece in merc.gear.values():
        session.add(
            m.DelveCompanionGear(
                card_id=int(merc.card_id),
                equipment_slot=int(piece.slot),
                template_id=piece.template_id,
                family_key=piece.family_key,
                name=piece.name,
                slot_type=piece.slot_type,
                base_ilvl=int(piece.base_ilvl),
                enchant_level=int(piece.enchant_level),
                scaled_plus=int(piece.scaled_plus),
                prefix_stat=piece.prefix_stat,
                prefix_tier=int(piece.prefix_tier) if piece.prefix_stat else None,
                suffix_family=piece.suffix_family,
                suffix_tier=int(piece.suffix_tier) if piece.suffix_family else None,
            )
        )
    for cid, qty in merc.bag.items():
        if int(qty) <= 0:
            continue
        session.add(
            m.DelveCompanionBag(
                card_id=int(merc.card_id),
                consumable_id=str(cid),
                qty=int(qty),
                player_id=int(player_id),
            )
        )


def snapshot_party(
    state: m.DelveState,
    cards: list[m.CompanionCard],
    gear_map: dict[int, list[m.DelveCompanionGear]],
    bag_map: dict[int, list[m.DelveCompanionBag]],
    *,
    now: datetime,
) -> PqParty:
    origin = state.run_origin or state.last_pq_ts or state.t_origin or now
    last = state.last_pq_ts or origin
    mercs = [
        merc_from_card(card, gear_map.get(int(card.id), []), bag_map.get(int(card.id), []))
        for card in cards
        if card.slot
    ]
    party = PqParty(
        seed=int(state.pq_seed or state.spine_seed or 0),
        run_origin=origin,
        last_ts=last,
        wipe_count=int(state.wipe_count or 0),
        last_cycle=int(getattr(state, "pq_last_cycle", 0) or 0),
        last_d=int(getattr(state, "pq_last_d", 0) or 0),
        gold_today=int(state.pq_gold_today or 0),
        xp_today=int(state.pq_xp_today or 0),
        grant_day=state.pq_grant_day_msk,
        mercs=mercs,
    )
    apply_layer_dump(party, getattr(state, "pq_layer_json", None) if isinstance(getattr(state, "pq_layer_json", None), dict) else None)
    return party


def write_party(state: m.DelveState, party: PqParty) -> None:
    state.run_origin = party.run_origin
    state.last_pq_ts = party.last_ts
    state.wipe_count = int(party.wipe_count)
    state.pq_last_cycle = int(party.last_cycle)
    state.pq_last_d = int(party.last_d)
    state.pq_gold_today = int(party.gold_today)
    state.pq_xp_today = int(party.xp_today)
    state.pq_grant_day_msk = party.grant_day
    if not state.pq_seed:
        state.pq_seed = int(state.spine_seed or party.seed or 0)
    if int(getattr(party, "layer", 2) or 2) >= 2:
        state.pq_layer_json = layer_state_dump(party)


def pq_payload_fields(party: PqParty | None) -> dict[str, Any]:
    if party is None or not party.mercs:
        return {
            "pq_enabled": True,
            "pq_layer": PQ_LAYER_DEFAULT,
            "party_power": 0,
            "d_max": d_max_of(0),
            "wipe_count": 0,
            "shop_log": [],
            "T_eff": T_NODE_SEC,
            "last_d": 0,
            "checkpoint_d": 0,
            "event": None,
            "recent_events": [],
            "chips": [],
        }
    power = party_power(party.mercs)
    layer = int(getattr(party, "layer", 2) or 2)
    dmax = d_max_eff(party.mercs, depth=int(party.last_d or 0)) if layer >= 2 else d_max_of(power)
    return {
        "pq_enabled": True,
        "pq_layer": layer,
        "party_power": power,
        "party_power_eff": round(party_power_eff(party.mercs, depth=int(party.last_d or 0), d_max=dmax, living_only=False), 2) if layer >= 2 else power,
        "d_max": dmax,
        "wipe_count": int(party.wipe_count),
        "shop_log": list(party.shop_log[-12:]),
        "run_origin": party.run_origin.isoformat() if party.run_origin else None,
        "T_eff": int(party.t_eff or T_NODE_SEC),
        "last_d": int(party.last_d or 0),
        "checkpoint_d": int(getattr(party, "checkpoint_d", 0) or 0),
        "event": party.last_event,
        "recent_events": list(party.recent_events or [])[-3:],
        "chips": list(party.chips or []),
    }


async def resolve_pq(
    session: AsyncSession,
    state: m.DelveState,
    cards: list[m.CompanionCard],
    companions: list[m.DelveCompanion],
    *,
    now: datetime | None = None,
    cfg: dict[str, str] | None = None,
) -> PqParty | None:
    if not is_pq_enabled(cfg):
        return None
    now = now or _now()
    seated = [c for c in cards if c and c.slot]
    if not seated:
        return None
    layer = pq_layer_of(cfg)
    t_node = pq_t_node_of(cfg)
    blob = state.pq_layer_json if isinstance(getattr(state, "pq_layer_json", None), dict) else {}
    if state.last_pq_ts is None:
        state.last_pq_ts = now
        state.run_origin = state.run_origin or now
        if not state.pq_seed:
            state.pq_seed = int(state.spine_seed or 0)
    if layer >= 2 and not blob.get("armed"):
        state.last_pq_ts = now
        blob = {**blob, "armed": True}
        state.pq_layer_json = blob
    ids = [int(c.id) for c in seated]
    gear_map, bag_map = await _load_rows(session, ids)
    party = snapshot_party(state, seated, gear_map, bag_map, now=now)
    party.layer = layer
    party.t_node = t_node
    simulate_pq(party, now, pb_depth=int(state.pb_depth or 0))
    write_party(state, party)
    by_slot = {int(r.slot): r for r in companions}
    for card, merc in zip(seated, party.mercs):
        apply_merc_to_card(card, merc)
        row = by_slot.get(int(card.slot or 0))
        if row is not None:
            apply_merc_to_delve(row, merc)
        await persist_merc_items(session, int(state.player_id), merc)
    if party.wipe_log:
        journal = list(state.journal_json or []) if isinstance(state.journal_json, list) else []
        have = {(str(x.get("kind")), int(x.get("d") or 0), int(x.get("n") or 0)) for x in journal if isinstance(x, dict)}
        palette = state.committed_palette or "ash"
        for item in party.wipe_log:
            key = ("wipe", int(item.get("d") or 0), int(item.get("n") or 0))
            if key in have:
                continue
            have.add(key)
            journal.append({"kind": "wipe", "d": int(item.get("d") or 0), "n": int(item.get("n") or 0), "palette": palette})
        state.journal_json = journal[:120]
    return party


async def seed_templates(session: AsyncSession) -> None:
    """Idempotent catalog upsert from JSON. Safe for tests and migrations."""
    existing_g = {
        str(r.id): r
        for r in (await session.execute(select(m.DelveGearTemplate))).scalars().all()
    }
    fams = load_families()
    for tpl in load_gear_templates():
        slot_type = str(fams.get(tpl.family_key, {}).get("slot_type") or tpl.slot_type)
        row = existing_g.get(tpl.id)
        if row is None:
            session.add(
                m.DelveGearTemplate(
                    id=tpl.id,
                    name=tpl.name,
                    family_key=tpl.family_key,
                    slot_type=slot_type,
                    tier=tpl.tier,
                    base_ilvl=tpl.base_ilvl,
                )
            )
        else:
            row.name = tpl.name
            row.family_key = tpl.family_key
            row.slot_type = slot_type
            row.tier = tpl.tier
            row.base_ilvl = tpl.base_ilvl
    existing_c = {
        str(r.id): r
        for r in (await session.execute(select(m.DelveConsumableTemplate))).scalars().all()
    }
    for spec in load_consumables():
        row = existing_c.get(spec.id)
        heal_pct = int(round(spec.heal_frac * 100))
        if row is None:
            session.add(
                m.DelveConsumableTemplate(
                    id=spec.id,
                    name=spec.name,
                    effect=spec.effect,
                    heal_frac=heal_pct,
                    price_per_band=spec.price_per_band,
                    stack_cap=spec.stack_cap,
                    party=1 if spec.party else 0,
                )
            )
        else:
            row.name = spec.name
            row.effect = spec.effect
            row.heal_frac = heal_pct
            row.price_per_band = spec.price_per_band
            row.stack_cap = spec.stack_cap
            row.party = 1 if spec.party else 0


