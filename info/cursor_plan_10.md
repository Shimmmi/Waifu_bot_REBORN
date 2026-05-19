# ТЗ для CURSOR: Броня и вторичные бонусы аксессуаров (v1.2)

---

## Три задачи

1. **Броня** — применить `armor_base` из `item_base_templates` к расчёту урона ОВ
2. **Аксессуары** — добавить вторичные бонусы (крит/уклонение/HP/опыт/золото)
3. **UI** — показывать новые параметры в карточке предмета

---

## Задача 1: Броня реально снижает урон

### Запустить миграцию
```bash
psql "$DATABASE_URL" -f info/item_secondary_migration.sql
```

### Проблема в backend
`armor_base` есть в БД, но не суммируется при расчёте урона по ОВ.

Найти в `services/dungeon.py` или `services/combat.py`:
```bash
grep -rn "armor\|damage.*waifu\|waifu.*damage\|hp.*reduce\|DMG.*minus" \
  app/ services/ | grep -v ".pyc|test|migration" | head -20
```

### Формула (уже в ТЗ, нужно реализовать):
```
урон_по_ОВ = max(1, DMG_монстра − armor_total) × (1 − ВЫН_снижение%)
```

Где `armor_total` = сумма `armor_base` всех экипированных предметов:
```python
async def get_waifu_armor(waifu_id: int, db: AsyncSession) -> int:
    """Суммирует armor_base всех экипированных предметов."""
    result = await db.execute("""
        SELECT COALESCE(SUM(ibt.armor_base), 0) as total_armor
        FROM waifu_equipment we
        JOIN items i        ON i.id = we.item_id
        JOIN item_base_templates ibt ON ibt.id = i.base_template_id
        WHERE we.waifu_id = :wid
          AND we.item_id IS NOT NULL
    """, {"wid": waifu_id})
    return result.scalar() or 0
```

### Ожидаемые значения брони по тиру
| Тип | Т1 | Т3 | Т5 | Т7 | Т10 |
|-----|----|----|----|----|-----|
| Щит | 4 | 11 | 22 | 38 | 74 |
| Лёгкая | 3 | 10 | 21 | 37 | 73 |
| Средняя | 5 | 16 | 31 | 53 | 100 |
| Тяжёлая | 8 | 24 | 47 | 79 | 147 |
| Мантия | 2 | 7 | 15 | 26 | 51 |

### Проверить что items.base_template_id заполнен
```sql
SELECT i.id, i.name, i.base_template_id, ibt.armor_base
FROM items i
LEFT JOIN item_base_templates ibt ON ibt.id = i.base_template_id
WHERE i.item_type IN ('armor','weapon')
  AND ibt.subtype IN ('offhand','light','medium','heavy','robe')
LIMIT 10;
```
Если `base_template_id` NULL — найти где лут создаётся и добавить привязку.

---

## Задача 2: Вторичные бонусы аксессуаров

### После миграции SQL в БД появятся поля:
- `secondary_bonus_type` — тип бонуса (строка)
- `secondary_bonus_value` — значение (float, десятичная дробь)

### Таблица бонусов по типу аксессуара

| Аксессуар (stat1) | Вторичный бонус | Т1 | Т5 | Т10 |
|---|---|---|---|---|
| Кольцо СИЛ | Снижение урона | +0.3% | +1.5% | +3.0% |
| Кольцо ЛОВ | Шанс крита | +0.5% | +2.5% | +5.0% |
| Амулет ВЫН | Бонус к HP макс | +0.5% | +2.5% | +5.0% |
| Амулет ИНТ | Бонус к опыту | +0.5% | +2.5% | +5.0% |
| Амулет ОБА/УДЧ | Бонус к золоту | +0.5% | +2.5% | +5.0% |

### Применение бонусов в combat/stat calculation

Найти функцию которая считает итоговые статы ОВ:
```bash
grep -rn "crit_chance\|evade_chance\|gold_bonus\|exp_bonus\|hp_max.*calc\|calc.*stats" \
  app/ services/ | grep -v ".pyc|test" | head -20
```

Добавить суммирование вторичных бонусов:
```python
async def get_waifu_secondary_bonuses(waifu_id: int, db: AsyncSession) -> dict:
    """Суммирует все вторичные бонусы от экипированных аксессуаров."""
    result = await db.execute("""
        SELECT ibt.secondary_bonus_type, SUM(ibt.secondary_bonus_value) as total
        FROM waifu_equipment we
        JOIN items i ON i.id = we.item_id
        JOIN item_base_templates ibt ON ibt.id = i.base_template_id
        WHERE we.waifu_id = :wid
          AND we.item_id IS NOT NULL
          AND ibt.secondary_bonus_type IS NOT NULL
        GROUP BY ibt.secondary_bonus_type
    """, {"wid": waifu_id})
    
    bonuses = {
        "crit_chance_pct":  0.0,
        "evade_pct":        0.0,
        "dmg_reduce_pct":   0.0,
        "hp_max_pct":       0.0,
        "exp_bonus_pct":    0.0,
        "gold_bonus_pct":   0.0,
    }
    for row in result.fetchall():
        if row.secondary_bonus_type in bonuses:
            bonuses[row.secondary_bonus_type] += row.total
    return bonuses
```

