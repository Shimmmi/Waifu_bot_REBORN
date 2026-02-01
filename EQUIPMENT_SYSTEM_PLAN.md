# План реализации системы экипировки

## Анализ текущего состояния

### Что уже есть:
1. **API endpoints:**
   - `GET /waifu/equipment` - получение экипированных предметов и инвентаря
   - `POST /waifu/equipment/equip?inventory_item_id=X&slot=Y` - экипировка предмета
   - `POST /waifu/equipment/unequip?inventory_item_id=X` - снятие предмета
   - `GET /inventory` - получение инвентаря игрока

2. **Модели данных:**
   - `InventoryItem` с полем `equipment_slot` (1-6)
   - `ItemTemplate` с полем `slot_type` (weapon_1h, weapon_2h, costume, ring, amulet)
   - `InventoryAffix` для аффиксов/суффиксов предметов
   - `requirements` в JSON формате (level, strength, agility, etc.)

3. **Фронтенд:**
   - `renderProfileGear()` - отображение слотов экипировки (но без обработки кликов)
   - `loadProfileInventory()` - загрузка инвентаря (но без обработки кликов)
   - Модальные окна для магазина (можно переиспользовать структуру)

### Проблемы:
1. **Нет связи slot_type -> equipment_slot:**
   - `ItemTemplate.slot_type` не сохраняется в `InventoryItem`
   - Нет функции определения, в какие слоты можно экипировать предмет
   - Маппинг: `weapon_1h` -> [1, 2], `weapon_2h` -> [1, 2], `costume` -> [3], `ring` -> [4, 5], `amulet` -> [6]

2. **Неполная проверка требований:**
   - Сейчас проверяется только `level`
   - Нужно проверять: `strength`, `agility`, `intelligence`, `endurance`

3. **Бонусы от экипировки не учитываются:**
   - `_compute_details()` не учитывает бонусы от предметов
   - Нужно суммировать бонусы от всех экипированных предметов и их аффиксов

4. **Нет UI для экипировки:**
   - Слоты не кликабельны
   - Предметы в инвентаре не кликабельны
   - Нет модальных окон для выбора/просмотра предметов

## План реализации

### Этап 1: Бэкенд - Определение слотов и проверка требований

#### 1.1. Добавить поле `slot_type` в `InventoryItem` (или определить через ItemTemplate)
**Вариант A:** Добавить поле `slot_type` в `InventoryItem` при генерации
**Вариант B:** Хранить связь `item_template_id` в `InventoryItem`
**Вариант C:** Определять `slot_type` по `weapon_type` и `attack_type` (менее надежно)

**Рекомендация:** Вариант A - добавить поле `slot_type` в `InventoryItem` при генерации из `ItemTemplate`.

**Файлы:**
- `src/waifu_bot/db/models/item.py` - добавить поле `slot_type: Mapped[str | None]`
- `alembic/versions/XXXX_add_slot_type.py` - миграция
- `src/waifu_bot/services/item_service.py` - сохранять `slot_type` при генерации

#### 1.2. Создать функцию маппинга slot_type -> equipment_slot
```python
SLOT_TYPE_TO_EQUIPMENT_SLOTS = {
    "weapon_1h": [1, 2],      # Оружие 1H -> Weapon_1 или Weapon_2
    "weapon_2h": [1, 2],      # Оружие 2H -> Weapon_1 или Weapon_2 (занимает оба слота)
    "offhand": [2],           # Щит -> Weapon_2
    "costume": [3],           # Костюм -> Costume
    "ring": [4, 5],           # Кольцо -> Ring_1 или Ring_2
    "amulet": [6],            # Амулет -> Amulet
}
```

**Файлы:**
- `src/waifu_bot/api/routes.py` - добавить константу и функцию `get_available_slots_for_item(inv: InventoryItem) -> list[int]`

#### 1.3. Расширить проверку требований в `equip_item`
Проверять:
- `requirements.level` <= `main_waifu.level`
- `requirements.strength` <= `main_waifu.strength`
- `requirements.agility` <= `main_waifu.agility`
- `requirements.intelligence` <= `main_waifu.intelligence`
- `requirements.endurance` <= `main_waifu.endurance`

**Файлы:**
- `src/waifu_bot/api/routes.py` - обновить `equip_item()`

#### 1.4. Создать endpoint для получения доступных предметов для слота
```python
@router.get("/waifu/equipment/available", tags=["equipment"])
async def get_available_items_for_slot(
    slot: int = Query(..., ge=1, le=6),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """
    Возвращает список предметов из инвентаря, которые можно экипировать в указанный слот.
    Включает проверку требований (уровень, статы).
    """
```

**Файлы:**
- `src/waifu_bot/api/routes.py` - добавить endpoint
- `src/waifu_bot/api/schemas.py` - добавить `EquipmentAvailableResponse`

### Этап 2: Бэкенд - Расчет бонусов от экипировки

#### 2.1. Создать функцию расчета бонусов от предмета
```python
def calculate_item_bonuses(inv: InventoryItem) -> dict:
    """
    Возвращает словарь с бонусами от предмета:
    {
        "strength": +X,
        "agility": +X,
        "intelligence": +X,
        "endurance": +X,
        "charm": +X,
        "luck": +X,
        "hp": +X,
        "defense": +X,
        "crit_chance": +X%,
        "merchant_discount": +X%,
        "melee_damage": +X,
        "ranged_damage": +X,
        "magic_damage": +X,
    }
    """
```

**Файлы:**
- `src/waifu_bot/api/routes.py` - добавить функцию

