"""Unit tests for guild skill attribution helpers."""
from __future__ import annotations

from waifu_bot.services.guild_skill_effects import (
    GuildSkillContribution,
    apply_guild_solo_reward_mults,
    apply_price_discount_pct,
    apply_raid_gxp_guild_bonuses,
    format_guild_bonus_suffix_ru,
    guild_reward_bonus_dicts,
    pct_bonus_lines_ru,
)


def test_pct_bonus_lines_ru():
    contribs = [
        GuildSkillContribution(param="monster_gold_pct", name="Торговый пакт", value=0.1),
        GuildSkillContribution(param="global_reward_pct", name="Легенда гильдии", value=0.05),
    ]
    assert pct_bonus_lines_ru(contribs) == [
        "Торговый пакт (+10%)",
        "Легенда гильдии (+5%)",
    ]


def test_format_guild_bonus_suffix_ru():
    lines = ["Торговый пакт (+10%)"]
    assert format_guild_bonus_suffix_ru(lines) == " (Торговый пакт (+10%))"
    assert format_guild_bonus_suffix_ru([]) == ""


def test_apply_guild_solo_reward_mults_stacks_global_once_in_contribs():
    gfx = {
        "monster_gold_pct": 0.1,
        "dungeon_exp_pct": 0.2,
        "global_reward_pct": 0.05,
    }
    gold_m, exp_m, contribs = apply_guild_solo_reward_mults(gfx)
    assert gold_m == 1.15
    assert exp_m == 1.25
    params = {c.param for c in contribs}
    assert params == {"monster_gold_pct", "dungeon_exp_pct", "global_reward_pct"}


def test_guild_reward_bonus_dicts():
    contribs = [GuildSkillContribution(param="monster_gold_pct", name="Торговый пакт", value=0.1)]
    assert guild_reward_bonus_dicts(contribs) == [
        {"param": "monster_gold_pct", "name": "Торговый пакт", "pct": 0.1}
    ]


def test_apply_price_discount_pct():
    assert apply_price_discount_pct(100, 0.1) == 90
    assert apply_price_discount_pct(0, 0.5) == 0


def test_apply_raid_gxp_guild_bonuses_multiplier_not_additive():
    gfx = {"raid_gxp_multiplier": 1.5, "raid_completion_reward_pct": 0.10}
    assert apply_raid_gxp_guild_bonuses(100, gfx) == int(round(100 * 1.5 * 1.10))


def test_apply_raid_gxp_guild_bonuses_completion_only():
    assert apply_raid_gxp_guild_bonuses(200, {"raid_completion_reward_pct": 0.20}) == 240
