# Cloudflare Worker: прокси для Telegram Bot API

Нужен, если с VPS не открывается `api.telegram.org`, но до Cloudflare доступ есть. Исходящие запросы aiogram идут на Worker; Worker пересылает их на официальный Bot API.

## Вариант A: только редактор Cloudflare (без Wrangler)

1. Открой [`worker-cf-dashboard.js`](worker-cf-dashboard.js), скопируй **весь** файл в **Edit code** своего Worker.
2. **Settings → Variables** у этого Worker: добавь **`ALLOWED_TOKENS`** = твой `BOT_TOKEN` (как в `.env`, строка `123456:ABC...`). Включи **Encrypt**. Несколько ботов — токены через запятую.
3. **Deploy**. В `.env` на VPS: `TELEGRAM_API_BASE_URL=https://<твой-worker>.workers.dev` (без `/` в конце).

Проверка: `curl -sS "https://<host>/bot<TOKEN>/getMe"` → `"ok": true`.

## Безопасность (Wrangler / SECRET_PREFIX)

Задайте **SECRET_PREFIX** — длинную случайную строку (например 32+ символа). URL вида `https://<worker>.workers.dev/<SECRET_PREFIX>` не должен угадываться. Без секрета Worker превратился бы в открытый прокси к Bot API.

## Деплой

1. Установите [Wrangler](https://developers.cloudflare.com/workers/wrangler/) и войдите: `npx wrangler login`
2. В этом каталоге задайте секрет (один раз):

   ```bash
   cd scripts/cloudflare-telegram-proxy
   npx wrangler secret put SECRET_PREFIX
   ```

3. При необходимости измените `name` в `wrangler.toml` (имя Worker в аккаунте CF).
4. Деплой:

   ```bash
   npx wrangler deploy
   ```

5. Запомните выданный URL (например `https://waifu-telegram-api-proxy.<поддомен>.workers.dev`).

## Проверка

Подставьте свой префикс, токен бота и хост Worker:

```bash
curl -sS "https://<YOUR_WORKER_HOST>/<SECRET_PREFIX>/bot<YOUR_BOT_TOKEN>/getMe"
```

Ожидается JSON с `"ok": true`.

## Приложение (VPS)

В `.env`:

```env
TELEGRAM_API_BASE_URL=https://<YOUR_WORKER_HOST>/<SECRET_PREFIX>
```

Без завершающего `/`. Не задавайте `TELEGRAM_BOT_PROXY` для этого сценария (базовый URL имеет приоритет).
