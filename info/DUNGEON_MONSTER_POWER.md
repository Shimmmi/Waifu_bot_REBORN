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

## HP и урон (Dungeon+)

Базовая формула в `_roll_monster_from_template`:

`hp = hp_base + hp_per_level * level`,  
`damage = dmg_base + dmg_per_level * level`.

После ролла и power-variance при `plus_level > 0` применяется **развязанное** скалирование
(`waifu_bot.game.dungeon_plus_scaling` → `DungeonService._scale_rolled_stats_for_plus_level`):

| Параметр | Формула |
|----------|---------|
| Якорь DPS | `REF_MSG_DAMAGE = 5000` |
| Целевой TTK (сообщ.) | `ttk_normal(N) = 3.0 + 0.4 × N` |
| Цель HP (обычный моб) | `REF_MSG_DAMAGE × ttk_normal(N)` |
| `hp_mult` | `max(1, hp_target / rolled_hp)` |
| `dmg_mult` | `1.0 + 0.08 × N` (медленнее HP) |
| Extra монстры | `N // 4` к `obstacle_min/max` |
| Награды | `1 + N×0.22 + ln(1+N)×0.15` |

Бюджет сложности рана (`difficulty_rating`) масштабируется на `budget_mult = ttk_normal(N)` (подбор шаблонов / аналитика), не как боевой HP.

### Ожидаемый TTK @5k (обычный моб)

| +N | HP ≈ | TTK @5k | `dmg_mult` |
|----|------|---------|------------|
| +1 | ~17k | ~3.4 | 1.08 |
| +5 | ~25k | ~5 | 1.40 |
| +10 | ~35k | ~7 | 1.80 |
| +20 | ~55k | ~11 | 2.60 |
| +30 | ~75k | ~15 | 3.40 |

Боссы: `boss_hp_mult = 2.5` поверх цели → TTK ≈ `2.5 × ttk_normal`.

**История:** раньше общий `hp_dmg_mult = 1 + N×0.20` умножал и HP, и DMG одинаково; при эндгейм‑уроне ~5k+ монстры one-shot’ились, а retaliation рос вместе с «сложностью».

## Пул шаблонов монстров (Dungeon+)

- **Обычный данж** (`plus_level = 0`): шаблоны из пула акта/тегов данжа (`_get_tag_tier_candidates` или legacy pool).
- **Dungeon+** (`plus_level > 0`, не финальный сюжетный босс): **cross-act пул** — все `monster_templates` с пересечением актов 1–5 (`act_min <= 5 AND act_max >= 1`), с dedupe `template_id` внутри одного забега (`_get_plus_cross_act_candidates`). Если пул исчерпан, допускается повтор с предупреждением в лог.
- **Финальный босс +5…+30**: по-прежнему `StoryBossDefinition` + свой `image_webp_path` (`/static/game/bosses/webp/{slug}.webp`).

Уровень монстров в D+ по-прежнему `50 + (plus_level - 1) * 5` ±2; меняется только разнообразие **шаблонов**, не формула уровня.

Поле `difficulty_hint` по-прежнему влияет только на число `difficulty` в UI/аналитике, не на боевые формулы.

## Данные `monster_templates` (однотипность кривых)

Скрипт `scripts/analyze_monster_templates.py` читает `info/monster_templates_import.sql` и считает распределение без БД.

На текущем сиде: **5** уникальных пар `(hp_base, hp_per_level)` и **5** пар `(dmg_base, dmg_per_level)` — по одному набору на **tier** 1–5; внутри tier все семейства/имена делят одну и ту же кривую. Различия между монстрами — в основном имя, family, теги, tier.

## Решение по плану аудита

| Вариант | Статус |
|--------|--------|
| A — умножать `max_hp` и `damage` на общий `hp_dmg_mult` для D+ | Заменено развязанным HP/DMG + TTK-якорем |
| B — отдельный пул шаблонов для D+ | не делалось (при необходимости отдельно) |
| C — ревизия SQL кривых по family | не делалось; скрипт анализа — основа для дальнейшей балансировки |
| D — TTK-якорь `REF_MSG_DAMAGE=5000`, decoupled `dmg_mult`, extra mobs | **Реализовано** в `dungeon_plus_scaling.py` |
