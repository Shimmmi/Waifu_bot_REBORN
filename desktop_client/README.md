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

```bash
git clone <this repo> && cd waifu-bot-REBORN/desktop_client
npm install
cp config.json config.local.json   # edit backendUrl if needed (gitignored)
npm run dev
```

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
      overlayWindow.js     Transparent always-on-top corner window (battle.html)
      appWindow.js         Main window + openTabWindow() for shop/tavern/... "tabs"
    input/                 Этап 5: global click/keypress tracker + batch sender
  config.json               Committed defaults (points at staging)
  config.local.json          Your personal overrides (gitignored)
```

## Packaging (Этап 6, once there's a Steamworks account)

`npm run dist` (electron-builder, see `package.json` "build" section) once
this is ready for a real build. Steam-specific packaging (SteamPipe,
`steam_appid.txt`, the Steamworks SDK native module) is added in that stage.
