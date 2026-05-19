# ТЗ для CURSOR: Система заточки предметов (Enchanting)

---

## Суть

Заточка (+1..+10) усиливает предмет через **плоские прибавки**, рассчитанные
один раз при создании предмета. Не проценты от базы — это даёт нулевой
результат на слабых предметах.

**Формулы шага заточки:**
```
enchant_dmg_step = max(1, round((dmg_min + dmg_max) / 2 * 0.15))
enchant_arm_step = max(1, round(armor_base * 0.12))
enchant_sec_step = round(secondary_bonus_value * 0.20, 4)
```

**Итоговые параметры при любом уровне:**
```python
dmg_min_eff  = base_dmg_min  + enchant_dmg_step * enchant_level
dmg_max_eff  = base_dmg_max  + enchant_dmg_step * enchant_level
armor_eff    = armor_base    + enchant_arm_step * enchant_level
secondary_eff = secondary_value + enchant_sec_step * enchant_level
```

---

## Шаг 1: Миграция БД

```sql
-- 1. Добавить поля в items
ALTER TABLE items
  ADD COLUMN IF NOT EXISTS enchant_level    INT     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS enchant_dmg_step INT     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS enchant_arm_step INT     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS enchant_sec_step FLOAT   NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS is_broken        BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Добавить параметры в game_config
INSERT INTO game_config (key, value, description) VALUES
  ('enchant.dmg_ratio',        '0.15',  'Коэффициент шага урона'),
  ('enchant.arm_ratio',        '0.12',  'Коэффициент шага брони'),
  ('enchant.sec_ratio',        '0.20',  'Коэффициент шага вторичного бонуса'),
  ('enchant.safe_max',         '7',     'Макс уровень без риска (+1..+7 = 100%)'),
  ('enchant.chance_8',         '0.70',  'Шанс успеха +7→+8'),
  ('enchant.chance_9',         '0.50',  'Шанс успеха +8→+9'),
  ('enchant.chance_10',        '0.30',  'Шанс успеха +9→+10'),
  ('enchant.stone_drop_chance','0.02',  'Шанс дропа Камня защиты (Чип +8+)'),
  ('enchant.stone_shop_price', '5000',  'Цена Камня защиты в магазине')
ON CONFLICT (key) DO NOTHING;

-- 3. Ретрофитировать существующие items — заполнить шаги для уже выданных предметов
UPDATE items i
SET
  enchant_dmg_step = GREATEST(1, ROUND(
    ((ibt.dmg_min + ibt.dmg_max)::FLOAT / 2) * 0.15
  )),
  enchant_arm_step = GREATEST(1, ROUND(ibt.armor_base * 0.12)),
  enchant_sec_step = ROUND((ibt.secondary_bonus_value * 0.20)::NUMERIC, 4)
FROM item_base_templates ibt
WHERE i.base_template_id = ibt.id
  AND i.enchant_level = 0;
-- Для предметов без armor/dmg шаги останутся 0 — это корректно
```

---

## Шаг 2: Backend — сервис заточки

Создать файл `services/enchanting.py`:

