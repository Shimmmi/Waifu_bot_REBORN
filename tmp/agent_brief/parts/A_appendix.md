## Приложение A. Справочник

Справочные материалы для ИИ-агента. При портировании на Steam страницы WebApp адаптируются под нативный UI или встроенный браузер Electron.

### WebApp-страницы (13 файлов)

| Файл | Назначение | Backend (концептуально) |
|------|------------|-------------------------|
| `index.html` | Старт: новая игра / продолжить | profile, auth |
| `waifu_generator.html` | Создание ОВ: раса, класс, портрет, био | profile, LLM bio |
| `profile.html` | Профиль ОВ: статы, инвентарь, экипировка | profile, equipment |
| `dungeons.html` | Подземелья, экспедиции, бездна (вкладки) | dungeon, expedition, abyss |
| `battle.html` | Бой в WebApp (SSE) | combat, sse |
| `shop.html` | Магазин: покупка, продажа, gamble | shop |
| `tavern.html` | Таверна: найм waifus, banter AI, BGM | tavern |
| `caravan.html` | Караван: смена акта, карта, tip AI | player/acts |
| `training_hall.html` | Пассивные навыки | passive_skills |
| `guild_hall.html` | Гильдия: банк, навыки, рейды, войны | guild |
| `mail.html` | Игровая почта | player_mail |
| `settings.html` | Настройки, уведомления | player prefs |
| `player.html` | Публичный профиль другого игрока | profile (read-only) |

**Armory** (`/armory`, Vue SPA) — отдельный браузерный портал статистики, не входит в WebApp.

### Публичные bot-команды

| Команда | Окружение | Назначение |
|---------|-----------|------------|
| `/start` | все чаты | Приветствие, вход в игру |
| `/help` | все чаты | Справка |
| `/gd_join` | группы | Запись в цикл GD v1 |

Legacy `/gd_start`, `/engage` отключены.

### Концептуальные группы API

- **profile** — данные игрока и ОВ
- **equipment** — экипировка, инвентарь
- **battle** — соло-бой, урон, награды
- **expeditions** — слоты, старт, claim, abort
- **guild** — банк, навыки, рейды, войны, квесты
- **shop / tavern / caravan** — экономика и найм
- **abyss** — башня, атаки, лидерборд
- **chat-rewards** — награды за активность в чате
- **armory** — публичная статистика (отдельный клиент)
- **sse** — real-time обновления боя

### Фоновые задачи (ticks)

| Задача | Назначение |
|--------|------------|
| `expedition_tick` | Тики экспедиций, LLM-нарратив |
| `expedition_notify` | DM о завершении экспедиции |
| `gd_v1_round` | Раунды GD, буфер, LLM |
| `guild_tick` | Рейды, войны, muster |
| `guild_war_narrative` | LLM-нарратив войны |
| `chat_rewards_flush` | Сброс буфера наград чата |
| `abyss_daily_reset` / `abyss_weekly_reset` | Сбросы бездны |

### Связанные документы

| Документ | Содержание |
|----------|------------|
| [ARCHITECTURE_AND_INTERACTIONS.md](ARCHITECTURE_AND_INTERACTIONS.md) | Runtime-архитектура |
| [COMBAT_FORMULAS.md](COMBAT_FORMULAS.md) | Боевые формулы (баланс) |
| [technical_spec.md](technical_spec.md) | Техническая спецификация |
