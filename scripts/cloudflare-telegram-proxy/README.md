# Cloudflare Worker: прокси для Telegram Bot API

Нужен, если с VPS не открывается `api.telegram.org`, но до Cloudflare доступ есть. Исходящие запросы aiogram идут на Worker; Worker пересылает их на официальный Bot API.

## Вариант A: только редактор Cloudflare (без Wrangler)

1. Открой [`worker-cf-dashboard.js`](worker-cf-dashboard.js), скопируй **весь** файл в **Edit code** своего Worker.
2. **Settings → Variables** у этого Worker: добавь **`ALLOWED_TOKENS`** = твой `BOT_TOKEN` (как в `.env`, строка `123456:ABC...`). Включи **Encrypt**. Несколько ботов — токены через запятую.
3. **Deploy**. В `.env` на VPS: `TELEGRAM_API_BASE_URL=https://<твой-worker>.workers.dev` (без `/` в конце).
4. Проверка: `./verify-jwks.sh https://<твой-worker>.workers.dev` — должно быть `OK` для health и JWKS.

Альтернатива (Wrangler): `CLOUDFLARE_API_TOKEN=... ./deploy-dashboard.sh`

Проверка версии Worker (новый код содержит OIDC):

```bash
curl -sS "https://<host>/health"
# ожидается поле: "oauth_jwks":"/oauth/.well-known/jwks.json"
```

Проверка Bot API: `curl -sS "https://<host>/bot<TOKEN>/getMe"` → `"ok": true`.

Проверка OIDC JWKS (Armory login на VPS без доступа к `oauth.telegram.org`):

```bash
curl -sS "https://<host>/oauth/.well-known/jwks.json" | head
```

Ожидается JSON с `"keys": [...]`. После деплоя Worker бэкенд автоматически использует этот URL, если задан `TELEGRAM_API_BASE_URL` (или явно `TELEGRAM_OIDC_JWKS_URL`).

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

### Dashboard Worker (без SECRET_PREFIX в URL)

Если `TELEGRAM_API_BASE_URL=https://waifu.<account>.workers.dev` (как в `.env` без префикса):

```bash
cd scripts/cloudflare-telegram-proxy
npx wrangler login   # один раз
npx wrangler deploy -c wrangler-dashboard.toml
```

Имя Worker в `wrangler-dashboard.toml` (`name = "waifu"`) должно совпадать с subdomain workers.dev.

## Проверка

Подставьте свой префикс, токен бота и хост Worker:

```bash
curl -sS "https://<YOUR_WORKER_HOST>/<SECRET_PREFIX>/bot<YOUR_BOT_TOKEN>/getMe"
```

Ожидается JSON с `"ok": true`.

JWKS (Armory OIDC, Wrangler с SECRET_PREFIX):

```bash
curl -sS "https://<YOUR_WORKER_HOST>/<SECRET_PREFIX>/oauth/.well-known/jwks.json" | head
```

## Приложение (VPS)

В `.env`:

```env
TELEGRAM_API_BASE_URL=https://<YOUR_WORKER_HOST>/<SECRET_PREFIX>
```

Без завершающего `/`. Не задавайте `TELEGRAM_BOT_PROXY` для этого сценария (базовый URL имеет приоритет).

Armory OIDC: JWKS для проверки id_token подтягивается с `{TELEGRAM_API_BASE_URL}/oauth/.well-known/jwks.json` (см. проверку curl выше). Явный override: `TELEGRAM_OIDC_JWKS_URL=...`.