```python
import random
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Item, Player
from app.config import get_game_config
from app.exceptions import GameError

async def calculate_enchant_steps(item: Item) -> dict:
    """Рассчитать шаги заточки для предмета. Вызывается при создании item."""
    cfg = await get_game_config()
    dmg_ratio = float(cfg.get('enchant.dmg_ratio', 0.15))
    arm_ratio  = float(cfg.get('enchant.arm_ratio', 0.12))
    sec_ratio  = float(cfg.get('enchant.sec_ratio', 0.20))

    avg_dmg = (item.base_dmg_min + item.base_dmg_max) / 2
    return {
        'enchant_dmg_step': max(1, round(avg_dmg * dmg_ratio)) if avg_dmg > 0 else 0,
        'enchant_arm_step': max(1, round(item.base_armor * arm_ratio)) if item.base_armor > 0 else 0,
        'enchant_sec_step': round(item.base_secondary_value * sec_ratio, 4) if item.base_secondary_value else 0.0,
    }

async def enchant_item(
    item_id: int,
    player_id: int,
    use_protection_stone: bool,
    db: AsyncSession,
) -> dict:
    """
    Попытка заточки. Возвращает результат:
    {'success': bool, 'new_level': int, 'broken': bool, 'stone_used': bool}
    """
    item = await db.get(Item, item_id)
    if not item or item.owner_id != player_id:
        raise GameError("item_not_found")
    if item.is_broken:
        raise GameError("item_is_broken")
    if item.enchant_level >= 10:
        raise GameError("enchant_max_reached")

    cfg = await get_game_config()
    safe_max   = int(cfg.get('enchant.safe_max', 7))
    chances    = {8: float(cfg.get('enchant.chance_8', 0.70)),
                  9: float(cfg.get('enchant.chance_9', 0.50)),
                  10: float(cfg.get('enchant.chance_10', 0.30))}

    current = item.enchant_level
    target  = current + 1

    # Гарантированная зона
    if current < safe_max:
        item.enchant_level = target
        await db.commit()
        return {'success': True, 'new_level': target, 'broken': False, 'stone_used': False}

    # Рискованная зона
    chance = chances.get(target, 0.30)
    roll   = random.random()

    if roll < chance:
        # Успех
        item.enchant_level = target
        await db.commit()
        return {'success': True, 'new_level': target, 'broken': False, 'stone_used': False}
    else:
        # Неудача
        if use_protection_stone:
            # Камень защиты: откат до +6 вместо поломки
            item.enchant_level = 6
            # TODO: списать камень из инвентаря игрока
            await db.commit()
            return {'success': False, 'new_level': 6, 'broken': False, 'stone_used': True}
        elif target == 10:
            # +9→+10 без камня: поломка
            item.is_broken = True
            item.enchant_level = 0
            await db.commit()
            return {'success': False, 'new_level': 0, 'broken': True, 'stone_used': False}
        else:
            # +7→+8 или +8→+9 без камня: откат
            rollback = 7 if target == 8 else 6
            item.enchant_level = rollback
            await db.commit()
            return {'success': False, 'new_level': rollback, 'broken': False, 'stone_used': False}

def get_effective_params(item: Item) -> dict:
    """Итоговые параметры предмета с учётом заточки. Использовать везде вместо base."""
    e = item.enchant_level if not item.is_broken else 0
    return {
        'dmg_min':   item.base_dmg_min  + item.enchant_dmg_step * e,
        'dmg_max':   item.base_dmg_max  + item.enchant_dmg_step * e,
        'armor':     item.base_armor    + item.enchant_arm_step * e,
        'secondary': (item.base_secondary_value or 0) + item.enchant_sec_step * e,
        'enchant_level': e,
    }
```

---

## Шаг 3: API эндпоинты

```
POST /api/items/{item_id}/enchant
Body: { "use_protection_stone": false }
Response: { "success": true, "new_level": 8, "broken": false, "stone_used": false }

GET  /api/items/{item_id}/enchant-preview
Response: {
  "current_level": 7,
  "target_level": 8,
  "chance": 0.70,          # null если гарантировано
  "is_risky": true,
  "current_params": { "dmg_min": 13, "dmg_max": 15, "armor": 0, "secondary": 0 },
  "target_params":  { "dmg_min": 14, "dmg_max": 16, "armor": 0, "secondary": 0 },
}
```

---

## Шаг 4: Подключить шаги к генерации лута

Найти функцию `generate_loot_item()` в `services/dungeon.py` и добавить расчёт шагов:

```python
# После создания объекта Item из base_template:
from services.enchanting import calculate_enchant_steps

steps = await calculate_enchant_steps(item)
item.enchant_dmg_step = steps['enchant_dmg_step']
item.enchant_arm_step = steps['enchant_arm_step']
item.enchant_sec_step = steps['enchant_sec_step']
# enchant_level остаётся 0 — предмет создаётся незаточенным
```

---

## Шаг 5: Подключить get_effective_params везде где читаются параметры предмета

```bash
# Найти все места где используются base_dmg_min, base_dmg_max, armor_base
grep -rn "base_dmg_min\|base_dmg_max\|armor_base\|secondary_bonus_value" \
  app/ services/ | grep -v "migration\|template\|.pyc" | head -20
```

