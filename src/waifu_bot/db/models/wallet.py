"""Player wallet balances and economy ledger."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base

WALLET_CURRENCY_KEYS = (
    "enchant_dust",
    "abyss_shards",
    "refine_core",
    "refine_essence",
    "legendary_ember",
)


class PlayerWalletBalance(Base):
    """Per-player currency row. Gold stays on players.gold."""

    __tablename__ = "player_wallet_balances"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    currency_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_wallet_amount_nonneg"),
        CheckConstraint(
            "currency_key IN ("
            "'enchant_dust','abyss_shards','refine_core','refine_essence','legendary_ember'"
            ")",
            name="ck_wallet_currency_key",
        ),
    )


class EconomyLedger(Base):
    """Append-only currency movement log. Gold uses currency_key='gold'."""

    __tablename__ = "economy_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # in | out
    currency_key: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint("direction IN ('in','out')", name="ck_ledger_direction"),
        CheckConstraint("amount >= 0", name="ck_ledger_amount_nonneg"),
        Index(
            "uq_economy_ledger_idempotent",
            "player_id",
            "source",
            "ref_type",
            "ref_id",
            unique=True,
            postgresql_where=text(
                "source IN ('challenge_first','admin','temper','reforge','refine','respec')"
            ),
        ),
    )


class AdminGrant(Base):
    """One-shot admin grant token for ledger idempotency."""

    __tablename__ = "admin_grants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    currency_key: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )
