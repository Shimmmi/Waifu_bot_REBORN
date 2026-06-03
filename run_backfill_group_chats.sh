#!/bin/bash
# Backfill bot_group_chats from historical sources (run migrate 0095 first).
set -euo pipefail
cd /opt/waifu-bot-REBORN
if [ -f .venv/bin/python ]; then
  exec .venv/bin/python run_backfill_group_chats.py "$@"
fi
exec python3 run_backfill_group_chats.py "$@"
