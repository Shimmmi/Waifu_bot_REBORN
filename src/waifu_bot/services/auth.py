"""Telegram WebApp initData validation."""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_OIDC_ISSUER = "https://oauth.telegram.org"
TELEGRAM_JWKS_URL = "https://oauth.telegram.org/.well-known/jwks.json"
TELEGRAM_ID_TOKEN_LEEWAY_SEC = 30
JWKS_FETCH_HEADERS = {
    "User-Agent": "waifu-bot-armory/1.0 (Telegram OIDC JWKS)",
    "Accept": "application/json",
}

_jwks_client: PyJWKClient | None = None
_jwks_client_url: str | None = None


def resolve_jwks_url() -> str:
    """JWKS endpoint for Telegram OIDC id_token verification."""
    custom = (settings.telegram_oidc_jwks_url or "").strip()
    if custom:
        return custom
    base = (settings.telegram_api_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}/oauth/.well-known/jwks.json"
    return TELEGRAM_JWKS_URL


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_client_url
    url = resolve_jwks_url()
    if _jwks_client is None or _jwks_client_url != url:
        _jwks_client = PyJWKClient(
            url,
            cache_keys=True,
            lifespan=600,
            headers=JWKS_FETCH_HEADERS,
        )
        _jwks_client_url = url
        logger.info("Telegram JWKS client configured: %s", url)
    return _jwks_client


def _audience_matches(claims: dict, client_id: str) -> bool:
    aud = claims.get("aud")
    if aud is None:
        return False
    allowed = {str(client_id)}
    if isinstance(aud, list):
        return any(str(value) in allowed for value in aud)
    return str(aud) in allowed


def _compute_hash(data_check_string: str, bot_token: str) -> str:
    """Compute HMAC-SHA256 of data_check_string."""
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(init_data: str, bot_token: str, max_age_sec: int = 24 * 3600) -> dict:
    """
    Validate Telegram WebApp initData.

    Steps:
    - parse key=value pairs
    - build data_check_string sorted by key excluding 'hash'
    - compute HMAC-SHA256 with secret key = HMAC("WebAppData", bot_token)
    - compare with provided hash
    - check auth_date not older than max_age_sec
    """
    # Parse init data
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="hash missing in init data")

    # Build data_check_string
    data_check_items = [f"{k}={v}" for k, v in sorted(parsed.items())]
    data_check_string = "\n".join(data_check_items)

    # Compute expected hash
    expected_hash = _compute_hash(data_check_string, bot_token)
    if not hmac.compare_digest(provided_hash, expected_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid init data hash")

    # Check auth_date
    auth_date = int(parsed.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > max_age_sec:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="init data expired")

    # Decode user json if present
    if "user" in parsed:
        try:
            parsed["user"] = json.loads(parsed["user"])
        except json.JSONDecodeError:
            pass

    return parsed


def validate_telegram_login(data: dict, bot_token: str, max_age_sec: int = 3600) -> dict:
    """
    Validate Telegram Login Widget callback data.

    Algorithm (https://core.telegram.org/widgets/login#checking-authorization):
    - secret_key = SHA256(bot_token)
    - data_check_string = sorted key=value pairs joined by newline (excluding hash)
    - HMAC-SHA256(data_check_string, secret_key) == hash
    """
    if not data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="empty login data")

    payload = {k: str(v) for k, v in data.items() if v is not None}
    provided_hash = payload.pop("hash", None)
    if not provided_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="hash missing in login data")

    data_check_items = [f"{k}={payload[k]}" for k in sorted(payload.keys())]
    data_check_string = "\n".join(data_check_items)

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_hash, expected_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid login hash")

    auth_date = int(payload.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > max_age_sec:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login data expired")

    result = dict(payload)
    if "id" in result:
        result["id"] = int(result["id"])
    if "auth_date" in result:
        result["auth_date"] = int(result["auth_date"])
    return result


def validate_telegram_id_token(id_token: str, client_id: str) -> dict:
    """
    Validate Telegram OIDC id_token from telegram-login.js popup.

    https://core.telegram.org/bots/telegram-login
    """
    token = (id_token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="id_token missing")

    if token.count(".") != 2 or not token.startswith("eyJ"):
        logger.warning(
            "Telegram id_token malformed: len=%s prefix=%r",
            len(token),
            token[:12],
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="id_token malformed")

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "EdDSA", "ES256K"],
            issuer=TELEGRAM_OIDC_ISSUER,
            leeway=TELEGRAM_ID_TOKEN_LEEWAY_SEC,
            options={"verify_aud": False, "require": ["iss", "exp", "iat", "sub"]},
        )
    except PyJWKClientConnectionError as e:
        global _jwks_client, _jwks_client_url
        _jwks_client = None
        _jwks_client_url = None
        logger.warning(
            "Telegram JWKS fetch failed from %s: %s",
            resolve_jwks_url(),
            e,
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="jwks unavailable") from e
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="id_token expired") from e
    except jwt.InvalidTokenError as e:
        logger.warning("Telegram id_token invalid: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid id_token") from e

    if not _audience_matches(claims, client_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="id_token bad audience")

    user_id = claims.get("id")
    if user_id is None:
        user_id = claims.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="id_token missing user id")

    name = str(claims.get("name") or "").strip()
    first_name: str | None = name or None
    last_name: str | None = None
    if " " in name:
        parts = name.split(" ", 1)
        first_name = parts[0] or None
        last_name = parts[1] or None

    return {
        "id": int(user_id),
        "username": claims.get("preferred_username"),
        "first_name": first_name,
        "last_name": last_name,
    }

