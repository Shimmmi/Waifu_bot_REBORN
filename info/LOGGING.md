# Просмотр логов приложения

Логи по умолчанию выводятся **в терминал (stdout)**. Никакой отдельной настройки не нужно — достаточно запустить приложение и смотреть вывод в консоли.

## Запуск с логами в терминале

Из **корня проекта** (где лежит `pyproject.toml` и `.env`):

```bash
# Вариант 1: скрипт (сам выберет порт 8000 или 8001, если 8000 занят)
bash scripts/run_with_logs.sh
```

```bash
# Вариант 2: вручную (если пакет не установлен — нужен PYTHONPATH)
export PYTHONPATH="$PWD/src"
uvicorn waifu_bot.main:app --reload --host 0.0.0.0 --port 8000
```

Если порт 8000 уже занят (**Address already in use**):

- **Вариант А.** Запустить на другом порту и смотреть логи здесь:
  ```bash
  uvicorn waifu_bot.main:app --reload --host 0.0.0.0 --port 8001
  ```
  (доступ к приложению тогда по адресу с портом 8001; nginx/прокси при необходимости перенастроить на 8001)

- **Вариант Б.** Узнать, кто занял 8000, и смотреть логи того процесса:
  ```bash
  sudo lsof -i :8000
  # или
  ss -tlnp | grep 8000
  ```
  Если это уже ваш waifu-bot (systemd, screen и т.п.) — логи смотреть там (journalctl, вывод screen и т.д.).

- **Вариант В.** Остановить процесс на 8000 и запустить заново в этом терминале:
  ```bash
  sudo fuser -k 8000/tcp
  uvicorn waifu_bot.main:app --reload --host 0.0.0.0 --port 8000
  ```

После запуска откройте магазин в WebApp, нажмите на торговца — в этом же терминале появятся строки с префиксом `[shop merchant-line]`.

## Сохранение логов в файл (опционально)

Через перенаправление вывода:

```bash
uvicorn waifu_bot.main:app --reload --host 0.0.0.0 --port 8000 2>&1 | tee app.log
```

Просмотр в реальном времени и поиск по магазину:

```bash
tail -f app.log
# или только сообщения генерации реплики торговца:
tail -f app.log | grep "shop merchant-line"
```

## Уровень логов

По умолчанию используется **INFO** — этого достаточно, чтобы видеть сообщения `[shop merchant-line]` в терминале.

## 504 Gateway Time-out при генерации портрета наёмницы

Если при повторной генерации вайфу в таверне приходит **504 Gateway Time-out** от nginx, запрос к OpenRouter на генерацию изображения занимает больше времени, чем разрешает прокси.

- Таймаут в коде приложения увеличен до **120 секунд** (httpx в `generate_hire_waifu_image`).
- В nginx для upstream API нужно увеличить `proxy_read_timeout`, например до 120–180 секунд:

```nginx
location /api/ {
    proxy_pass http://backend;
    proxy_read_timeout 120s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 120s;
}
```

После изменений перезагрузите nginx: `sudo nginx -s reload`.

---

## Мониторинг Telegram-обновлений (webhook / polling pipeline)

### Текущий режим: Polling

Бот использует **long-polling** (`.env: TELEGRAM_UPDATE_MODE=polling`) вместо webhook.
Причина: VPS `45.156.21.149` имеет плохую сетевую связность с серверами доставки
Telegram (`91.108.5.5`) — TLS-рукопожатие не завершается из-за потерь пакетов
и RTT > 8 секунд. Polling обходит эту проблему, т.к. бот сам инициирует
исходящие запросы через Cloudflare Worker прокси (`TELEGRAM_API_BASE_URL`).

### Чек-лист при запуске

```bash
# 1. Проверить, что сервис запущен и работает
systemctl is-active waifu-bot

# 2. Проверить режим обновлений в логах
journalctl -u waifu-bot --since "5 min ago" | grep "update mode"
# Ожидаем: "Telegram update mode: polling"

# 3. Проверить, что polling запущен
journalctl -u waifu-bot --since "5 min ago" | grep -i polling
# Ожидаем: "Start polling", "Run polling for bot @shimmi_gacha_bot"

# 4. Проверить identity бота
journalctl -u waifu-bot --since "5 min ago" | grep "bot logged in"
# Ожидаем: "@shimmi_gacha_bot (id=7401283035)"
```

### Мониторинг входящих обновлений

```bash
# Наблюдение за обработкой сообщений в реальном времени
journalctl -u waifu-bot -f | grep -E "telegram.trace|group combat|WEBHOOK_INCOMING"

# Детализация обработки сообщения
journalctl -u waifu-bot -f | grep "update_begin\|update_end"
```

### Диагностические API-эндпоинты

```bash
# Статус вебхука (работает в обоих режимах)
curl -s https://shimmirpgbot.ru/api/webhook/status | python3 -m json.tool
# В polling-режиме url="" и pending_update_count=0

# Принудительная перерегистрация вебхука (только для режима webhook)
# Требует admin-авторизацию через initData
curl -s -X POST "https://shimmirpgbot.ru/api/webhook/re-register?initData=..."
```

### Диагностика nginx (режим webhook)

```bash
# Лог только webhook-запросов
tail -f /var/log/nginx/waifu-webhook.log

# Основной access log
tail -f /var/log/nginx/waifu-bot-access.log | grep webhook

# Error log
tail -f /var/log/nginx/waifu-bot-error.log
```

### Проверка Telegram API

```bash
# Статус вебхука из Telegram
source /opt/waifu-bot-REBORN/.env
curl -s "https://waifu.timurkhazarzhan.workers.dev/bot${BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool

# В режиме polling: url должен быть пустым, pending_update_count=0
# В режиме webhook: url = "https://shimmirpgbot.ru/api/webhook"
```

### Сетевая диагностика

```bash
# Проверка соединений с Telegram
ss -tn | grep -E "91.108|149.154"

# Детали TCP-соединения (RTT, retransmits)
ss -tni dst 91.108.5.5
# RTT > 1000ms или retrans > 0 = сетевые проблемы → использовать polling

# Проверка маршрута
ip route get 91.108.5.5
```

### Переключение режимов

В `.env` изменить `TELEGRAM_UPDATE_MODE`:
- `polling` — бот сам запрашивает обновления (рекомендуется при проблемах с сетью)
- `webhook` — Telegram доставляет обновления на `POST /api/webhook`

После изменения:
```bash
systemctl kill -s SIGKILL waifu-bot && sleep 3 && systemctl start waifu-bot
journalctl -u waifu-bot --since "1 min ago" | grep "update mode"
```

### Env-переменные для диагностики

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_UPDATE_MODE` | `webhook` | `webhook` или `polling` |
| `TELEGRAM_TRACE_LOG` | `true` | Подробные логи каждого update |
| `TELEGRAM_COMMAND_DEBUG_DM` | `false` | Эхо команд в ЛС админам |
| `WEBHOOK_DROP_PENDING` | `true` | Отбросить pending при старте |
| `APP_ENV` | `dev` | `prod` = регистрация webhook/polling |
