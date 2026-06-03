"""Add flavor_ru to item_base_templates for library codex.

Revision ID: 0093_item_base_flavor_ru
Revises: 0092_legendary_curated_templates
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0093_item_base_flavor_ru"
down_revision: Union[str, None] = "0092_legendary_curated_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_base_templates",
        sa.Column("flavor_ru", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("item_base_templates", "flavor_ru")
