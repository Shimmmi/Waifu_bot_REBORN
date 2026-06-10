"""Activate text_content legendary bonuses after extra_data text pipeline.

Revision ID: 0106_activate_text_content_bonuses
Revises: 0105_legendary_bonus_pool
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0106_activate_text_content_bonuses"
down_revision: Union[str, None] = "0105_legendary_bonus_pool"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEXT_CONTENT_KEYS = (
    "CAPS_FURY",
    "QUESTION_MARK",
    "EXCLAMATION_STORM",
    "EMOJI_SPICE",
    "NUMERIC_CODE",
    "ONE_WORD_VERDICT",
    "PALINDROME_MAGIC",
    "WALL_OF_TEXT",
    "SAME_CHAR_SCREAM",
    "INTERROGATION",
    "CAPS_SIEGE",
    "EMOJI_HEALER",
    "ONE_WORD_EXECUTION",
    "DIGIT_GAMBIT",
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE legendary_bonuses
            SET is_active = TRUE
            WHERE bonus_key = ANY(:keys)
              AND trigger_group = 'text_content'
              AND params->>'handler' = 'text_content'
            """
        ),
        {"keys": list(_TEXT_CONTENT_KEYS)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE legendary_bonuses
            SET is_active = FALSE
            WHERE bonus_key = ANY(:keys)
            """
        ),
        {"keys": list(_TEXT_CONTENT_KEYS)},
    )
