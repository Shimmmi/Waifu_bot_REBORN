"""Monster power stat_profile, ability templates, run debuffs JSON.

Revision ID: 0064_monster_power_and_abilities
Revises: 0063_dungeon_run_monster_elite_state_split
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0064_monster_power_and_abilities"
down_revision: Union[str, None] = "0063_dungeon_run_monster_elite_state_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monster_ability_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=32), nullable=False, server_default="main_waifu"),
        sa.Column("effect_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monster_ability_templates_slug", "monster_ability_templates", ["slug"], unique=True)

    op.add_column(
        "monster_templates",
        sa.Column("monster_ability_template_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_monster_templates_monster_ability_template_id",
        "monster_templates",
        "monster_ability_templates",
        ["monster_ability_template_id"],
        ["id"],
    )

    op.add_column(
        "dungeon_runs",
        sa.Column("active_waifu_debuffs", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )

    op.add_column(
        "dungeon_run_monsters",
        sa.Column("stat_profile", sa.String(length=16), nullable=True),
    )

    op.execute(
        """
        INSERT INTO monster_ability_templates (slug, name, description, trigger, target, effect_json)
        VALUES
        (
            'viper_poison',
            'Яд укуса',
            'Урон основной вайфу в течение нескольких ваших сообщений подряд.',
            'first_player_hit',
            'main_waifu',
            '{"kind": "dot_poison", "ticks": 5, "damage_per_tick": 8}'::jsonb
        ),
        (
            'static_shock',
            'Статический разряд',
            'Шанс, что ваше сообщение не нанесёт урон по монстру.',
            'first_player_hit',
            'main_waifu',
            '{"kind": "shock", "charges": 5, "skip_chance": 0.12}'::jsonb
        ),
        (
            'spore_weakness',
            'Усыпляющие споры',
            'Ваш урон по монстру снижен на несколько ударов.',
            'first_player_hit',
            'main_waifu',
            '{"kind": "weakness", "hits": 4, "player_dmg_mult": 0.88}'::jsonb
        );
        """
    )

    # asyncpg: one statement per execute (no multiple commands in one prepared statement)
    op.execute(
        """
        UPDATE monster_templates SET monster_ability_template_id = (
            SELECT id FROM monster_ability_templates WHERE slug = 'viper_poison'
        )
        WHERE slug IN ('velikiy_zmey', 'morskoy_zmey')
        """
    )
    op.execute(
        """
        UPDATE monster_templates SET monster_ability_template_id = (
            SELECT id FROM monster_ability_templates WHERE slug = 'static_shock'
        )
        WHERE slug = 'vozdushnyy_zmey'
        """
    )
    op.execute(
        """
        UPDATE monster_templates SET monster_ability_template_id = (
            SELECT id FROM monster_ability_templates WHERE slug = 'spore_weakness'
        )
        WHERE slug = 'boevoy_golem'
        """
    )

    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('monster_ability_templates', 'id'),
            COALESCE((SELECT MAX(id) FROM monster_ability_templates), 1)
        );
        """
    )


def downgrade() -> None:
    op.drop_column("dungeon_run_monsters", "stat_profile")
    op.drop_column("dungeon_runs", "active_waifu_debuffs")
    op.drop_constraint("fk_monster_templates_monster_ability_template_id", "monster_templates", type_="foreignkey")
    op.drop_column("monster_templates", "monster_ability_template_id")
    op.drop_index("ix_monster_ability_templates_slug", table_name="monster_ability_templates")
    op.drop_table("monster_ability_templates")
