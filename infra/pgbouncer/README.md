# PgBouncer for Waifu Bot

1. Install: `apt install pgbouncer` (Debian/Ubuntu).
2. Copy `pgbouncer.ini.example` → `/etc/pgbouncer/pgbouncer.ini` and set user/password/database.
3. Copy `userlist.txt.example` → `/etc/pgbouncer/userlist.txt` with `md5` hashes (`pg_md5 -m -u user password`).
4. `systemctl enable --now pgbouncer`
5. Point `POSTGRES_DSN` in `.env` to port **6432** (see [docs/STAGE1_INFRA.md](../../docs/STAGE1_INFRA.md)).

`pool_mode = transaction` is required for asyncpg/SQLAlchemy.
