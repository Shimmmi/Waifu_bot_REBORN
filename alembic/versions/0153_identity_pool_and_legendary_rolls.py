"""Placeholder matching DBs already stamped from the delve branch.

Revision ID: 0153_identity_pool_and_legendary_rolls
Revises: 0152_companion_memory

The full identity-pool / legendary-rolls migration lives on `delve`.
This no-op keeps design's Alembic graph aligned with that stamp so later
revisions (0154+) can upgrade without importing delve-only modules.
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "0153_identity_pool_and_legendary_rolls"
down_revision: Union[str, None] = "0152_companion_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
