"""PQ layer 2: hole drain, phrases, traits, trauma, wall-clock faucet."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from waifu_bot.game.delve_pq import (
    MercState,
    PqParty,
    combat_drain,
    compute_power,
    d_max_of,
    do_wipe,
    grant_merc_faucet,
    piece_for_family_tier,
    install_piece,
    simulate_pq,
)
from waifu_bot.game.delve_pq_layer import (
    STATUS_BY_ID,
    apply_status,
    assemble_phrase,
    boss_drain_hole,
    combat_drain_hole,
    events_by_kind,
    load_node_events,
    power_eff_of,
    t_eff_of,
    tick_city_return,
)


def _merc(**kwargs) -> MercState:
    base = dict(
        card_id=1,
        slot=1,
        name="Мира",
        loyalty=50,
        level=1,
        gold_wallet=0,
        class_id=1,
        stance="shield",
        temper="stay",
        traits=[],
    )
    base.update(kwargs)
    return MercState(**base)


def _party(*mercs: MercState, seed: int = 11, t_node: int = 30) -> PqParty:
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return PqParty(
        seed=seed,
        run_origin=origin,
        last_ts=origin,
        mercs=list(mercs),
        layer=2,
        t_node=t_node,
        t_eff=t_node,
    )


def test_catalog_has_eighteen_rows():
    rows = load_node_events()
    assert len(rows) == 18
    kinds = {r["kind"] for r in rows}
    assert kinds == {"empty", "monster", "event", "npc", "find"}
    assert len(events_by_kind("monster")) == 6
    assert len(events_by_kind("empty")) == 3


def test_hole_drain_table():
    assert combat_drain(3, 1) == 9
    assert combat_drain(8, 1) == 13
    assert combat_drain(8, 15) == 7
    assert combat_drain_hole(8, 1) > combat_drain_hole(8, 15) > combat_drain_hole(8, 40)
    assert boss_drain_hole(10, 1) == 19


def test_phrase_has_no_double_name():
    phrase = assemble_phrase(
        kind="monster",
        depth=12,
        line="Крысолюд ударил {who}",
        who="Милфа",
        hp_by_name={"Милфа": 6},
    )
    assert phrase == "[Монстр] Глубина 12 · Крысолюд ударил Милфа (−6 HP)"
    assert phrase.count("Милфа") == 1
    assert not phrase.startswith("Милфа:")


def test_cautious_slower_and_safer_than_fearless():
    cautious = _merc(traits=["осторожная"], class_id=6, stance="guide", temper="stay")
    fearless = _merc(traits=["бесстрашная"], class_id=5, stance="scout", temper="curiosity")
    t_c = t_eff_of([cautious], t_node=30)
    t_f = t_eff_of([fearless], t_node=30)
    assert 15 <= t_f < t_c <= 50
    assert t_c - t_f >= 5
    from waifu_bot.game.delve_pq_layer import actor_mods

    inj_c = actor_mods(cautious, party_size=1)["injury"]
    inj_f = actor_mods(fearless, party_size=1)["injury"]
    assert inj_c <= inj_f - 0.012


def test_three_cautious_same_tick_as_one():
    rows = [_merc(card_id=i, slot=i, traits=["осторожная"], class_id=6, stance="guide") for i in (1, 2, 3)]
    assert t_eff_of(rows, t_node=30) == t_eff_of(rows[:1], t_node=30)
    assert t_eff_of(rows, t_node=30) == 37


def test_buy_raises_raw_and_eff():
    merc = _merc()
    raw0 = compute_power(merc)
    eff0 = power_eff_of(merc, party_size=1)
    install_piece(merc, piece_for_family_tier("sword", 1, 1))
    assert compute_power(merc) > raw0
    assert power_eff_of(merc, party_size=1) > eff0


def test_faucet_ignores_node_tick():
    a = _party(_merc(), t_node=15)
    b = _party(_merc(card_id=2), t_node=50)
    end = a.run_origin + timedelta(hours=1)
    grant_merc_faucet(a, now=end, band=1)
    grant_merc_faucet(b, now=end, band=1)
    assert a.mercs[0].gold_wallet == b.mercs[0].gold_wallet
    assert a.mercs[0].gold_wallet > 0


def test_simulate_layer_deterministic_and_drops_hp():
    def run() -> PqParty:
        party = _party(_merc(gold_wallet=0), seed=99)
        return simulate_pq(party, party.run_origin + timedelta(minutes=8), pb_depth=0)

    a = run()
    b = run()
    assert a.mercs[0].hp_current == b.mercs[0].hp_current
    assert a.last_event and b.last_event
    assert a.last_event["phrase"] == b.last_event["phrase"]
    assert a.mercs[0].hp_current < a.mercs[0].hp_max
    assert "[" in (a.last_event.get("phrase") or "")
    assert not (a.last_event.get("phrase") or "").startswith("Мира:")


def test_wipe_keeps_serious_and_ticks_return():
    merc = _merc(hp_current=0)
    apply_status(merc, "eye_hurt")
    party = _party(merc)
    do_wipe(party, now=datetime(2026, 1, 2, tzinfo=timezone.utc), depth=8)
    kept = party.mercs[0]
    assert kept.hp_current == kept.hp_max
    assert kept.flesh
    assert kept.flesh[0]["id"] == "eye_hurt"
    assert int(kept.flesh[0]["returns_left"]) == 1


def test_city_tick_removes_spent_serious():
    merc = _merc()
    apply_status(merc, "arm_cut")
    assert merc.flesh[0]["returns_left"] == 1
    tick_city_return(merc)
    assert merc.flesh == []


def test_light_heals_without_city():
    merc = _merc()
    apply_status(merc, "arm_graze")
    from waifu_bot.game.delve_pq_layer import heal_light

    heal_light(merc)
    assert merc.flesh == []


def test_sixteen_statuses_present():
    assert len(STATUS_BY_ID) == 16


def test_d_max_still_starts_at_eight():
    assert d_max_of(1) == 8
