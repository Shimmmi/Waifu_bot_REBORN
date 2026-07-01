# Performance runbook

Operational checklist after the optimizations in `FIX_OPTIMISATION_ANALYSIS.md` / performance implementation plan. Default gameplay is unchanged unless `game_config` flags are set.

## Quick health checks

| Check | Command / signal | Expected |
|-------|------------------|----------|
| API up | `curl -sS https://<host>/health` | 200 |
| Redis | `redis-cli PING` | `PONG` |
| Postgres | app logs, slow query log | no sustained `gd_cycles` full scans on group flood |
| Bot identity | startup log `Telegram bot logged in` | matches bot in group |

## Redis keys to monitor

| Pattern | Meaning | Alert if |
|---------|---------|----------|
| `gd_v1_buf:{cycle_id}` | GD round action buffer | memory spike during busy group; keys not expiring after round |
| `gd_v1_active:{chat_id}` | Cached active cycle id (TTL 45s) | stale solo/GD branch rare; invalidated on status change |
| `player_activity:touch:{user_id}` | Activity debounce (default 300s) | N/A — reduces `players.last_active` commits |
| `chat_reward:buf:*` | Buffered chat rewards | large backlog before flush |
| `bg:lock:*` | Background tick leader locks | all ticks skipped on one host (Redis down → all workers run ticks) |
| `sse:{player_id}` | WebApp pub/sub | subscribers disconnected — clients refetch on reconnect |

## Background loops (single leader)

With multiple uvicorn workers, `background_lock.try_acquire_background_tick` ensures one instance runs each tick. TTL is slightly below the loop interval (e.g. `chat_rewards_flush` 55s lock, 30s interval).

If Redis is unavailable, locks are skipped (same as pre-optimization behavior).

## Feature flags (`game_config`)

| Key | Default | Effect |
|-----|---------|--------|
| `gd_v1_skip_group_solo_while_active` | `0` | `1` — skip solo combat + Abyss in group while GD v1 `active` (raid + chat rewards unchanged) |

Process-local `game_config` cache TTL: 45s. Admin KV changes may take up to TTL unless `invalidate_game_config_cache()` is called.

## PostgreSQL

- **Stuck GD cycles:** `SELECT id, chat_id, status, updated_at FROM gd_cycles WHERE status = 'active' AND updated_at < now() - interval '6 hours';` — investigate or set `done` / use `/gd_v1_test_reset`.
- **Group hot path:** after warm `gd_v1_active` cache, `get_active_v1_cycle` should not hit DB on every message.

## Redis durability (production)

- Enable **AOF** (or RDB + AOF) for chat reward buffers and GD round buffers.
- Consider a **replica** for read failover; writes still go to primary.
- Backup: host cron `scripts/pg_backup.sh` (Postgres), Redis per your host policy.

## LLM and Telegram burst

- `llm_client`: module semaphore (default 2 concurrent `post_chat_completions`).
- GD finale DMs: parallel `send_message` with per-user retry (3 attempts).
- Watch OpenRouter latency during `gd_v1_round` (20s) and expedition ticks.

## WebApp SSE

On `EventSource` error, `app.js` reconnects after 3s and debounces `refreshBattleState` / `loadProfile` (300ms). If UI looks stale after reconnect, confirm hooks exist on battle/profile pages.

## Chat rewards UI

`GET /api/chat-rewards/status` includes `buffer_pending: true` when Redis buffer has unflushed points. Flush interval: **30s** (`CHAT_REWARDS_FLUSH_INTERVAL` in `background.py`). Claim still flushes before wallet update.

## Load / regression tests

```bash
PYTHONPATH=src pytest tests/unit/test_game_config_cache.py \
  tests/unit/test_gd_active_cache.py \
  tests/unit/test_player_activity_debounce.py -q
```

Optional: `test_abyss.py::test_handle_abyss_attack_no_session_skips_for_update`.

## Rollback

| Change | Rollback |
|--------|----------|
| GD active cache | Disable Redis or shorten TTL; SQL path always works on cache miss/failure |
| Activity debounce | Set `PLAYER_ACTIVITY_DEBOUNCE_SECONDS=0` or remove Redis key pattern usage |
| Skip solo while GD | Set `gd_v1_skip_group_solo_while_active=0` |
| Background locks | Redis down → all workers run ticks (pre-plan behavior) |

## Stage 1 (small online) ops

- **PgBouncer + Redis AOF:** [STAGE1_INFRA.md](STAGE1_INFRA.md), `infra/pgbouncer/`, `infra/redis/`
- **Alerts script:** `scripts/check_perf_alerts.sh` (cron every 15 min optional)
- **Index audit:** `scripts/pg_index_audit.sql` after migration `0096_performance_hot_path_indexes`
- **Baseline P95:** `PERF_METRICS_ENABLED=true` for 1–2 weeks; `./scripts/collect_perf_baseline.sh` → `info/perf_metrics_baseline.json`; `./scripts/check_worker_gate.sh`
- **Stage 1 ops cutover:** `./scripts/stage1_ops_cutover.sh` (PgBouncer check, migrate 0096, index audit)
- **WebApp bundle:** `./scripts/build_webapp.sh` → `src/waifu_bot/webapp/bundle/` (minified JS + Vue combat island)
- **Workers gate:** [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md) — `BACKGROUND_MODE`, Dramatiq, [DOCKER.md](DOCKER.md)
- **Stage 2 gate:** [STAGE2_GATE.md](STAGE2_GATE.md)
- **Full stage analysis:** [OPTIMIZATION_STAGES_ANALYSIS.md](OPTIMIZATION_STAGES_ANALYSIS.md)

## Related docs

- [ARCHITECTURE_AND_INTERACTIONS.md](ARCHITECTURE_AND_INTERACTIONS.md) — §11 Redis, §14 performance appendix, §15 ops
- [FIX_OPTIMISATION_ANALYSIS.md](FIX_OPTIMISATION_ANALYSIS.md) — verified findings and priorities
- [GROUP_CHAT_SOLO_AND_GD_DIAGNOSTICS.md](GROUP_CHAT_SOLO_AND_GD_DIAGNOSTICS.md) — group webhook debugging
