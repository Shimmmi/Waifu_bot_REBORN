#!/usr/bin/env bash
# Stage 1 ops checklist: PgBouncer smoke, migrations, index audit (see docs/STAGE1_INFRA.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Stage 1 ops cutover checklist ==="

if [[ -f "$ROOT/scripts/setup_pgbouncer_check.sh" ]]; then
  echo "--- PgBouncer check ---"
  bash "$ROOT/scripts/setup_pgbouncer_check.sh" || echo "WARN: PgBouncer check failed (configure infra/pgbouncer first)"
fi

echo "--- Alembic migrate (0096+ indexes) ---"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
PY="${PYTHON:-}"
if [[ -z "$PY" && -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
if [[ -z "$PY" ]]; then
  PY="python3"
fi
PYTHONPATH=src "$PY" -m waifu_bot.cli migrate

echo "--- Index audit SQL ---"
DSN="${POSTGRES_DSN:-}"
if [[ -z "$DSN" ]]; then
  echo "SKIP: POSTGRES_DSN not set"
else
  PQ="${DSN/postgresql+asyncpg/postgresql}"
  FINDINGS="$ROOT/docs/pg-index-audit/findings/$(date +%Y-%m-%d)-live.md"
  mkdir -p "$(dirname "$FINDINGS")"
  {
    echo "# Index audit — $(date -Iseconds)"
    echo ""
    echo '```'
    psql "$PQ" -f "$ROOT/scripts/pg_index_audit.sql" 2>&1 || true
    echo '```'
  } | tee "$FINDINGS"
  echo "Wrote $FINDINGS"
fi

echo "--- Redis AOF ---"
if command -v redis-cli >/dev/null 2>&1; then
  AOF="$(redis-cli CONFIG GET appendonly 2>/dev/null | tail -1 || true)"
  echo "appendonly=${AOF:-unknown}"
else
  echo "SKIP: redis-cli not installed"
fi

echo "--- Perf alerts ---"
bash "$ROOT/scripts/check_perf_alerts.sh" || true

echo "=== Done. Update POSTGRES_DSN to PgBouncer (127.0.0.1:6432) before prod cutover. ==="
