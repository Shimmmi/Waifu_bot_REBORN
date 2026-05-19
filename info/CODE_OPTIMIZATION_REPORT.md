# Отчёт по оптимизации кода — Waifu Bot REBORN

Дата: 2026-04-02

## 1. Сводка выполненных изменений

### P0 — Критические исправления (баги)

| Изменение | Файл(ы) | Описание |
|-----------|---------|----------|
| Startup-диагностика | `main.py` | Проверка при старте: `gd_dungeon_templates` пуста → WARNING, активные `gd_cycle` → WARNING с chat_id |
| Улучшенная ошибка `/gd_join` | `gd_cycle_service.py` | Если шаблоны GD отсутствуют — явное сообщение `"GD v1 не настроен"` вместо общего `"Регистрация закрыта"` |
| Логирование ADMIN_IDS | `main.py` | При старте в лог выводятся ADMIN_IDS и environment для диагностики прав |
| Настраиваемый `drop_pending_updates` | `webhook.py`, `config.py` | Новая env-переменная `WEBHOOK_DROP_PENDING` (default=true); позволяет не терять сообщения при деплое |

**Диагностика для двух основных багов:**

#### 1A. Соло-подземелья: урон по сообщению не работает

Наиболее вероятная причина: **активный цикл GD v1** в том же чате (`gd_cycle.status = 'active'`). При активном цикле все сообщения попадают в Redis-буфер раунда, `CombatService.process_message_damage` не вызывается.

Проверка: `SELECT * FROM gd_cycle WHERE status = 'active';`

Исправление: `/gd_v1_test_reset` в чате, или `UPDATE gd_cycle SET status = 'done' WHERE ...`

Теперь при старте бот логирует WARNING для каждого "зависшего" active-цикла.

#### 1B. Групповые подземелья: команды не реагируют

Наиболее вероятная причина: **таблица `gd_dungeon_templates` пуста** (не запущен `seed_gd_content.py`). Теперь при старте бот логирует WARNING если шаблонов нет, а `/gd_join` возвращает явное сообщение администратору.

Другие причины: `ADMIN_IDS` не настроен в `.env`, webhook secret mismatch, бот без прав в группе.

---

### P1 — Рефакторинг для стабильности

| Изменение | Файл(ы) | Описание |
|-----------|---------|----------|
| Удалён мёртвый `continue_battle` | `services/dungeon.py` | Placeholder с `damage = 10`, нигде не вызывался |
| Удалены неиспользуемые импорты | `models/player.py` (`IntEnum`), `models/skill.py` (`Boolean`, `BigInteger`) | Чистка импортов |
| Удалены legacy ORM-модели | `models/group_dungeon.py`, `models/__init__.py`, `alembic/env.py` | `GDSession`, `GDPlayerContribution` — заменены `GDCycle`; таблицы в БД остались |
| Background loops → модуль | `services/background.py`, `main.py` | 7 background loops вынесены из `_startup()` в `services/background.py`; graceful shutdown через `cancel_all_background_tasks()` |
| Spam tracker → Redis fallback | `services/combat.py` | Redis-первый подход с fallback на in-memory; warning при отсутствии Redis; eviction при > 5000 записей |
| Убран двойной commit | `services/bot_handlers.py` | `apply_raid_message_damage` уже коммитит; лишний commit в хендлере убран |

---

### P2 — Архитектурная оптимизация

| Изменение | Файл(ы) | Описание |
|-----------|---------|----------|
| Разбивка `routes.py` | `api/guild_routes.py`, `admin_routes.py`, `shop_routes.py`, `tavern_routes.py`, `dungeon_routes.py`, `skill_routes.py` | 3800+ → ~2160 строк в `routes.py`; 6 доменных модулей |
| Deprecation DungeonProgress | `services/dungeon.py`, `services/combat.py` | WARNING при использовании legacy-пути; все новые данжы используют `DungeonRun` |
| Удалены legacy-колонки HiredWaifu | `models/waifu.py`, `alembic/versions/0058_*` | 6 неиспользуемых stat-колонок; миграция Alembic готова |
| Пакетная группировка сервисов | `services/gd/`, `services/guild_ops/`, `services/expedition_ops/` | `__init__.py` с ре-экспортами; новый код может импортировать из пакетов |

---

## 2. Соответствие ТЗ v1.4

### Полностью реализовано

- Основной чердак (ОЧ), подвал навигации, все 9 HTML-страниц
- Профиль: портрет, характеристики, HP, EXP, инвентарь (экипировка + сумка)
- Одиночные подземелья: 5 актов, монстры, боссы, процедурная генерация, Dungeon+
- Боевая система: текст → урон, медиа → навыки, антиспам, критические удары
- Монстры: tag/biome система, 5 тиров, аффиксы для элитных, WebP-арт
- Предметы: шаблоны, двухслойная модель, аффиксы, заточка +1..+10
- Навыки: активные (по медиа), пассивное дерево (3 ветки), 27 скрытых навыков
- Таверна: пул наёмниц, перки (60 шт.), лечение, прокачка, увольнение
- Экспедиции: legacy + v2 redesign с тик-системой
- Магазин: покупка, продажа, gamble, merchant AI-фраза
- Караван: переход между актами
- Гильдии: создание, поиск, вступление, банк, рейды, войны, навыки
- AI-нарратив (OpenRouter) с fallback при отключении
- Game config в БД, конфигурируемые параметры

### Частично реализовано / на рассмотрении

| Фича | Статус | Примечание |
|-------|--------|-----------|
| Гильдейские квесты | Не реализовано | Помечено "на рассмотрение" в ТЗ |
| Normal/Nightmare/Hell | Не реализовано | Упомянуто как будущее |
| Авто/ручная раздача рейдового лута | Частично | Автоматическое по вкладу |
| 2D пиксельная модель персонажа | Не реализовано | ТЗ описывает для инвентаря |

---

## 3. Рекомендации на будущее

### 3.1 JSON-колонки: кандидаты на нормализацию

| Модель | Колонка | Тип данных | Рекомендация |
|--------|---------|------------|-------------|
| `HiredWaifu` | `perks` | `[{perk_id, level, name}]` | Нормализовать в `hired_waifu_perks(waifu_id, perk_id, level)` для SQL-аналитики |
| `ActiveExpedition` | `squad_waifu_ids` | `[int]` | Нормализовать в `expedition_squad(expedition_id, waifu_id, position)` |
| `ExpeditionSlot` | `affixes` + `affix_ids` | Двойное представление | Оставить только `affix_ids` со связью через FK |
| `GDCycle` | `battle_state_json` | Сложный объект | Допустимо как JSON — редко запрашивается по полям |
| `GDRound` | `actions_json`, `outcomes_json` | Лог раунда | Допустимо как JSON — историческая запись |
| `MonsterAffix` | `behavior_params` | Конфиг аффикса | Допустимо как JSON — справочные данные |

Приоритет нормализации: `perks` > `squad_waifu_ids` > `affixes`/`affix_ids` дублирование.

### 3.2 Дальнейший рефакторинг

1. **Полная миграция DungeonProgress → DungeonRun**: после подтверждения что все активные данжи используют DungeonRun, убрать fallback-код в `combat.py` и `dungeon.py`. Миграция данных: конвертировать существующие `DungeonProgress` с `is_active=True` в `DungeonRun`.

2. **Физическое перемещение сервисов в пакеты**: сейчас `services/gd/`, `services/guild_ops/`, `services/expedition_ops/` содержат только `__init__.py` с ре-экспортами. Следующий шаг — переместить файлы (`gd_*.py` → `gd/`), обновить все импорты.

3. **routes.py**: оставшиеся ~2160 строк содержат profile/waifu/equipment/acts/expeditions/SSE/webhook/helpers. Следующий этап — выделить `waifu_routes.py` и `expedition_api_routes.py`.

4. **Тестирование**: добавить интеграционные тесты для цепочки webhook → handler → service (сейчас в `tests/unit/` только юнит-тесты).

5. **CORS**: `allow_origins=["*"]` в `main.py` — ужесточить для production.

### 3.3 Архитектурная схема после оптимизации

```
src/waifu_bot/
├── main.py                    (app factory, ~125 строк)
├── api/
│   ├── routes.py              (core + profile + webhook, ~2160 строк)
│   ├── guild_routes.py        (20 guild endpoints)
│   ├── admin_routes.py        (10 admin endpoints)
│   ├── shop_routes.py         (8 shop endpoints)
│   ├── tavern_routes.py       (9 tavern endpoints)
│   ├── dungeon_routes.py      (10 dungeon/battle/GD endpoints)
│   ├── skill_routes.py        (6 skill endpoints)
│   ├── inventory_routes.py    (enchanting, detailed item API)
│   ├── expedition_routes.py   (expedition API detail)
│   ├── schemas.py             (Pydantic models)
│   └── deps.py                (FastAPI dependencies)
├── core/
│   ├── config.py              (+WEBHOOK_DROP_PENDING)
│   ├── logging.py
│   └── redis.py
├── db/
│   └── models/                (ORM: -GDSession, -GDPlayerContribution, -HiredWaifu legacy cols)
├── game/                      (constants, formulas, pure game logic)
├── services/
│   ├── background.py          (NEW: все background loops)
│   ├── gd/                    (NEW: package re-exports)
│   ├── guild_ops/             (NEW: package re-exports)
│   ├── expedition_ops/        (NEW: package re-exports)
│   ├── combat.py              (Redis-first spam, DungeonProgress deprecation)
│   ├── bot_handlers.py        (fixed double commit)
│   ├── webhook.py             (configurable drop_pending)
│   └── ... (38 other services)
└── webapp/                    (HTML Mini App)
```

---

## 4. Миграции Alembic

| Файл | Описание | Статус |
|------|----------|--------|
| `0058_drop_hired_waifu_legacy_stats.py` | Удаление 6 неиспользуемых колонок из `hired_waifus` | Готова, не применена |

**Перед применением:** убедитесь что ни один сервис/API не читает `hired_waifus.strength/agility/...` (проверено: не читают).

```bash
alembic upgrade head
```

---

## 5. Контрольный чеклист для развёртывания

- [ ] Запустить `python scripts/seed_gd_content.py` если `gd_dungeon_templates` пуста
- [ ] Проверить `ADMIN_IDS` в `.env` (через запятую: `ADMIN_IDS=123456,789012`)
- [ ] Проверить `WEBHOOK_SECRET` совпадает между `.env` и Telegram
- [ ] Проверить что `APP_ENV` **не** `dev`/`testing` на production
- [ ] Проверить `SELECT * FROM gd_cycle WHERE status = 'active'` — нет "зависших" циклов
- [ ] Применить миграцию `alembic upgrade head` (0058)
- [ ] Проверить логи при старте: `Startup diagnostics: ...`
- [ ] Проверить `log_bot_identity`: @username совпадает с ботом в группе
- [ ] Убедиться что бот имеет права на отправку сообщений в целевой группе
