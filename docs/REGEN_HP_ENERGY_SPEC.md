# Спецификация: регенерация HP и энергии во времени

## Целевые показатели

| Ресурс | Скорость регенерации | Кап |
|--------|----------------------|-----|
| Энергия | **1 ед/мин** | `max_energy` |
| Здоровье (HP) | **5 ед/мин + бонус от ВЫН** | `max_hp` |

---

## Текущее состояние

### Энергия
- **Файл:** `src/waifu_bot/services/energy.py`
- **Скорость:** 5 ед/час (`ENERGY_REGEN_PER_HOUR = 5`)
- **Учёт времени:** `main_waifus.energy_updated_at` (DateTime timezone)
- **Алгоритм:** дискретные почасовые тики: `hours = (now - last) // 3600`, `gain = hours * 5`, ограничение по `max_energy`, сдвиг `energy_updated_at` на `hours` вперёд
- **Вызовы:** `apply_energy_regen(waifu)` из:
  - `api/routes.py` — при загрузке профиля (`/waifu/profile`, ~стр. 500)
  - `services/combat.py` — перед боем в подземелье

### Здоровье (HP)
- Регенерация HP **не реализована**
- Поля: `main_waifus.current_hp`, `main_waifus.max_hp`
- Отдельного `hp_updated_at` нет

---

## Изменения в БД

### Миграция Alembic

Добавить в `main_waifus`:

```python
hp_updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    nullable=True,  # для обратной совместимости при миграции
)
```

- **Backfill:** для существующих строк `hp_updated_at = COALESCE(updated_at, created_at)` или `NOW()` — считаем, что «последний тик» регена HP — момент миграции (или `updated_at`), чтобы не начислять HP за прошлое.
- После миграции в коде использовать `hp_updated_at or now` при первом запуске логики.

---

## Алгоритм регенерации

### Общие принципы

1. **Единица времени — 1 минута.** Оба ресурса считаются по минутам.
2. **Формула длительности:**  
   `minutes = max(0, int((now - last).total_seconds() / 60))`
3. **Ограничение по капу:**  
   - энергия: `energy = min(max_energy, energy + minutes * ENERGY_REGEN_PER_MIN)`  
   - HP: `current_hp = min(max_hp, current_hp + minutes * HP_REGEN_PER_MIN)`
4. **Сдвиг метки времени:**  
   - `energy_updated_at = last + timedelta(minutes=minutes)` (для энергии)  
   - `hp_updated_at = last + timedelta(minutes=minutes)` (для HP)  
   Чтобы не «терять» дробные минуты при долгом офлайне.
5. **Пропуск, если уже на капе:** если `energy >= max_energy`, только обновить `energy_updated_at = now` (аналогично для HP), чтобы при следующем заходе не начислять лишнее.

### Константы (предлагаемые)

```python
# services/energy.py или constants
ENERGY_REGEN_PER_MIN = 1
HP_REGEN_PER_MIN = 5
```

### Псевдокод для энергии (1/мин)

```text
если energy >= max_energy:
    energy_updated_at = now
    return
last = energy_updated_at or now
minutes = (now - last).total_seconds() / 60
если minutes < 1: return
minutes = int(minutes)
gain = min(minutes * 1, max_energy - energy)
energy += gain
energy_updated_at = last + timedelta(minutes=minutes)
```

### Псевдокод для HP (5/мин + бонус от ВЫН)

```text
если current_hp >= max_hp:
    hp_updated_at = now
    return
last = hp_updated_at or now
minutes = (now - last).total_seconds() / 60
если minutes < 1: return
minutes = int(minutes)
per_min = 5 + max(0, endurance - 10)
gain = min(minutes * per_min, max_hp - current_hp)
current_hp += gain
hp_updated_at = last + timedelta(minutes=minutes)
```

### Один или два модуля

- **Вариант A:** одна функция `apply_regen(waifu, now)` в `services/energy.py` (или переименовать в `regen.py`), внутри вызываются расчёты и для энергии, и для HP.
- **Вариант B:** `apply_energy_regen` и `apply_hp_regen` по отдельности; в точках входа вызывать обе.

