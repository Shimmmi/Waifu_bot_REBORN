"""Delve Progress Quest invariants: power, shop, wipe, faucet isolation, balance."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from waifu_bot.game.delve_pq import (
    GEAR_PATH,
    MercState,
    PqParty,
    POTION_ID,
    SALVE_ID,
    ShopOffer,
    apply_drain,
    band_of_depth,
    buy_increases_power,
    combat_drain,
    compute_power,
    d_max_of,
    do_wipe,
    equipped_ilvl,
    gear_price,
    hp_max_of,
    install_piece,
    load_consumables,
    load_gear_templates,
    merc_faucet_band,
    merc_gold_cap_day,
    piece_for_family_tier,
    refresh_derived,
    resolve_shop,
    roll_flavor_affixes,
    shop_offers,
    simulate_pq,
    sharpen_cost,
    xp_to_next,
)
from waifu_bot.game.delve_catalog import gold_cap_day


def _merc(**kwargs) -> MercState:
    base = dict(
        card_id=1,
        slot=1,
        name="Мира",
        loyalty=50,
        level=1,
        xp_unspent=0,
        gold_wallet=200,
        power=1,
        hp_current=48,
        hp_max=48,
    )
    base.update(kwargs)
    return MercState(**base)


def _party(merc: MercState, *, seed: int = 11) -> PqParty:
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return PqParty(
        seed=seed,
        run_origin=origin,
        last_ts=origin,
        mercs=[merc],
    )


def test_catalog_has_eighty_named_bases():
    rows = load_gear_templates()
    assert len(rows) == 80
    assert GEAR_PATH.is_file()
    families = {r.family_key for r in rows}
    assert families == {"sword", "dagger", "axe", "bow", "shield", "costume", "ring", "amulet"}
    assert all(r.base_ilvl == r.tier * 4 for r in rows)


def test_xp_level_and_power_formulas():
    assert xp_to_next(1) == 40
    assert xp_to_next(2) == 63
    merc = _merc(level=3)
    install_piece(merc, piece_for_family_tier("sword", 1, 1))
    assert compute_power(merc) == 3 + 4
    assert hp_max_of(7) == 40 + 56
    assert d_max_of(1) == 8
    assert band_of_depth(4) == 1
    assert band_of_depth(21) == 2


def test_buy_and_sharpen_always_increase_power():
    merc = _merc()
    before = compute_power(merc)
    piece = piece_for_family_tier("costume", 1, 3)
    assert buy_increases_power(merc, piece)
    install_piece(merc, piece)
    assert compute_power(merc) > before
    mid = compute_power(merc)
    merc.gear[3].enchant_level += 1
    assert compute_power(merc) == mid + 1
    merc.gear[3].enchant_level = 100
    refresh_derived(merc)
    assert compute_power(merc) == mid + 100
    assert merc.gear[3].enchant_level == 100


def test_shop_never_offers_weaker_or_equal_ilvl():
    merc = _merc()
    install_piece(merc, piece_for_family_tier("sword", 3, 1))
    current = equipped_ilvl(merc, 1)
    offers = shop_offers(merc, depth=4, seed=7, cycle=0)
    gear = [o for o in offers if o.kind == "gear"]
    assert gear
    for offer in gear:
        assert offer.ilvl > equipped_ilvl(merc, int(offer.slot or 0)) or offer.slot != 1
        if offer.slot == 1:
            assert offer.ilvl > current


def test_wipe_returns_to_checkpoint_and_keeps_progress():
    merc = _merc(level=4, gold_wallet=7, xp_unspent=12, hp_current=0)
    install_piece(merc, piece_for_family_tier("ring", 2, 4))
    party = _party(merc)
    party.checkpoint_d = 15
    party.last_d = 22
    do_wipe(party, now=datetime(2026, 1, 2, tzinfo=timezone.utc), depth=22, band=1)
    kept = party.mercs[0]
    assert party.last_d == 15
    assert party.checkpoint_d == 15
    assert kept.gold_wallet == 7
    assert kept.xp_unspent == 12
    assert kept.level == 4
    assert kept.hp_current == kept.hp_max
    assert kept.gear[4].name


def test_wipe_keeps_gear_wallet_level_and_restores_hp():
    merc = _merc(level=4, gold_wallet=90, hp_current=0)
    install_piece(merc, piece_for_family_tier("ring", 2, 4))
    gear_name = merc.gear[4].name
    party = _party(merc)
    do_wipe(party, now=datetime(2026, 1, 2, tzinfo=timezone.utc), depth=8)
    kept = party.mercs[0]
    assert kept.gear[4].name == gear_name
    assert kept.level == 4
    assert kept.gold_wallet == 90
    assert kept.hp_current == kept.hp_max
    assert party.wipe_count == 1
    assert party.last_d == 0


def test_player_gold_cap_unchanged_by_merc_formula():
    assert gold_cap_day() == 300
    assert merc_gold_cap_day(1) == 80
    assert merc_gold_cap_day(3) == 240


def test_simulate_is_deterministic():
    def run() -> PqParty:
        merc = _merc(gold_wallet=0)
        party = _party(merc, seed=99)
        end = party.run_origin + timedelta(hours=8)
        return simulate_pq(party, end, pb_depth=0)

    a = run()
    b = run()
    assert a.mercs[0].gold_wallet == b.mercs[0].gold_wallet
    assert a.mercs[0].level == b.mercs[0].level
    assert compute_power(a.mercs[0]) == compute_power(b.mercs[0])
    assert a.mercs[0].hp_current == b.mercs[0].hp_current
    assert {(s, p.name, p.ilvl) for s, p in a.mercs[0].gear.items()} == {
        (s, p.name, p.ilvl) for s, p in b.mercs[0].gear.items()
    }


def test_comfort_depth_not_a_wall():
    assert d_max_of(10) == 12
    merc = _merc(level=20)
    assert d_max_of(compute_power(merc)) >= 8
    party = _party(_merc(power=3, hp_current=64, hp_max=64, level=3))
    party.layer = 2
    party.t_node = 30
    simulate_pq(party, party.run_origin + timedelta(minutes=12), pb_depth=1)
    assert party.last_d > 9 or party.wipe_count > 0 or int(getattr(party, "checkpoint_d", 0) or 0) > 0
    if party.wipe_count == 0:
        assert party.last_d > 9


def test_d_max_curve_matches_trio_targets():
    assert d_max_of(3) == 9
    assert d_max_of(125) == 117
    assert d_max_of(321) == 527
    assert d_max_of(800) == 2760


def test_merc_faucet_band_follows_record_not_d_max():
    assert merc_faucet_band(0) == 1
    assert merc_faucet_band(20) == 1
    assert merc_faucet_band(21) == 2
    assert merc_faucet_band(100) == 5
    assert d_max_of(321) > 500
    assert merc_faucet_band(40) == 2


def test_balance_day_band_does_not_skip_two_tiers():
    for band in (1, 2, 3, 4, 5):
        merc = _merc(gold_wallet=0, level=1)
        party = _party(merc, seed=3 + band)
        end = party.run_origin + timedelta(hours=24)
        simulate_pq(party, end, pb_depth=max(1, (band - 1) * 20 + 1))
        bought = [p for p in party.mercs[0].gear.values()]
        assert bought or party.mercs[0].gold_wallet > 0
        for piece in bought:
            tier = max(1, piece.base_ilvl // 4)
            assert tier <= band + 1, (band, piece.name, tier)


def test_gear_price_table_matches_tz():
    assert gear_price(4, 1) == 48
    assert gear_price(8, 2) == 108
    assert gear_price(4, 80) == 48
    assert sharpen_cost(4, 1) == 16
    assert sharpen_cost(4, 10) == 160
    assert sharpen_cost(4, 100) == 1600
    assert sharpen_cost(4, 100) > sharpen_cost(4, 10)


def test_sharpen_offer_has_no_enchant_cap():
    merc = _merc(gold_wallet=10_000)
    piece = piece_for_family_tier("costume", 1, 3)
    piece.enchant_level = 99
    install_piece(merc, piece)
    offers = shop_offers(merc, depth=4, seed=7, cycle=0)
    sharpen = [o for o in offers if o.kind == "sharpen"]
    assert sharpen
    assert sharpen[0].enchant_to == 100
    assert sharpen[0].price == sharpen_cost(4, 100)


def test_flavor_prefix_name_not_empty():
    piece = piece_for_family_tier("sword", 1, 1)
    roll_flavor_affixes(piece, seed=11, cycle=0, depth=4, card_id=1, band=1)
    assert piece.prefix_stat
    assert piece.display_name
    assert "Меч" in piece.display_name
    assert piece.display_name != "Меч +0"
    again = piece_for_family_tier("sword", 1, 1)
    roll_flavor_affixes(again, seed=11, cycle=0, depth=4, card_id=1, band=1)
    assert again.prefix_stat == piece.prefix_stat
    assert again.display_name == piece.display_name


def test_shop_log_uses_display_name():
    merc = _merc(gold_wallet=200)
    bought = resolve_shop(merc, depth=4, seed=7, cycle=0)
    gear = [b for b in bought if b.get("kind") == "gear"]
    assert gear
    assert " +" in gear[0]["name"]


def test_shop_holds_gold_for_tier1_instead_of_potions():
    by_id = {c.id: c for c in load_consumables()}
    assert by_id[POTION_ID].stack_cap == 3
    assert by_id[SALVE_ID].stack_cap == 1
    merc = _merc(gold_wallet=40)
    bought = resolve_shop(merc, depth=4, seed=7, cycle=0)
    assert not any(b.get("kind") == "gear" for b in bought)
    assert not any(b.get("kind") == "consumable" for b in bought)
    assert merc.gold_wallet == 40
    assert merc.bag.get(POTION_ID, 0) == 0


def test_shop_potion_stack_stops_at_three():
    merc = _merc(gold_wallet=500)
    resolve_shop(merc, depth=4, seed=7, cycle=0)
    assert merc.bag.get(POTION_ID, 0) <= 3
    assert merc.bag.get(SALVE_ID, 0) <= 1
    assert any(merc.gear.values())


def test_combat_drain_follows_overage():
    assert d_max_of(1) == 8
    assert d_max_of(3) == 9
    assert combat_drain(9, 3) == 5
    assert combat_drain(18, 3) == 10
    assert combat_drain(8, 1) == 5
    assert combat_drain(16, 1) == 10
    assert combat_drain(40, 5) > combat_drain(4, 20)


def test_deepcopy_shop_offer_type():
    offer = ShopOffer(kind="gear", name="Меч", price=48, slot=1, ilvl=4)
    assert deepcopy(offer).price == 48


def test_apply_drain_splits_and_can_wipe():
    a = _merc(card_id=1, slot=1, name="А", power=10, hp_current=5, hp_max=48)
    b = _merc(card_id=2, slot=2, name="Б", power=10, hp_current=5, hp_max=48)
    apply_drain([a, b], 20)
    assert a.hp_current == 0
    assert b.hp_current == 0


@dataclass
class _WatchParty(PqParty):
    pb: int = 0

    def __setattr__(self, name, value):
        if name == "last_d":
            cur = int(value or 0)
            if cur > int(getattr(self, "pb", 0) or 0):
                object.__setattr__(self, "pb", cur)
        super().__setattr__(name, value)


def _pace_merc(card_id: int, slot: int, name: str, stance: str, class_id: int) -> MercState:
    merc = MercState(
        card_id=card_id,
        slot=slot,
        name=name,
        loyalty=50,
        level=1,
        gold_wallet=0,
        power=1,
        hp_current=48,
        hp_max=48,
        class_id=class_id,
        stance=stance,
        temper="stay",
    )
    refresh_derived(merc, fill_if_full=True)
    return merc


def _run_pace(n: int, seed: int, *, days: float, step_h: int = 2) -> _WatchParty:
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    roster = [("Мира", "guide", 4), ("Сера", "shield", 1), ("Кайра", "scout", 3)]
    party = _WatchParty(
        seed=seed,
        run_origin=origin,
        last_ts=origin,
        mercs=[_pace_merc(i + 1, i + 1, *roster[i]) for i in range(n)],
        layer=2,
        t_node=30,
        pb=0,
    )
    now = origin
    end = origin + timedelta(hours=int(days * 24))
    while now < end:
        now += timedelta(hours=step_h)
        simulate_pq(party, now, pb_depth=max(int(party.pb), 1))
        if party.pb >= 3000:
            break
    return party


def test_trio_hits_100_500_3000_pace():
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    party = _WatchParty(
        seed=11,
        run_origin=origin,
        last_ts=origin,
        mercs=[
            _pace_merc(i + 1, i + 1, *row)
            for i, row in enumerate(
                (("Мира", "guide", 4), ("Сера", "shield", 1), ("Кайра", "scout", 3))
            )
        ],
        layer=2,
        t_node=30,
        pb=0,
    )
    now = origin
    pending = {100: 7.5, 500: 32.0, 3000: 95.0}
    while pending and (now - origin).total_seconds() / 86400.0 <= 95.0:
        now += timedelta(hours=2)
        simulate_pq(party, now, pb_depth=max(int(party.pb), 1))
        days = (now - origin).total_seconds() / 86400.0
        for depth, limit in list(pending.items()):
            if party.pb >= depth:
                assert days <= limit, (depth, days, party.pb)
                del pending[depth]
    assert pending == {}, (party.pb, pending)


def test_solo_day30_deeper_than_old_plateau():
    party = _run_pace(1, 11, days=30, step_h=2)
    assert party.pb >= 40
    assert party.checkpoint_d >= 15
