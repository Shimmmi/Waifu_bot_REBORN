"""Unit tests for Steam identity linking/resolution (player_identity_links)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from waifu_bot.api import deps as deps_module
from waifu_bot.services import auth_steam


@pytest.mark.asyncio
async def test_validate_steam_ticket_not_configured(monkeypatch):
    monkeypatch.setattr(auth_steam.settings, "steam_web_api_key", None)
    monkeypatch.setattr(auth_steam.settings, "steam_app_id", None)
    with pytest.raises(HTTPException) as exc_info:
        await auth_steam.validate_steam_ticket("some-ticket")
    assert exc_info.value.status_code == 501


@pytest.mark.asyncio
async def test_validate_steam_ticket_missing_ticket():
    with pytest.raises(HTTPException) as exc_info:
        await auth_steam.validate_steam_ticket("")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_resolve_or_create_player_for_steam_existing_link():
    session = AsyncMock()
    existing_link = MagicMock(player_id=42)
    session.scalar = AsyncMock(return_value=existing_link)

    player_id = await auth_steam.resolve_or_create_player_for_steam(session, "7656119...")

    assert player_id == 42
    session.execute.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_or_create_player_for_steam_creates_new_player():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    nextval_result = MagicMock()
    nextval_result.scalar_one = MagicMock(return_value=-1)
    session.execute = AsyncMock(return_value=nextval_result)
    session.commit = AsyncMock()

    player_id = await auth_steam.resolve_or_create_player_for_steam(session, "7656119...", "Persona")

    assert player_id == -1
    assert session.add.call_count == 2  # Player + PlayerIdentityLink
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_link_steam_identity_idempotent_same_player():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=MagicMock(player_id=10))

    await auth_steam.link_steam_identity_to_player(session, 10, "steamid")

    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_link_steam_identity_conflict_other_player():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=MagicMock(player_id=99))

    with pytest.raises(HTTPException) as exc_info:
        await auth_steam.link_steam_identity_to_player(session, 10, "steamid")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_link_steam_identity_creates_new_link():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.commit = AsyncMock()

    await auth_steam.link_steam_identity_to_player(session, 10, "steamid")

    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_player_id_steam_ticket_dev_only_in_dev_envs(monkeypatch):
    monkeypatch.setattr(deps_module.settings, "environment", "production")
    monkeypatch.setattr(deps_module, "resolve_or_create_player_for_steam", AsyncMock(return_value=-5))
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await deps_module.get_player_id(
            init_data=None,
            init_data_query=None,
            x_player_id=None,
            x_dev_token=None,
            x_steam_ticket=None,
            x_steam_ticket_dev="7656119...",
            session=session,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_player_id_steam_ticket_dev_accepted_in_stage(monkeypatch):
    monkeypatch.setattr(deps_module.settings, "environment", "stage")
    monkeypatch.setattr(deps_module, "resolve_or_create_player_for_steam", AsyncMock(return_value=-5))
    monkeypatch.setattr(deps_module, "is_player_banned", AsyncMock(return_value=False))
    session = AsyncMock()

    player_id = await deps_module.get_player_id(
        init_data=None,
        init_data_query=None,
        x_player_id=None,
        x_dev_token=None,
        x_steam_ticket=None,
        x_steam_ticket_dev="7656119...",
        session=session,
    )
    assert player_id == -5
