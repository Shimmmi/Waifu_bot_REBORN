"""Player mail between guild members.

Revision ID: 0070_player_mail
Revises: 0069_guild_member_contribution
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0070_player_mail"
down_revision: Union[str, None] = "0069_guild_member_contribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("inventory_items", "player_id", existing_type=sa.BigInteger(), nullable=True)

    op.create_table(
        "player_mail",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sender_player_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_player_id", sa.BigInteger(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("gold_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inventory_item_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="unread"),
        sa.Column("recipient_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["sender_player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_mail_recipient_inbox",
        "player_mail",
        ["recipient_player_id", "recipient_deleted", "created_at"],
    )
    op.create_index(
        "ix_player_mail_sender",
        "player_mail",
        ["sender_player_id", "created_at"],
    )

    cfg_rows = [
        ("mail.max_body_length", "500", "Макс. длина текста письма"),
        ("mail.max_gold_per_send", "100000", "Макс. золота в одном письме"),
        ("mail.max_inbox", "50", "Макс. писем во входящих у получателя"),
        ("mail.daily_send_limit", "20", "Макс. отправок в сутки на игрока"),
    ]
    for key, val, desc in cfg_rows:
        op.execute(
            text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(k=key, v=val, d=desc)
        )


def downgrade() -> None:
    op.drop_index("ix_player_mail_sender", table_name="player_mail")
    op.drop_index("ix_player_mail_recipient_inbox", table_name="player_mail")
    op.drop_table("player_mail")
    op.alter_column("inventory_items", "player_id", existing_type=sa.BigInteger(), nullable=False)
    for key in (
        "mail.max_body_length",
        "mail.max_gold_per_send",
        "mail.max_inbox",
        "mail.daily_send_limit",
    ):
        op.execute(text("DELETE FROM game_config WHERE key = :k").bindparams(k=key))
