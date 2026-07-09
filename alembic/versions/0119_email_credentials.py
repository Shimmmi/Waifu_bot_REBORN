"""Desktop interim auth: email_credentials table.

Revision ID: 0119_email_credentials
Revises: 0118_player_identity_links
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0119_email_credentials"
down_revision: Union[str, None] = "0118_player_identity_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_credentials",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
        sa.UniqueConstraint("email", name="uq_email_credentials_email"),
    )
    op.create_index("ix_email_credentials_email", "email_credentials", ["email"])


def downgrade() -> None:
    op.drop_index("ix_email_credentials_email", table_name="email_credentials")
    op.drop_table("email_credentials")
