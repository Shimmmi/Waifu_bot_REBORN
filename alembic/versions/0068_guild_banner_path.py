"""Guild hero banner path on guilds table.

Revision ID: 0068_guild_banner_path
Revises: 0067_guild_activity_logs
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0068_guild_banner_path"
down_revision: Union[str, None] = "0067_guild_activity_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guilds", sa.Column("banner_path", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("guilds", "banner_path")
