"""Unit tests for affix effect UI helpers."""

from waifu_bot.game.affix_effect_ui import BONUS_CATEGORY_ORDER, effect_bonus_category


def test_effect_bonus_category_primary_stats():
    assert effect_bonus_category("strength") == ("stats", "Основные статы")
    assert effect_bonus_category("Luck") == ("stats", "Основные статы")


def test_effect_bonus_category_damage():
    assert effect_bonus_category("damage_flat")[0] == "damage"
    assert effect_bonus_category("crit_chance_pct")[0] == "damage"
    assert effect_bonus_category("melee_damage_flat")[0] == "damage"


def test_effect_bonus_category_defense():
    assert effect_bonus_category("defense_flat")[0] == "defense"
    assert effect_bonus_category("hp_max_pct")[0] == "defense"
    assert effect_bonus_category("evade_pct")[0] == "defense"


def test_effect_bonus_category_economy():
    assert effect_bonus_category("gold_bonus_pct")[0] == "economy"
    assert effect_bonus_category("merchant_discount_percent")[0] == "economy"
    assert effect_bonus_category("magic_find_pct")[0] == "economy"


def test_effect_bonus_category_skills():
    assert effect_bonus_category("passive_all_nodes_level_add")[0] == "skills"
    assert effect_bonus_category("passive_branch_level_add:warrior")[0] == "skills"
    assert effect_bonus_category("passive_node_level_add:w_bash")[0] == "skills"


def test_effect_bonus_category_monster():
    assert effect_bonus_category("damage_vs_monster_type_flat:beast")[0] == "monster"
    assert effect_bonus_category("damage_vs_monster_type_percent:undead")[0] == "monster"


def test_effect_bonus_category_media():
    assert effect_bonus_category("media_damage_text_percent")[0] == "media"
    assert effect_bonus_category("media_damage_audioo_percent")[0] == "media"


def test_effect_bonus_category_other():
    assert effect_bonus_category("")[0] == "other"
    assert effect_bonus_category("unknown_custom_key")[0] == "other"


def test_bonus_category_order_covers_all_labels():
    ids = set(BONUS_CATEGORY_ORDER)
    assert "stats" in ids
    assert "other" in ids
    assert len(ids) == len(BONUS_CATEGORY_ORDER)
