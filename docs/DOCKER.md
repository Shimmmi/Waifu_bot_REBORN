# Docker Compose (Stage 1)

Local/staging stack: API + Dramatiq workers + Postgres + PgBouncer + Redis.

## Quick start

```bash
cp .env.example .env
# Set BOT_TOKEN, WEBHOOK_SECRET, OPENROUTER_API_KEY, PUBLIC_BASE_URL

docker compose build
docker compose up -d postgres redis pgbouncer
docker compose run --rm api python -m waifu_bot.cli migrate
docker compose up -d
curl -sS http://127.0.0.1:8000/health
```

## Services

| Service | Role |
|---------|------|
| `api` | FastAPI + webhook (`BACKGROUND_MODE=worker` — no inline loops) |
| `worker` | Dramatiq queue `default` (gameplay ticks) |
| `scheduler` | Enqueues tick actors on interval |
| `llm-worker` | Dramatiq queue `llm` (`LLM_WORKER_ENABLED=true`) |
| `pgbouncer` | Transaction pooling to `postgres` |
| `redis` | AOF enabled |

## CLI equivalents

```bash
docker compose exec api python -m waifu_bot.cli worker -Q default
docker compose exec api python -m waifu_bot.cli worker -Q llm
docker compose exec api python -m waifu_bot.cli scheduler
```

## Production

Prod may stay on **systemd** ([infra/systemd/](../infra/systemd/)) until compose is validated. See [STAGE1_INFRA.md](STAGE1_INFRA.md).

## Related

- [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md)
- [k8s/README.md](../k8s/README.md)
