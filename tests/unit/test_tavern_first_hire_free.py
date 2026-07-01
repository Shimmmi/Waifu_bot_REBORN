"""Unit tests for first free mercenary hire in tavern."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.tavern import (
    compute_effective_tavern_hire_price,
    is_first_hire_free,
)


@pytest.mark.asyncio
async def test_is_first_hire_free_when_no_history():
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[0, 0])

    assert await is_first_hire_free(session, 42) is True
    assert session.scalar.await_count == 2


@pytest.mark.asyncio
async def test_is_first_hire_free_false_when_has_hired_waifu():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=1)

    assert await is_first_hire_free(session, 42) is False
    assert session.scalar.await_count == 1


@pytest.mark.asyncio
async def test_is_first_hire_free_false_when_used_slot_without_waifu():
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[0, 2])

    assert await is_first_hire_free(session, 42) is False
    assert session.scalar.await_count == 2


@pytest.mark.asyncio
async def test_compute_effective_price_zero_for_first_hire():
    session = AsyncMock()

    with patch(
        "waifu_bot.services.tavern.is_first_hire_free",
        new_callable=AsyncMock,
        return_value=True,
    ):
        price = await compute_effective_tavern_hire_price(session, 42)

    assert price == 0


@pytest.mark.asyncio
async def test_compute_effective_price_uses_normal_formula_after_first_hire():
    session = AsyncMock()

    with patch(
        "waifu_bot.services.tavern.is_first_hire_free",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "waifu_bot.services.tavern.compute_tavern_hire_price",
        new_callable=AsyncMock,
        return_value=7500,
    ) as mock_price:
        price = await compute_effective_tavern_hire_price(session, 42)

    assert price == 7500
    mock_price.assert_awaited_once()
