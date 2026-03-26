"""Normalize monster template names: `BaseName N` → `BaseName-N`.

Revision ID: 0019_update_monster_templates_names
Revises: 0018_monster_affixes
Create Date: 2026-03-09
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


revision: str = "0019_update_monster_templates_names"
down_revision: str | None = "0018_monster_affixes"
branch_labels: str | None = None
depends_on: str | None = None


def _iter_templates(connection):
    metadata = sa.MetaData()
    metadata.bind = connection
    monster_templates = sa.Table(
        "monster_templates",
        metadata,
        autoload_with=connection,
    )

    select_stmt = sa.select(
        monster_templates.c.id,
        monster_templates.c.name,
    )
    for row in connection.execute(select_stmt):
        yield monster_templates, row


def upgrade() -> None:
    """Convert names like 'Скелет-воин 2' → 'Скелет-воин-2' for all templates."""
    connection = op.get_bind()

    pattern = re.compile(r"^(?P<base>.+?) (?P<variant>[0-9]+)$")

    for monster_templates, row in _iter_templates(connection):
        name = row.name
        match = pattern.match(name)
        if not match:
            continue

        base = match.group("base")
        variant = match.group("variant")
        new_name = f"{base}-{variant}"

        if new_name == name:
            continue

        update_stmt = (
            monster_templates.update()
            .where(monster_templates.c.id == row.id)
            .values(name=new_name)
        )
        connection.execute(update_stmt)


def downgrade() -> None:
    """Revert names like 'Скелет-воин-2' → 'Скелет-воин 2'."""
    connection = op.get_bind()

    pattern = re.compile(r"^(?P<base>.+?)-(?P<variant>[0-9]+)$")

    for monster_templates, row in _iter_templates(connection):
        name = row.name
        match = pattern.match(name)
        if not match:
            continue

        base = match.group("base")
        variant = match.group("variant")
        old_name = f"{base} {variant}"

        if old_name == name:
            continue

        update_stmt = (
            monster_templates.update()
            .where(monster_templates.c.id == row.id)
            .values(name=old_name)
        )
        connection.execute(update_stmt)

