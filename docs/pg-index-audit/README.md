# PostgreSQL index audit project

Formal audit process for hot-path queries (Stage 1 PR2).

## When to run

- After migration `0096_performance_hot_path_indexes`
- Quarterly, or after features touching `gd_cycles`, `dungeon_progress`, `abyss_progress`, expeditions, chat rewards

## Steps

1. `python -m waifu_bot.cli migrate` (includes 0096)
2. `psql "$POSTGRES_URL" -f scripts/pg_index_audit.sql` → save output
3. Fill [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) → store under `findings/YYYY-MM-DD.md`
4. Follow-up indexes only via new Alembic revision (`0097_*`), not ad-hoc prod DDL

## VPS tuning (recommended)

```sql
-- postgresql.conf (requires restart)
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.track = all
log_min_duration_statement = 500
```

## Hot tables

| Table | Primary queries |
|-------|-----------------|
| `gd_cycles` | `get_active_v1_cycle` by `chat_id` + `status=active` |
| `dungeon_progress` | active solo run by `player_id` |
| `abyss_progress` | `has_active_abyss_session` |
| `players` | profile, `last_active` |
| `active_expeditions` | due ticks, notify |
| `player_chat_reward_*` | flush, wallet |

## Related

- [scripts/pg_index_audit.sql](../../scripts/pg_index_audit.sql)
- [alembic/versions/0096_performance_hot_path_indexes.py](../../alembic/versions/0096_performance_hot_path_indexes.py)
