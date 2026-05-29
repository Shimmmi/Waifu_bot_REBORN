"""Regression: guild_skill_contributions list must not shadow battle_state contribution dict."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.guild_skill_effects import GuildSkillContribution
from waifu_bot.services.gd_round_engine import _execute_player_action


@pytest.mark.asyncio
async def test_execute_player_action_updates_contrib_when_guild_skills_return_list() -> None:
    uid = 305174198
    contrib: dict = {}
    party = [
        {
            "user_id": uid,
            "class_id": 1,
            "level": 10,
            "strength": 15,
            "agility": 12,
            "intelligence": 8,
            "current_hp": 100,
            "max_hp": 100,
        }
    ]
    monsters = [{"id": 1, "hp": 500, "max_hp": 500, "level": 5, "n_players": 1, "hp_scale": 0.7}]
    state: dict = {"contribution": contrib}
    outcomes = {
        "hits": [],
        "heals": [],
        "flags": {"revive_no_target": False, "heal_no_target": False, "skill_on_cooldown": []},
    }
    actions_log: list = []
    fx: list = []
    cycle = AsyncMock()
    cycle.id = 1
    session = AsyncMock()

    guild_list = [
        GuildSkillContribution(param="gd_party_damage_pct", name="Боевой клич", value=0.1),
    ]

    with (
        patch(
            "waifu_bot.services.guild_skill_effects.gd_party_damage_multiplier",
            new=AsyncMock(return_value=1.1),
        ),
        patch(
            "waifu_bot.services.guild_skill_effects.guild_skill_contributions",
            new=AsyncMock(return_value=guild_list),
        ),
        patch(
            "waifu_bot.services.gd_round_engine._consume_buff_crit_next",
            new=AsyncMock(return_value=1.0),
        ),
        patch(
            "waifu_bot.services.gd_round_engine._apply_player_damage_to_monster",
            new=AsyncMock(return_value=25),
        ),
        patch(
            "waifu_bot.services.gd_round_engine._grant_loot_if_monster_died",
            new=AsyncMock(),
        ),
    ):
        await _execute_player_action(
            session,
            cycle,
            1,
            party[0],
            {"kind": "text", "len": 42, "count": 1},
            party,
            monsters,
            state,
            outcomes,
            actions_log,
            contrib,
            fx,
            1,
        )

    assert isinstance(contrib, dict)
    assert str(uid) in contrib
    assert contrib[str(uid)]["text"] == 25
    assert any(a.get("kind") == "text" for a in actions_log)
