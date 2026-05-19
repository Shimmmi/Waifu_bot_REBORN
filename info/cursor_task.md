# Cursor — задание на разработку Вайфу-бота

> Полная спецификация проекта — в файле `waifu_bot_full_tz.md`.
> Этот файл — операционное задание для разработки: стек, структура проекта, порядок реализации, ключевые контракты.

---

## Контекст проекта

**Вайфу-бот** — Telegram IDLE RPG на базе Telegram Bot API + Mini App (WebApp).

Игрок управляет персонажем («Основная Вайфу», ОВ), которая проходит подземелья через активность в групповом чате Telegram: каждое текстовое сообщение = удар по монстру, медиа-сообщения = активные навыки. Интерфейс — HTML-страницы внутри Telegram Mini App.

---

## Технический стек

### Backend
- **Python 3.11+**
- **aiogram 3.x** — Telegram Bot (обработка сообщений чата, уведомления в личку)
- **FastAPI** — REST API для WebApp (Mini App)
- **PostgreSQL 15** — основная БД
- **SQLAlchemy 2.0** (async) — ORM
- **Alembic** — миграции
- **Celery + Redis** — фоновые задачи (тики экспедиций, регенерация HP, рейды, войны гильдий)
- **httpx** — HTTP-клиент для OpenRouter

### Frontend
- Vanilla JS (ES2022) — без фреймворков
- HTML5 + CSS3 (CSS Variables, Grid, Flexbox)
- Telegram WebApp JS SDK (`window.Telegram.WebApp`)
- Все страницы — статические HTML, JS тянет данные через API

### Инфраструктура
- VPS (Ubuntu 22.04)
- **nginx** — реверс-прокси + раздача статики `/static/monsters/` без участия backend
- **systemd** — управление процессами

### Внешние API
- **OpenRouter** — генерация нарратива экспедиций, реплики торговца, сводки войн гильдий
- **Telegram Bot API** — основной интерфейс

---

## Структура проекта

```
waifu-bot/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── bot.py               # aiogram bot entry point
│   │   ├── config.py            # settings (pydantic-settings)
│   │   ├── database.py          # async engine, session factory
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── player.py
│   │   │   ├── waifu.py         # Основная Вайфу (ОВ)
│   │   │   ├── item.py
│   │   │   ├── dungeon.py
│   │   │   ├── monster.py
│   │   │   ├── expedition.py
│   │   │   ├── hire_unit.py     # Наёмные вайфу
│   │   │   ├── guild.py
│   │   │   ├── guild_raid.py
│   │   │   ├── guild_war.py
│   │   │   └── skill.py
│   │   ├── routers/             # FastAPI routers (один файл = один экран)
│   │   │   ├── profile.py
│   │   │   ├── dungeons.py
│   │   │   ├── shop.py
│   │   │   ├── tavern.py
│   │   │   ├── expedition.py
│   │   │   ├── guild.py
│   │   │   ├── training.py
│   │   │   └── caravan.py
│   │   ├── handlers/            # aiogram handlers (обработка сообщений чата)
│   │   │   ├── chat_message.py  # текст → урон монстру
│   │   │   ├── chat_media.py    # медиа → активный навык
│   │   │   └── commands.py      # /start, /gd_start, etc.
│   │   ├── services/            # бизнес-логика
│   │   │   ├── combat.py        # расчёт урона, смерть монстра, лут
│   │   │   ├── expedition.py    # тик экспедиции, OpenRouter
│   │   │   ├── guild.py         # GXP, рейды, войны
│   │   │   ├── shop.py          # цены, заточка
│   │   │   ├── character.py     # характеристики, левелап
│   │   │   └── ai_narrative.py  # OpenRouter wrapper
│   │   ├── tasks/               # Celery tasks
│   │   │   ├── expedition_tick.py
│   │   │   ├── hp_regen.py
│   │   │   ├── raid_tick.py
│   │   │   └── war_narrative.py
│   │   └── utils/
│   │       ├── formulas.py      # все игровые формулы
│   │       └── slug.py          # генератор slug для монстров
│   ├── alembic/
│   ├── scripts/
│   │   └── bulk_update_has_image.py
│   └── tests/
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   │   └── main.css
│   │   ├── js/
│   │   │   ├── api.js           # fetch-обёртка с auth-заголовком
│   │   │   ├── app.js           # инициализация WebApp, роутер
│   │   │   └── pages/           # логика каждой страницы
│   │   └── monsters/            # WebP изображения монстров
│   ├── profile.html
│   ├── dungeons.html
│   ├── shop.html
│   ├── tavern.html
│   ├── caravan.html
│   ├── training_hall.html
│   ├── guild_hall.html
│   ├── settings.html
│   └── waifu_generator.html
├── nginx/
│   └── waifu-bot.conf
├── docker-compose.yml           # postgres + redis для dev
└── .env.example
```