Применить к расчёту урона:
```python
# В calculate_damage_to_waifu():
sec = await get_waifu_secondary_bonuses(waifu_id, db)

# dmg_reduce_pct суммируется с ВЫН-снижением
total_reduce = vyn_reduce + sec["dmg_reduce_pct"]
damage = max(1, (monster_dmg - armor_total) * (1 - total_reduce))

# Уклонение: шанс уклонения = LOV-based + evade_pct от аксессуаров
total_evade = lov_evade + sec["evade_pct"]

# Крит-шанс ОВ увеличивается
total_crit = base_crit + sec["crit_chance_pct"]

# HP макс: hp_max * (1 + hp_max_pct)
effective_hp_max = base_hp_max * (1 + sec["hp_max_pct"])
```

---

## Задача 3: UI — показывать новые параметры в карточке предмета

### В shop.html / profile.html — модальное окно предмета

Найти место рендера параметров предмета в `app.js`:
```bash
grep -rn "renderItemModal\|itemCard\|item.*modal\|modal.*item\|armor_base\|Урон\|Броня" \
  app.js webapp/ | grep -v ".pyc" | head -20
```

Добавить строки в карточку:

**Для брони и щитов** (если `armor_base > 0`):
```javascript
// Добавить в параметры предмета:
if (item.armor_base > 0) {
    rows.push({label: 'Броня', value: `${item.armor_base}`});
}
```

**Для аксессуаров** (если `secondary_bonus_type`):
```javascript
const SECONDARY_LABELS = {
    crit_chance_pct:  'Шанс крита',
    evade_pct:        'Уклонение',
    dmg_reduce_pct:   'Снижение урона',
    hp_max_pct:       'Бонус HP',
    exp_bonus_pct:    'Бонус к опыту',
    gold_bonus_pct:   'Бонус к золоту',
};
if (item.secondary_bonus_type && item.secondary_bonus_value > 0) {
    const label = SECONDARY_LABELS[item.secondary_bonus_type] || item.secondary_bonus_type;
    const pct   = (item.secondary_bonus_value * 100).toFixed(1);
    rows.push({label, value: `+${pct}%`});
}
```

### Ожидаемый вид карточки после фикса

**Башенный щит (Т6):**
```
Броня           41
Скорость атаки  10 (мин. символов)
Тип оружия      offhand
Бонусы: ВЫН +3
```

**Эгида (Т7):**
```
Броня           53
Скорость атаки  10 (мин. символов)
Тип оружия      offhand
Бонусы: ВЫН +3
```
→ Теперь очевидно что Эгида лучше (53 vs 41 брони)

**Кольцо ловкача (Т2):**
```
Бонусы: ЛОВ +1, ИНТ +1
Шанс крита  +1.0%
```

**Кольцо тени (Т8):**
```
Бонусы: ЛОВ +4, ИНТ +4
Шанс крита  +4.0%
```

---

## Чеклист для Cursor

### БД
- [ ] `psql "$DATABASE_URL" -f info/item_secondary_migration.sql`
- [ ] Проверить: `SELECT name, secondary_bonus_type, secondary_bonus_value FROM item_base_templates WHERE item_type IN ('ring','amulet') LIMIT 10`

### Backend
- [ ] Реализовать `get_waifu_armor(waifu_id, db)` — сумма `armor_base` экипированных предметов
- [ ] Применить `armor_total` в формуле урона по ОВ
- [ ] Реализовать `get_waifu_secondary_bonuses(waifu_id, db)` — суммирование вторичных бонусов
- [ ] Применить `dmg_reduce_pct` к расчёту урона
- [ ] Применить `crit_chance_pct`, `hp_max_pct` к расчёту статов ОВ
- [ ] Применить `exp_bonus_pct`, `gold_bonus_pct` к наградам за подземелье
- [ ] API: возвращать `armor_base`, `secondary_bonus_type`, `secondary_bonus_value` в данных предмета

### Frontend
- [ ] Показывать строку «Броня: N» в карточке предмета (щиты и броня)
- [ ] Показывать вторичный бонус «Шанс крита: +X%» и т.д. в карточке аксессуара
- [ ] В разделе «Показатели» профиля: добавить строку «Броня: N» (суммарно с экипировки)
