"""Desktop Electron auth: email/password + Telegram OIDC → X-Desktop-Session JWT."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_redis
from waifu_bot.core.config import settings
from waifu_bot.db import models as m
from waifu_bot.services.armory_rate_limit import rate_limit_by_ip
from waifu_bot.services.armory_session import mark_telegram_login_hash_used
from waifu_bot.services.auth import validate_telegram_id_token
from waifu_bot.services.auth_email import (
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
)
from waifu_bot.services.desktop_session import (
    create_desktop_session_token,
    decode_desktop_session_token,
    resolve_player_id_from_desktop_session,
    revoke_desktop_session_jti,
    store_desktop_session_jti,
)
from waifu_bot.services.player_ban import is_player_banned

TELEGRAM_OIDC_TOKEN_URL = "https://oauth.telegram.org/token"


def _telegram_oidc_token_url() -> str:
    """Prefer Cloudflare Worker proxy when VPS cannot reach oauth.telegram.org."""
    base = (settings.telegram_api_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}/oauth/token"
    return TELEGRAM_OIDC_TOKEN_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/desktop", tags=["auth-desktop"])

EMAIL_PROVIDER = "email"
TELEGRAM_PROVIDER = "telegram"


class EmailAuthBody(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=256)


class TelegramAuthBody(BaseModel):
    id_token: str = Field(min_length=10)


class TelegramCodeAuthBody(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    redirect_uri: str = Field(min_length=8, max_length=2048)
    code_verifier: str = Field(min_length=43, max_length=128)


class DesktopSessionOut(BaseModel):
    access_token: str
    player_id: int
    auth_provider: str
    expires_in_days: int


class DesktopMeOut(BaseModel):
    player_id: int
    auth_provider: Optional[str] = None
    providers: list[str] = Field(default_factory=list)
    email: Optional[str] = None


def _bot_id_from_token() -> str:
    if settings.telegram_oidc_client_id:
        return str(settings.telegram_oidc_client_id).strip()
    token = (settings.bot_token or "").strip()
    if not token or ":" not in token:
        return ""
    return token.split(":", 1)[0].strip()


def _public_origin() -> str:
    return str(settings.public_base_url).rstrip("/")


async def _issue_session(
    redis: Any, player_id: int, *, auth_provider: str
) -> DesktopSessionOut:
    token, jti = create_desktop_session_token(player_id, auth_provider=auth_provider)
    await store_desktop_session_jti(redis, player_id, jti)
    return DesktopSessionOut(
        access_token=token,
        player_id=player_id,
        auth_provider=auth_provider,
        expires_in_days=int(settings.desktop_session_ttl_days),
    )


def _integrity_constraint_name(exc: IntegrityError) -> str:
    orig = getattr(exc, "orig", None)
    # asyncpg exposes constraint_name on the exception; psycopg2 uses .diag.
    for candidate in (
        getattr(orig, "constraint_name", None),
        getattr(getattr(orig, "diag", None), "constraint_name", None),
    ):
        if candidate:
            return str(candidate)
    text_orig = str(orig or exc)
    for marker in (
        "players_pkey",
        "uq_email_credentials_email",
        "email_credentials_pkey",
        "uq_player_identity_provider_external",
        "player_identity_links_pkey",
        "email_credentials_email_key",
    ):
        if marker in text_orig:
            return marker
    # Keep a short fingerprint so UI/logs show the real DB error.
    compact = " ".join(text_orig.split())
    if compact:
        return compact[:120]
    return "unknown"


async def _ensure_synthetic_seq_ahead(session: AsyncSession) -> None:
    """Keep player_synthetic_id_seq below existing negative Player.id values.

    Steam stub / manual inserts can create negative ids without advancing the
    sequence; the next nextval then collides on players_pkey and used to be
    misreported as email_taken.
    """
    min_row = await session.execute(text("SELECT MIN(id) FROM players WHERE id < 0"))
    min_id = min_row.scalar()
    if min_id is None:
        return
    seq_row = await session.execute(
        text("SELECT last_value, is_called FROM player_synthetic_id_seq")
    )
    last_value, is_called = seq_row.one()
    next_candidate = int(last_value) - 1 if is_called else int(last_value)
    # Both negative: next_candidate >= min_id means collision or already used.
    if next_candidate >= int(min_id):
        await session.execute(
            text("SELECT setval('player_synthetic_id_seq', :v, true)"),
            {"v": int(min_id)},
        )
        logger.warning(
            "Synced player_synthetic_id_seq to min_player_id=%s (was next=%s)",
            min_id,
            next_candidate,
        )


async def _ensure_identity_link_seq_ahead(session: AsyncSession) -> None:
    """Repair player_identity_links.id sequence if it lags behind MAX(id)."""
    try:
        await session.execute(
            text(
                """
                SELECT setval(
                    COALESCE(
                        pg_get_serial_sequence('player_identity_links', 'id'),
                        'player_identity_links_id_seq'
                    ),
                    GREATEST(COALESCE((SELECT MAX(id) FROM player_identity_links), 1), 1)
                )
                """
            )
        )
    except Exception:
        logger.exception("Failed to sync player_identity_links id sequence")


async def _allocate_synthetic_player_id(session: AsyncSession) -> int:
    await _ensure_synthetic_seq_ahead(session)
    for _ in range(32):
        row = await session.execute(text("SELECT nextval('player_synthetic_id_seq')"))
        new_id = int(row.scalar_one())
        exists = await session.get(m.Player, new_id)
        if exists is None:
            return new_id
        logger.warning("Synthetic player id %s already taken; advancing sequence", new_id)
    min_row = await session.execute(text("SELECT COALESCE(MIN(id), 0) FROM players WHERE id < 0"))
    fallback = int(min_row.scalar_one()) - 1
    if fallback >= 0:
        fallback = -1
    await session.execute(
        text("SELECT setval('player_synthetic_id_seq', :v, true)"),
        {"v": fallback},
    )
    return fallback


async def _email_identity_taken(session: AsyncSession, email: str) -> bool:
    cred = await session.scalar(
        select(m.EmailCredential).where(m.EmailCredential.email == email)
    )
    if cred is not None:
        return True
    link = await session.scalar(
        select(m.PlayerIdentityLink).where(
            m.PlayerIdentityLink.provider == EMAIL_PROVIDER,
            m.PlayerIdentityLink.external_id == email,
        )
    )
    return link is not None


def _require_telegram_client_id() -> str:
    client_id = _bot_id_from_token()
    if not client_id or not client_id.isdigit() or len(client_id) < 5:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram_bot_not_configured",
        )
    # Dummy staging/dev tokens (e.g. 0000000000:STAGING_...) — Telegram OIDC
    # answers "bot id required". Prefer TELEGRAM_OIDC_CLIENT_ID with the real bot id.
    if client_id in {"123456", "000000", "111111"} or set(client_id) == {"0"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram_bot_not_configured",
        )
    return client_id


@router.get("/login-url")
async def desktop_login_url(client: str | None = None):
    """OIDC config for desktop/steam or mobile Telegram Login popup."""
    client_id = _require_telegram_client_id()
    origin = _public_origin()
    client_key = (client or "").strip().lower()
    if client_key == "mobile":
        suggested = f"{origin}/webapp/mobile/login.html"
        # Steam-oriented DESKTOP_OIDC_REDIRECT_URI must not override mobile page URI.
        override = None
    else:
        suggested = f"{origin}/webapp/steam/login.html"
        override = (settings.desktop_oidc_redirect_uri or "").strip() or None
    payload: dict[str, str] = {
        "client_id": client_id,
        "origin": origin,
        "suggested_redirect_uri": suggested,
    }
    if override:
        payload["redirect_uri_override"] = override
    return payload


@router.post("/register", response_model=DesktopSessionOut)
async def desktop_register(
    request: Request,
    body: EmailAuthBody,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_ip(redis, request, "desktop_register", 10)
    email = normalize_email(body.email)
    password = validate_password(body.password)

    if await _email_identity_taken(session, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_taken")

    await _ensure_identity_link_seq_ahead(session)
    password_hash = hash_password(password)
    username = email.split("@", 1)[0][:255]
    new_id: int | None = None
    last_integrity: IntegrityError | None = None
    last_constraint = "unknown"

    for attempt in range(8):
        if await _email_identity_taken(session, email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_taken")

        new_id = await _allocate_synthetic_player_id(session)
        now = datetime.now(timezone.utc)
        try:
            session.add(m.Player(id=new_id, username=username, first_name="Desktop"))
            await session.flush()

            link_id_row = await session.execute(
                text(
                    """
                    SELECT nextval(
                        COALESCE(
                            pg_get_serial_sequence('player_identity_links', 'id'),
                            'player_identity_links_id_seq'
                        )
                    )
                    """
                )
            )
            link_id = int(link_id_row.scalar_one())

            session.add(
                m.EmailCredential(
                    player_id=new_id,
                    email=email,
                    password_hash=password_hash,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                m.PlayerIdentityLink(
                    id=link_id,
                    player_id=new_id,
                    provider=EMAIL_PROVIDER,
                    external_id=email,
                    display_name=email,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            break
        except IntegrityError as exc:
            last_integrity = exc
            last_constraint = _integrity_constraint_name(exc)
            await session.rollback()
            logger.warning(
                "Desktop email register IntegrityError attempt=%s email=%s player_id=%s constraint=%s orig=%s",
                attempt + 1,
                email,
                new_id,
                last_constraint,
                getattr(exc, "orig", None),
            )
            if await _email_identity_taken(session, email):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="email_taken"
                ) from None
            # Retry id/sequence collisions; other unique failures still retry a few times
            # in case of races, then surface the DB fingerprint.
            await _ensure_identity_link_seq_ahead(session)
            await _ensure_synthetic_seq_ahead(session)
            continue
    else:
        logger.exception(
            "Desktop email register exhausted retries email=%s constraint=%s last=%s",
            email,
            last_constraint,
            last_integrity,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"register_conflict:{last_constraint}",
        ) from None

    assert new_id is not None
    logger.info("Desktop email register player_id=%s email=%s", new_id, email)
    return await _issue_session(redis, new_id, auth_provider=EMAIL_PROVIDER)


@router.post("/login", response_model=DesktopSessionOut)
async def desktop_login(
    request: Request,
    body: EmailAuthBody,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_ip(redis, request, "desktop_login", 10)
    email = normalize_email(body.email)
    password = body.password or ""

    cred = await session.scalar(select(m.EmailCredential).where(m.EmailCredential.email == email))
    if cred is None or not verify_password(password, cred.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if await is_player_banned(session, cred.player_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")

    return await _issue_session(redis, int(cred.player_id), auth_provider=EMAIL_PROVIDER)


def _require_telegram_client_secret() -> str:
    secret = (settings.telegram_oidc_client_secret or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram_oidc_client_secret_not_configured",
        )
    return secret


def _assert_redirect_uri_allowed(redirect_uri: str) -> str:
    """Return redirect_uri without query/hash; must match BotFather + authorize request."""
    uri = (redirect_uri or "").strip().split("#", 1)[0]
    if not uri:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing redirect_uri")
    base = uri.split("?", 1)[0]
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_redirect_uri")
    origin = _public_origin()
    same_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/") == origin
    path = parsed.path or ""
    allowed = (
        path == "/webapp/mobile/login.html"
        or path == "/webapp/steam/login.html"
        or path == "/armory/login"
    )
    if not same_origin or not allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri_not_allowed")
    return base


async def _exchange_telegram_auth_code(
    *, code: str, redirect_uri: str, code_verifier: str, client_id: str, client_secret: str
) -> str:
    try:
        token_url = _telegram_oidc_token_url()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        logger.warning("telegram oidc token exchange timeout url=%s: %s", _telegram_oidc_token_url(), exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="telegram_token_exchange_timeout",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("telegram oidc token exchange failed url=%s: %s", _telegram_oidc_token_url(), exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="telegram_token_exchange_failed"
        ) from exc

    try:
        payload = resp.json()
    except Exception:
        payload = {}
    if resp.status_code >= 400:
        err = payload.get("error") if isinstance(payload, dict) else None
        desc = payload.get("error_description") if isinstance(payload, dict) else None
        detail = str(desc or err or f"telegram_token_http_{resp.status_code}")
        logger.warning("telegram oidc token error: %s", detail)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    id_token = payload.get("id_token") if isinstance(payload, dict) else None
    if not isinstance(id_token, str) or len(id_token) < 10:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing id_token")
    return id_token


async def _complete_telegram_desktop_login(
    *,
    session: AsyncSession,
    redis: Any,
    id_token: str,
    client_id: str,
) -> DesktopSessionOut:
    validated = validate_telegram_id_token(id_token, client_id)
    replay_key = hashlib.sha256(id_token.encode()).hexdigest()
    if await mark_telegram_login_hash_used(redis, f"desktop:{replay_key}"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="login_replay")

    tg_id = int(validated["id"])
    if await is_player_banned(session, tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")

    player = await session.get(m.Player, tg_id)
    if not player:
        player = m.Player(
            id=tg_id,
            username=validated.get("username"),
            first_name=validated.get("first_name"),
            last_name=validated.get("last_name"),
        )
        session.add(player)
    else:
        player.username = validated.get("username") or player.username
        player.first_name = validated.get("first_name") or player.first_name
        player.last_name = validated.get("last_name") or player.last_name

    now = datetime.now(timezone.utc)
    link = await session.scalar(
        select(m.PlayerIdentityLink).where(
            m.PlayerIdentityLink.provider == TELEGRAM_PROVIDER,
            m.PlayerIdentityLink.external_id == str(tg_id),
        )
    )
    if link is None:
        session.add(
            m.PlayerIdentityLink(
                player_id=tg_id,
                provider=TELEGRAM_PROVIDER,
                external_id=str(tg_id),
                display_name=validated.get("username") or validated.get("first_name"),
                created_at=now,
                updated_at=now,
            )
        )

    await session.commit()
    return await _issue_session(redis, tg_id, auth_provider=TELEGRAM_PROVIDER)


@router.post("/telegram", response_model=DesktopSessionOut)
async def desktop_telegram(
    request: Request,
    body: TelegramAuthBody,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_ip(redis, request, "desktop_telegram", 10)
    client_id = _require_telegram_client_id()
    return await _complete_telegram_desktop_login(
        session=session,
        redis=redis,
        id_token=body.id_token,
        client_id=client_id,
    )


@router.post("/telegram/code", response_model=DesktopSessionOut)
async def desktop_telegram_code(
    request: Request,
    body: TelegramCodeAuthBody,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Mobile Capacitor path: authorization_code + PKCE → desktop session."""
    await rate_limit_by_ip(redis, request, "desktop_telegram_code", 10)
    client_id = _require_telegram_client_id()
    client_secret = _require_telegram_client_secret()
    redirect_uri = _assert_redirect_uri_allowed(body.redirect_uri)
    id_token = await _exchange_telegram_auth_code(
        code=body.code.strip(),
        redirect_uri=redirect_uri,
        code_verifier=body.code_verifier.strip(),
        client_id=client_id,
        client_secret=client_secret,
    )
    return await _complete_telegram_desktop_login(
        session=session,
        redis=redis,
        id_token=id_token,
        client_id=client_id,
    )


