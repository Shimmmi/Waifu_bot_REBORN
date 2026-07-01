#!/usr/bin/env bash
# Verify PgBouncer connectivity and pool stats (Stage 1 PR1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PGB_HOST="${PGBOUNCER_HOST:-127.0.0.1}"
PGB_PORT="${PGBOUNCER_PORT:-6432}"
DB_NAME="${PGBOUNCER_DATABASE:-waifu}"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source <(grep -E '^POSTGRES_DSN=' .env | sed 's/^/export /') || true
fi

if [[ -n "${POSTGRES_DSN:-}" ]]; then
  PQ="${POSTGRES_DSN/postgresql+asyncpg/postgresql}"
  echo "==> psql via POSTGRES_DSN"
  psql "$PQ" -c "SELECT 1 AS ok" || { echo "FAIL: cannot connect via POSTGRES_DSN"; exit 1; }
  echo "OK: application DSN"
else
  echo "WARN: POSTGRES_DSN not set — set in .env or export POSTGRES_DSN"
fi

if command -v psql >/dev/null 2>&1 && [[ -n "${PGBOUNCER_TEST_URL:-}" ]]; then
  echo "==> psql via PGBOUNCER_TEST_URL"
  psql "$PGBOUNCER_TEST_URL" -c "SELECT 1"
fi

if command -v psql >/dev/null 2>&1; then
  ADMIN="${PGBOUNCER_ADMIN_URL:-postgresql://postgres@127.0.0.1:6432/pgbouncer}"
  if psql "$ADMIN" -c "SHOW POOLS" 2>/dev/null; then
    echo "OK: SHOW POOLS"
  else
    echo "SKIP: admin psql to pgbouncer (set PGBOUNCER_ADMIN_URL if needed)"
  fi
fi

if ss -tlnp 2>/dev/null | grep -q ':6432 '; then
  echo "OK: something listens on 6432 (PgBouncer?)"
else
  echo "NOTE: port 6432 not listening — PgBouncer not installed yet; DSN may still use :5432 (OK for small prod)"
fi

echo "==> done (host=${PGB_HOST} port=${PGB_PORT} db=${DB_NAME})"
echo "Migrate: alembic upgrade head  OR  PYTHONPATH=src .venv/bin/python -m waifu_bot.cli migrate"
