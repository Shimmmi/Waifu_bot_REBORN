"""Unit tests for Armory auth and access control."""

import hashlib
import hmac
import time

import jwt
import pytest
from fastapi import HTTPException

from waifu_bot.services import auth as auth_module
from waifu_bot.services.armory_access import armory_access_level, can_view_private
from waifu_bot.services.auth import (
    JWKS_FETCH_HEADERS,
    resolve_jwks_url,
    validate_telegram_id_token,
    validate_telegram_login,
)

FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"


def test_resolve_jwks_url_explicit(monkeypatch):
    monkeypatch.setattr(
        auth_module.settings,
        "telegram_oidc_jwks_url",
        "https://proxy.example/jwks.json",
    )
    monkeypatch.setattr(auth_module.settings, "telegram_api_base_url", "https://worker.dev")
    assert resolve_jwks_url() == "https://proxy.example/jwks.json"


def test_resolve_jwks_url_from_api_base(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "telegram_oidc_jwks_url", None)
    monkeypatch.setattr(
        auth_module.settings,
        "telegram_api_base_url",
        "https://waifu.timurkhazarzhan.workers.dev",
    )
    assert (
        resolve_jwks_url()
        == "https://waifu.timurkhazarzhan.workers.dev/oauth/.well-known/jwks.json"
    )


def test_resolve_jwks_url_default(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "telegram_oidc_jwks_url", None)
    monkeypatch.setattr(auth_module.settings, "telegram_api_base_url", None)
    assert resolve_jwks_url() == "https://oauth.telegram.org/.well-known/jwks.json"


