"""Item display name composition (multi-prefix / multi-suffix)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.game.item_display_name import (
    compose_item_display_name_ru,
    inflect_adj_ru,
    resolve_base_name_ru,
)


def _affix(name: str, kind: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, kind=kind)


def _inv(
    *,
    base: str = "Мантия демонов жизни",
    affixes: list[SimpleNamespace] | None = None,
    is_legendary: bool = False,
    rarity: int = 2,
) -> SimpleNamespace:
    return SimpleNamespace(
        item=SimpleNamespace(name=base),
        slot_type="costume",
        weapon_type=None,
        affixes=affixes or [],
        is_legendary=is_legendary,
        rarity=rarity,
    )


def test_compose_multi_prefix_suffix() -> None:
    inv = _inv(
        affixes=[
            _affix("мощный", "affix"),
            _affix("богатый", "affix"),
            _affix("грубый", "suffix"),
            _affix("демонов", "suffix"),
        ]
    )
    base, display = compose_item_display_name_ru(inv)
    assert base == "Мантия демонов жизни"
    assert display.startswith("мощная богатая ")
    assert "Мантия демонов жизни" in display
    assert display.endswith("грубый демонов")
    parts = display.split()
    assert "мощная" in parts
    assert "богатая" in parts


def test_inflect_prefix_feminine() -> None:
    assert inflect_adj_ru("мощный", "f") == "мощная"


def test_compose_legendary_skips_affix_rollup() -> None:
    inv = _inv(
        base="Бич седьмого легиона",
        affixes=[
            _affix("мощный", "affix"),
            _affix("рубящий", "affix"),
            _affix("стойкости", "suffix"),
        ],
        is_legendary=True,
        rarity=5,
    )
    base, display = compose_item_display_name_ru(inv)
    assert base == "Бич седьмого легиона"
    assert display == "Бич седьмого легиона"
    assert "мощный" not in display.lower()


def test_resolve_base_name_fallback() -> None:
    inv = SimpleNamespace(
        item=SimpleNamespace(name="Предмет"),
        slot_type="ring",
        weapon_type=None,
        affixes=[],
    )
    assert resolve_base_name_ru(inv) == "Кольцо"


def test_admin_spawn_route_uses_composed_name() -> None:
    from waifu_bot.api import admin_routes as ar

    async def _run() -> None:
        session = AsyncMock()
        player = MagicMock()
        player.current_act = 1
        session.get = AsyncMock(return_value=player)

        inv = MagicMock()
        inv.id = 9001
        inv.rarity = 2
        inv.affixes = [
            _affix("мощный", "affix"),
            _affix("богатый", "affix"),
            _affix("грубый", "suffix"),
        ]
        inv.item = SimpleNamespace(name="Мантия демонов жизни")
        inv.slot_type = "costume"
        inv.weapon_type = None

        with patch.object(ar.item_service, "generate_admin_inventory_item", new_callable=AsyncMock) as gen:
            gen.return_value = (inv, 3, 3)
            from waifu_bot.api.schemas import AdminSpawnItemRequest

            body = AdminSpawnItemRequest(base_template_id=10, level=8, rarity=2)
            resp = await ar.admin_spawn_inventory_item(body=body, player_id=99, session=session)

        assert "мощная" in resp.name
        assert "богатая" in resp.name
        assert "Мантия демонов жизни" in resp.name
        assert "грубый" in resp.name

    import asyncio

    asyncio.run(_run())
