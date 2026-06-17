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

**⚠️ ВАЖНО**: Создайте `.env` файл на основе `.env.example`. НИКОГДА не коммитьте реальный `.env` файл в git!

Пример `.env` (см. `.env.example` для полного списка):
```
BOT_TOKEN=your_bot_token
WEBHOOK_SECRET=supersecret
PUBLIC_BASE_URL=https://shimmirpgbot.ru
POSTGRES_DSN=postgresql+asyncpg://user:pass@localhost:5432/waifu
REDIS_URL=redis://localhost:6379/0
ADMIN_IDS=305174198
```

## Безопасность

🔒 **Критически важно**: Перед коммитом проверьте код на наличие токенов:
```bash
python scripts/check_secrets.py
```

Подробности: см. [SECURITY.md](SECURITY.md)

## Armory (браузерная статистика)

Портал WoW Armory-подобной статистики: **https://shimmirpgbot.ru/armory**

- Публичные профили, рейтинги, поиск игроков
- Telegram Login (OIDC popup через `telegram-login.js`) для приватных данных (инвентарь, история, характеристики)
- Админ-панель: `/armory/admin` (список игроков, вайп, бан, выдача gold)

### Настройка

1. В `.env` добавьте (см. `.env.example`):
   - `ARMORY_SESSION_SECRET` — `python -c "import secrets; print(secrets.token_hex(32))"`
   - `ARMORY_COOKIE_DOMAIN=.shimmirpgbot.ru`
   - `ARMORY_PUBLIC_ORIGIN=https://shimmirpgbot.ru`
   - `BOT_USERNAME=YourBotName` (без @)
2. В @BotFather: **Bot Settings → Web Login** (режим Telegram Login Library / OpenID):
   - **Trusted Origins** — только origin: `https://shimmirpgbot.ru` (путь после `.ru` сюда не добавляется)
   - **Redirect URIs** — полный URL страницы логина: `https://shimmirpgbot.ru/armory/login` (должен совпадать с URL в браузере 1:1)
   На странице `/armory/login` показан точный Redirect URI для копирования в BotFather.
   Client Secret для popup/post_message не нужен.
   На VPS без прямого доступа к `oauth.telegram.org` задайте `TELEGRAM_API_BASE_URL` (Cloudflare Worker) — JWKS для проверки JWT подтянется через Worker автоматически. Обновите код Worker и задеployьте (см. `scripts/cloudflare-telegram-proxy/`).
3. Миграции: `PYTHONPATH=src python -m waifu_bot.cli migrate` (на VPS: `./run_migrate.sh`)
4. Backfill групповых чатов (Armory admin): `./run_backfill_group_chats.sh`
5. Сборка фронта:
   ```bash
   cd armory_frontend && npm ci && npm run build
   ```
   Результат в `static/armory/`.

API: `/api/armory/*` (отдельно от Telegram WebApp `/webapp`).

## Что есть
- FastAPI приложение с роутером `/api`.
- Webhook endpoint `/api/webhook` с проверкой `X-Webhook-Secret`.
- Заготовка SSE `/api/sse/ping` и сервис `services/sse.py`.
- Инициализация aiogram бота и диспетчера; парсинг Telegram update.
- Базовая настройка логов.
- Подготовка к async Postgres (SQLAlchemy) через `db/session.py`.
- Техническое ТЗ: `docs/technical_spec.md`.
- **Полная архитектура и цепочки взаимодействий (EN):** `docs/ARCHITECTURE_AND_INTERACTIONS.md` — runtime reference for performance and operability analysis.
- **GAME_AGENT_BRIEF (RU):** `docs/GAME_AGENT_BRIEF.md` — презентационный бриф игровых механик для ИИ-агента и миграции WebApp → Steam. Сборка: `PYTHONPATH=src python3 scripts/build_game_agent_brief.py --preset expert --resume`.
- **Сверка FIX_OPTIMISATION с кодом (RU):** `docs/FIX_OPTIMISATION_ANALYSIS.md` — верификация 12 пунктов производительности и выводы.
- **Performance runbook (EN):** `docs/PERFORMANCE_RUNBOOK.md` — мониторинг Redis/GD, флаги `game_config`, откат оптимизаций.
- **Этапы оптимизации (RU):** `docs/OPTIMIZATION_STAGES_ANALYSIS.md` — Этап 1 (малый онлайн) и анализ Этапа 2; `docs/STAGE1_INFRA.md`, `docs/STAGE1_WORKERS_DECISION.md`, `docs/STAGE2_GATE.md`.
- **Docker / workers:** `docs/DOCKER.md`, `docker-compose.yml`, `infra/systemd/`, `k8s/README.md`.
- **Prod cutover (RU):** `docs/PROD_CUTOVER.md` — миграции, PgBouncer, workers на VPS.

## Что дальше
- Реализовать WebApp HTML/JS для зданий/актов + SSE каналы.
- Добавить CLI/скрипты: установка вебхука, инициализация БД, загрузка справочников.
- Определить миграции Alembic (после установки зависимостей).
- Настроить CI/CD, бэкапы, мониторинг.

