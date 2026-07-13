"""Unit tests for tutorial progress service."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from waifu_bot.services.tutorial import (
    INTRO_TUTORIAL_GOLD_REWARD,
    KNOWN_TUTORIAL_STEPS,
    PAPERDOLL_KIT_ID,
    SHOP_KIT_ID,
    SHOP_KIT_MIN_DUST,
    complete_tutorial_step,
    normalize_tutorial_progress,
    provision_tutorial_kit,
    reset_tutorial_progress,
)


def test_normalize_tutorial_progress_empty():
    state = normalize_tutorial_progress(None)
    assert state["version"] == 1
    assert state["completed"] == {}
    assert state["skipped"] is False
    assert state["intro_reward_claimed"] is False
    assert state["shop_kit_claimed"] is False
    assert state["shop_kit_sell_item_id"] is None
    assert state["shop_kit_buy_slot"] is None
    assert state["paperdoll_kit_claimed"] is False


def test_normalize_tutorial_progress_parses_completed():
    raw = {
        "version": 2,
        "completed": {"intro": "2026-05-23T12:00:00+00:00", "bad": 123},
        "skipped": True,
        "intro_reward_claimed": True,
        "shop_kit_claimed": True,
        "shop_kit_sell_item_id": 42,
        "shop_kit_buy_slot": "3",
        "paperdoll_kit_claimed": True,
    }
    state = normalize_tutorial_progress(raw)
    assert state["version"] == 2
    assert state["completed"] == {"intro": "2026-05-23T12:00:00+00:00"}
    assert state["skipped"] is True
    assert state["intro_reward_claimed"] is True
    assert state["shop_kit_claimed"] is True
    assert state["shop_kit_sell_item_id"] == 42
    assert state["shop_kit_buy_slot"] == 3
    assert state["paperdoll_kit_claimed"] is True


def test_known_steps_include_intro_and_sections():
    assert "intro" in KNOWN_TUTORIAL_STEPS
    assert "shop" in KNOWN_TUTORIAL_STEPS
    assert "equip" in KNOWN_TUTORIAL_STEPS
    assert "paperdoll" in KNOWN_TUTORIAL_STEPS
    assert "expeditions" in KNOWN_TUTORIAL_STEPS
    assert INTRO_TUTORIAL_GOLD_REWARD == 500
    assert SHOP_KIT_ID == "shop_loop"
    assert PAPERDOLL_KIT_ID == "paperdoll"
    assert SHOP_KIT_MIN_DUST == 50


def test_provision_unknown_kit_raises():
    session = AsyncMock()

    async def _run():
        try:
            await provision_tutorial_kit(session, 1, "nope")
            raise AssertionError("expected ValueError")
        except ValueError as e:
            assert "unknown_tutorial_kit" in str(e)

    asyncio.run(_run())


def test_provision_shop_kit_idempotent():
    player = SimpleNamespace(
        id=7,
        gold=10,
        enchant_dust=0,
        current_act=1,
        tutorial_progress={},
    )
    session = AsyncMock()
    junk = SimpleNamespace(id=99)

    async def _run():
        with (
            patch(
                "waifu_bot.services.tutorial.get_or_create_player",
                AsyncMock(return_value=player),
            ),
            patch(
                "waifu_bot.services.tutorial._find_cheapest_shop_offer",
                AsyncMock(return_value=(2, 40)),
            ),
            patch(
                "waifu_bot.services.tutorial._create_junk_inventory_item",
                AsyncMock(return_value=junk),
            ),
        ):
            first = await provision_tutorial_kit(session, 7, SHOP_KIT_ID)
            assert first["already_claimed"] is False
            assert first["gold_granted"] > 0
            assert first["dust_granted"] == SHOP_KIT_MIN_DUST
            assert first["sell_item_id"] == 99
            assert first["buy_hint"]["slot"] == 2
            assert player.tutorial_progress["shop_kit_claimed"] is True

            second = await provision_tutorial_kit(session, 7, SHOP_KIT_ID)
            assert second["already_claimed"] is True
            assert second["gold_granted"] == 0
            assert second["dust_granted"] == 0
            assert second["sell_item_id"] == 99

    asyncio.run(_run())


def test_complete_new_steps():
    player = SimpleNamespace(id=3, gold=0, tutorial_progress={})
    session = AsyncMock()

    async def _run():
        with patch(
            "waifu_bot.services.tutorial.get_or_create_player",
            AsyncMock(return_value=player),
        ):
            state, gold = await complete_tutorial_step(session, 3, "equip")
            assert "equip" in state["completed"]
            assert gold is None
            state, gold = await complete_tutorial_step(session, 3, "expeditions")
            assert "expeditions" in state["completed"]
            assert gold is None

    asyncio.run(_run())


def test_reset_preserves_shop_kit_claimed():
    player = SimpleNamespace(
        id=5,
        tutorial_progress={
            "completed": {"intro": "2026-01-01T00:00:00+00:00"},
            "intro_reward_claimed": True,
            "shop_kit_claimed": True,
            "shop_kit_sell_item_id": 11,
            "shop_kit_buy_slot": 1,
            "paperdoll_kit_claimed": True,
        },
    )
    session = AsyncMock()

    async def _run():
        with patch(
            "waifu_bot.services.tutorial.get_or_create_player",
            AsyncMock(return_value=player),
        ):
            reset = await reset_tutorial_progress(session, 5)
            assert reset["completed"] == {}
            assert reset["intro_reward_claimed"] is True
            assert reset["shop_kit_claimed"] is True
            assert reset["shop_kit_sell_item_id"] == 11
            assert reset["paperdoll_kit_claimed"] is True

    asyncio.run(_run())


def test_provision_paperdoll_kit_grants_bonus_when_exhausted():
    player = SimpleNamespace(id=9, tutorial_progress={})
    main = SimpleNamespace(
        paperdoll_image_data="abc",
        paperdoll_bonus_generations=0,
    )
    session = AsyncMock()
    result = SimpleNamespace(scalar_one_or_none=lambda: main)
    session.execute = AsyncMock(return_value=result)

    async def _run():
        with patch(
            "waifu_bot.services.tutorial.get_or_create_player",
            AsyncMock(return_value=player),
        ):
            first = await provision_tutorial_kit(session, 9, PAPERDOLL_KIT_ID)
            assert first["already_claimed"] is False
            assert first["bonus_granted"] == 1
            assert main.paperdoll_bonus_generations == 1
            assert player.tutorial_progress["paperdoll_kit_claimed"] is True

            second = await provision_tutorial_kit(session, 9, PAPERDOLL_KIT_ID)
            assert second["already_claimed"] is True
            assert second["bonus_granted"] == 0

    asyncio.run(_run())


def test_provision_paperdoll_kit_skips_when_first_free_available():
    player = SimpleNamespace(id=10, tutorial_progress={})
    main = SimpleNamespace(
        paperdoll_image_data=None,
        paperdoll_bonus_generations=0,
    )
    session = AsyncMock()
    result = SimpleNamespace(scalar_one_or_none=lambda: main)
    session.execute = AsyncMock(return_value=result)

    async def _run():
        with patch(
            "waifu_bot.services.tutorial.get_or_create_player",
            AsyncMock(return_value=player),
        ):
            out = await provision_tutorial_kit(session, 10, PAPERDOLL_KIT_ID)
            assert out["already_claimed"] is False
            assert out["bonus_granted"] == 0
            assert main.paperdoll_bonus_generations == 0
            assert player.tutorial_progress["paperdoll_kit_claimed"] is True

    asyncio.run(_run())


def test_complete_paperdoll_step():
    player = SimpleNamespace(id=3, gold=0, tutorial_progress={})
    session = AsyncMock()

    async def _run():
        with patch(
            "waifu_bot.services.tutorial.get_or_create_player",
            AsyncMock(return_value=player),
        ):
            state, gold = await complete_tutorial_step(session, 3, "paperdoll")
            assert "paperdoll" in state["completed"]
            assert gold is None

    asyncio.run(_run())
