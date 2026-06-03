# Index audit report — YYYY-MM-DD

**Environment:** staging | prod  
**Migration baseline:** 0096_performance_hot_path_indexes (yes/no)  
**Auditor:**

## Summary

- [ ] EXPLAIN hot paths use Index Scan (not Seq Scan on representative data volume)
- [ ] No unexpected duplicate indexes
- [ ] Follow-up migration needed: yes / no

## gd_cycles

**Query:** active cycle by chat_id

```
(paste EXPLAIN from pg_index_audit.sql)
```

**Verdict:**

## dungeon_progress

**Query:** active run by player_id

**Verdict:**

## abyss_progress

**Query:** session_active by player_id

**Verdict:**

## pg_stat_statements (if enabled)

| Query (truncated) | calls | mean_ms | total_ms | recommendation |
|-------------------|-------|---------|----------|----------------|
| | | | | |

## Actions

| Priority | Action | Alembic revision |
|----------|--------|------------------|
| P1 | | |
| P2 | | |
