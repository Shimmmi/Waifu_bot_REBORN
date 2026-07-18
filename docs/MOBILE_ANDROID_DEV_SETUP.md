# Mobile Android (Activity) — developer setup

## Branch policy (critical)

| Track | Branch | Purpose |
|-------|--------|---------|
| Android / activity | **`feature/mobile-android`** | Capactor APK, activity API, dual economy |
| Telegram prod | `main` / `webapp-perf-prod` / etc. | Do not land activity migrations here casually |
| Steam desktop | `feature/steam-client` (ancestor) | Electron; combat aligned via activity claim |

**Rule:** all Android/activity commits stay on `feature/mobile-android` until an explicit merge PR. Cherry-picks into Telegram branches only when approved.

### Cursor / disk layout (same pattern as Steam)

| Path | Branch | Purpose |
|------|--------|---------|
| `/opt/waifu-bot-REBORN` | Telegram (`webapp-perf-prod` / `main`) | prod / TG |
| `/opt/waifu-bot-steam-client` | `feature/steam-client` | Electron / Steam |
| `/opt/waifu-bot-mobile-client` | `feature/mobile-android` | Capacitor / Android + activity API |

Prefer a **git worktree** from REBORN (one `.git`, shared history):

```bash
cd /opt/waifu-bot-REBORN
git fetch origin
git checkout webapp-perf-prod   # keep TG checkout off mobile
git worktree add /opt/waifu-bot-mobile-client feature/mobile-android
```

Open Cursor on `/opt/waifu-bot-mobile-client` for Android/activity work — do not mix with Telegram edits in REBORN.

```bash
git fetch origin
git checkout feature/mobile-android
git pull origin feature/mobile-android
```

Remote: `origin/feature/mobile-android` (created for isolation from Telegram).


## Prod isolation (critical)

- **Prod Telegram API** runs only from `/opt/waifu-bot-REBORN` (`webapp-perf-prod` / `main`). Never checkout `feature/mobile-android` there.
- **Activity/mobile work** stays in `/opt/waifu-bot-mobile-client`. Apply `0129_activity_economy` on **staging** only.
- Do not merge this branch into `main` until perfection (`0121_player_perfection` … `0125_…`) is verified present and activity migrations sit after `0125` (0126–0129).

## Backend

```bash
# on staging DB only — never apply 0129_activity_economy to prod Telegram by accident
alembic upgrade head   # includes 0129_activity_economy

docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

Env:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` | Google Sign-In audience (prod) |
| `DESKTOP_SESSION_SECRET` | JWT for `X-Desktop-Session` |
| `APP_ENV=stage` | enables `google_sub_dev` stubs |
| `WAIFU_MOBILE_BACKEND_URL` | used by Capacitor `server.url` / smoke scripts |

## Local PC: Windows → first debug APK

Целевой путь: **Windows 11 + Git Bash** (`npm run android:*` — bash-скрипты; проверка env также через `mobile_client/scripts/check_android_dev_env.ps1`). На macOS/Linux те же `npm`-команды после установки пакетов; пути SDK другие.

Краткий индекс: [mobile_client/README.md](../mobile_client/README.md).

Жёсткие ограничения:

- Код — ветка **`feature/mobile-android`** (merge main + `0129_activity_economy`).
- APK **не собирать на VPS** (на VPS нет Android SDK).
- Backend для WebView — **staging** с миграцией `0129`; не применять `0129` к prod DB.
- Prod Telegram остаётся в `/opt/waifu-bot-REBORN` на `webapp-perf-prod`.

### 0. Что получится в конце

Файл:

`mobile_client/android/app/build/outputs/apk/debug/app-debug.apk`

Package id: `ru.shimmirpgbot.waifu.activity`

При сборке `WAIFU_MOBILE_BACKEND_URL` прописывается в `capacitor.config.json` → WebView открывает:

`{BACKEND}/webapp/activity.html?mobileClient=1&economy=activity`

(см. `mobile_client/scripts/write_capacitor_config.js`).

### 1. Установить базовое ПО

#### 1.1. Git for Windows (обязательно)

1. Скачать: https://git-scm.com/download/win
2. Установить с опцией **Git Bash**.
3. Проверка в Git Bash:

```bash
git --version
bash --version
```

Все дальнейшие команды — в **Git Bash**, не в cmd.

#### 1.2. Node.js 20 LTS

1. Скачать LTS 20.x: https://nodejs.org/
2. Установить с «Add to PATH».
3. Проверка:

```bash
node -v   # v20.x или выше
npm -v
```