def test_get_jwks_client_uses_custom_headers(monkeypatch):
    captured: dict = {}

    class _FakePyJWKClient:
        def __init__(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs

    monkeypatch.setattr(auth_module, "_jwks_client", None)
    monkeypatch.setattr(auth_module, "_jwks_client_url", None)
    monkeypatch.setattr(auth_module, "PyJWKClient", _FakePyJWKClient)
    monkeypatch.setattr(auth_module.settings, "telegram_oidc_jwks_url", None)
    monkeypatch.setattr(
        auth_module.settings,
        "telegram_api_base_url",
        "https://waifu.timurkhazarzhan.workers.dev",
    )

    auth_module._get_jwks_client()

    assert captured["url"] == "https://waifu.timurkhazarzhan.workers.dev/oauth/.well-known/jwks.json"
    assert captured["kwargs"]["headers"] == JWKS_FETCH_HEADERS
    assert captured["kwargs"]["cache_keys"] is True
    assert captured["kwargs"]["lifespan"] == 600


def _make_login_payload(bot_token: str, user_id: int = 12345, **extra) -> dict:
    auth_date = int(time.time())
    data = {"id": str(user_id), "first_name": "Test", "auth_date": str(auth_date), **extra}
    data_check = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret = hashlib.sha256(bot_token.encode()).digest()
    data["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return data


@pytest.fixture
def mock_telegram_jwks(monkeypatch):
    class _FakeSigningKey:
        key = object()

    class _FakeJwksClient:
        def get_signing_key_from_jwt(self, _token: str):
            return _FakeSigningKey()

    fake = _FakeJwksClient()
    monkeypatch.setattr(auth_module, "_get_jwks_client", lambda: fake)


def test_validate_telegram_id_token_valid(mock_telegram_jwks, monkeypatch):
    def _decode(*_args, **_kwargs):
        return {
            "sub": "98765",
            "id": 98765,
            "aud": 123456,
            "name": "John Doe",
            "preferred_username": "johndoe",
        }

    monkeypatch.setattr(auth_module.jwt, "decode", _decode)
    result = validate_telegram_id_token(FAKE_JWT, "123456")
    assert result["id"] == 98765
    assert result["username"] == "johndoe"
    assert result["first_name"] == "John"
    assert result["last_name"] == "Doe"


def test_validate_telegram_id_token_numeric_aud(mock_telegram_jwks, monkeypatch):
    def _decode(*_args, **_kwargs):
        return {
            "sub": "98765",
            "id": 98765,
            "aud": 7401283035,
            "name": "Test User",
        }

    monkeypatch.setattr(auth_module.jwt, "decode", _decode)
    result = validate_telegram_id_token(FAKE_JWT, "7401283035")
    assert result["id"] == 98765


def test_validate_telegram_id_token_bad_audience(mock_telegram_jwks, monkeypatch):
    def _decode(*_args, **_kwargs):
        return {
            "sub": "98765",
            "id": 98765,
            "aud": 999999,
            "name": "John Doe",
        }

    monkeypatch.setattr(auth_module.jwt, "decode", _decode)
    with pytest.raises(HTTPException) as exc:
        validate_telegram_id_token(FAKE_JWT, "123456")
    assert exc.value.status_code == 401
    assert exc.value.detail == "id_token bad audience"


def test_validate_telegram_id_token_malformed():
    with pytest.raises(HTTPException) as exc:
        validate_telegram_id_token("\x89PNG\r\n\x1a\n", "123456")
    assert exc.value.status_code == 401
    assert exc.value.detail == "id_token malformed"


def test_validate_telegram_id_token_invalid_signature(mock_telegram_jwks, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise jwt.InvalidSignatureError("bad signature")

    monkeypatch.setattr(auth_module.jwt, "decode", _raise)
    with pytest.raises(HTTPException) as exc:
        validate_telegram_id_token(FAKE_JWT, "123456")
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid id_token"


def test_validate_telegram_id_token_expired(mock_telegram_jwks, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise jwt.ExpiredSignatureError("expired")

    monkeypatch.setattr(auth_module.jwt, "decode", _raise)
    with pytest.raises(HTTPException) as exc:
        validate_telegram_id_token(FAKE_JWT, "123456")
    assert "expired" in str(exc.value.detail)


def test_validate_telegram_login_valid():
    token = "123456:ABC-DEF"
    payload = _make_login_payload(token)
    result = validate_telegram_login(payload, token)
    assert result["id"] == 12345


def test_validate_telegram_login_invalid_hash():
    token = "123456:ABC-DEF"
    payload = _make_login_payload(token)
    payload["hash"] = "deadbeef"
    with pytest.raises(HTTPException) as exc:
        validate_telegram_login(payload, token)
    assert exc.value.status_code == 401


def test_validate_telegram_login_expired():
    token = "123456:ABC-DEF"
    old = int(time.time()) - 7200
    payload = {"id": "1", "auth_date": str(old)}
    data_check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload.keys()))
    secret = hashlib.sha256(token.encode()).digest()
    payload["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(HTTPException) as exc:
        validate_telegram_login(payload, token, max_age_sec=3600)
    assert "expired" in str(exc.value.detail)


def test_armory_access_level_matrix():
    assert armory_access_level(None, 100) == "public"
    assert armory_access_level(100, 100) == "owner"
    assert can_view_private(100, 100) is True
    assert can_view_private(None, 100) is False


def test_armory_access_admin():
    from waifu_bot.core.config import settings

    admin_id = settings.admin_ids[0] if settings.admin_ids else 305174198
    assert armory_access_level(admin_id, 999) == "admin"
    assert can_view_private(admin_id, 999) is True


def test_armory_api_field_names():
    """Summary uses viewer_access_level; admin full dump exposes target_is_bot_admin."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    routes_src = (root / "src/waifu_bot/api/armory_routes.py").read_text(encoding="utf-8")
    service_src = (root / "src/waifu_bot/services/armory_service.py").read_text(encoding="utf-8")
    assert '"viewer_access_level": access' in service_src
    assert '"access_level": access' not in service_src
    assert '"target_is_bot_admin": settings.is_admin(tg_id)' in routes_src