Рекомендация: **вариант A** — меньше дублирования и один проход по `waifu` и `now`.

---

## Точки вызова

Вызывать `apply_regen(waifu)` (или пару `apply_energy_regen` + `apply_hp_regen`) в тех же местах, где сейчас вызывается только `apply_energy_regen`:

1. **`/waifu/profile`** (`api/routes.py`) — при отдаче профиля основной вайфу.
2. **Перед боем в подземелье** (`services/combat.py` или сервис подземелий) — перед списанием энергии/урона.

Дополнительно рассмотреть (по дизайну геймплея):

- **При старте подземелья** (`/dungeon/start` или аналог) — чтобы регенерация «в городе» учитывалась до входа в данж.
- **При выходе из подземелья** — если реген во время прохождения запрещена; иначе не нужен отдельный вызов.

---

## Когда НЕ регенерировать

- **В бою (в подземелье):** по текущему замыслу реген во время боя/данжа обычно отключают. Если позже включат — потребуется явный вызов в конце хода/этапа.
- **Мёртвая вайфу (`current_hp <= 0`):** в спецификации не восстановление из мёртвого состояния; при реализации можно либо не вызывать `apply_hp_regen`, либо внутри проверять `current_hp > 0` (во избежание «оживания» только за счёт регена).

Детали (реген в данже, при 0 HP) оставить на этап реализации и баланса.

---

## Ограничение «долгого офлайна» (опционально)

Сейчас логика позволяет начислить много энергии/HP за недели офлайна. Варианты:

- **Без лимита** — оставить как в псевдокоде; после долгого отсутствия ресурсы быстро выходят на кап.
- **С лимитом:** например, считать реген не более чем за последние N часов (24–168).  
  Пример: `minutes = min(minutes, 24 * 60)` перед расчётом `gain`.

В первом приближении достаточно **без лимита**; при необходимости лимит добавляется в расчёт `minutes` до применения формул.

---

## Чек-лист реализации

- [x] Миграция: добавить `hp_updated_at` в `main_waifus`, backfill. (`0010_waifu_hp_regen_timestamp.py`)
- [x] В `MainWaifu` (модель) добавить `hp_updated_at`.
- [x] Константы: `ENERGY_REGEN_PER_MIN = 1`, `HP_REGEN_PER_MIN = 5` (и при необходимости убрать/заменить `ENERGY_REGEN_PER_HOUR`).
- [x] Переписать `apply_energy_regen` на **минутные** тики и 1 ед/мин.
- [x] Реализовать реген HP (5 ед/мин) с `hp_updated_at`.
- [x] Объединить в `apply_regen(waifu, now)` или оставить две функции и вызывать обе в точках входа.
- [x] Вызывать реген в: `GET /profile`, перед боем в подземелье, при старте подземелья (`start_dungeon`).
- [x] Решить: реген в подземелье/в бою и при `current_hp <= 0` — при `current_hp <= 0` HP-реген не начисляется (только refresh `hp_updated_at`). В бою реген вызывается в начале каждого `process_message_damage` (как раньше энергия); при старте данжа — в `start_dungeon`.
- [x] Обновить/зафиксировать в `game/constants.py` и `technical_spec.md` значения 1 энерг/мин и 5 HP/мин.

---

## Ссылки на код

| Что | Файл |
|-----|------|
| Модель `MainWaifu` | `src/waifu_bot/db/models/waifu.py` |
| Текущая регенерация энергии | `src/waifu_bot/services/energy.py` |
| Вызов при /profile | `src/waifu_bot/api/routes.py` (~стр. 498–502) |
| Вызов перед боем | `src/waifu_bot/services/combat.py` (~стр. 82–83) |
| Константы (энергия) | `src/waifu_bot/game/constants.py` |
| Миграция `energy_updated_at` | `alembic/versions/0009_waifu_energy_regen_timestamp.py` |
