-- Migration: add missing columns to monster_templates
-- Run this BEFORE the import SQL if columns don't exist

-- Add tier (1-5)
ALTER TABLE monster_templates
  ADD COLUMN IF NOT EXISTS tier INT NOT NULL DEFAULT 1;

-- Add slug (URL-safe unique identifier for image filenames)
ALTER TABLE monster_templates
  ADD COLUMN IF NOT EXISTS slug VARCHAR(128);

-- Add image flags
ALTER TABLE monster_templates
  ADD COLUMN IF NOT EXISTS has_image BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE monster_templates
  ADD COLUMN IF NOT EXISTS image_updated_at TIMESTAMP;

-- Add unique constraint on slug
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'monster_templates_slug_key'
  ) THEN
    ALTER TABLE monster_templates ADD CONSTRAINT monster_templates_slug_key UNIQUE (slug);
  END IF;
END $$;

-- Update dungeons table: ensure tags column exists
ALTER TABLE dungeons
  ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb;

-- Auto-populate dungeon tags from location_type if empty
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
WHERE tags IS NULL OR tags::text IN ('[]', '{}', 'null');

-- Verify
SELECT act, COUNT(*) as dungeon_count,
       SUM(CASE WHEN tags IS NULL OR tags::text IN ('[]', '{}', 'null') THEN 1 ELSE 0 END) as empty_tags
FROM dungeons
GROUP BY act ORDER BY act;
