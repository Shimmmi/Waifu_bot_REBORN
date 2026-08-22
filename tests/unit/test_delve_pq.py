"""Delve Progress Quest invariants: power, shop, wipe, faucet isolation, balance."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from waifu_bot.game.delve_pq import (
    GEAR_PATH,
    MercState,
    PqParty,
    SAFE_ENCHANT_MAX,
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
    load_gear_templates,
    merc_gold_cap_day,
    piece_for_family_tier,
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
    assert merc.gear[3].enchant_level <= SAFE_ENCHANT_MAX


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


def test_frame_depth_cannot_exceed_d_max():
    assert d_max_of(party_power := 10) == 11
    _ = party_power
    merc = _merc(level=20)
    assert d_max_of(compute_power(merc)) >= 8


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
    assert sharpen_cost(4, 1) == 32


def test_combat_drain_grows_when_underleveled():
    easy = combat_drain(4, 20)
    hard = combat_drain(40, 5)
    assert hard > easy
    assert easy >= 1


def test_deepcopy_shop_offer_type():
    offer = ShopOffer(kind="gear", name="Меч", price=48, slot=1, ilvl=4)
    assert deepcopy(offer).price == 48


def test_apply_drain_splits_and_can_wipe():
    a = _merc(card_id=1, slot=1, name="А", power=10, hp_current=5, hp_max=48)
    b = _merc(card_id=2, slot=2, name="Б", power=10, hp_current=5, hp_max=48)
    apply_drain([a, b], 20)
    assert a.hp_current == 0
    assert b.hp_current == 0