Заменить прямое чтение на `get_effective_params(item)`:
```python
# БЫЛО:
damage = random.randint(item.base_dmg_min, item.base_dmg_max)
armor  = item.armor_base

# СТАЛО:
from services.enchanting import get_effective_params
eff    = get_effective_params(item)
damage = random.randint(eff['dmg_min'], eff['dmg_max'])
armor  = eff['armor']
```

Критически важные места:
- `services/combat.py` — расчёт урона ОВ по монстру и урона монстра по ОВ
- `services/shop.py` — отображение параметров в магазине
- API-ответы для карточки предмета в инвентаре

---

## Шаг 6: UI — карточка предмета

В `app.js` / `profile.html` при отображении предмета:

```javascript
function renderItemParams(item) {
  const e = item.enchant_level || 0;
  const isBroken = item.is_broken;

  // Заточка в названии
  const enchantSuffix = e > 0 ? ` <span class="enchant-badge">+${e}</span>` : '';
  const brokenBadge   = isBroken ? ' <span class="broken-badge">💔 Сломан</span>' : '';

  // Параметры с показом изменения
  if (e > 0 && !isBroken) {
    const baseDmg = `${item.base_dmg_min}–${item.base_dmg_max}`;
    const effDmg  = `${item.base_dmg_min + item.enchant_dmg_step * e}–${item.base_dmg_max + item.enchant_dmg_step * e}`;
    // Показать: "3–5 → 13–15" со стрелкой
    dmgDisplay = e > 0 ? `${baseDmg} → <b>${effDmg}</b>` : baseDmg;
  }
}

// CSS:
// .enchant-badge { color: #fbbf24; font-weight: 700; font-size: 11px; }
// .broken-badge  { color: #ef4444; font-size: 10px; }
```

---

## Шаг 7: UI — экран заточки (кузнец)

Добавить вкладку «⚒ Заточка» в `shop.html` (рядом с Купить/Продать/Гемба):

```
┌─────────────────────────────────────┐
│  Выберите предмет для заточки       │
│  [Кинжал +7  ▸  tier1, lvl 4]      │
├─────────────────────────────────────┤
│  Текущий уровень:  ●●●●●●●○○○ +7   │
│  Следующий:        +8               │
│                                     │
│  Параметры:                         │
│  Урон:  3–5 → 11–13  (+8 × 1)      │
│  Броня: —                           │
│                                     │
│  ⚠️ Шанс успеха: 70%                │
│  При неудаче: откат до +7           │
│                                     │
│  [🛡 Использовать Камень защиты]    │
│                                     │
│  [      Заточить  🪙 200      ]     │
└─────────────────────────────────────┘
```

Стоимость заточки: `base_price × enchant_level × 0.1` (растёт с уровнем).
Переменная game_config: `enchant.cost_ratio = 0.1`.

---

## Чеклист

### БД
- [ ] `ALTER TABLE items ADD COLUMN enchant_level, enchant_dmg_step, enchant_arm_step, enchant_sec_step, is_broken`
- [ ] INSERT в game_config все переменные enchant.*
- [ ] UPDATE items — заполнить шаги для существующих предметов

### Backend
- [ ] Создать `services/enchanting.py` с функциями: `calculate_enchant_steps`, `enchant_item`, `get_effective_params`
- [ ] `POST /api/items/{id}/enchant` — попытка заточки
- [ ] `GET /api/items/{id}/enchant-preview` — превью параметров
- [ ] В `generate_loot_item()` — заполнять enchant_*_step при создании
- [ ] В `combat.py` — заменить прямое чтение параметров на `get_effective_params()`
- [ ] В `shop.py` — аналогично

### Frontend
- [ ] Суффикс `+N` в названии предмета (золотой цвет)
- [ ] Бейдж `💔 Сломан` для broken предметов
- [ ] Стрелка «было → стало» в карточке при enchant_level > 0
- [ ] Вкладка «⚒ Заточка» в shop.html
- [ ] Слот Камня защиты (показывать при target >= 8)
- [ ] Анимация результата (успех/неудача/поломка)
