-- Stage 1: PostgreSQL index audit for hot paths (read-only).
-- Run: psql "$POSTGRES_URL" -f scripts/pg_index_audit.sql

\echo '=== Existing indexes on hot tables ==='
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'gd_cycles', 'dungeon_progress', 'abyss_progress', 'players',
    'active_expeditions', 'player_chat_reward_wallets'
  )
ORDER BY tablename, indexname;

\echo '=== gd_cycles: active cycle by chat (expect ix_gd_cycles_chat_id_status_active) ==='
EXPLAIN (COSTS OFF)
SELECT id FROM gd_cycles WHERE chat_id = -100123 AND status = 'active' LIMIT 1;

\echo '=== dungeon_progress: active run by player ==='
EXPLAIN (COSTS OFF)
SELECT id FROM dungeon_progress WHERE player_id = 1 AND is_active = true LIMIT 1;

\echo '=== abyss_progress: active session by player ==='
EXPLAIN (COSTS OFF)
SELECT session_active FROM abyss_progress WHERE player_id = 1 AND session_active = true LIMIT 1;

\echo '=== Optional: pg_stat_statements top queries (if extension enabled) ==='
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
WHERE query ILIKE '%gd_cycles%'
   OR query ILIKE '%dungeon_progress%'
   OR query ILIKE '%abyss_progress%'
ORDER BY total_exec_time DESC
LIMIT 10;
