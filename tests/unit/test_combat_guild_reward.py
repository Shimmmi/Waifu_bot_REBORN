"""Combat solo monster reward guild attribution (helpers)."""
from __future__ import annotations

from waifu_bot.services.combat import _solo_monster_reward_log_payload
from waifu_bot.services.guild_skill_effects import GuildSkillContribution


def test_solo_monster_reward_log_payload_includes_guild_suffix():
    contribs = [
        GuildSkillContribution(param="monster_gold_pct", name="Торговый пакт", value=0.1),
    ]
    event_data, bonus = _solo_monster_reward_log_payload(
        exp=20,
        gold=100,
        guild_contribs=contribs,
        monster_name="Гоблин",
    )
    assert event_data["exp"] == 20
    assert event_data["gold"] == 100
    assert event_data["guild_bonus_lines"] == ["Торговый пакт (+10%)"]
    assert "Торговый пакт (+10%)" in event_data["summary_ru"]
    assert bonus[0]["name"] == "Торговый пакт"
