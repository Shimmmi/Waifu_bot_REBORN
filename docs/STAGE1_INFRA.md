# Этап 1 (малый онлайн): инфраструктура

PgBouncer, Redis persistence и алерты. Код приложения не меняется — только деплой и DSN.

## PgBouncer

### Зачем

Async SQLAlchemy + несколько uvicorn workers создают много соединений к PostgreSQL. PgBouncer (`pool_mode=transaction`) сглаживает churn и снижает риск `too many connections`.

### Пример конфигурации

См. [`infra/pgbouncer/pgbouncer.ini.example`](../infra/pgbouncer/pgbouncer.ini.example) и [`infra/pgbouncer/README.md`](../infra/pgbouncer/README.md).

### DSN приложения

После установки PgBouncer на `127.0.0.1:6432`:

```env
# Было (прямо в Postgres):
# POSTGRES_DSN=postgresql+asyncpg://user:pass@localhost:5432/waifu

# Стало (через PgBouncer):
POSTGRES_DSN=postgresql+asyncpg://user:pass@127.0.0.1:6432/waifu
```

Рекомендуемые лимиты пула в приложении (на worker): `pool_size=5`, `max_overflow=10` — подстроить под `default_pool_size` в PgBouncer.

### Проверка

```bash
./scripts/setup_pgbouncer_check.sh
curl -sS https://<host>/health
```

### Cutover checklist (prod)

1. **Backup:** сохранить текущий `POSTGRES_DSN` (прямой порт 5432) в `.env.backup`.
2. **Install:** PgBouncer по [infra/pgbouncer/README.md](../infra/pgbouncer/README.md); `pool_mode=transaction`.
3. **Staging:** переключить DSN на `127.0.0.1:6432`, `alembic upgrade head`, smoke `/health` + одно групповое сообщение.
4. **Pool app:** `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10` (см. `.env.example`).
5. **Rollback:** вернуть DSN на 5432, `systemctl restart waifu-bot`; PgBouncer можно оставить выключенным.

---

## Redis AOF

### Зачем

Ключи `gd_v1_buf:*`, `chat_reward:buf:*` не дублируются в PG до flush/round end. Потеря Redis без AOF = потеря буферов.

### Пример

[`infra/redis/redis-production.conf.example`](../infra/redis/redis-production.conf.example)

Минимум в `redis.conf`:

```
appendonly yes
appendfsync everysec
```

### Проверка

```bash
redis-cli CONFIG GET appendonly
redis-cli INFO persistence | grep aof
```

---

## Алерты (чеклист)

Используйте [PERFORMANCE_RUNBOOK.md](PERFORMANCE_RUNBOOK.md) и скрипт [`scripts/check_perf_alerts.sh`](../scripts/check_perf_alerts.sh).

| Сигнал | Действие |
|--------|----------|
| Redis `used_memory` рост на `gd_v1_buf:*` | Проверить активные GD, сбросить зависший цикл |
| `gd_cycles.status=active` > 6 ч | SQL из runbook или `/gd_v1_test_reset` |
| Нет `bg:lock:*` renewal + дубли flush в логах | Redis down или все workers skip locks |
| `perf_metric summary` P95 `group_message_damage_ms` > 500 | См. STAGE1_WORKERS_DECISION |
| Postgres connections near max | Включить/настроить PgBouncer |

### Cron (опционально)

```cron
*/15 * * * * /opt/waifu-bot-REBORN/scripts/check_perf_alerts.sh >> /var/log/waifu-perf-alerts.log 2>&1
```

---

## Что не входит в Этап 1 infra

- Dramatiq / отдельный LLM process — [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md)
- Микросервисы — [STAGE2_GATE.md](STAGE2_GATE.md)
