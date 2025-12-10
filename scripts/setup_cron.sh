#!/bin/bash
# Setup cron jobs for backups and auto-push

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="/opt/waifu-bot-REBORN"

# Make scripts executable
chmod +x "$SCRIPT_DIR/pg_backup.sh"
chmod +x "$SCRIPT_DIR/auto_push.sh"

# Backup cron job (03:00 daily)
BACKUP_CRON="0 3 * * * $SCRIPT_DIR/pg_backup.sh >> /var/log/waifu-bot/backup.log 2>&1"

# Auto-push cron job (00:00 MSK = 21:00 UTC previous day)
# Note: Adjust timezone if server is not in UTC
AUTO_PUSH_CRON="0 0 * * * TZ='Europe/Moscow' $SCRIPT_DIR/auto_push.sh"

# Remove existing cron jobs for these scripts
(crontab -l 2>/dev/null | grep -v "$SCRIPT_DIR/pg_backup.sh" | grep -v "$SCRIPT_DIR/auto_push.sh") | crontab -

# Add new cron jobs
(crontab -l 2>/dev/null; echo "$BACKUP_CRON"; echo "$AUTO_PUSH_CRON") | crontab -

echo "Cron jobs installed:"
echo "  - PostgreSQL backup: 03:00 daily"
echo "  - Auto-push to GitHub: 00:00 MSK daily"
crontab -l | grep -E "(pg_backup|auto_push)"

