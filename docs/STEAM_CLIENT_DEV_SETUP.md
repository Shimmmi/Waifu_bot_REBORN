# Steam-клиент: гайд разработчика — от git clone до запуска .exe

Самодостаточная пошаговая инструкция для разработчика на **своей машине**
(не VPS — см. "Почему не VPS" ниже). Цель: довести окружение до состояния
"собранный установщик/`.exe` реально запускается и показывает прозрачный
оверлей вайфу поверх рабочего стола".

Это практическое руководство "по шагам"; фоновые архитектурные решения и
чек-лист для реального Steamworks-аккаунта — в
[`docs/STEAM_STEAMWORKS_SETUP.md`](STEAM_STEAMWORKS_SETUP.md) и
[`desktop_client/README.md`](../desktop_client/README.md).

## Почему не VPS

Прод/staging-сервер headless (нет дисплея) и уже ограничен по месту на
диске. `npm start`/`npm run dev` у Electron требует реального дисплея,
чтобы вообще показать окно, а нативная сборка `uiohook-napi` (и позже
Steamworks SDK) тянет за собой toolchain, которому нечего делать на общем
сервере. Всё, что ниже, выполняется на обычном Windows/macOS/Linux ПК с
монитором.

## Шаг 0 — предварительные требования

Установить на машину разработчика:

| Что | Зачем | Проверка (Windows) | Проверка (macOS/Linux) |
|---|---|---|---|
| **Git** | клонировать репозиторий | `git --version` | `git --version` |
| **Node.js LTS** (20.x или новее) + npm | Electron, electron-builder | `node --version`, `npm --version` | то же |
| **Python 3.11+** | `node-gyp` для сборки `uiohook-napi` | `python --version` | `python3 --version` |
| **Компилятор C/C++** (см. ниже по ОС) | `node-gyp` компилирует `uiohook-napi` при `npm install` | — | — |
| **Docker Desktop** | staging-бэкенд одной командой (вариант A) | `docker --version`, `docker compose version` | то же / `docker compose` |

Если этот шаг пропустить, `npm install` в `desktop_client/` упадёт на
сборке `uiohook-napi` — см. раздел Troubleshooting.

### Windows 10/11 + Docker Desktop (рекомендуемый путь)

Порядок установки **важен**: WSL2 включают **до** Docker Desktop, а Python
и компилятор C/C++ ставят **до** `npm install` в `desktop_client/`.

