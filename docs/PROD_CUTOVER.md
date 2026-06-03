# Prod cutover — Stage 1 (ручные шаги)

Чеклист для VPS (`/opt/waifu-bot-REBORN`). На сервере **нет** команды `python` — используйте **`python3`**, **`alembic`** или **`.venv/bin/python`**.

## Текущий статус (проверка)

```bash
cd /opt/waifu-bot-REBORN
./scripts/setup_pgbouncer_check.sh
alembic current                    # ожидается 0096 (head)
curl -sf http://127.0.0.1:8001/health
systemctl is-active waifu-bot
```

| Шаг | Статус на типичном prod |
|-----|-------------------------|
| Миграция 0096 (индексы) | `alembic upgrade head` — OK |
| PgBouncer на :6432 | Часто **ещё нет** (DSN всё ещё `:5432`) |
| `BACKGROUND_MODE=worker` | Часто **ещё нет** (по умолчанию `inline`) |
| Dramatiq systemd units | Установить из `infra/systemd/` при переходе на workers |

---

## 1. Миграции (уже сделано у вас)

```bash
cd /opt/waifu-bot-REBORN
alembic upgrade head
# или:
PYTHONPATH=src .venv/bin/python -m waifu_bot.cli migrate
```

**Не используйте** `python -m` — будет `command not found` или нет `typer` в системном python3.

```bash
sudo systemctl daemon-reload   # если меняли unit-файлы
sudo systemctl restart waifu-bot
curl -sf http://127.0.0.1:8001/health
```

---

## 2. PgBouncer (опционально, когда будете ставить)

Сейчас Postgres слушает **5432** напрямую. PgBouncer **не обязателен** при одном процессе uvicorn и малом онлайне.

### Установка (Debian/Ubuntu)

```bash
sudo apt install -y pgbouncer
sudo cp infra/pgbouncer/pgbouncer.ini.example /etc/pgbouncer/pgbouncer.ini
# Отредактировать user/password/database под .env
sudo systemctl enable --now pgbouncer
ss -tlnp | grep 6432
```

### Переключение DSN

```bash
cp .env .env.backup.$(date +%F)
# В .env заменить порт 5432 → 6432 (хост 127.0.0.1):
# POSTGRES_DSN=postgresql+asyncpg://USER:PASS@127.0.0.1:6432/waifu_bot_reborn

./scripts/setup_pgbouncer_check.sh
alembic upgrade head    # smoke: одна транзакция
sudo systemctl restart waifu-bot
```

### Откат PgBouncer

Вернуть `POSTGRES_DSN` на `:5432` из `.env.backup.*`, `sudo systemctl restart waifu-bot`.

---

## 3. Пул приложения и метрики (рекомендуется в `.env`)

```env
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_PRE_PING=true
PERF_METRICS_ENABLED=true
```

После правки: `sudo systemctl restart waifu-bot`. Через 1–2 недели смотреть в логах строки `perf_metric summary`.

---

## 4. Redis AOF (рекомендуется)

```bash
redis-cli CONFIG GET appendonly
# Если no — в redis.conf: appendonly yes, appendfsync everysec, затем restart redis
```

---

## 5. Dramatiq workers (опционально, не срочно)

Пока **оставьте** `BACKGROUND_MODE=inline` (или не задавайте) — бот работает как раньше.

Переход на workers только при симптомах из [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md).

### Когда решите включить workers

```bash
cd /opt/waifu-bot-REBORN
.venv/bin/pip install -r requirements.txt   # dramatiq

# В .env:
# BACKGROUND_MODE=worker
# LLM_WORKER_ENABLED=true   # только с llm-worker

sudo cp infra/systemd/waifu-bot-worker.service /etc/systemd/system/
sudo cp infra/systemd/waifu-bot-scheduler.service /etc/systemd/system/
# sudo cp infra/systemd/waifu-bot-llm-worker.service /etc/systemd/system/  # если LLM offload

sudo systemctl daemon-reload
sudo systemctl enable --now waifu-bot-worker waifu-bot-scheduler
# sudo systemctl enable --now waifu-bot-llm-worker

sudo systemctl restart waifu-bot
systemctl is-active waifu-bot waifu-bot-worker waifu-bot-scheduler
```

**Важно:** в `waifu-bot-worker.service` поправьте `User=` и путь к python на `.venv/bin/python`, если не root.

---

## 6. Алерты (cron)

```bash
chmod +x scripts/check_perf_alerts.sh
sudo mkdir -p /var/log/waifu-bot
# crontab -e:
# */15 * * * * /opt/waifu-bot-REBORN/scripts/check_perf_alerts.sh >> /var/log/waifu-bot/perf-alerts.log 2>&1
```

---

## 7. Деплой из git (как обычно)

```bash
./scripts/deploy.sh
# внутри уже: python3 -m waifu_bot.cli migrate
```

---

## Что у вас уже OK

- `setup_pgbouncer_check.sh` → **OK: application DSN** (подключение к БД работает)
- `alembic upgrade head` → **0096** применена
- `/health` → **ok**
- Ошибка `python: command not found` — **не блокер**, миграции через `alembic` или `.venv/bin/python`

---

## Связанные документы

- [STAGE1_INFRA.md](STAGE1_INFRA.md)
- [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md)
- [PERFORMANCE_RUNBOOK.md](PERFORMANCE_RUNBOOK.md)
