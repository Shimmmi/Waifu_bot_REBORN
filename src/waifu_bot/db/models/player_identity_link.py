"""Multi-platform identity links (Telegram + Steam + future Apple/Google).

Telegram remains authoritative for existing accounts: ``Player.id`` stays the
Telegram user id and nothing about the existing Telegram auth path changes.
This table only maps *additional* external identities (Steam SteamID64, and
later Apple/Google subject ids) onto a single ``Player.id``, so one waifu can
be shared across platforms without duplicating game state.

Steam-native players (no Telegram account yet) get a synthetic negative
``Player.id`` (see ``player_synthetic_id_seq``), which can never collide with
a real Telegram user id (always positive).
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class PlayerIdentityLink(Base):
    """One external-platform identity linked to a Player."""

    __tablename__ = "player_identity_links"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_player_identity_provider_external"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 'telegram' | 'steam' | 'apple' | 'google' | ...
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # SteamID64 / Apple sub / Google sub / Telegram user id (as string)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional display name from the provider (e.g. Steam persona name), for admin/debug UI only.
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
