# Waifu Bot REBORN — desktop client (Electron)

Steam/PC client: a transparent corner overlay (Bongo-Cat-style) showing the
main waifu, plus draggable windows reusing the *existing* Telegram WebApp
pages (`src/waifu_bot/webapp/*.html`) served over HTTP. No page was
duplicated for this — see `webapp/app.js` (`isDesktopClient()`) and
`webapp/desktop-theme.css` for the (additive-only) theming hook.

## Do NOT run this on the production VPS

This app must be developed and built on a regular desktop machine (Windows/
macOS/Linux with a display), not on the headless prod/staging server. See
the plan's §1.6/§1.4 — Electron + native deps (`uiohook-napi`, later the
Steamworks SDK) pull in a lot of disk/toolchain weight that has no reason to
live on a disk-constrained shared VPS, and `npm start` needs a real display
to show windows. The code here is meant to be `git pull`-ed onto your own
machine.

## Setup (on your dev machine)

Full walkthrough (Windows + Docker staging, clone → exe):
[`docs/STEAM_CLIENT_DEV_SETUP.md`](../docs/STEAM_CLIENT_DEV_SETUP.md).

After installing prerequisites (Step 0), verify on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_windows_dev_env.ps1
```

Quick start:

```bash
git clone git@github.com:Shimmmi/Waifu_bot_REBORN.git && cd Waifu_bot_REBORN
git checkout feature/mobile-android   # or feature/steam-client; activity combat lives on mobile-android
# start staging (see docs/STEAM_CLIENT_DEV_SETUP.md); --wait blocks until
# the api container's healthcheck passes, instead of returning as soon as
# the process forks (which races npm run dev and can look like a broken
# backend for a few seconds)
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build --wait
powershell -ExecutionPolicy Bypass -File scripts/check_staging_backend.ps1   # all [OK] before dev
cd desktop_client
npm install
cp config.example.json config.local.json   # Windows: Copy-Item config.example.json config.local.json
npm run dev
# or: npm run dev:wait  — extra preflight poll before Electron starts
```

Before `npm run dev`, verify the backend from the **Windows host** (not only
`docker ps` showing `healthy`). After `git pull` + `--build`, run
`check_staging_backend.ps1` from repo root — skipping this step is the most
common cause of `ERR_EMPTY_RESPONSE`. See `docs/STEAM_CLIENT_DEV_SETUP.md`.

`npm run dev` waits for `/health` via [`src/backend/waitForBackend.js`](src/backend/waitForBackend.js)
before opening windows. As defense in depth, renderer pages also retry transient
`Failed to fetch` (desktop `apiFetch`) and auto-reload on `ERR_EMPTY_RESPONSE`
([`src/windows/loadWithRetry.js`](src/windows/loadWithRetry.js)).

By default `config.json` points at the isolated staging stack
(`docker-compose.staging.yml`, `http://127.0.0.1:18000`) so you never point
the desktop client at production by accident. Point `backendUrl` (in
`config.local.json`, or via `WAIFU_BACKEND_URL` env var) at wherever your
backend actually runs — e.g. `http://127.0.0.1:8000` for a plain local
`uvicorn` run, or an SSH-tunneled staging port.

Steam auth isn't wired up yet (Этап 6 needs a real Steamworks Partner
account). Until then, set `steamTicketDev` in `config.local.json` (or
`WAIFU_STEAM_TICKET_DEV` env var) to any string — it's sent as
`X-Steam-Ticket-Dev` and only accepted by the backend when
`APP_ENV=dev|stage|testing` (see `api/deps.py`). This auto-creates (or
resolves) a Steam-native player the first time you use it.

## Structure

```
desktop_client/
  src/
    main.js              Electron main process: creates the overlay + main window
    preload.js            contextBridge -> window.waifuDesktop (read by webapp/app.js)
    config.js              Resolves backendUrl / steamTicketDev / window sizes
    windows/
      overlayWindow.js     Transparent always-on-top corner window (webapp/overlay.html companion HUD)
      appWindow.js         Main window + openTabWindow() for shop/tavern/... "tabs"
      loadWithRetry.js      Auto-retries window loadURL() on transient backend-not-ready errors
    input/                 Этап 5: global click/keypress tracker + batch sender
  config.json               Committed defaults (points at staging)
  config.local.json          Your personal overrides (gitignored)
```

## Steam auth / packaging (Этап 6, needs a real Steamworks account)

`src/steam/steamworksClient.js` is a deliberate no-op scaffold — see its
docstring and [`docs/STEAM_STEAMWORKS_SETUP.md`](../docs/STEAM_STEAMWORKS_SETUP.md)
for the full manual checklist (Steamworks Partner account + $100 fee, App ID,
Web API key, installing `steamworks.js`, SteamPipe). `steam_appid.txt`
currently holds `480` (Valve's public "Spacewar" test app) as a placeholder —
replace it with your real App ID once you have one.

`npm run dist` (electron-builder, see `package.json` "build" section) once
ready for a real build.
