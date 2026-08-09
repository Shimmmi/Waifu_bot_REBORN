# Mobile ↔ Telegram: вход и привязка

Два пути (приоритет сверху вниз).

## 1) Основной — «Войти через Telegram» в APK

Экран: `/webapp/mobile/login.html` → кнопка **Войти через Telegram**.

### Capacitor APK (native)

Popup/`post_message` на Android уходит во внешний браузер и не возвращает токен в WebView. Поэтому APK использует **authorization code + PKCE** внутри WebView:

1. `GET /api/auth/desktop/login-url?client=mobile`
2. Redirect на `oauth.telegram.org/auth?response_type=code&…&code_challenge=…`
3. После confirm Telegram возвращает на  
   `https://…/webapp/mobile/login.html?code=…&state=…` (в APK, не в Chrome)
4. `POST /api/auth/desktop/telegram/code` `{ code, redirect_uri, code_verifier }`  
   → server exchange у Telegram → `id_token` → desktop session
5. Токен в `localStorage` / `waifuMobile` → `/webapp/mobile/shell.html`

Нужно в `.env.staging` / prod:

```bash
TELEGRAM_OIDC_CLIENT_ID=7401283035
TELEGRAM_OIDC_CLIENT_SECRET=<Client Secret из BotFather → Web Login>  # НЕ bot token
# VPS часто не достучится до oauth.telegram.org — обмен code идёт через CF Worker:
TELEGRAM_API_BASE_URL=https://waifu.timurkhazarzhan.workers.dev
```

Без `TELEGRAM_OIDC_CLIENT_SECRET` endpoint отвечает `503 telegram_oidc_client_secret_not_configured`.

Worker должен проксировать **POST** `/oauth/token` → `https://oauth.telegram.org/token`  
(см. `scripts/cloudflare-telegram-proxy/worker-cf-dashboard.js`). После обновления Worker — Redeploy в Cloudflare.

Capacitor: `allowNavigation` включает `oauth.telegram.org`; в `AndroidManifest` есть VIEW intent на `/webapp/mobile/login` (stage + prod), если ОС всё же откроет браузер.

**Пересборка APK обязательна** после смены `capacitor.config` / manifest (`npm run android:setup` / `android:apk`, переустановка).

### Browser / Desktop (не APK)

Как Armory: popup `response_type=post_message` → `POST /api/auth/desktop/telegram` с `id_token`. Client Secret не нужен.

### BotFather — Trusted Origins **и** Redirect URIs

В [@BotFather](https://t.me/BotFather) → бот → **Bot Settings → Web Login** (OpenID). Нужны **два разных** поля + Client Secret:

| Поле | Staging | Production |
|------|---------|------------|
| **Trusted Origins** | `https://stage.shimmirpgbot.ru` | `https://shimmirpgbot.ru` |
| **Redirect URIs** | `https://stage.shimmirpgbot.ru/webapp/mobile/login.html` | `https://shimmirpgbot.ru/webapp/mobile/login.html` |
| **Client Secret** | в `TELEGRAM_OIDC_CLIENT_SECRET` на API | то же на prod API |

Только Redirect URI **недостаточно**. Если origin не в Trusted Origins, Telegram показывает misleading **«Bot ID required»**.

Также можно держать Steam/Armory URI:

- `https://stage.shimmirpgbot.ru/webapp/steam/login.html`
- `https://shimmirpgbot.ru/webapp/steam/login.html`
- `https://shimmirpgbot.ru/armory/login`

### Staging: dummy `BOT_TOKEN` + OIDC

На stage `BOT_TOKEN` — заглушка (`0000000000:...`), чтобы не перехватить prod webhook:

```bash
TELEGRAM_OIDC_CLIENT_ID=7401283035
TELEGRAM_OIDC_CLIENT_SECRET=...   # из BotFather Web Login
```

## 2) Запасной — код из профиля Telegram

1. Откройте WebApp в Telegram (stage или prod).
2. **Профиль → ☰ → «Код для Mobile / Steam»**  
   или **Игрок → Настройки → «Код для Mobile / Steam»**.
3. «Получить код» → «Скопировать» (TTL ~10 мин).
4. В APK: раскрыть «Запасной вход» → вставить код → «Войти с кодом».

Deep-link: `/webapp/mobile_link.html`.

API: `POST /api/auth/link_code` → на stage `POST /api/auth/mobile/google` с `link_code` + `google_sub_dev`.

## Краткий DoD

- [ ] Trusted Origin + Redirect URI + Client Secret настроены
- [ ] Stage API с `TELEGRAM_OIDC_CLIENT_SECRET`, пересобран
- [ ] APK пересобран/переустановлен (allowNavigation + intent-filters)
- [ ] Из APK: confirm в Telegram → возврат в приложение → shell
- [ ] Код-path на stage всё ещё работает
