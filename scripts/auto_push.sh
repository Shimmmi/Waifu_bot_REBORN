#!/bin/bash
# Auto-push script for Waifu_bot_REBORN
# Run daily at 00:00 MSK via cron

set -e

REPO_DIR="/opt/waifu-bot-REBORN"
LOG_FILE="/var/log/waifu-bot/auto_push.log"

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cd "$REPO_DIR" || exit 1

log "Starting auto-push process..."

# Check if there are uncommitted changes
if [ -n "$(git status --porcelain)" ]; then
    log "Uncommitted changes detected, committing..."
    
    # Pull latest changes first
    git pull --rebase origin main || {
        log "ERROR: Failed to pull changes. Skipping push to avoid conflicts."
        exit 1
    }
    
    # Add all changes
    git add -A
    
    # Commit with timestamp
    COMMIT_MSG="auto-push $(date -Iseconds)"
    git commit -m "$COMMIT_MSG" || {
        log "WARNING: Nothing to commit (changes may have been pulled)"
    }
    
    # Push to remote
    if git push origin main; then
        log "Successfully pushed changes to GitHub"
    else
        log "ERROR: Failed to push to GitHub"
        exit 1
    fi
else
    log "No uncommitted changes, pulling latest..."
    git pull --rebase origin main || {
        log "WARNING: Failed to pull changes"
    }
fi

log "Auto-push process completed"