#### 1.3. JDK 17 (Temurin)

1. Adoptium Temurin 17 (Windows x64 MSI): https://adoptium.net/
2. В установщике: **Set JAVA_HOME**, **Add to PATH**.
3. Проверка:

```bash
java -version   # должна быть 17 (или 21)
echo "$JAVA_HOME"
```

Если `java` есть, а `JAVA_HOME` пустой — задать вручную (см. §2).

#### 1.4. Android Studio

1. Скачать: https://developer.android.com/studio
2. Установить; в Wizard отметить:
   - Android SDK
   - Android SDK Platform
   - Android Virtual Device (по желанию; для первого APK достаточно телефона)
3. После первого запуска: **More Actions → SDK Manager** (или Settings → Languages & Frameworks → Android SDK).

В вкладке **SDK Platforms** установить:

- **Android 14.0 (API 34)** — checkbox «Android SDK Platform 34»

В **SDK Tools** установить:

- Android SDK Build-Tools **34.0.x**
- Android SDK Platform-Tools (`adb`)
- Android SDK Command-line Tools (latest)

Проект: `compileSdk` / `targetSdk` = 34, `minSdk` = 22 (`mobile_client/android/variables.gradle`).

Типичный путь SDK на Windows:

`C:\Users\<YOU>\AppData\Local\Android\Sdk`

### 2. Переменные окружения Windows

**Параметры системы → Дополнительные → Переменные среды** (или `Win+R` → `sysdm.cpl`):

| Имя | Значение (пример) |
|-----|-------------------|
| `JAVA_HOME` | `C:\Program Files\Eclipse Adoptium\jdk-17.x.x-hotspot` |
| `ANDROID_HOME` | `C:\Users\<YOU>\AppData\Local\Android\Sdk` |

В **Path** пользователя добавить:

- `%JAVA_HOME%\bin`
- `%ANDROID_HOME%\platform-tools`
- `%ANDROID_HOME%\cmdline-tools\latest\bin` (если есть)

Закрыть и заново открыть Git Bash, затем:

```bash
echo "$ANDROID_HOME"
adb version
sdkmanager --version   # если cmdline-tools в PATH
```

Если `ANDROID_HOME` в Git Bash пустой при том, что в Windows задан — экспортировать на сессию:

```bash
export ANDROID_HOME="/c/Users/<YOU>/AppData/Local/Android/Sdk"
export PATH="$ANDROID_HOME/platform-tools:$PATH"
```

Постоянно для Git Bash — дописать те же `export` в `~/.bashrc`.

### 3. Клонировать репозиторий на ноутбуке

Не worktree с VPS — обычный clone на диск ноутбука:

```bash
cd /c/dev   # или любая папка
git clone git@github.com:Shimmmi/Waifu_bot_REBORN.git waifu-bot-mobile
cd waifu-bot-mobile
git fetch origin
git checkout feature/mobile-android
git pull origin feature/mobile-android
```

Проверка, что на месте:

```bash
ls mobile_client/android/gradlew
ls mobile_client/package.json
test -f alembic/versions/0129_activity_economy.py && echo "0129 OK"
test -f alembic/versions/0121_player_perfection.py && echo "perfection migration OK"
```

`android/` уже в ветке — `cap add android` обычно не нужен; `android:setup` сделает `npm ci` + sync + plugin.

### 4. Указать staging backend

Нужен **HTTPS-хост staging** с кодом `feature/mobile-android` и БД на `0129_activity_economy`.

В Git Bash (подставить реальный URL):

```bash
export WAIFU_MOBILE_BACKEND_URL="https://<staging-host>"
```

Без переменной скрипт сборки подставит `https://shimmirpgbot.ru` — для первого debug APK лучше явно staging.

Проверка с ноутбука:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "$WAIFU_MOBILE_BACKEND_URL/health"
```

Ожидаемо `200` (или иной успешный ответ health).

### 5. One-time setup проекта

```bash
cd /c/dev/waifu-bot-mobile/mobile_client

