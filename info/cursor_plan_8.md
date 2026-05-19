# ТЗ для CURSOR: Исправление ошибки dungeon_pool_invalid

---

## Суть проблемы

При входе в первое подземелье 3 акта выбрасывается `dungeon_pool_invalid`.

Причина: система подбора монстров работает в два этапа —
1. Ищет записи в таблице `dungeon_pool` (заранее заготовленные пулы для конкретных данжей)
2. Если пул пуст или не найден — **падает с ошибкой**

Для подземелий 3 акта заранее заготовленный пул не заполнен.
Решение: добавить fallback на тег/тир подбор из `monster_templates`.

---

## Логика подбора по тегам и тиру (уже описана в ТЗ)

Правило из ТЗ (раздел «Система монстров подземелий»):
- Монстр допускается в пул если есть **хотя бы одно пересечение тегов** с локацией
- Тир: слабые = D−1, основные = D, элитные = D+1 (где D = тир подземелья)
- Боссы: тир D+1 с `boss_allowed = true`
- Тег `cursed`: weight × 1.5 для undead и demon семейств

---

## Фикс в `services/dungeon.py`

### Найти функцию сборки пула монстров

Скорее всего называется `build_monster_pool`, `get_dungeon_monsters`,
`_select_monsters` или похожее. Найти место где бросается `dungeon_pool_invalid`.

```python
# БЫЛО (упрощённо):
def build_monster_pool(dungeon_id: int, dungeon_tier: int) -> list:
    pool = db.query(DungeonPool).filter_by(dungeon_id=dungeon_id).all()
    if not pool:
        raise GameError("dungeon_pool_invalid")   # ← ошибка здесь
    return pool
```

### Добавить fallback через _get_tag_tier_candidates

```python
def build_monster_pool(
    dungeon_id: int,
    dungeon_tier: int,          # тир данжа (1-5, соответствует акту)
    dungeon_tags: list[str],    # теги локации: ["cave", "ruins"] и т.д.
    db: Session,
) -> list[MonsterTemplate]:
    """
    Собирает пул монстров для подземелья.
    Приоритет 1: заранее заготовленный пул (dungeon_pool)
    Приоритет 2: динамический подбор по тегам и тиру (fallback)
    """

    # ── Приоритет 1: заготовленный пул ───────────────────────────
    pool_entries = db.query(DungeonPool).filter_by(dungeon_id=dungeon_id).all()
    if pool_entries:
        return [entry.monster_template for entry in pool_entries]

    # ── Приоритет 2: fallback по тегам и тиру ────────────────────
    candidates = _get_tag_tier_candidates(
        dungeon_tags=dungeon_tags,
        dungeon_tier=dungeon_tier,
        db=db,
    )

    if not candidates:
        # Последний resort: если совсем ничего не нашли —
        # взять любых монстров подходящего тира без фильтра тегов
        candidates = _get_tier_only_candidates(dungeon_tier=dungeon_tier, db=db)

    if not candidates:
        raise GameError("dungeon_pool_invalid")   # только если БД пуста

    return candidates


def _get_tag_tier_candidates(
    dungeon_tags: list[str],
    dungeon_tier: int,
    db: Session,
) -> list[MonsterTemplate]:
    """
    Подбирает монстров из monster_templates по правилу:
    - Пересечение тегов с dungeon_tags (хотя бы один общий)
    - Тир: D-1 (слабые), D (основные), D+1 (элитные/боссы)
    - Учитывает act_min/act_max соответствующий тиру
    """
    # Тиры которые допускаются в данж тира D
    allowed_tiers = [
        max(1, dungeon_tier - 1),  # слабые
        dungeon_tier,               # основные
        min(5, dungeon_tier + 1),  # элитные/боссы
    ]

    # Получить все шаблоны подходящего тира
    all_templates = db.query(MonsterTemplate).filter(
        MonsterTemplate.tier.in_(allowed_tiers)
    ).all()

    # Фильтр по пересечению тегов
    dungeon_tag_set = set(dungeon_tags)
    result = []

    for template in all_templates:
        # tags хранится как JSON: ["cave", "ruins", "undead"]
        monster_tags = set(template.tags or [])

        # Тег "cursed" в данже — специальный модификатор веса, не фильтр
        effective_dungeon_tags = dungeon_tag_set - {"cursed"}

        if monster_tags & effective_dungeon_tags:  # есть пересечение
            result.append(template)

    # Применить weight × 1.5 для undead/demon если в данже есть cursed
    if "cursed" in dungeon_tag_set:
        for template in result:
            if template.family in ("undead", "demon"):
                template._weight_override = int(template.weight * 1.5)

    return result


def _get_tier_only_candidates(
    dungeon_tier: int,
    db: Session,
) -> list[MonsterTemplate]:
    """
    Последний resort: монстры любого семейства нужного тира.
    Используется только если тег-фильтрация дала 0 результатов.
    Логирует предупреждение — означает что теги подземелья не покрыты шаблонами.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(
        f"[dungeon pool] Tag filter returned 0 results for tier={dungeon_tier}. "
        f"Falling back to tier-only selection. Check dungeon tags and monster_templates."
    )

    allowed_tiers = [
        max(1, dungeon_tier - 1),
        dungeon_tier,
        min(5, dungeon_tier + 1),
    ]
    return db.query(MonsterTemplate).filter(
        MonsterTemplate.tier.in_(allowed_tiers)
    ).all()
```

