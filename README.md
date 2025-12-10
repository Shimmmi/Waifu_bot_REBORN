# Waifu_bot_REBORN

Черновой каркас проекта Telegram бота с WebApp/SSE.

## Стек
- Python 3.11+
- FastAPI (REST + webhook), aiogram 3 (бот)
- Postgres + SQLAlchemy + Alembic
- Redis для сессий/кэша

## Быстрый старт (dev)
1. Создайте `.env` в корне (пример ниже).
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Запуск API: `uvicorn waifu_bot.main:app --reload`
5. При необходимости выставьте вебхук: `python -m waifu_bot.cli webhook`
6. Применить миграции: `python -m waifu_bot.cli migrate`

Пример `.env`:
```
BOT_TOKEN=your_bot_token
WEBHOOK_SECRET=supersecret
PUBLIC_BASE_URL=https://shimmirpgbot.ru
POSTGRES_DSN=postgresql+asyncpg://user:pass@localhost:5432/waifu
REDIS_URL=redis://localhost:6379/0
ADMIN_IDS=305174198
```

## Что есть
- FastAPI приложение с роутером `/api`.
- Webhook endpoint `/api/webhook` с проверкой `X-Webhook-Secret`.
- Заготовка SSE `/api/sse/ping` и сервис `services/sse.py`.
- Инициализация aiogram бота и диспетчера; парсинг Telegram update.
- Базовая настройка логов.
- Подготовка к async Postgres (SQLAlchemy) через `db/session.py`.
- Техническое ТЗ: `docs/technical_spec.md`.

## Что дальше
- Реализовать WebApp HTML/JS для зданий/актов + SSE каналы.
- Добавить CLI/скрипты: установка вебхука, инициализация БД, загрузка справочников.
- Определить миграции Alembic (после установки зависимостей).
- Настроить CI/CD, бэкапы, мониторинг.