1. **Git for Windows** — [git-scm.com/download/win](https://git-scm.com/download/win),
   настройки по умолчанию (Git Bash включён). Проверка: `git --version`.

2. **WSL2** (нужен Docker Desktop) — PowerShell **от администратора**:
   ```powershell
   wsl --install
   ```
   Если WSL уже установлен: `wsl --update`. После установки — **перезагрузка**.
   Проверка: `wsl --status` → `Default Version: 2`.

3. **Docker Desktop for Windows** —
   [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).
   При установке оставить «Use WSL 2 instead of Hyper-V» (обычно по умолчанию).
   Запустить Docker Desktop, дождаться **Engine running**.
   Проверка: `docker --version`, `docker compose version`.

4. **Node.js LTS** (20.x+) — [nodejs.org](https://nodejs.org/) (Windows Installer
   `.msi`), настройки по умолчанию. Проверка: `node --version` (≥ v20),
   `npm --version`.

5. **Python 3.11+** — [python.org/downloads/windows](https://www.python.org/downloads/windows/).
   **Обязательно** включить «Add python.exe to PATH» на первом экране инсталлятора.
   Нужен для `node-gyp` (бэкенд в варианте A идёт через Docker, Python на хост
   для API не обязателен). Проверка: `python --version`.

6. **Visual Studio Build Tools 2022** — раздел «Tools for Visual Studio» на
   [visualstudio.microsoft.com/downloads](https://visualstudio.microsoft.com/downloads/).
   Workload: **Desktop development with C++** (MSVC + Windows SDK).
   Пакет `npm install --global windows-build-tools` **не использовать** — он
   устарел и часто ломается на современных Node.js/Windows.
   После установки перезапустите терминал (иногда — ПК).

**Автопроверка** (из корня репозитория после `git clone`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_windows_dev_env.ps1
```

**Ручная проверка** в PowerShell:

```powershell
git --version
node --version
npm --version
python --version
docker --version
docker compose version
wsl --status
```

Все команды должны отработать без ошибок. Если что-то не найдено — проверьте
PATH или перезапустите терминал/ПК.

### macOS / Linux (кратко)

Компилятор для `node-gyp`:

- **macOS**: `xcode-select --install` (Command Line Tools).
- **Linux**: `sudo apt-get install build-essential python3` (Debian/Ubuntu).

Docker Desktop — опционально; для варианта B достаточно локальных Postgres/Redis.

## Шаг 1 — клонирование и ветка

```bash
git clone git@github.com:Shimmmi/Waifu_bot_REBORN.git
cd Waifu_bot_REBORN
git checkout feature/steam-client
```

HTTPS (если SSH-ключ не настроен):

```bash
git clone https://github.com/Shimmmi/Waifu_bot_REBORN.git
```

PowerShell / Git Bash на Windows — те же команды.

## Шаг 2 — поднять бэкенд

Desktop-клиент — это просто ещё один HTTP-клиент существующего FastAPI
бэкенда (`/api/...` + статика `webapp/*.html`). Ему нужен **работающий
бэкенд**, до которого он может достучаться по HTTP. Два варианта — выберите
один.

### Вариант A — staging-стек через Docker (рекомендуется, изолирован от прод-данных)

Git Bash / macOS / Linux:

```bash
cp .env.example .env.staging
# отредактируйте .env.staging: APP_ENV=stage обязателен,
# BOT_TOKEN/WEBHOOK_SECRET можно оставить заглушками — desktop-клиент
# их не использует, но Settings требует непустые значения при старте.
# BOT_TOKEN обязан выглядеть как настоящий Telegram-токен ("<цифры>:<строка>",
# без пробелов) — aiogram.Bot(...) проверяет формат при старте процесса,
# даже если реальных вызовов к Telegram никогда не будет:
#   BOT_TOKEN=123456:dev-stub-not-a-real-token
#   WEBHOOK_SECRET=dev-stub-secret
#   PUBLIC_BASE_URL=http://localhost:18000
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

PowerShell (Windows):

```powershell
Copy-Item .env.example .env.staging
notepad .env.staging
# впишите (APP_ENV в этом файле неважен — docker-compose.staging.yml задаёт APP_ENV=stage сам):
#   BOT_TOKEN=123456:dev-stub-not-a-real-token
#   WEBHOOK_SECRET=dev-stub-secret
#   PUBLIC_BASE_URL=http://localhost:18000
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

Поднимутся `waifu_staging_postgres` (порт 15432), `waifu_staging_redis`
(16379) и `waifu_staging_api` (**18000** — этот порт и нужен клиенту). Схема
БД в контейнере пустая — либо накатите миграции вручную (см. ниже), либо
используйте [`scripts/staging_seed_from_prod_dump.sh`](../scripts/staging_seed_from_prod_dump.sh)
для анонимизированного слепка прод-данных (нужен доступ к проду).

Применить миграции на пустой staging-БД:

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging \
  exec api python -m waifu_bot.cli migrate
```

Проверка, что бэкенд жив: откройте в браузере `http://127.0.0.1:18000/health`
или в терминале `curl http://127.0.0.1:18000/health` (PowerShell:
`Invoke-WebRequest http://127.0.0.1:18000/health`). Эндпоинт называется
`/health` (см. [`src/waifu_bot/main.py`](../src/waifu_bot/main.py)), **не**
`/healthz` — на `/healthz` сервер вернёт 404.

### Вариант B — обычный локальный uvicorn (без Docker)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# в .env: POSTGRES_DSN/REDIS_URL на свои локальные Postgres/Redis,
# BOT_TOKEN/WEBHOOK_SECRET/PUBLIC_BASE_URL — заглушки достаточно (см. пример выше,
# BOT_TOKEN обязан быть формата "<цифры>:<строка>")
python -m waifu_bot.cli migrate
uvicorn waifu_bot.main:app --reload   # слушает http://127.0.0.1:8000
```

Здесь нужен свой локальный Postgres+Redis (или тот же Docker, просто без
`docker-compose.staging.yml` — см. основной `README.md` проекта).

## Шаг 3 — настройка desktop_client

```bash
cd desktop_client
npm install
```

Создайте `config.local.json` **только с двумя полями** (не копируйте весь
`config.json` через `Copy-Item` — иначе в локальном конфиге застрянет
устаревший `overlay.page: battle.html` и появится предупреждение при старте):

```powershell
Copy-Item config.example.json config.local.json
```

Или вручную:

```json
{
  "backendUrl": "http://127.0.0.1:18000",
  "steamTicketDev": "dev-player-1"
}
```

Размер оверлея и страница (`overlay.html`, 300x420) берутся из
[`desktop_client/config.json`](../desktop_client/config.json) автоматически.

- `backendUrl` — куда стучаться: `18000` для варианта A (staging в Docker),
  `8000` для варианта B (локальный uvicorn).
- `steamTicketDev` — любая непустая строка. Она отправляется как заголовок
  `X-Steam-Ticket-Dev` и принимается бэкендом только когда `APP_ENV` в
  `dev|stage|testing` (см. `src/waifu_bot/api/deps.py`). При первом
  обращении под этим "тикетом" автоматически создаётся Steam-нативный
  игрок (отрицательный синтетический `Player.id`) — реальный Steamworks-
  аккаунт для этого шага не нужен.

Полный список поддерживаемых переменных окружения (приоритетнее файла) —
в [`desktop_client/src/config.js`](../desktop_client/src/config.js):
`WAIFU_BACKEND_URL`, `WAIFU_STEAM_TICKET_DEV`, `WAIFU_OVERLAY_WIDTH`,
`WAIFU_OVERLAY_HEIGHT`.

## Шаг 4 — запуск в dev-режиме (проверка до сборки)

Перед `npm run dev` убедитесь, что staging API отвечает (иначе Electron
покажет `ERR_EMPTY_RESPONSE` и `[input-tracker] failed to flush hit batch:
fetch failed`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_staging_backend.ps1
```

Скрипт проверяет Docker, контейнер `waifu_staging_api`, `GET /health`,
`/webapp/overlay.html` и nav webp. Все пункты должны быть `[OK]`.

```bash
npm run dev
```

Ожидаемый результат:

- Прозрачное окно-оверлей (компаньон) в правом нижнем углу экрана
  (`overlay.html`, ~300x420), поверх всех окон, всегда наверху,
  перетаскивается мышью за любое пустое место. В нём:
  - портрет основной вайфу + имя + HP-бар;
  - строка ресурсов (золото, пыль) и кнопка меню `☰` — меню открывает
    Профиль/Подземелья/Магазин и т.д. отдельными перетаскиваемыми окнами;
  - при активном подземелье сверху появляется мини-блок монстра
    (портрет + HP-бар);
  - анимации по состоянию: АФК (>60 сек без кликов) — вайфу «спит»
    (затемнение + Zzz; в подземелье монстр тоже спит), активность в бою —
    «выпад» портрета на каждый клик + вспышка на монстре + всплывающие
    цифры урона, активность вне боя — покачивание и случайные милые
    эмодзи-эмоции; при HP=0 — серый портрет с нимбом, при HP<25% —
    красная пульсация HP-бара.
- Основное окно приложения (`index.html`) — обычное, с рамкой.
- Клики/нажатия клавиш где-либо на экране должны через несколько секунд
  (батчинг) отправляться на `/api/pc/hits/batch` и наносить урон монстру —
  проверяется по изменению HP монстра в оверлее/основном окне (оверлей
  обновляет HP мгновенно из ответа батча, не дожидаясь поллинга).
- Открытие вкладок (магазин, таверна и т.п.) из меню оверлея или основного
  окна открывает отдельное перетаскиваемое окно поверх остальных
  (`appWindow.js` → `openTabWindow`).

Если что-то не так — не переходите к сборке, сначала разберитесь здесь
(проще отлаживать в dev-режиме, чем в собранном инсталляторе).

Desktop-клиент создаёт **отдельного Steam-native игрока** (синтетический
отрицательный `player_id` по `steamTicketDev`), а не ваш Telegram-аккаунт.
Для первого входа на title screen нажмите «Новая игра» и создайте персонажа —
не ожидайте автоматического входа в существующий Telegram-прогресс.

После `git pull` на ветке `feature/steam-client` **пересоберите** (не просто
`restart`!) контейнер `api`, чтобы подхватить обновлённый webapp с сервера:
у `api` в `docker-compose.staging.yml` нет volume-монтирования `src/` внутрь
контейнера — файлы (в т.ч. `app.min.js`, `battle.html`) копируются в образ
только на этапе `docker build`, поэтому `restart` продолжит работать со
старым образом:
```powershell
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

## Шаг 5 — сборка в exe

```bash
npm run dist
```

Это запускает `electron-builder` с конфигом уже прописанным в
[`desktop_client/package.json`](../desktop_client/package.json) (секция
`"build"`): для Windows — `nsis`-установщик, для Linux — `AppImage`, для
macOS — `dmg`. Кросс-платформенная сборка (например, `.exe` на Linux-хосте)
без дополнительной настройки Wine может не работать — надёжнее всего
собирать `.exe` именно на Windows-машине.

Результат появляется в `desktop_client/dist/`:

- Windows: `dist/Waifu Bot REBORN Setup <версия>.exe` — это установщик;
  после его прохождения в `Program Files` появится сам `.exe`, который и
  запускает приложение. (Если нужен portable-запуск без установки —
  добавьте `"target": "portable"` в `build.win` перед сборкой.)
- Linux: `dist/Waifu Bot REBORN-<версия>.AppImage` — исполняемый файл, `chmod +x` и запускать напрямую.
- macOS: `dist/Waifu Bot REBORN-<версия>.dmg`.

`config.local.json` **не** попадает в сборку по умолчанию (см. `files` в
`package.json`) — собранное приложение всё ещё читает
`config.json`/переменные окружения по тем же правилам, что и в dev-режиме
(`desktop_client/src/config.js`). Убедитесь, что `config.json` указывает на
тот бэкенд, который должен использовать собранный exe (для локальной
проверки — тот же staging), прежде чем собирать.

## Шаг 6 — запуск exe

Запустите установщик/AppImage/dmg из `dist/`, как обычное приложение.
Ожидаемое поведение то же, что и в Шаге 4 (dev-режим), но уже как
самостоятельный установленный процесс, а не через `electron .`.

**Готово — это и есть состояние "запуск exe файла".**

## Что дальше всё ещё стаб (не блокирует получение exe)

- **Реальная Steam-аутентификация** не подключена — используется только
  dev-заглушка `X-Steam-Ticket-Dev`. Для настоящего Steamworks-аккаунта,
  `STEAM_WEB_API_KEY`/`STEAM_APP_ID` на бэкенде и SDK на клиенте см.
  [`docs/STEAM_STEAMWORKS_SETUP.md`](STEAM_STEAMWORKS_SETUP.md). Это
  отдельный (платный, $100) шаг, который сознательно отложен и не мешает
  тестировать/собирать exe уже сейчас.
- **Публикация в Steam через SteamPipe** — отдельный шаг после того, как
  Steamworks-аккаунт появится; `electron-builder` только собирает
  установщик, загрузка в Steam делается отдельно через `steamcmd`.
- **Код-сайнинг** — несобранный/неподписанный exe с глобальным перехватом
  ввода (`uiohook-napi`) может триггерить антивирусы/SmartScreen. Для
  локальной разработки это не проблема, но перед публичной раздачей
  собранный exe стоит подписать.

## Troubleshooting

**Вариант A: `api`-контейнер падает с `ModuleNotFoundError: No module named 'PIL'`**
Пересоберите образ после `git pull` — `Pillow` был добавлен в `requirements.txt`
(старый образ мог остаться в кэше сборки `docker compose ... up -d --build`):
```powershell
docker compose -f docker-compose.staging.yml --env-file .env.staging build --no-cache api
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

**Вариант A/B: `aiogram.utils.token.TokenValidationError: Token is invalid!`**
`BOT_TOKEN` в `.env.staging`/`.env` не может быть произвольной строкой —
`aiogram.Bot(...)` проверяет формат `<цифры>:<непустая строка без пробелов>`
уже при старте процесса, даже если реальных вызовов к Telegram не будет.
Используйте, например, `BOT_TOKEN=123456:dev-stub-not-a-real-token`.

**`npm install` падает на сборке `uiohook-napi` / `node-gyp` ошибки**
Обычно означает отсутствие компилятора C/C++ или Python из Шага 0. На
Windows — установите Visual Studio Build Tools 2022 с workload **Desktop
development with C++** и убедитесь, что `python` (3.x) доступен в PATH
(галочка «Add python.exe to PATH» при установке Python). Запустите
`scripts/check_windows_dev_env.ps1`. Полный текст ошибки обычно содержит
`gyp ERR!` — по нему легко гуглить конкретную причину.

**WSL / Docker не стартует на Windows**
Включите виртуализацию в BIOS/UEFI (Intel VT-x / AMD-V). Убедитесь, что
WSL2 установлен (`wsl --status`) **до** Docker Desktop. После `wsl --install`
нужна перезагрузка.

**`Unable to load preload script` / `module not found: ./config` в Console**
Preload не может `require("./config")` в sandboxed-режиме Electron 20+.
Убедитесь, что в `desktop_client/src/windows/appWindow.js` и
`overlayWindow.js` в `webPreferences` стоит `sandbox: false` (уже в ветке
`feature/steam-client`). Перезапустите `npm run dev` после `git pull`.

**`/api/profile` → 401 на profile/shop/tavern, но index.html работает**
Страницы вроде `profile.html` грузят `bundle/app.min.js`. Если бандл
устарел и не содержит desktop-auth (`isDesktopClient`, `X-Steam-Ticket-Dev`),
запросы идут без заголовка и сервер отвечает 401. На dev-машине с Node:
```bash
cd webapp_frontend && npm ci && npx vite build --config vite.app.config.js
```
(или `./scripts/build_webapp.sh` для всех бандлов). Закоммить/подтянуть
обновлённый `src/waifu_bot/webapp/bundle/app.min.js`, затем **пересобрать**
образ (`docker compose ... up -d --build`, не просто `restart` — см. Шаг 4).

**Оверлей застревает на «ВАША ВАЙФУ: Загрузка…»**
Устарело: оверлей больше не использует `battle.html` — теперь это отдельная
самодостаточная страница `overlay.html` + `pages/overlay.js` (не зависит от
`app.js`/бандлов). Если вы всё ещё видите старый оверлей с текстом «ВАША
ВАЙФУ» — клиент запущен со старым `config.local.json`, где явно задан
`overlay.page: "battle.html"`: удалите ключ `overlay` из локального конфига
(или поменяйте на `"overlay.html"`) и перезапустите `npm run dev`.

**`[input-tracker] hit batch rejected: 500 null`**
`POST /api/pc/hits/batch` и `GET /api/profile` оба вызывают
`resolve_or_create_player_for_steam()` на **первом** запуске (создание
Steam-native игрока по `steamTicketDev`). Оверлей и основное окно стартуют
почти одновременно, поэтому оба запроса могут попытаться создать одну и ту
же запись `PlayerIdentityLink` параллельно — до фикса второй запрос падал
с `IntegrityError` (нарушение `UniqueConstraint`) вместо аккуратной отдачи
уже созданного `player_id` (см. `src/waifu_bot/services/auth_steam.py`,
уже исправлено в `feature/steam-client`). Если ошибка повторяется после
`git pull` — убедитесь, что `api` **пересобран** (`up -d --build`), а не
просто перезапущен: как и `app.min.js`, код бэкенда копируется в образ
только на этапе `build`.

**404 на `static/game/ui/nav/*.webp` и похожие ассеты**
Исправлено: ассеты `static/game/` восстановлены из `main` в ветку
`feature/steam-client`, а `Dockerfile` теперь копирует `static/` в образ.
Если 404 остались — пересоберите образ (`up -d --build`): старый образ был
собран без каталога `static/`.

**Оверлей не появляется / окно сразу закрывается**
Проверьте консоль (`npm run dev` печатает в терминал), обычно это ошибка
подключения к `backendUrl` (бэкенд не запущен/не тот порт) — оверлей грузит
`overlay.html`, который делает fetch-запросы к API при старте.

**`ERR_EMPTY_RESPONSE` / `fetch failed` при `npm run dev`**
На порту `18000` никто не отдаёт HTTP (Docker Desktop выключен, контейнер
`waifu_staging_api` не запущен или упал). Это **не** отсутствие
`overlay.html` в git — страница уже в репозитории, но API недоступен.

1. Запустите Docker Desktop (дождитесь Running).
2. Из корня репозитория:
   ```powershell
   git pull origin feature/steam-client
   docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
   docker compose -f docker-compose.staging.yml --env-file .env.staging exec api alembic upgrade head
   powershell -ExecutionPolicy Bypass -File scripts/check_staging_backend.ps1
   ```
3. Только когда скрипт показывает все `[OK]`, снова `cd desktop_client; npm run dev`.
4. Если `api` в статусе Exited: `docker compose ... logs api --tail 80` —
   часто неверный `BOT_TOKEN` в `.env.staging` (нужен формат `123456:stub`).

**Оверлей показывает «Загрузка…» / эмодзи вместо портрета**
Оверлей берёт портрет из `GET /api/profile?lite=1` (`main_waifu.portrait_url`).
Если портрета нет — у персонажа не сгенерирован портрет (создайте персонажа
с портретом в основном окне) либо образ `api` старый и lite-профиль ещё не
отдаёт `portrait_url` (нужен `up -d --build` после `git pull`).

**Клики/нажатия не наносят урон**
1. Убедитесь, что `steamTicketDev` задан и бэкенд запущен с `APP_ENV` в
   `dev|stage|testing` — иначе `X-Steam-Ticket-Dev` отклоняется (401).
2. Батчинг не мгновенный — подождите несколько секунд (см.
   `desktop_client/src/input/inputTracker.js`, `FLUSH_INTERVAL_MS`).
3. Если `uiohook-napi` не установился (см. первый пункт) — трекер
   деградирует безопасно, но кликов вообще не будет; смотрите лог на
   предупреждение об этом при старте.

**CORS/сетевые ошибки, если бэкенд на другой машине/в другой сети**
`backendUrl` должен быть доступен именно с машины, где запущен
desktop-клиент (не `localhost`, если бэкенд удалённый) — например, IP
машины с Docker или SSH-туннель на `18000`/`8000`.

**Антивирус/Windows Defender ругается на приложение**
Ожидаемо для неподписанного exe с глобальным перехватом ввода — см. раздел
про код-сайнинг выше. Для локальной разработки — добавить исключение.
