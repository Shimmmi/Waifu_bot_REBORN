"""Unit tests for legendary bonus engine pieces."""

from __future__ import annotations

from waifu_bot.game.legendary_bonuses.compat import (
    bonuses_compatible,
    slot_allowed,
)
from waifu_bot.game.legendary_bonuses.context import BonusContext
from waifu_bot.game.legendary_bonuses.generic import (
    GENERIC_HANDLERS,
    generic_counter,
    generic_monster_state,
    generic_media,
    generic_text_content,
    generic_text_length,
)
from waifu_bot.game.legendary_bonuses.engine import run_outgoing_handlers
from waifu_bot.game.legendary_bonuses.handlers import (
    handler_charged_discharge,
    handler_survivor_spirit,
    handler_type_hunter,
)
from waifu_bot.services.legendary_combat import LegendaryCombatBridge
from waifu_bot.services.legendary_combat import build_legendary_extra_data
from waifu_bot.game.constants import MediaType
from waifu_bot.game.legendary_bonuses.state import (
    increment_message_counters,
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


def test_id_mod_uses_sequence_not_db_id():
    ctx_hit = _ctx(
        monster_id=49,
        monster_sequence_index=7,
        bonus_params={
            "handler": "monster_state",
            "condition": "id_mod",
            "mod": 7,
            "remainder": 0,
            "effects": {"damage_multiplier": 2.5},
        },
    )
    assert generic_monster_state(ctx_hit).damage_multiplier == 2.5

    ctx_miss = _ctx(
        monster_id=49,
        monster_sequence_index=6,
        bonus_params={
            "handler": "monster_state",
            "condition": "id_mod",
            "mod": 7,
            "remainder": 0,
            "effects": {"damage_multiplier": 2.5},
        },
    )
    assert generic_monster_state(ctx_miss).damage_multiplier == 1.0


def test_monster_self_damage_from_generic_passive():
    ctx = _ctx(
        base_damage=200,
        bonus_params={
            "handler": "passive",
            "effects": {"monster_self_damage_pct_base": 0.25},
        },
    )
    res = GENERIC_HANDLERS["passive"](ctx)
    assert res.monster_self_damage == 50


def test_milestone_session_scope_centurion():
    state = initial_battle_state()
    state["total_messages_in_session"] = 100
    state["total_messages_in_fight"] = 5
    ctx = _ctx(
        message_type="text",
        battle_state=state,
        bonus_params={
            "handler": "counter",
            "mode": "milestone",
            "scope": "session",
            "n": 100,
            "effects": {"damage_multiplier": 20.0},
        },
    )
    assert generic_counter(ctx).damage_multiplier == 20.0

    ctx_fight_only = _ctx(
        message_type="text",
        battle_state=state,
        bonus_params={
            "handler": "counter",
            "mode": "milestone",
            "n": 100,
            "effects": {"damage_multiplier": 20.0},
        },
    )
    assert generic_counter(ctx_fight_only).damage_multiplier == 1.0


def test_fibonacci_resets_per_monster():
    st = initial_battle_state()
    st["total_messages_in_fight"] = 55
    out = reset_fight_level_keys(st)
    assert out["total_messages_in_fight"] == 0

    st2 = merge_battle_state(out, increment_message_counters(out, "text"))
    ctx = _ctx(
        message_type="text",
        battle_state=st2,
        bonus_params={
            "handler": "counter",
            "mode": "fibonacci",
            "effects": {"damage_multiplier": 2.5},
        },
    )
    assert generic_counter(ctx).damage_multiplier == 2.5


def test_charged_discharge_requires_five_texts_not_three():
    state = initial_battle_state()
    for _ in range(4):
        state = merge_battle_state(state, increment_message_counters(state, "text"))
    ctx = _ctx(
        message_type="text",
        battle_state=state,
        bonus_key="CHARGED_DISCHARGE",
        bonus_params={"text_count_required": 5},
    )
    res = handler_charged_discharge(ctx)
    assert not res.battle_state_patch.get("discharge_ready")

    state = merge_battle_state(state, increment_message_counters(state, "text"))
    ctx_ready = _ctx(
        message_type="text",
        battle_state=state,
        bonus_key="CHARGED_DISCHARGE",
        bonus_params={"text_count_required": 5},
    )
    res_ready = handler_charged_discharge(ctx_ready)
    assert res_ready.battle_state_patch.get("discharge_ready") is True


def test_abyss_kill_resets_fight_counters():
    bridge = LegendaryCombatBridge()
    st = initial_battle_state()
    st["total_messages_in_fight"] = 20
    st["consecutive_text_count"] = 8
    st["total_damage_dealt_fight"] = 500
    out = bridge.on_monster_killed(st, 500)
    assert out["total_messages_in_fight"] == 0
    assert out["consecutive_text_count"] == 0
    assert out["monsters_killed_session"] == 1
    assert out["prev_fight_total_damage"] == 500


def test_increment_message_counters_tracks_session_total():
    st = initial_battle_state()
    p1 = increment_message_counters(st, "text")
    assert p1["total_messages_in_fight"] == 1
    assert p1["total_messages_in_session"] == 1
    st2 = merge_battle_state(st, p1)
    st2 = merge_battle_state(st2, reset_fight_level_keys(st2))
    p2 = increment_message_counters(st2, "text")
    assert p2["total_messages_in_fight"] == 1
    assert p2["total_messages_in_session"] == 2


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
