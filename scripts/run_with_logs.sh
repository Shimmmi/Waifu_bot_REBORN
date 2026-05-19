#!/bin/bash
# Запуск API с логами в терминал. Выбирается первый свободный порт из 8000..8009.
# Из корня проекта: bash scripts/run_with_logs.sh

cd "$(dirname "$0")/.."
export PYTHONPATH="${PWD}/src"

PORT=""
for p in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  if ! ss -tlnp 2>/dev/null | grep -q ":${p} "; then
    PORT=$p
    break
  fi
done

if [ -z "$PORT" ]; then
  echo "Все порты 8000–8009 заняты. Освободите один: sudo fuser -k 8000/tcp"
  exit 1
fi

if [ "$PORT" != "8000" ]; then
  echo "Порты 8000 и др. заняты, запуск на $PORT. Логи в этом терминале."
fi
echo "PYTHONPATH=$PYTHONPATH"
echo "Порт: $PORT"
exec python3 -m uvicorn waifu_bot.main:app --reload --host 0.0.0.0 --port "$PORT"
