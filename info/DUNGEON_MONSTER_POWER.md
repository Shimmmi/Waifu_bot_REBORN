# Сила монстров: обычные данжи vs Dungeon+

## Уровень монстра (`DungeonRunMonster.level`)

- **Обычный режим** (`plus_level = 0`): `base_lvl = dungeon.level`, затем `+0..2` (RNG), clamp к `level_min` / `level_max` шаблона.
- **Dungeon+** (`plus_level > 0`): `base_lvl = 50 + (plus_level - 1) * 5`, `+0..2`, для D+ верх шаблона `level_max` не ограничивает уровень.

### `dungeon.level` (сид Alembic `0007_seed_base_dungeons`)

Формула: `level = (act - 1) * 10 + (dungeon_number - 1) * 2 + 1`.

Примеры:

| Данж   | `dungeon.level` (база) | Уровень монстра (пример, +0..2) |
|--------|--------------------------|----------------------------------|
| акт 1 #1 | 1                        | 1–3                              |
| акт 5 #1 | 41                       | 41–43                            |

Отсюда обычный данж 5-1 даёт монстров **~40+** уровня при том же распределении шаблонов, что и низкоуровневые данжи, но с **более высоким** `dungeon.level`.

## HP и урон (до правок и после)

Базовая формула в `_roll_monster_from_template`:

`hp = hp_base + hp_per_level * level`,  
`damage = dmg_base + dmg_per_level * level`.

**Раньше:** множитель `_difficulty_params(plus_level)["hp_dmg_mult"]` = `1.0 + plus_level * 0.20` использовался **только** для увеличения **бюджета** сложности (`budget`) при выборе шаблона из пула. На итоговые `max_hp` и `damage` он **не** умножался — из-за этого Dungeon+ мог ощущаться слабее сильного обычного данжа высокого акта (сильный шаблон tier + элита).

**Сейчас:** при `plus_level > 0` после `_roll_monster_from_template` те же `max_hp` и `damage` дополнительно умножаются на `hp_dmg_mult` (см. `DungeonService._scale_rolled_stats_for_plus_level` в `dungeon.py`).

Поле `difficulty_hint` по-прежнему влияет только на число `difficulty` в UI/аналитике, не на боевые формулы.

## Данные `monster_templates` (однотипность кривых)

Скрипт `scripts/analyze_monster_templates.py` читает `info/monster_templates_import.sql` и считает распределение без БД.

На текущем сиде: **5** уникальных пар `(hp_base, hp_per_level)` и **5** пар `(dmg_base, dmg_per_level)` — по одному набору на **tier** 1–5; внутри tier все семейства/имена делят одну и ту же кривую. Различия между монстрами — в основном имя, family, теги, tier.

## Решение по плану аудита

| Вариант | Статус |
|--------|--------|
| A — умножать `max_hp` и `damage` на `hp_dmg_mult` для D+ | **Реализовано** в коде |
| B — отдельный пул шаблонов для D+ | не делалось (при необходимости отдельно) |
| C — ревизия SQL кривых по family | не делалось; скрипт анализа — основа для дальнейшей балансировки |
