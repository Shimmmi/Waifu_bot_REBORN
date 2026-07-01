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

| Что | Зачем | Проверка |
|---|---|---|
| **Git** | клонировать репозиторий | `git --version` |
| **Node.js LTS** (20.x или новее) + npm | Electron, electron-builder | `node --version`, `npm --version` |
| **Python 3.11+** | нужен и бэкенду, и `node-gyp` для сборки нативного `uiohook-napi` | `python3 --version` |
| **Компилятор C/C++** (см. ниже по ОС) | `node-gyp` компилирует `uiohook-napi` из исходников при `npm install` | — |
| **Docker Desktop** (опционально) | самый быстрый способ поднять staging-бэкенд (Postgres+Redis+API одной командой) | `docker --version` |

Компилятор для `node-gyp` по ОС:

- **Windows**: `npm install --global windows-build-tools` (запускать от
  администратора) **или** поставить Visual Studio Build Tools вручную с
  workload "Desktop development with C++". Также нужен Python (см. выше) —
  `node-gyp` его использует напрямую.
- **macOS**: `xcode-select --install` (Command Line Tools).
- **Linux**: `sudo apt-get install build-essential python3`.

Если этот шаг пропустить, `npm install` в `desktop_client/` упадёт на
сборке `uiohook-napi` — см. раздел Troubleshooting.

## Шаг 1 — клонирование и ветка

```bash
git clone <URL этого репозитория>
cd waifu-bot-REBORN
git checkout feature/steam-client
```

## Шаг 2 — поднять бэкенд

Desktop-клиент — это просто ещё один HTTP-клиент существующего FastAPI
бэкенда (`/api/...` + статика `webapp/*.html`). Ему нужен **работающий
бэкенд**, до которого он может достучаться по HTTP. Два варианта — выберите
один.

### Вариант A — staging-стек через Docker (рекомендуется, изолирован от прод-данных)

```bash
cp .env.example .env.staging
# отредактируйте .env.staging: APP_ENV=stage обязателен,
# BOT_TOKEN/WEBHOOK_SECRET можно оставить заглушками — desktop-клиент
# их не использует, но Settings требует непустые значения при старте
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

Проверка, что бэкенд жив: `curl http://127.0.0.1:18000/healthz` (или
откройте в браузере).

### Вариант B — обычный локальный uvicorn (без Docker)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# в .env: POSTGRES_DSN/REDIS_URL на свои локальные Postgres/Redis,
# BOT_TOKEN/WEBHOOK_SECRET — заглушки достаточно (см. примечание выше)
python -m waifu_bot.cli migrate
uvicorn waifu_bot.main:app --reload   # слушает http://127.0.0.1:8000
```

Здесь нужен свой локальный Postgres+Redis (или тот же Docker, просто без
`docker-compose.staging.yml` — см. основной `README.md` проекта).

## Шаг 3 — настройка desktop_client

```bash
cd desktop_client
npm install
cp config.json config.local.json
```

Отредактируйте `config.local.json` (файл в `.gitignore`, безопасно хранить
локальные настройки):

```json
{
  "backendUrl": "http://127.0.0.1:18000",
  "steamTicketDev": "dev-player-1"
}
```

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

```bash
npm run dev
```

Ожидаемый результат:

- Небольшое прозрачное окно-оверлей в правом нижнем углу экрана с вайфу
  (`battle.html`), поверх всех окон, всегда наверху.
- Основное окно приложения (`index.html`) — обычное, с рамкой.
- Клики/нажатия клавиш где-либо на экране должны через несколько секунд
  (батчинг) отправляться на `/api/pc/hits/batch` и наносить урон монстру —
  проверяется по изменению HP монстра в оверлее/основном окне.
- Открытие вкладок (магазин, таверна и т.п.) из основного окна открывает
  отдельное перетаскиваемое окно поверх остальных (`appWindow.js` →
  `openTabWindow`).

Если что-то не так — не переходите к сборке, сначала разберитесь здесь
(проще отлаживать в dev-режиме, чем в собранном инсталляторе).

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

**`npm install` падает на сборке `uiohook-napi` / `node-gyp` ошибки**
Обычно означает отсутствие компилятора C/C++ или Python из Шага 0. На
Windows — переустановите Visual Studio Build Tools с C++ workload и
убедитесь, что `python` (3.x) доступен в PATH. Полный текст ошибки обычно
содержит `gyp ERR!` — по нему легко гуглить конкретную причину.

**Оверлей не появляется / окно сразу закрывается**
Проверьте консоль (`npm run dev` печатает в терминал), обычно это ошибка
подключения к `backendUrl` (бэкенд не запущен/не тот порт) — оверлей грузит
`battle.html`, который делает fetch-запросы к API при старте.

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