---

## Убедиться что dungeon_tags заполнены для 3 акта

Ошибка может возникать не только из-за отсутствия пула, но и из-за того
что у подземелья 3 акта не заданы теги — тогда тег-фильтрация тоже вернёт 0.

Проверить в БД:
```sql
-- Посмотреть теги подземелий 3 акта
SELECT id, name, act, tags, location_type
FROM dungeons
WHERE act = 3
ORDER BY id;
```

Если `tags` пустой или NULL:
```sql
-- Проставить теги исходя из location_type
UPDATE dungeons
SET tags = CASE location_type
    WHEN 'cave'     THEN '["cave"]'
    WHEN 'forest'   THEN '["forest"]'
    WHEN 'ruins'    THEN '["ruins"]'
    WHEN 'crypt'    THEN '["crypt"]'
    WHEN 'fortress' THEN '["fortress"]'
    WHEN 'swamp'    THEN '["swamp"]'
    WHEN 'desert'   THEN '["desert"]'
    WHEN 'volcano'  THEN '["volcano"]'
    WHEN 'abyss'    THEN '["abyss"]'
    ELSE '["ruins"]'  -- fallback
END
WHERE act = 3 AND (tags IS NULL OR tags = '[]' OR tags = '{}');
```

---

## Проверить что monster_templates покрывают тир 3

3 акт соответствует тиру 3 (уровни 18–30). Проверить что в БД есть монстры тира 3:
```sql
SELECT tier, COUNT(*) as cnt, array_agg(DISTINCT family) as families
FROM monster_templates
WHERE tier IN (2, 3, 4)  -- D-1, D, D+1 для акта 3
GROUP BY tier
ORDER BY tier;
```

Если монстров тира 3 нет — нужно запустить импорт `monster_templates.csv`
(файл был сгенерирован ранее, содержит 285 шаблонов тиров 1-5).

---

## Проверить что параметр dungeon_tags передаётся в build_monster_pool

Найти в коде место где вызывается `build_monster_pool` и убедиться
что `dungeon_tags` передаётся:

```python
# НАЙТИ вызов вроде:
pool = build_monster_pool(dungeon_id=dungeon.id, dungeon_tier=dungeon.tier)
#                                                              ^^^^^^^^^^^
# Добавить dungeon_tags:
pool = build_monster_pool(
    dungeon_id=dungeon.id,
    dungeon_tier=dungeon.tier,
    dungeon_tags=dungeon.tags or ["ruins"],  # ← добавить
    db=db,
)
```

Если в модели `Dungeon` нет поля `tags` — добавить:
```sql
ALTER TABLE dungeons ADD COLUMN tags JSONB DEFAULT '[]';
```

---

## Чеклист для Cursor

### Диагностика
- [ ] Найти в `services/dungeon.py` место где бросается `dungeon_pool_invalid`
- [ ] Проверить SQL: `SELECT tags FROM dungeons WHERE act = 3` — есть ли теги?
- [ ] Проверить SQL: `SELECT COUNT(*) FROM monster_templates WHERE tier = 3` — есть ли монстры?

### Backend
- [ ] Добавить `_get_tag_tier_candidates(dungeon_tags, dungeon_tier, db)` — подбор по тегам
- [ ] Добавить `_get_tier_only_candidates(dungeon_tier, db)` — последний resort с логом
- [ ] В `build_monster_pool` добавить fallback: пустой пул → тег-подбор → тир-подбор → ошибка
- [ ] Убедиться что `dungeon_tags` передаётся в вызов `build_monster_pool`

### БД
- [ ] Если `dungeons.tags` NULL для акта 3 — проставить по `location_type`
- [ ] Если монстров тира 3 нет — запустить импорт `monster_templates.csv`
- [ ] После фикса: проверить акты 4 и 5 аналогичным образом (не ждать жалоб)
