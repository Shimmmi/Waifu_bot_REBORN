"""Delve PQ: infinite sharpen + flavor affix columns.

Revision ID: 0148_delve_pq_enchant_uncap
Revises: 0147_delve_pq_layer
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0148_delve_pq_enchant_uncap"
down_revision: Union[str, None] = "0147_delve_pq_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_delve_companion_gear_enchant", "delve_companion_gear", type_="check")
    op.alter_column(
        "delve_companion_gear",
        "name",
        existing_type=sa.String(length=80),
        type_=sa.String(length=160),
        existing_nullable=False,
    )
    op.alter_column(
        "delve_companion_gear",
        "enchant_level",
        existing_type=sa.SmallInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
    )
    op.add_column("delve_companion_gear", sa.Column("prefix_stat", sa.String(length=32), nullable=True))
    op.add_column("delve_companion_gear", sa.Column("prefix_tier", sa.SmallInteger(), nullable=True))
    op.add_column("delve_companion_gear", sa.Column("suffix_family", sa.String(length=40), nullable=True))
    op.add_column("delve_companion_gear", sa.Column("suffix_tier", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "ck_delve_companion_gear_enchant_nonneg",
        "delve_companion_gear",
        "enchant_level >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_delve_companion_gear_enchant_nonneg", "delve_companion_gear", type_="check")
    op.drop_column("delve_companion_gear", "suffix_tier")
    op.drop_column("delve_companion_gear", "suffix_family")
    op.drop_column("delve_companion_gear", "prefix_tier")
    op.drop_column("delve_companion_gear", "prefix_stat")
    op.alter_column(
        "delve_companion_gear",
        "enchant_level",
        existing_type=sa.Integer(),
        type_=sa.SmallInteger(),
        existing_nullable=False,
        existing_server_default="0",
    )
    op.alter_column(
        "delve_companion_gear",
        "name",
        existing_type=sa.String(length=160),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_delve_companion_gear_enchant",
        "delve_companion_gear",
        "enchant_level >= 0 AND enchant_level <= 10",
    )
