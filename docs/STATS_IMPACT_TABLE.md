# Таблица влияния характеристик (СИЛ/ЛОВ/ИНТ/ВЫН/ОБА/УДЧ) на параметры (по текущему коду)

## Важно (чтобы не было путаницы)

- **Есть 2 набора “формул” в проекте**:
  1) **Боевые формулы** в `src/waifu_bot/game/formulas.py` (используются в бою/уроне/критах/увороте/ценах).
  2) **UI-агрегация “Info”** в `src/waifu_bot/api/routes.py::_compute_details` (то, что вы видите во вкладке “Info” профиля — melee/ranged/magic damage, crit chance, defense, merchant discount, hp_max).

Эти наборы **не полностью совпадают** (например, crit chance считается по-разному: в бою и в “Info”).

---

## Сводная таблица

| Характеристика | На что влияет | Где считается | Ключ/параметр |
|---|---|---|---|
| **СИЛ (strength)** | Урон ближнего боя в бою (масштабирование) | `game/formulas.py::calculate_damage` | `MELEE_DAMAGE_COEFFICIENT` |
|  | “Урон ближ.” во вкладке Info (простой “(strength-10)+…”) | `api/routes.py::_compute_details` | `base_melee_damage = max(0, strength-10)` |
| **ЛОВ (agility)** | Урон дальнего боя в бою (масштабирование) | `game/formulas.py::calculate_damage` | `RANGED_DAMAGE_COEFFICIENT` |
|  | Крит шанс в бою | `game/formulas.py::calculate_crit_chance` | `CRIT_CHANCE_AGILITY` |
|  | Уворот в бою | `game/formulas.py::calculate_dodge_chance` | `DODGE_CHANCE_AGILITY` |
|  | “Урон дальн.” во вкладке Info | `api/routes.py::_compute_details` | `base_ranged_damage = max(0, agility-10)` |
|  | “Шанс крита” во вкладке Info (другая формула!) | `api/routes.py::_compute_details` | `5 + (agility-10)*0.5 + (luck-10)*0.25` |
| **ИНТ (intelligence)** | Урон магией в бою (масштабирование) | `game/formulas.py::calculate_damage` | `SPELL_DAMAGE_COEFFICIENT` |
|  | “Урон маг.” во вкладке Info | `api/routes.py::_compute_details` | `base_magic_damage = max(0, intelligence-10)` |
| **ВЫН (endurance)** | Максимальное HP | `game/formulas.py::calculate_max_hp` | `BASE_HP_PER_LEVEL`, `HP_K_COEFFICIENT` |
|  | Защита во вкладке Info | `api/routes.py::_compute_details` | `base_defense = max(0, endurance-10)` |
|  | **Реген HP** | `services/energy.py::apply_regen` | **5 HP/мин + max(0, ВЫН-10) HP/мин** |
| **ОБА (charm)** | Скидка у торговцев во вкладке Info | `api/routes.py::_compute_details` | `merchant_discount = clamp((charm-10)*1%, 0..50%) + item bonuses` |
|  | Цена покупки в магазине | `game/formulas.py::calculate_shop_price` | **base * (1 - discount%)** |
|  | Цена продажи (инвентарь → золото) | `game/formulas.py::calculate_shop_price` | `0.5..0.9` по той же скидке |
| **УДЧ (luck)** | Крит шанс в бою | `game/formulas.py::calculate_crit_chance` | `CRIT_CHANCE_LUCK` |
|  | Уворот в бою | `game/formulas.py::calculate_dodge_chance` | `DODGE_CHANCE_LUCK` |
|  | “Шанс крита” во вкладке Info (вносит вклад) | `api/routes.py::_compute_details` | `+ (luck-10)*0.25` |

---

## Детали по каждому стату (ссылки)

### СИЛ (strength)
- **Бой (урон)**: `calculate_damage` выбирает `strength * MELEE_DAMAGE_COEFFICIENT` при `attack_type == "melee"`  
  См. `src/waifu_bot/game/formulas.py` (`calculate_damage`).
- **UI Info (урон ближ.)**: `base_melee_damage = max(0, strength - 10)` + плоские бонусы экипировки  
  См. `src/waifu_bot/api/routes.py` (`_compute_details`, строки вокруг `base_melee_damage` и `melee_damage`).

### ЛОВ (agility)
- **Бой (урон ranged)**: `agility * RANGED_DAMAGE_COEFFICIENT`  
  `src/waifu_bot/game/formulas.py::calculate_damage`
- **Бой (крит)**: `agility*0.4% + luck*0.2%`  
  `src/waifu_bot/game/formulas.py::calculate_crit_chance`
- **Бой (уворот)**: `agility*0.2% + luck*0.1%`  
  `src/waifu_bot/game/formulas.py::calculate_dodge_chance`
- **UI Info**: отдельная формула crit chance (не из `game/formulas.py`)  
  `src/waifu_bot/api/routes.py::_compute_details`

### ИНТ (intelligence)
- **Бой (урон magic/spell)**: `intelligence * SPELL_DAMAGE_COEFFICIENT`  
  `src/waifu_bot/game/formulas.py::calculate_damage`
- **UI Info (урон маг.)**: `max(0, intelligence-10)` + плоские бонусы  
  `src/waifu_bot/api/routes.py::_compute_details`

### ВЫН (endurance)
- **Макс HP**: `BASE_HP_PER_LEVEL*level + endurance*HP_K_COEFFICIENT`  
  `src/waifu_bot/game/formulas.py::calculate_max_hp`
- **UI Info (защита)**: `max(0, endurance-10)` + бонусы  
  `src/waifu_bot/api/routes.py::_compute_details`
- **Реген HP**: `5 HP/мин + max(0, ВЫН-10) HP/мин`  
  `src/waifu_bot/services/energy.py::apply_regen`

### ОБА (charm)
- **Скидка (Info)**: `base_merchant_discount = clamp((charm-10)*1%, 0..50%)` + экипировка  
  `src/waifu_bot/api/routes.py::_compute_details`
- **Цена в магазине**: должна соответствовать этой скидке  
  `src/waifu_bot/game/formulas.py::calculate_shop_price`  
  `src/waifu_bot/api/routes.py::get_shop_inventory` (передаёт effective charm)

### УДЧ (luck)
- **Крит/уворот в бою**: см. `calculate_crit_chance`, `calculate_dodge_chance`  
  `src/waifu_bot/game/formulas.py`
- **UI Info**: участвует в “Шанс крита” через `(luck-10)*0.25`  
  `src/waifu_bot/api/routes.py::_compute_details`

---

## Примечания по экипировке и аффиксам

- Экипировка влияет на базовые характеристики через `calculate_item_bonuses` и суммирование по надетым предметам.  
  См. `src/waifu_bot/api/routes.py::calculate_item_bonuses` и `::get_profile`/`::_compute_details`.
- В магазине для корректной цены важно использовать **effective charm** (base + bonuses), а не `waifu.charm` из БД.

