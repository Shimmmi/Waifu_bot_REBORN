#!/bin/bash
# Скрипт для перезапуска бота и обновления webhook
# Использование: bash scripts/restart_bot.sh

set -e

echo "🔄 Перезапуск бота..."
sudo systemctl restart waifu-bot.service
sleep 3

echo "✅ Проверка статуса..."
systemctl status waifu-bot.service --no-pager | head -10

echo ""
echo "🔄 Обновление webhook..."
cd /opt/waifu-bot-REBORN
PYTHONPATH=/opt/waifu-bot-REBORN/src:/usr/local/lib/python3.12/dist-packages \
    python3 scripts/update_webhook.py

echo ""
echo "✅ Проверка health endpoint..."
sleep 1
curl -s http://localhost:8001/health && echo "" || echo "⚠️  Health check не прошел"

echo ""
echo "✅ Готово! Бот перезапущен и webhook обновлен."

