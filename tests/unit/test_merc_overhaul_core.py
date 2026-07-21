"""Unit tests for merc overhaul core (perks, archetypes, CR, pity math)."""
from __future__ import annotations

import random
from types import SimpleNamespace

from waifu_bot.db.models.waifu import WaifuRarity
from waifu_bot.game.merc_archetypes import resolve_archetype, stance_edge, STANCE_ASSAULT, STANCE_WARD
from waifu_bot.game.merc_arena import ArenaFighter, simulate_3v3
from waifu_bot.game.merc_combat_rating import compute_hired_cr
from waifu_bot.game.merc_config import merc_balance_from_cfg, PITY_LEG_HARD, PITY_EPIC_HARD
from waifu_bot.game.merc_perks import (
    LEGACY_PERK_MAP,
    map_legacy_perk_id,
    roll_perk_ids_for_rarity,
    tag_coverage,
    PERK_BY_ID,
)
from waifu_bot.game.merc_potential import bench_cap_for_main_level, perk_level_cap, fodder_cost_for_next_star
from waifu_bot.services.merc_systems import _parse_guild_assist, _roll_rarity_with_pity


def test_archetypes_table():
    assert resolve_archetype(["ATK", "ATK", "ATK"]).id == "berserker"
    assert resolve_archetype(["DEF", "DEF", "DEF"]).id == "citadel"
    assert resolve_archetype(["SUP", "SUP", "SUP"]).id == "oracle"
    assert resolve_archetype(["ATK", "DEF", "SUP"]).id == "tactician"


def test_stance_edge_rps():
    assert stance_edge(STANCE_ASSAULT, STANCE_WARD) > 0
    assert stance_edge(STANCE_WARD, STANCE_ASSAULT) < 0
    assert stance_edge(STANCE_ASSAULT, STANCE_ASSAULT) == 0


def test_cr_grows_with_stars():
    base = compute_hired_cr(10, 4)
    starred = compute_hired_cr(10, 4, potential_stars=3)
    assert starred > base


def test_bench_cap_levels():
    assert bench_cap_for_main_level(1) == 8
    assert bench_cap_for_main_level(10) == 12
    assert bench_cap_for_main_level(40) == 24


def test_perk_level_cap():
    assert perk_level_cap(0) == 1
    assert perk_level_cap(5) == 6


def test_no_creature_perks_in_catalog():
    for pid in PERK_BY_ID:
        assert "orc" not in pid
        assert "elf_slayer" not in pid
        assert "dragon" not in pid


def test_legacy_map_covers_orc_hunter():
    assert map_legacy_perk_id("orc_hunter") in PERK_BY_ID
    assert "orc_hunter" in LEGACY_PERK_MAP


def test_epic_never_rolls_legendary_perk():
    rng = random.Random(42)
    for _ in range(40):
        ids = roll_perk_ids_for_rarity(int(WaifuRarity.EPIC), rng=rng)
        for pid in ids:
            assert PERK_BY_ID[pid].rarity <= 4


def test_legendary_has_legendary_perk_when_forced():
    ids = roll_perk_ids_for_rarity(5, forced_legendary_id="leg_storm")
    assert "leg_storm" in ids
    assert len(ids) == 3


def test_tag_coverage_capped():
    cov = tag_coverage(["leg_storm", "leg_citadel", "leg_oracle"])
    for v in cov.values():
        assert v <= 0.55 + 1e-9


def test_arena_sim_deterministic():
    a = [ArenaFighter("A", 100, ["cleave_u"], "Assault", "vanguard")]
    b = [ArenaFighter("B", 100, ["ironwall_u"], "Ward", "bulwark")]
    r1 = simulate_3v3(a, b, match_seed="seed-1")
    r2 = simulate_3v3(a, b, match_seed="seed-1")
    assert r1["winner"] == r2["winner"]
    assert r1["log"] == r2["log"]


def test_parse_guild_assist_day_encoding():
    day, wid = _parse_guild_assist(SimpleNamespace(guild_assist_day="2026-07-21:42"))
    assert day == "2026-07-21"
    assert wid == 42
    day2, wid2 = _parse_guild_assist(SimpleNamespace(guild_assist_day="2026-07-21"))
    assert day2 == "2026-07-21"
    assert wid2 is None


def test_fodder_cost_grows():
    assert fodder_cost_for_next_star(0) >= 1
    assert fodder_cost_for_next_star(4) >= fodder_cost_for_next_star(0)


def test_hard_pity_legendary_resets():
    st = SimpleNamespace(pity_legendary=PITY_LEG_HARD - 1, pity_epic=0)
    r = _roll_rarity_with_pity(st, random.Random(0))
    assert r == WaifuRarity.LEGENDARY
    assert st.pity_legendary == 0


def test_epic_hard_pity():
    st = SimpleNamespace(pity_legendary=1, pity_epic=PITY_EPIC_HARD - 1)

    class R(random.Random):
        def random(self):
            return 0.999

    r = _roll_rarity_with_pity(st, R())
    assert r == WaifuRarity.EPIC
    assert st.pity_epic == 0


def test_merc_balance_defaults():
    bal = merc_balance_from_cfg({})
    assert bal["pity_leg_hard"] == 50
    assert bal["leg_base_rate"] == 0.0075
    bal2 = merc_balance_from_cfg({"merc_pity_leg_hard": "40"})
    assert bal2["pity_leg_hard"] == 40
