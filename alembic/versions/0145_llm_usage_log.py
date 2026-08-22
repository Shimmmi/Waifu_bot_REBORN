"""Create llm_usage_log for Armory admin LLM spend.

Revision ID: 0145_llm_usage_log
Revises: 0144_companion_cards
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0145_llm_usage_log"
down_revision: Union[str, None] = "0144_companion_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("caller", sa.String(length=80), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="background"),
        sa.Column("trigger", sa.String(length=160), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_log_created_at", "llm_usage_log", ["created_at"])
    op.create_index("ix_llm_usage_log_player_created", "llm_usage_log", ["player_id", "created_at"])
    op.create_index("ix_llm_usage_log_caller_created", "llm_usage_log", ["caller", "created_at"])
    op.create_index("ix_llm_usage_log_modality_created", "llm_usage_log", ["modality", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_log_modality_created", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_log_caller_created", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_log_player_created", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_log_created_at", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")
