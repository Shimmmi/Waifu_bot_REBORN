"""Add slug, has_image, image_updated_at to monster_templates; backfill dungeons.tags by location_type (ТЗ import).

Revision ID: 0030_monster_slug_images
Revises: 0029_dungeon_tags_backfill
Create Date: 2026-03-16

Соответствует info/monster_templates_migration.sql: колонки для шаблонов монстров
и детальный маппинг тегов данжей (temple -> [ruins,crypt], dungeon -> [ruins,cave] и т.д.).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0030_monster_slug_images"
down_revision: Union[str, None] = "0029_dungeon_tags_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- monster_templates: slug, has_image, image_updated_at (идемпотентно, как в migration SQL) ---
    conn.execute(sa.text("ALTER TABLE monster_templates ADD COLUMN IF NOT EXISTS slug VARCHAR(128)"))
    conn.execute(
        sa.text(
            "ALTER TABLE monster_templates ADD COLUMN IF NOT EXISTS has_image BOOLEAN NOT NULL DEFAULT FALSE"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE monster_templates ADD COLUMN IF NOT EXISTS image_updated_at TIMESTAMP"
        )
    )
    conn.execute(
        sa.text("""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'monster_templates_slug_key'
              ) THEN
                ALTER TABLE monster_templates ADD CONSTRAINT monster_templates_slug_key UNIQUE (slug);
              END IF;
            END $$;
        """)
    )

    # --- dungeons: детальный backfill tags из location_type (как в monster_templates_migration.sql) ---
    conn.execute(
        sa.text("""
            UPDATE dungeons
            SET tags = CASE location_type
                WHEN 'cave'       THEN '["cave"]'::jsonb
                WHEN 'forest'     THEN '["forest"]'::jsonb
                WHEN 'ruins'      THEN '["ruins"]'::jsonb
                WHEN 'crypt'      THEN '["crypt"]'::jsonb
                WHEN 'fortress'   THEN '["fortress"]'::jsonb
                WHEN 'swamp'      THEN '["swamp"]'::jsonb
                WHEN 'desert'     THEN '["desert"]'::jsonb
                WHEN 'volcano'    THEN '["volcano"]'::jsonb
                WHEN 'abyss'      THEN '["abyss"]'::jsonb
                WHEN 'sea_depth'  THEN '["sea_depth"]'::jsonb
                WHEN 'sky'        THEN '["sky"]'::jsonb
                WHEN 'tundra'     THEN '["tundra"]'::jsonb
                WHEN 'temple'     THEN '["ruins", "crypt"]'::jsonb
                WHEN 'dungeon'    THEN '["ruins", "cave"]'::jsonb
                ELSE              '["ruins"]'::jsonb
            END
            WHERE tags IS NULL
               OR tags::jsonb = '[]'::jsonb
               OR tags::jsonb = '{}'::jsonb
        """)
    )


def downgrade() -> None:
    op.drop_constraint("monster_templates_slug_key", "monster_templates", type_="unique")
    op.drop_column("monster_templates", "image_updated_at")
    op.drop_column("monster_templates", "has_image")
    op.drop_column("monster_templates", "slug")