#### 2.2. Обновить `_compute_details()` для учета экипировки
1. Получить все экипированные предметы
2. Для каждого предмета рассчитать бонусы (base_stat + affixes)
3. Суммировать все бонусы
4. Применить к базовым статам вайфу

**Файлы:**
- `src/waifu_bot/api/routes.py` - обновить `_compute_details()`

### Этап 3: Фронтенд - Модальные окна и обработка кликов

#### 3.1. Модальное окно для выбора предмета при клике на слот
**Структура:**
- Заголовок: "Выберите предмет для слота [Название]"
- Список доступных предметов (из `/waifu/equipment/available?slot=X`)
- Для каждого предмета: название, уровень, редкость, требования
- Кнопка "Экипировать" для каждого предмета
- Кнопка "Снять текущий предмет" (если слот занят)

**Файлы:**
- `src/waifu_bot/webapp/profile.html` - добавить структуру модального окна
- `src/waifu_bot/webapp/app.js` - функции `openSlotModal(slot)`, `equipItemFromSlot(itemId, slot)`
- `src/waifu_bot/webapp/styles.css` - стили для модального окна

#### 3.2. Модальное окно с деталями предмета при клике на предмет в инвентаре
**Структура:**
- Заголовок: название предмета, редкость, уровень
- Детали: урон, скорость атаки, тип атаки, тип оружия
- Бонусы: base_stat, аффиксы/суффиксы
- Требования: уровень, статы (с индикацией выполнения)
- Кнопка "Экипировать" (активна только если требования выполнены)
- Кнопка "Снять" (если предмет экипирован)

**Файлы:**
- `src/waifu_bot/webapp/profile.html` - добавить структуру модального окна
- `src/waifu_bot/webapp/app.js` - функции `openItemModal(item)`, `equipItem(itemId)`, `unequipItem(itemId)`
- `src/waifu_bot/webapp/styles.css` - стили для модального окна

#### 3.3. Обновить `renderProfileGear()` для обработки кликов
- Добавить обработчик клика на каждый слот
- При клике вызывать `openSlotModal(slot)`

**Файлы:**
- `src/waifu_bot/webapp/app.js` - обновить `renderProfileGear()`

#### 3.4. Обновить `loadProfileInventory()` для обработки кликов
- Сделать каждый предмет кликабельным
- При клике вызывать `openItemModal(item)`

**Файлы:**
- `src/waifu_bot/webapp/app.js` - обновить `loadProfileInventory()`

### Этап 4: Интеграция и тестирование

#### 4.1. Обновление профиля после экипировки/снятия
- После успешной экипировки/снятия вызывать `loadProfile()` для обновления статов
- Обновлять отображение слотов и инвентаря

#### 4.2. Обработка ошибок
- Показывать понятные сообщения об ошибках (недостаточно статов, уровень и т.д.)
- Валидация на фронтенде перед отправкой запроса

## Детали реализации

### Маппинг slot_type -> equipment_slot

```python
SLOT_TYPE_TO_EQUIPMENT_SLOTS = {
    "weapon_1h": [1, 2],      # Одноручное оружие -> Weapon_1 или Weapon_2
    "weapon_2h": [1, 2],      # Двуручное оружие -> Weapon_1 и Weapon_2 (занимает оба)
    "offhand": [2],           # Щит -> Weapon_2
    "costume": [3],           # Костюм -> Costume
    "ring": [4, 5],           # Кольцо -> Ring_1 или Ring_2
    "amulet": [6],            # Амулет -> Amulet
}

EQUIPMENT_SLOT_NAMES = {
    1: "Оружие 1",
    2: "Оружие 2",
    3: "Костюм",
    4: "Кольцо 1",
    5: "Кольцо 2",
    6: "Амулет",
}
```

### Расчет бонусов от аффиксов

Аффиксы могут давать бонусы к:
- Статам: `strength`, `agility`, `intelligence`, `endurance`, `charm`, `luck`
- HP: `hp_flat`, `hp_percent`
- Защите: `defense_flat`, `defense_percent`
- Криту: `crit_chance_flat`, `crit_chance_percent`
- Урону: `damage_flat`, `damage_percent`, `melee_damage`, `ranged_damage`, `magic_damage`
- Скидкам: `merchant_discount_flat`, `merchant_discount_percent`

### Проверка требований

```python
def check_item_requirements(inv: InventoryItem, waifu: MainWaifu) -> tuple[bool, list[str]]:
    """
    Проверяет требования предмета.
    Возвращает (можно_экипировать, список_ошибок).
    """
    errors = []
    req = inv.requirements or {}
    
    if req.get("level", 0) > waifu.level:
        errors.append(f"Требуется уровень {req['level']}, у вас {waifu.level}")
    
    if req.get("strength", 0) > waifu.strength:
        errors.append(f"Требуется СИЛ {req['strength']}, у вас {waifu.strength}")
    
    # ... аналогично для других статов
    
    return len(errors) == 0, errors
```

## Порядок выполнения

1. **Бэкенд:**
   - Добавить `slot_type` в `InventoryItem` (миграция + обновление генерации)
   - Создать маппинг slot_type -> equipment_slot
   - Расширить проверку требований
   - Создать endpoint `/waifu/equipment/available`
   - Реализовать расчет бонусов от экипировки
   - Обновить `_compute_details()`

2. **Фронтенд:**
   - Добавить модальные окна в HTML
   - Реализовать функции открытия модальных окон
   - Обновить `renderProfileGear()` и `loadProfileInventory()` для обработки кликов
   - Добавить функции экипировки/снятия
   - Добавить обновление профиля после действий

3. **Тестирование:**
   - Проверить экипировку предметов в разные слоты
   - Проверить проверку требований
   - Проверить расчет бонусов
   - Проверить UI/UX


