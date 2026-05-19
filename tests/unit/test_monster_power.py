"""Monster power budget: HP/DMG split preserves weighted sum on average."""
import random

from waifu_bot.game.constants import MONSTER_POWER_W_DMG, MONSTER_POWER_W_HP
from waifu_bot.game.monster_power import vary_hp_dmg_for_power_budget


def test_power_budget_preserved_exact_after_rounding_loop():
    rng = random.Random(42)
    hp0, dmg0 = 500, 120
    p = MONSTER_POWER_W_HP * hp0 + MONSTER_POWER_W_DMG * dmg0
    for _ in range(200):
        hp, dmg, _ = vary_hp_dmg_for_power_budget(hp0, dmg0, rng)
        p2 = MONSTER_POWER_W_HP * hp + MONSTER_POWER_W_DMG * dmg
        assert abs(p2 - p) <= 2  # rounding tolerance


def test_variance_not_flatline():
    rng = random.Random(0)
    pairs = {vary_hp_dmg_for_power_budget(200, 50, rng)[:2] for _ in range(50)}
    assert len(pairs) >= 3
