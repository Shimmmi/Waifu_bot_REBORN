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
| **СИЛ (strength)** | Урон ближнего боя (`× MELEE_DAMAGE_COEFFICIENT`, сейчас 1.2) | `game/formulas.py::calculate_damage` | `MELEE_DAMAGE_COEFFICIENT` |
|  | “Урон ближ.” во вкладке Info (тот же `calculate_damage` + weapon/flats) | `api/routes.py::_compute_details` | `_damage_bounds("melee", …)` |
| **ЛОВ (agility)** | Урон дальнего боя (`× RANGED_DAMAGE_COEFFICIENT`, сейчас 1.2) | `game/formulas.py::calculate_damage` | `RANGED_DAMAGE_COEFFICIENT` |
|  | Крит шанс в бою | `game/formulas.py::calculate_crit_chance` | `CRIT_CHANCE_AGILITY` |
|  | Уворот в бою | `game/formulas.py::calculate_dodge_chance` | `DODGE_CHANCE_AGILITY` |
|  | “Урон дальн.” во вкладке Info | `api/routes.py::_compute_details` | `_damage_bounds("ranged", …)` |
| **ИНТ (intelligence)** | Урон магией (`× SPELL_DAMAGE_COEFFICIENT`, сейчас 1.2) | `game/formulas.py::calculate_damage` | `SPELL_DAMAGE_COEFFICIENT` |
|  | “Урон маг.” во вкладке Info | `api/routes.py::_compute_details` | `_damage_bounds("magic", …)` |
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
- **Бой / Info (урон)**: `calculate_damage(..., attack_type="melee")` → `base + strength * MELEE_DAMAGE_COEFFICIENT` (1.2) + weapon/flats.  
  См. `formulas.py` и `_compute_details` → `_damage_bounds`.

### ЛОВ (agility)
- **Бой / Info (урон ranged)**: `agility * RANGED_DAMAGE_COEFFICIENT` (1.2)  
- **Бой (крит)**: `agility*0.1% + luck*0.1%` (`CRIT_CHANCE_*`)  
- **Бой (уворот)**: `agility*0.1%` (УДЧ не участвует; cap 40%)  

### ИНТ (intelligence)
- **Бой / Info (урон magic/spell)**: `intelligence * SPELL_DAMAGE_COEFFICIENT` (1.2)  
- **Медиа (не TEXT/LINK)**: доп. `INT_SKILL_DAMAGE_COEFF` (1.2)

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