# 5.1 Проверка окружения
npm run android:env
# Windows PowerShell альтернатива:
# powershell -File scripts/check_android_dev_env.ps1
```

Ожидание: `[OK]` для Node, Java, `ANDROID_HOME`, adb; в конце `Environment check PASSED.`

Если FAIL — не продолжать, починить §1–2.

```bash
# 5.2 Генерация/sync android + StepCounter + BridgeLoader
npm run android:setup
```

Что делает `scripts/setup_android_project.sh`:

1. `npm ci`
2. Пишет `capacitor.config.json` из `WAIFU_MOBILE_BACKEND_URL`
3. Готовит `www/` + `bridge.js`
4. `npx cap sync android` (или `cap add android`, если папки нет)
5. Копирует `WaifuStepCounterPlugin`, пишет `BridgeLoader` / `MainActivity`
6. Добавляет `ACTIVITY_RECOGNITION` в манифест

Первый запуск Gradle может скачать зависимости — нужен интернет, 5–15 минут.

### 6. Сборка первого debug APK

```bash
cd /c/dev/waifu-bot-mobile/mobile_client
export WAIFU_MOBILE_BACKEND_URL="https://<staging-host>"
export ANDROID_HOME="/c/Users/<YOU>/AppData/Local/Android/Sdk"
export PATH="$ANDROID_HOME/platform-tools:$PATH"

npm run android:apk
```

Скрипт `scripts/build_debug_apk.sh`: env-check → `npm ci` → config/www → `cap sync` → `./gradlew assembleDebug`.

Успех:

```text
[OK] Debug APK: .../android/app/build/outputs/apk/debug/app-debug.apk
```

APK можно скопировать на телефон вручную; для adb — §7.

### 7. Установка на устройство

1. На телефоне: **Параметры → О телефоне → 7× по номеру сборки** → Developer options.
2. Включить **USB debugging**.
3. Кабель USB → разрешить отладку на телефоне.
4. В Git Bash:

```bash
adb devices
# должна быть строка: <serial>    device
# если "unauthorized" — подтвердить диалог на телефоне

npm run android:install
# или: adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Запуск:

```bash
adb shell am start -n ru.shimmirpgbot.waifu.activity/.MainActivity
# или: npm run android:smoke
```

Эмулятор: Device Manager в Android Studio → Create Device → API 34 → Start; затем те же `adb` / `android:install`.

### 8. Минимальная проверка после установки

1. Приложение открывается; отказ в Activity Recognition — без краша.
2. WebView грузит activity page с staging (не белый экран / не «сайт недоступен» — иначе проверить URL/сеть/сертификат).
3. Backend-only без телефона (если есть link code):

```bash
export WAIFU_MOBILE_BACKEND_URL="https://<staging-host>"
export WAIFU_LINK_CODE="<from POST /api/auth/link_code>"
npm run android:api-smoke
```

Полный checklist: [MOBILE_ANDROID_SMOKE.md](MOBILE_ANDROID_SMOKE.md).

### 9. Типичные ошибки

| Симптом | Что сделать |
|---------|-------------|
| `ANDROID_HOME not set` | §2 + `export` в Git Bash |
| `java not found` / wrong version | JDK 17, `JAVA_HOME` |
| Gradle `SDK location not found` | `mobile_client/android/local.properties` с `sdk.dir=C:\\Users\\...\\Android\\Sdk` (часто создаёт Studio / `cap sync`) |
| `No adb device` | USB debugging, кабель data, `adb kill-server && adb start-server` |
| WebView не грузит | `WAIFU_MOBILE_BACKEND_URL`, HTTPS, `allowNavigation`, пересобрать APK после смены URL |
| Permission / pedometer | на эмуляторе шаги могут быть stub; реальный телефон надёжнее |

### 10. Что сознательно не делать на этом шаге

- Не мержить `feature/mobile-android` в `main` / не переключать prod Telegram service на mobile worktree.
- Не запускать `alembic upgrade` с ноутбука на **prod** DSN.
- Не нужен release keystore для первого debug APK (`android:signing` / `android:release` — позже, Play Internal).

## Key API

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/auth/link_code` | Telegram → one-time code |
| POST | `/api/auth/mobile/google` | Google login + optional link_code |
| GET | `/api/activity/status` | buffer, min_chars, starter dagger |
| POST | `/api/activity/input/claim` | steps/clicks → TEXT hits |
| POST | `/api/dungeons/{id}/start?economy=activity` | activity run |
| GET | `/api/inventory?economy=activity` | activity bag |
| POST | `/api/pc/hits/batch` | Steam → same activity claim |

## Combat model

- 1 step (mobile) = 1 click (Steam) = 1 TEXT character
- Weapon `attack_speed` → `min_chars`
- Chunk mode default `fill_cap` (up to 200 units/hit)
- No media types / no tap-to-hit on mobile

## Device smoke checklist

See [MOBILE_ANDROID_IMPLEMENTATION_STATUS.md](MOBILE_ANDROID_IMPLEMENTATION_STATUS.md) and `mobile_client` scripts `android:smoke` / `android:api-smoke`.
