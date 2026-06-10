"""Unit tests for legendary bonus engine pieces."""

from __future__ import annotations

from waifu_bot.game.legendary_bonuses.compat import (
    bonuses_compatible,
    slot_allowed,
)
from waifu_bot.game.legendary_bonuses.context import BonusContext
from waifu_bot.game.legendary_bonuses.generic import (
    GENERIC_HANDLERS,
    generic_media,
    generic_text_content,
    generic_text_length,
)
from waifu_bot.game.legendary_bonuses.engine import run_outgoing_handlers
from waifu_bot.game.legendary_bonuses.handlers import (
    handler_survivor_spirit,
    handler_type_hunter,
)
from waifu_bot.services.legendary_combat import build_legendary_extra_data
from waifu_bot.game.constants import MediaType
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


def test_generic_media_sticker_triple():
    ctx = _ctx(
        message_type="sticker",
        bonus_key="STICKER_TRIPLE",
        bonus_params={
            "handler": "media",
            "media_types": ["sticker"],
            "effects": {"damage_multiplier": 3.0},
        },
    )
    res = generic_media(ctx)
    assert res.damage_multiplier == 3.0


def test_generic_text_length_lucky_seven():
    ctx = _ctx(
        message_type="text",
        message_length=7,
        bonus_key="LUCKY_SEVEN_CHARS",
        bonus_params={
            "handler": "text_length",
            "op": "eq",
            "length": 7,
            "effects": {"damage_multiplier": 3.0},
        },
    )
    res = generic_text_length(ctx)
    assert res.damage_multiplier == 3.0


def test_generic_text_content_caps():
    ctx = _ctx(
        message_type="text",
        bonus_key="CAPS_FURY",
        bonus_params={
            "handler": "text_content",
            "mode": "caps",
            "effects": {"damage_multiplier": 2.0},
        },
        extra_data={"text": "ATTACK"},
    )
    res = generic_text_content(ctx)
    assert res.damage_multiplier == 2.0


def test_engine_dispatches_generic_handler_by_params():
    ctx = _ctx(message_type="gif")
    rows = [
        {
            "bonus_key": "GIF_LOOP",
            "params": {
                "handler": "media",
                "media_types": ["gif"],
                "effects": {"damage_multiplier": 2.5},
            },
            "inventory_item_id": 1,
            "slot_type": "weapon_two_hand",
        }
    ]
    agg = run_outgoing_handlers(rows, ctx)
    assert agg.damage_multiplier == 2.5


def test_build_legendary_extra_data_includes_text():
    data = build_legendary_extra_data(MediaType.TEXT, "hello")
    assert data["text"] == "hello"


def test_generic_handler_registry_covers_primitives():
    expected = {
        "media",
        "time_window",
        "tempo",
        "text_length",
        "text_content",
        "counter",
        "hp_state",
        "monster_state",
        "session_scale",
        "economy",
        "meta_scale",
        "state_flag",
        "random_proc",
        "passive",
    }
    assert expected.issubset(set(GENERIC_HANDLERS))
