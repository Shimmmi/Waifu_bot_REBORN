#!/usr/bin/env bash
# Lightweight performance alert checks (Stage 1 ops). Exit 1 if any check fails.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAIL=0
warn() { echo "WARN: $*"; FAIL=1; }
ok() { echo "OK: $*"; }

# Redis
if command -v redis-cli >/dev/null 2>&1; then
  if ! redis-cli PING 2>/dev/null | grep -q PONG; then
    warn "redis-cli PING failed"
  else
    ok "redis PING"
    MEM="$(redis-cli INFO memory 2>/dev/null | awk -F: '/^used_memory:/{gsub(/\r/,"",$2); print $2}')"
    if [[ -n "${MEM:-}" && "${MEM}" -gt 268435456 ]]; then
      warn "redis used_memory > 256MB (${MEM}) — check gd_v1_buf:* and chat_reward:buf:*"
    fi
    AOF="$(redis-cli CONFIG GET appendonly 2>/dev/null | tail -1)"
    if [[ "${AOF:-}" != "yes" ]]; then
      warn "redis appendonly is not yes (current: ${AOF:-unknown})"
    else
      ok "redis AOF enabled"
    fi
  fi
else
  echo "SKIP: redis-cli not installed"
fi

# Postgres stuck GD cycles (requires psql + POSTGRES_DSN or PG* env)
if command -v psql >/dev/null 2>&1; then
  DSN="${POSTGRES_DSN:-}"
  if [[ -z "$DSN" && -f .env ]]; then
    DSN="$(grep -E '^POSTGRES_DSN=' .env | head -1 | cut -d= -f2- | tr -d '"' || true)"
  fi
  if [[ -n "$DSN" ]]; then
    # asyncpg URL -> libpq: postgresql://...
    PQ="${DSN/postgresql+asyncpg/postgresql}"
    STUCK="$(psql "$PQ" -tAc "SELECT count(*) FROM gd_cycles WHERE status = 'active' AND created_at < now() - interval '6 hours'" 2>/dev/null || echo "")"
    if [[ "${STUCK:-}" =~ ^[0-9]+$ && "${STUCK}" -gt 0 ]]; then
      warn "gd_cycles active older than 6h: count=${STUCK}"
    else
      ok "no long-running active gd_cycles (or table unreachable)"
    fi
  fi
fi

# API health
BASE="${PUBLIC_BASE_URL:-http://127.0.0.1:8000}"
if curl -sf "${BASE%/}/health" >/dev/null 2>&1; then
  ok "HTTP /health"
else
  warn "HTTP /health failed at ${BASE%/}/health"
fi

exit "$FAIL"
