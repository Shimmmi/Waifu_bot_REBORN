"""Unit tests for desktop interim auth (email + session JWT)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from waifu_bot.services import auth_email, desktop_session


def test_normalize_email():
    assert auth_email.normalize_email("  Foo@Bar.COM ") == "foo@bar.com"


def test_normalize_email_invalid():
    with pytest.raises(HTTPException) as exc:
        auth_email.normalize_email("not-an-email")
    assert exc.value.status_code == 400


def test_validate_password_too_short():
    with pytest.raises(HTTPException) as exc:
        auth_email.validate_password("short")
    assert exc.value.detail == "password_too_short"


def test_hash_and_verify_password():
    h = auth_email.hash_password("password123")
    assert auth_email.verify_password("password123", h)
    assert not auth_email.verify_password("wrong", h)


def _patch_desktop_secret(monkeypatch):
    monkeypatch.setattr(desktop_session.settings, "environment", "testing")
    monkeypatch.setattr(desktop_session.settings, "webhook_secret", "whsec")
    monkeypatch.setattr(desktop_session.settings, "armory_session_secret", None)
    monkeypatch.setattr(desktop_session.settings, "desktop_session_secret", "test-desktop-secret-key")


def test_create_and_decode_desktop_session(monkeypatch):
    _patch_desktop_secret(monkeypatch)
    token, jti = desktop_session.create_desktop_session_token(-7, auth_provider="email")
    claims = desktop_session.decode_desktop_session_token(token)
    assert claims["player_id"] == -7
    assert claims["jti"] == jti
    assert claims["auth_provider"] == "email"


def test_resolve_player_id_revoked(monkeypatch):
    _patch_desktop_secret(monkeypatch)
    token, _jti = desktop_session.create_desktop_session_token(-3, auth_provider="email")
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=0)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(desktop_session.resolve_player_id_from_desktop_session(redis, token))
    assert exc.value.status_code == 401
    assert exc.value.detail == "desktop_session_revoked"


def test_resolve_player_id_ok(monkeypatch):
    _patch_desktop_secret(monkeypatch)
    token, _jti = desktop_session.create_desktop_session_token(-3, auth_provider="telegram")
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=1)

    pid = asyncio.run(desktop_session.resolve_player_id_from_desktop_session(redis, token))
    assert pid == -3
