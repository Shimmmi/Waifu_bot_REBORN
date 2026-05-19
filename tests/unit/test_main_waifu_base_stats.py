"""Плоские бонусы расы/класса ОВ: ключи и согласованность с базой."""

from waifu_bot.db.models.waifu import WaifuClass, WaifuRace
from waifu_bot.game.main_waifu_base_stats import (
    MAIN_WAIFU_BASE_STATS,
    MAIN_WAIFU_CLASS_FLAT_BONUSES,
    MAIN_WAIFU_RACE_FLAT_BONUSES,
    compute_main_waifu_base_stats,
    validate_bonus_dict_keys,
)

_STAT_KEYS = frozenset(MAIN_WAIFU_BASE_STATS.keys())


def test_race_bonus_keys_are_main_stats_only() -> None:
    for rid, bonuses in MAIN_WAIFU_RACE_FLAT_BONUSES.items():
        validate_bonus_dict_keys(bonuses, context=f"race {rid}")
        assert isinstance(rid, int)


def test_class_bonus_keys_are_main_stats_only() -> None:
    for cid, bonuses in MAIN_WAIFU_CLASS_FLAT_BONUSES.items():
        validate_bonus_dict_keys(bonuses, context=f"class {cid}")
        assert isinstance(cid, int)


def test_compute_matches_base_plus_bonuses() -> None:
    r = int(WaifuRace.ELF)
    c = int(WaifuClass.MAGE)
    out = compute_main_waifu_base_stats(r, c)
    expected = MAIN_WAIFU_BASE_STATS.copy()
    for k, v in MAIN_WAIFU_RACE_FLAT_BONUSES[r].items():
        expected[k] = expected.get(k, 0) + v
    for k, v in MAIN_WAIFU_CLASS_FLAT_BONUSES[c].items():
        expected[k] = expected.get(k, 0) + v
    assert out == expected
    assert set(out.keys()) == _STAT_KEYS


def test_human_knight_snapshot() -> None:
    out = compute_main_waifu_base_stats(WaifuRace.HUMAN, WaifuClass.KNIGHT)
    assert out["strength"] == 12
    assert out["endurance"] == 12
    assert out["luck"] == 10
