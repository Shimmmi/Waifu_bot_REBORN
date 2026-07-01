#!/usr/bin/env bash
# Снимает дамп прод-БД, обезличивает персональные данные и восстанавливает
# результат в изолированный staging-контейнер (docker-compose.staging.yml).
#
# Использование (на VPS, рядом с прод-стеком):
#   ./scripts/staging_seed_from_prod_dump.sh
#
# Требования:
#   - прод-стек (docker-compose.yml) уже запущен (сервис postgres/pgbouncer)
#   - staging-стек поднят: docker compose -f docker-compose.staging.yml up -d postgres
#   - переменные окружения PROD_PG_CONTAINER / STAGING_PG_CONTAINER можно переопределить
#
# ВАЖНО: этот скрипт не трогает прод-данные (только читает через pg_dump),
# обезличивание применяется к дампу/staging-копии, прод-БД не модифицируется.

set -euo pipefail

PROD_PG_CONTAINER="${PROD_PG_CONTAINER:-waifu-bot-postgres-1}"
PROD_DB_USER="${PROD_DB_USER:-waifu}"
PROD_DB_NAME="${PROD_DB_NAME:-waifu}"

STAGING_PG_CONTAINER="${STAGING_PG_CONTAINER:-waifu_staging_postgres}"
STAGING_DB_USER="${STAGING_DB_USER:-waifu_staging}"
STAGING_DB_NAME="${STAGING_DB_NAME:-waifu_staging}"

DUMP_FILE="/tmp/waifu_staging_seed_$(date +%Y%m%d_%H%M%S).dump"

echo "[1/4] Снимаю дамп прод-БД ($PROD_PG_CONTAINER/$PROD_DB_NAME) -> $DUMP_FILE"
docker exec "$PROD_PG_CONTAINER" pg_dump -U "$PROD_DB_USER" -Fc "$PROD_DB_NAME" > "$DUMP_FILE"

echo "[2/4] Восстанавливаю дамп в staging-контейнер ($STAGING_PG_CONTAINER/$STAGING_DB_NAME)"
docker exec -i "$STAGING_PG_CONTAINER" pg_restore -U "$STAGING_DB_USER" -d "$STAGING_DB_NAME" --clean --if-exists --no-owner --no-privileges < "$DUMP_FILE" || true

echo "[3/4] Обезличиваю персональные данные в staging-копии"
docker exec "$STAGING_PG_CONTAINER" psql -U "$STAGING_DB_USER" -d "$STAGING_DB_NAME" <<'SQL'
-- Telegram username/имя — не нужны для тестирования игровой логики/Steam-привязки.
UPDATE players SET
    username   = 'staging_user_' || id,
    first_name = 'Staging',
    last_name  = 'Player' || id
WHERE username IS NOT NULL OR first_name IS NOT NULL OR last_name IS NOT NULL;

-- На случай будущих таблиц с email/токенами: расширять этот блок по мере необходимости.
SQL

echo "[4/4] Готово. Локальный файл дампа: $DUMP_FILE (можно удалить вручную после проверки)."
