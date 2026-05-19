"""Story bosses (Dungeon+), player flags, first-kill table, hidden skills.

Revision ID: 0053_story_bosses_narrative
Revises: 0052_passive_affix_ilvl_bands
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
revision: str = "0053_story_bosses_narrative"
down_revision: Union[str, None] = "0052_passive_affix_ilvl_bands"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REGION = {
    1: "Вердгленд",
    2: "Каменный пояс",
    3: "Пепельные степи",
    4: "Мёртвые земли",
    5: "Преддверье Грани",
}

TIER_TITLE = {
    5: "Вестник тумана",
    10: "Караул сломанного колокола",
    15: "Легат пепла",
    20: "Судья без лика",
    25: "Звезда-осколок у Грани",
    30: "Страж последней щели",
}


def upgrade() -> None:
    op.create_table(
        "story_boss_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("act", sa.Integer(), nullable=False),
        sa.Column("plus_tier", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("monster_template_id", sa.Integer(), sa.ForeignKey("monster_templates.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_lore", sa.Text(), nullable=True),
        sa.Column("intro_text", sa.Text(), nullable=True),
        sa.Column("image_webp_path", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_story_boss_slug"),
        sa.UniqueConstraint("act", "plus_tier", name="uq_story_boss_act_plus_tier"),
    )
    op.create_index("ix_story_boss_definitions_act_tier", "story_boss_definitions", ["act", "plus_tier"])

    op.create_table(
        "player_story_boss_first_kill",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "story_boss_definition_id",
            sa.Integer(),
            sa.ForeignKey("story_boss_definitions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("killed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.add_column(
        "dungeon_run_monsters",
        sa.Column("story_boss_definition_id", sa.Integer(), sa.ForeignKey("story_boss_definitions.id"), nullable=True),
    )

    op.add_column(
        "players",
        sa.Column("secret_echo_boss_unlocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "players",
        sa.Column("secret_echo_boss_defeated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("players", "secret_echo_boss_unlocked", server_default=None)
    op.alter_column("players", "secret_echo_boss_defeated", server_default=None)

    conn = op.get_bind()
    tiers = (5, 10, 15, 20, 25, 30)
    for act in range(1, 6):
        for tier in tiers:
            slug = f"act{act}_p{tier}"
            base = TIER_TITLE[tier]
            reg = REGION[act]
            name = f"{base} ({reg})"
            short_lore = (
                f"Проявление эха на +{tier} в {reg}. Имена стёрты империей; осталась лишь угроза."
            )
            intro_text = (
                f"Наблюдатель: холод сжимает затылок — {base.lower()} выходит из глубины «карты шрама»."
            )
            tid = conn.execute(
                text(
                    "SELECT id FROM monster_templates WHERE boss_allowed = true "
                    "AND act_min <= :act AND act_max >= :act ORDER BY id LIMIT 1"
                ),
                {"act": act},
            ).scalar()
            if tid is None:
                tid = conn.execute(text("SELECT id FROM monster_templates WHERE boss_allowed = true ORDER BY id LIMIT 1")).scalar()
            if tid is None:
                continue
            conn.execute(
                text(
                    "INSERT INTO story_boss_definitions "
                    "(act, plus_tier, slug, monster_template_id, name, short_lore, intro_text, image_webp_path) "
                    "VALUES (:act, :tier, :slug, :tid, :name, :sl, :it, :img)"
                ),
                {
                    "act": act,
                    "tier": tier,
                    "slug": slug,
                    "tid": int(tid),
                    "name": name,
                    "sl": short_lore,
                    "it": intro_text,
                    "img": f"/static/game/bosses/webp/{slug}.webp",
                },
            )

    op.execute(
        sa.text(
            """
            INSERT INTO hidden_skill_definitions
            (id, name, icon, category, description, unlock_description, counter_type,
             thresholds, effect_types, effect_values, announce_in_group)
            VALUES
            ('echo_atlas', 'Атлас эха', '🗺', 'Подземелья',
             'Победы над сюжетными боссами Dungeon+.',
             'Победить сюжетных боссов на вехах +5…+30',
             'story_boss_total_kills',
             '[5, 25, 50, 100, 150]'::jsonb,
             '["boss_reward_pct"]'::jsonb,
             '[1, 2, 4, 6, 9]'::jsonb,
             true),
            ('echo_catalog', 'Свидетель осколков', '✦', 'Подземелья',
             'Уникальные сюжетные боссы (по одному на акт×веху).',
             'Победить каждого из 30 эхо-боссов хотя бы раз',
             'story_boss_unique_kills',
             '[6, 12, 18, 24, 30]'::jsonb,
             '["exp_bonus_pct"]'::jsonb,
             '[1, 2, 3, 4, 5]'::jsonb,
             true)
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM hidden_skill_definitions WHERE id IN ('echo_atlas', 'echo_catalog')"))
    op.drop_column("dungeon_run_monsters", "story_boss_definition_id")
    op.drop_table("player_story_boss_first_kill")
    op.drop_table("story_boss_definitions")
    op.drop_column("players", "secret_echo_boss_defeated")
    op.drop_column("players", "secret_echo_boss_unlocked")
