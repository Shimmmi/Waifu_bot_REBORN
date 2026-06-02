"""Unit tests for legendary bonus engine pieces."""

from __future__ import annotations

from waifu_bot.game.legendary_bonuses.compat import (
    bonuses_compatible,
    slot_allowed,
)
from waifu_bot.game.legendary_bonuses.context import BonusContext
from waifu_bot.game.legendary_bonuses.handlers import (
    handler_survivor_spirit,
    handler_type_hunter,
)
from waifu_bot.game.legendary_bonuses.state import (
    initial_battle_state,
    merge_battle_state,
    reset_fight_level_keys,
)


def _ctx(**kwargs) -> BonusContext:
    base = dict(
        player_id=1,
        waifu_id=1,
        session_id=1,
        message_type="sticker",
        message_length=10,
        monster_hp_current=100,
        monster_hp_max=100,
        waifu_hp_current=50,
        waifu_hp_max=100,
        base_damage=100,
        battle_state=initial_battle_state(),
    )
    base.update(kwargs)
    return BonusContext(**base)


def test_survivor_spirit_after_failed_run():
    ctx = _ctx(waifu_last_dungeon_knocked_out=True)
    res = handler_survivor_spirit(ctx)
    assert res.damage_multiplier == 1.3


def test_type_hunter_unlocks_aoe_on_fourth_media_type():
    state = initial_battle_state()
    state["media_types_used"] = ["sticker", "photo", "gif"]
    ctx = _ctx(message_type="voice", battle_state=state)
    res = handler_type_hunter(ctx)
    assert res.battle_state_patch.get("aoe_unlocked") is True
    assert res.remaining_monsters_damage_multiplier == 0.0

    state2 = merge_battle_state(state, res.battle_state_patch)
    state2["aoe_unlocked"] = True
    ctx2 = _ctx(message_type="voice", battle_state=state2)
    res2 = handler_type_hunter(ctx2)
    assert res2.remaining_monsters_damage_multiplier == 0.6


def test_reset_fight_level_keys_clears_fight_counters():
    st = initial_battle_state()
    st["total_messages_in_fight"] = 12
    st["crit_chain_ready"] = True
    st["monsters_killed_session"] = 3
    out = reset_fight_level_keys(st)
    assert out["total_messages_in_fight"] == 0
    assert out["crit_chain_ready"] is False
    assert out["monsters_killed_session"] == 3


def test_slot_restrictions():
    assert not slot_allowed("LAST_BREATH", "ring")
    assert slot_allowed("LAST_BREATH", "weapon_one_hand")


def test_incompatible_pairs():
    assert not bonuses_compatible({"AGONY"}, "LAST_BREATH")
    assert bonuses_compatible({"GOLD_PULSE"}, "AFFIX_MASTERY")
