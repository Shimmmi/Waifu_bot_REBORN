"""Reset marathon progress for all players after mapping fix.

Revision ID: 0080_hidden_skill_marathon_reset
Revises: 0079_guild_bank_inventory_item_id
Create Date: 2026-05-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0080_hidden_skill_marathon_reset"
down_revision: Union[str, None] = "0079_guild_bank_inventory_item_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The marathon skill was previously incremented for every dungeon_message/group_message.
    # Reset stored progress so players don't keep wrongly earned levels.
    op.execute(sa.text("DELETE FROM player_hidden_skills WHERE skill_id = 'marathon'"))


def downgrade() -> None:
    # Irreversible data loss by design. Kept as a no-op.
    pass

