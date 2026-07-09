"""Email/password credentials for desktop interim auth (pre-Steamworks)."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class EmailCredential(Base):
    """Password hash for a player who registered via email on the desktop client."""

    __tablename__ = "email_credentials"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
