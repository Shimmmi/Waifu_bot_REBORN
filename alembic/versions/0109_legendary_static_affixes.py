"""Add legendary_static_affixes JSONB profile on item_base_templates.

Revision ID: 0109_legendary_static_affixes
Revises: 0107_legendary_template_distribution
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0109_legendary_static_affixes"
down_revision: Union[str, None] = "0107_legendary_template_distribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_base_templates",
        sa.Column(
            "legendary_static_affixes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("item_base_templates", "legendary_static_affixes")