---

## Ключевые контракты API

### Аутентификация
Все запросы от WebApp содержат заголовок `X-Telegram-Init-Data: <initData>`.
Backend валидирует HMAC-подпись согласно [Telegram WebApp Auth](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).

```python
# backend/app/utils/auth.py
def validate_init_data(init_data: str, bot_token: str) -> dict:
    # returns parsed user data или raises HTTPException(403)
```

### Ключевые эндпоинты

```
GET  /api/profile                  # данные ОВ, характеристики, инвентарь
GET  /api/dungeons                 # список подземелий + активный бой
POST /api/dungeons/{id}/enter      # войти в подземелье
GET  /api/shop/items               # ассортимент магазина
POST /api/shop/buy/{item_id}       # купить
POST /api/shop/sell/{item_id}      # продать
GET  /api/expeditions/slots        # слоты экспедиций
POST /api/expeditions/start        # запустить экспедицию
POST /api/expeditions/{id}/abort   # досрочно завершить
GET  /api/guild                    # данные гильдии игрока
POST /api/guild/create             # создать гильдию
POST /api/guild/join/{guild_id}    # подать заявку
GET  /api/guild/raids              # список рейдов
POST /api/guild/raids/{id}/start   # запустить рейд
GET  /api/guild/war                # статус войны
POST /api/guild/war/declare        # объявить войну
GET  /api/training/skills          # дерево навыков
POST /api/training/skills/{id}/upgrade  # прокачать навык
```

### Обработка сообщений чата (aiogram)

```python
# Каждое входящее сообщение в групповом чате:
# 1. Определить тип (text / media)
# 2. Найти игрока по user_id
# 3. Найти активное подземелье для этого чата
# 4. Вызвать combat_service.process_message(player, dungeon, message_type)
# 5. Если монстр убит — запустить loot_service.generate_loot()
# 6. Если подземелье завершено — отправить reward_modal данные в WebApp через answerWebAppQuery или уведомление в ЛС
```

---

## Игровые формулы (реализовать в `utils/formulas.py`)

```python
# Регенерация HP
def hp_regen_per_hour(hp_max: float, vyn: int, divider: float = 100) -> float:
    return hp_max * (1 - math.exp(-vyn / divider))

# Урон по монстру
def calc_damage(dmg_min: int, dmg_max: int, stat_bonus: float,
                crit_chance: float, crit_mult: float) -> tuple[int, bool]:
    base = random.randint(dmg_min, dmg_max) * (1 + stat_bonus)
    is_crit = random.random() < crit_chance
    return int(base * (crit_mult if is_crit else 1.0)), is_crit

# Урон монстра по ОВ
def calc_monster_damage(monster_dmg: int, armor: int, vyn: int,
                         dodge_chance: float, divider: float = 200) -> int:
    if random.random() < dodge_chance:
        return 0
    reduced = max(1, monster_dmg - armor)
    vyn_reduction = 1 - math.exp(-vyn / divider)
    return max(1, int(reduced * (1 - vyn_reduction)))

# Торговля
def buy_price(base_price: float, trade: float) -> float:
    return base_price * (1 + math.exp(-trade / 100))

def sell_price(base_price: float, trade: float) -> float:
    return base_price * 0.5 * (2 - math.exp(-trade / 100))

# Шанс элитного монстра
def elite_chance(base: float, luck: int) -> float:
    return base * (1 + luck / 500)
```

---

## Переменные конфигурации (game_config в БД)

Все игровые параметры хранятся в таблице `game_config (key VARCHAR PK, value FLOAT)`.
Изменение без деплоя. Ключи:

```
hp_regen_divider        = 100    # делитель в формуле регенерации HP
dmg_reduction_divider   = 200    # делитель снижения урона от ВЫН
base_elite_chance       = 0.06   # базовый шанс элитного монстра
cursed_weight_mult      = 1.5    # множитель веса undead/demon в cursed-локациях
K_vampir, K_brs, K_met, K_ark, K_ten, K_reg, K_chut, K_hire, K_zhv
expedition_tick_min     = 5      # мин. интервал тика экспедиции (мин)
expedition_tick_max     = 10     # макс. интервал
base_heal_cost          = 0.5    # стоимость лечения за 1 HP
base_level_up_cost      = 100    # стоимость левелапа наёмницы
guild.gxp_per_message   = 1
guild.gxp_per_boss      = 20
guild.war_narrative_interval = 6 # часов между сводками
raid_scale_factor       = 10     # множитель HP рейд-монстра
enchant_dmg_pct         = 0.10   # % базового урона за уровень заточки
enchant_armor_pct       = 0.12
enchant_break_chance_9  = 0.30   # шанс провала +9→+10
enchant_rollback_chance = 0.40   # шанс отката +8→+9
```

---

## Порядок реализации

### Фаза 1 — Ядро (минимальный рабочий прототип)
1. Инициализация проекта: FastAPI + aiogram + PostgreSQL + Alembic
2. Модели БД: Player, Waifu (ОВ), Item, Dungeon, Monster, GameConfig
3. Создание персонажа (`waifu_generator.html`) → сохранение в БД
4. Обработчик сообщений чата → расчёт урона → смерть монстра
5. API профиля: характеристики, HP, инвентарь
6. Базовый UI: `profile.html`, `dungeons.html`
7. Список подземелий → войти → карточка активного боя

### Фаза 2 — Прогрессия
8. Инвентарь: слоты экипировки, сумка, фильтр/сортировка
9. Магазин: ассортимент, покупка, продажа, формулы Торговли
10. Таверна: найм вайфу, лечение, прокачка наёмниц
11. Система опыта и левелапов ОВ
12. Изображения монстров: nginx + fallback-цепочка на клиенте

### Фаза 3 — Навыки и глубина
13. Дерево пассивных навыков (`training_hall.html`)
14. Скрытые навыки Morrowind-стиля (счётчики + пороги)
15. Расовые и классовые пассивные навыки
16. Аффиксы элитных монстров
17. Система экспедиций v2: тики Celery, OpenRouter-нарратив

### Фаза 4 — Эндгейм и социальный контент
18. Заточка предметов
19. Система сложности подземелий (Чип +)
20. Гильдии: создание, вступление, банк, прокачка (GXP, навыки)
21. Рейды: тики, HP монстра, распределение наград
22. Войны гильдий: War Score, ИИ-сводки, награды
23. Гильдейские квесты *(опционально)*

---

## Важные ограничения и решения

### Боевая механика
- Монстр наносит урон ОВ **один раз** — в момент своей гибели, не за каждый удар. Это позволяет пассивным участникам чата участвовать в бою без риска блокировки прогресса.
- При HP = 0 ОВ «без сознания»: сообщения не наносят урон, прогресс сохраняется. Восстановление — пассивная регенерация.
- Регенерация HP в подземелье: начисляется между каждым сообщением пропорционально прошедшему времени.

### Изображения монстров
- Nginx раздаёт `/static/monsters/` напрямую, без backend.
- Клиент строит URL из `family` и `slug` монстра: `/{family}/{slug}.webp`.
- Fallback: `img.onerror` перебирает цепочку: индивидуальный → `_family_tN.webp` → `_family.webp` → `_unknown.webp`.

### OpenRouter
- ИИ получает только художественный контекст. Все числа рассчитывает backend **до** вызова ИИ.
- При ошибке OpenRouter — использовать fallback-фразы из массива, не блокировать игровой процесс.
- Модель: выбирается через конфиг, дефолт — `anthropic/claude-haiku`.

### Telegram WebApp
- Инициализация: `window.Telegram.WebApp.ready()` при загрузке каждой страницы.
- Тема: использовать CSS-переменные `--tg-theme-bg-color`, `--tg-theme-text-color` и т.д.
- `initData` передаётся в каждый API-запрос как заголовок `X-Telegram-Init-Data`.

### Балансировка
- Все игровые коэффициенты — в таблице `game_config`. Никогда не хардкодить магические числа в коде.
- Исключение: структурные константы (количество слотов экипировки = 6, максимальный уровень ОВ = 50).

---

## Что реализовывать в первую очередь при работе с Cursor

При открытии проекта начинай с **Фазы 1**. Если спрашиваешь про конкретный модуль — уточни в каком файле по структуре выше он должен быть и следуй контрактам API из этого документа.

Файл `waifu_bot_full_tz.md` — источник правды по всем игровым механикам. При любых неясностях по логике (например, как именно считается лут или что происходит при смерти ОВ) — обращайся к нему, раздел «Подземелья» и «Боевая механика».