@router.post("/logout")
async def desktop_logout(
    x_desktop_session: str | None = Header(None, alias="X-Desktop-Session"),
    redis=Depends(get_redis),
):
    if not x_desktop_session:
        return {"ok": True}
    try:
        claims = decode_desktop_session_token(x_desktop_session)
        player_id = int(claims.get("player_id") or claims.get("sub"))
        jti = str(claims.get("jti") or "")
        if jti:
            await revoke_desktop_session_jti(redis, player_id, jti)
    except HTTPException:
        pass
    return {"ok": True}


@router.get("/me", response_model=DesktopMeOut)
async def desktop_me(
    x_desktop_session: str | None = Header(None, alias="X-Desktop-Session"),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    if not x_desktop_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_session")
    player_id = await resolve_player_id_from_desktop_session(redis, x_desktop_session)
    claims = decode_desktop_session_token(x_desktop_session)

    links = (
        await session.scalars(
            select(m.PlayerIdentityLink).where(m.PlayerIdentityLink.player_id == player_id)
        )
    ).all()
    providers = sorted({str(l.provider) for l in links})
    email_cred = await session.get(m.EmailCredential, player_id)
    return DesktopMeOut(
        player_id=player_id,
        auth_provider=claims.get("auth_provider"),
        providers=providers,
        email=email_cred.email if email_cred else None,
    )
