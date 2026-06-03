"""Hot-path indexes for group_message_damage and related queries.

Revision ID: 0096_performance_hot_path_indexes
Revises: 0095_bot_group_chats
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0096_performance_hot_path_indexes"
down_revision: Union[str, None] = "0095_bot_group_chats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # get_active_v1_cycle: WHERE chat_id = ? AND status = 'active'
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_gd_cycles_chat_id_status_active
        ON gd_cycles (chat_id, status)
        WHERE status = 'active'
        """
    )
    # process_message_damage / active solo run
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dungeon_progress_player_active
        ON dungeon_progress (player_id)
        WHERE is_active = true
        """
    )
    # has_active_abyss_session
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_abyss_progress_player_session_active
        ON abyss_progress (player_id)
        WHERE session_active = true
        """
    )
    # Stuck-cycle ops queries (status + time)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_gd_cycles_status_created_at
        ON gd_cycles (status, created_at)
        WHERE status IN ('active', 'registration')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_gd_cycles_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_abyss_progress_player_session_active")
    op.execute("DROP INDEX IF EXISTS ix_dungeon_progress_player_active")
    op.execute("DROP INDEX IF EXISTS ix_gd_cycles_chat_id_status_active")
