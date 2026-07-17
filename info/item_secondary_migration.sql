-- ============================================================
-- MIGRATION v1.2: Add secondary_bonus columns + update accessories
-- ============================================================

-- Step 1: Add secondary bonus columns to item_base_templates
ALTER TABLE item_base_templates
  ADD COLUMN IF NOT EXISTS secondary_bonus_type  VARCHAR(32) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS secondary_bonus_value FLOAT       DEFAULT 0.0;

COMMENT ON COLUMN item_base_templates.secondary_bonus_type IS
  'crit_chance_pct | evade_pct | dmg_reduce_pct | hp_max_pct | exp_bonus_pct | gold_bonus_pct';
COMMENT ON COLUMN item_base_templates.secondary_bonus_value IS
  'Value as decimal: 0.005 = +0.5%. Applies on top of stat bonuses.';

-- Step 2: Update accessories with secondary bonuses
-- (Updates existing rows by name — safe to run multiple times)

UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.003 WHERE name='Простое кольцо' AND tier=1;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.006 WHERE name='Железное кольцо' AND tier=2;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.009 WHERE name='Кольцо силы' AND tier=3;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.012 WHERE name='Стальное кольцо' AND tier=4;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.015 WHERE name='Кольцо воина' AND tier=5;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.018 WHERE name='Кольцо чемпиона' AND tier=6;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.021 WHERE name='Кольцо берсерка' AND tier=7;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.024 WHERE name='Кольцо предка' AND tier=8;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.027 WHERE name='Кольцо легенды' AND tier=9;
UPDATE item_base_templates SET secondary_bonus_type='dmg_reduce_pct', secondary_bonus_value=0.03 WHERE name='Кольцо вечности' AND tier=10;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.005 WHERE name='Медное кольцо' AND tier=1;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.01 WHERE name='Кольцо ловкача' AND tier=2;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.015 WHERE name='Кольцо лучника' AND tier=3;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.02 WHERE name='Кольцо охотника' AND tier=4;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.025 WHERE name='Кольцо следопыта' AND tier=5;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.03 WHERE name='Кольцо стрелка' AND tier=6;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.035 WHERE name='Кольцо призрака' AND tier=7;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.04 WHERE name='Кольцо тени' AND tier=8;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.045 WHERE name='Кольцо мастера' AND tier=9;
UPDATE item_base_templates SET secondary_bonus_type='crit_chance_pct', secondary_bonus_value=0.05 WHERE name='Кольцо судьбы' AND tier=10;

-- Amulets: unique per-tier bonuses — see info/amulet_bonus_migration.sql (alembic 0113_amulet_fixed_bonuses)

-- Step 3: Verify armor values (should already be set from initial import)
SELECT name, tier, armor_base, stat1_type, stat1_value
FROM item_base_templates
WHERE subtype IN ('offhand','light','medium','heavy','robe')
ORDER BY subtype, tier;

-- Step 4: Verify secondary bonuses applied
SELECT item_type, subtype, tier, name,
       stat1_type, stat1_value,
       secondary_bonus_type, secondary_bonus_value
FROM item_base_templates
WHERE item_type IN ('ring','amulet')
ORDER BY item_type, stat1_type, tier;