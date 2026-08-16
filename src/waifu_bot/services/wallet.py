"""Central wallet + economy ledger. Dual-writes dust/shards mirrors until later."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.db.models.wallet import WALLET_CURRENCY_KEYS

IDEMPOTENT_SOURCES = frozenset(
    {"challenge_first", "admin", "temper", "reforge", "refine", "respec"}
)

MIRROR_PLAYER_KEYS = frozenset({"enchant_dust"})
MIRROR_ABYSS_KEYS = frozenset({"abyss_shards"})


class InsufficientCurrency(Exception):
    def __init__(self, currency_key: str, have: int, need: int):
        self.currency_key = currency_key
        self.have = have
        self.need = need
        super().__init__(f"insufficient {currency_key}: have={have} need={need}")


def _is_unique_violation(exc: BaseException) -> bool:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "pgcode", None)
    if code == "23505":
        return True
    msg = str(exc).lower()
    return "unique" in msg or "duplicate" in msg


async def lock_player(session: AsyncSession, player_id: int) -> m.Player | None:
    return await session.scalar(
        select(m.Player).where(m.Player.id == int(player_id)).with_for_update()
    )


async def get_amount(session: AsyncSession, player_id: int, currency_key: str) -> int:
    row = await session.get(m.PlayerWalletBalance, (int(player_id), str(currency_key)))
    if row is not None:
        return int(row.amount or 0)
    if currency_key == "enchant_dust":
        player = await session.get(m.Player, int(player_id))
        return int(getattr(player, "enchant_dust", 0) or 0) if player else 0
    if currency_key == "abyss_shards":
        prog = await session.scalar(
            select(m.AbyssProgress).where(m.AbyssProgress.player_id == int(player_id))
        )
        return int(getattr(prog, "abyss_shards", 0) or 0) if prog else 0
    return 0


async def wallet_snapshot(session: AsyncSession, player_id: int) -> dict[str, int]:
    out = {k: 0 for k in WALLET_CURRENCY_KEYS}
    rows = (
        await session.execute(
            select(m.PlayerWalletBalance).where(m.PlayerWalletBalance.player_id == int(player_id))
        )
    ).scalars().all()
    for r in rows:
        out[str(r.currency_key)] = int(r.amount or 0)
    if out["enchant_dust"] == 0:
        player = await session.get(m.Player, int(player_id))
        if player:
            out["enchant_dust"] = int(getattr(player, "enchant_dust", 0) or 0)
    if out["abyss_shards"] == 0:
        prog = await session.scalar(
            select(m.AbyssProgress).where(m.AbyssProgress.player_id == int(player_id))
        )
        if prog:
            out["abyss_shards"] = int(getattr(prog, "abyss_shards", 0) or 0)
    return out


async def _ensure_row(session: AsyncSession, player_id: int, currency_key: str) -> m.PlayerWalletBalance:
    row = await session.get(
        m.PlayerWalletBalance, (int(player_id), str(currency_key)), with_for_update=True
    )
    if row is not None:
        return row
    try:
        async with session.begin_nested():
            session.add(
                m.PlayerWalletBalance(
                    player_id=int(player_id), currency_key=str(currency_key), amount=0
                )
            )
            await session.flush()
    except IntegrityError as exc:
        if not _is_unique_violation(exc):
            raise
    row = await session.get(
        m.PlayerWalletBalance, (int(player_id), str(currency_key)), with_for_update=True
    )
    assert row is not None
    return row


async def _mirror(session: AsyncSession, player_id: int, currency_key: str, amount: int) -> None:
    if currency_key == "enchant_dust":
        player = await session.get(m.Player, int(player_id))
        if player is not None:
            player.enchant_dust = int(amount)
    elif currency_key == "abyss_shards":
        prog = await session.scalar(
            select(m.AbyssProgress)
            .where(m.AbyssProgress.player_id == int(player_id))
            .with_for_update()
        )
        if prog is not None:
            prog.abyss_shards = int(amount)


async def _write_ledger(
    session: AsyncSession,
    *,
    player_id: int,
    direction: str,
    currency_key: str,
    amount: int,
    source: str,
    ref_type: str | None,
    ref_id: str | None,
) -> bool:
    """Insert ledger row. Returns False if idempotent unique already exists."""
    if int(amount) <= 0:
        return True
    row = m.EconomyLedger(
        player_id=int(player_id),
        direction=str(direction),
        currency_key=str(currency_key),
        amount=int(amount),
        source=str(source),
        ref_type=ref_type,
        ref_id=None if ref_id is None else str(ref_id),
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
        return True
    except IntegrityError as exc:
        if source in IDEMPOTENT_SOURCES and _is_unique_violation(exc):
            return False
        raise


async def add(
    session: AsyncSession,
    player_id: int,
    currency_key: str,
    amount: int,
    *,
    source: str,
    ref_type: str | None = None,
    ref_id: Any = None,
) -> bool:
    amt = int(amount)
    if amt < 0:
        raise ValueError("amount must be >= 0")
    if amt == 0:
        return True
    if currency_key not in WALLET_CURRENCY_KEYS:
        raise ValueError(f"unknown currency {currency_key}")
    wrote = await _write_ledger(
        session,
        player_id=player_id,
        direction="in",
        currency_key=currency_key,
        amount=amt,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    if not wrote:
        return False
    row = await _ensure_row(session, player_id, currency_key)
    row.amount = int(row.amount or 0) + amt
    await _mirror(session, player_id, currency_key, int(row.amount))
    return True


async def spend(
    session: AsyncSession,
    player_id: int,
    currency_key: str,
    amount: int,
    *,
    source: str,
    ref_type: str | None = None,
    ref_id: Any = None,
) -> bool:
    amt = int(amount)
    if amt < 0:
        raise ValueError("amount must be >= 0")
    if amt == 0:
        return True
    if currency_key not in WALLET_CURRENCY_KEYS:
        raise ValueError(f"unknown currency {currency_key}")
    row = await _ensure_row(session, player_id, currency_key)
    have = int(row.amount or 0)
    if have < amt:
        raise InsufficientCurrency(currency_key, have, amt)
    wrote = await _write_ledger(
        session,
        player_id=player_id,
        direction="out",
        currency_key=currency_key,
        amount=amt,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    if not wrote:
        return False
    row.amount = have - amt
    await _mirror(session, player_id, currency_key, int(row.amount))
    return True


async def add_gold(
    session: AsyncSession,
    player: m.Player,
    amount: int,
    *,
    source: str,
    ref_type: str | None = None,
    ref_id: Any = None,
) -> bool:
    amt = int(amount)
    if amt < 0:
        raise ValueError("amount must be >= 0")
    if amt == 0:
        return True
    wrote = await _write_ledger(
        session,
        player_id=int(player.id),
        direction="in",
        currency_key="gold",
        amount=amt,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    if not wrote:
        return False
    player.gold = int(player.gold or 0) + amt
    return True


async def spend_gold(
    session: AsyncSession,
    player: m.Player,
    amount: int,
    *,
    source: str,
    ref_type: str | None = None,
    ref_id: Any = None,
) -> bool:
    amt = int(amount)
    if amt < 0:
        raise ValueError("amount must be >= 0")
    if amt == 0:
        return True
    have = int(player.gold or 0)
    if have < amt:
        raise InsufficientCurrency("gold", have, amt)
    wrote = await _write_ledger(
        session,
        player_id=int(player.id),
        direction="out",
        currency_key="gold",
        amount=amt,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    if not wrote:
        return False
    player.gold = have - amt
    return True
