#!/bin/bash
# PostgreSQL backup script for Waifu_bot_REBORN
# Run daily at 03:00 via cron

set -e

BACKUP_DIR="/var/backups/waifu"
RETENTION_DAYS=14
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Load environment variables
if [ -f /opt/waifu-bot-REBORN/.env ]; then
    export $(cat /opt/waifu-bot-REBORN/.env | grep -v '^#' | xargs)
fi

# Extract connection details from POSTGRES_DSN
# Format: postgresql+asyncpg://user:pass@host:port/dbname
DB_DSN=${POSTGRES_DSN#postgresql+asyncpg://}
DB_CREDS=${DB_DSN%%@*}
DB_USER=${DB_CREDS%%:*}
DB_PASS=${DB_CREDS#*:}
DB_HOST_PORT=${DB_DSN#*@}
DB_HOST=${DB_HOST_PORT%%:*}
DB_PORT=${DB_HOST_PORT#*:}
DB_PORT=${DB_PORT%%/*}
DB_NAME=${DB_DSN##*/}

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Perform backup
BACKUP_FILE="$BACKUP_DIR/waifu_${TIMESTAMP}.dump"

echo "[$(date)] Starting PostgreSQL backup..."
PGPASSWORD="$DB_PASS" pg_dump -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" \
    --format=custom \
    --compress=9 \
    --file="$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "[$(date)] Backup completed: $BACKUP_FILE"
    
    # Compress with zstd for weekly backups (if it's Sunday)
    if [ $(date +%u) -eq 7 ]; then
        zstd -f "$BACKUP_FILE" -o "${BACKUP_FILE}.zst"
        rm -f "$BACKUP_FILE"
        echo "[$(date)] Weekly backup compressed: ${BACKUP_FILE}.zst"
    fi
else
    echo "[$(date)] ERROR: Backup failed!" >&2
    exit 1
fi

# Cleanup old backups
echo "[$(date)] Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -type f \( -name "*.dump" -o -name "*.dump.zst" \) -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup process completed"

