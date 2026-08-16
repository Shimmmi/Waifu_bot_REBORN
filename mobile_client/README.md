# Waifu Mobile Client (Android / Activity)

Capacitor shell for the **activity** economy: pedometer steps map 1:1 to TEXT characters (`attack_speed` / `min_chars` gates hits). Shared inventory/skills with Steam; Telegram inventory stays separate.

## Git branch (isolation from Telegram)

All Android / activity work lives on **`feature/mobile-android`** only.

On the VPS/dev host, use the dedicated checkout (git worktree) at **`/opt/waifu-bot-mobile-client`** — same layout as Steam at `/opt/waifu-bot-steam-client`. Keep `/opt/waifu-bot-REBORN` on a Telegram branch (`webapp-perf-prod` / `main`). Open Cursor on the mobile path for APK + activity API work.

```bash
git fetch origin
git checkout feature/mobile-android
git pull
```

Do **not** merge this branch into Telegram prod branches (`main`, `webapp-perf-prod`, etc.) until an explicit PR review. Do **not** develop Android APK tooling on the headless prod VPS disk for Electron/Android SDK — clone this branch on your laptop.

**Полный гайд (Windows 11 → Git Bash → первый debug APK):** [docs/MOBILE_ANDROID_DEV_SETUP.md](../docs/MOBILE_ANDROID_DEV_SETUP.md) — секция «Local PC: Windows → first debug APK» (установка Git/Node/JDK/Android Studio, `ANDROID_HOME`, clone, `android:setup`, `android:apk`, adb). На Windows все `npm run android:*` запускайте из **Git Bash**, не из cmd.

## Prerequisites (dev laptop)

- Node.js **20+**
- JDK **17**
- Android Studio (SDK platform 34+, build-tools, platform-tools/`adb`)
- Staging backend on this same branch with migration `0129_activity_economy`
- `export WAIFU_MOBILE_BACKEND_URL=https://<your-staging-host>`

## One-time project setup

```bash
cd mobile_client
npm run android:env          # check Node/JDK/SDK
npm run android:setup        # npm ci + cap add android + StepCounter plugin + bridge
npm run android:signing      # optional: wire release keystore.properties.example
```

## Build & install debug APK

Краткий путь (детали и troubleshooting — в DEV_SETUP выше):

```bash
export WAIFU_MOBILE_BACKEND_URL=https://<staging-host>
npm run android:apk          # → android/app/build/outputs/apk/debug/app-debug.apk
npm run android:install      # adb install -r
npm run android:smoke        # launch + logcat filters
```

Dev WebView loads (via `capacitor.config.ts` `server.url`):

`{BACKEND}/webapp/activity.html?mobileClient=1&economy=activity`

`window.waifuMobile` is injected from native `BridgeLoader` on resume (and shipped as `www/bridge.js` for bundled mode).

## Backend API smoke (no device)

```bash
export WAIFU_MOBILE_BACKEND_URL=https://<staging-host>
export WAIFU_LINK_CODE=<from POST /api/auth/link_code>
npm run android:api-smoke
```

## Auth

1. Telegram WebApp on staging: `POST /api/auth/link_code`
2. APK / curl: `POST /api/auth/mobile/google` with `{ id_token }` or (dev/stage) `{ google_sub_dev, link_code }`
3. Store `desktop_session` via `waifuMobile.setDesktopSessionToken`
4. API calls use `X-Desktop-Session` (`app.js` mobile client path)

## Combat loop

1. `POST /api/dungeons/{id}/start?economy=activity`
2. Walk; onResume / «Забрать» → `POST /api/activity/input/claim`
3. Server buffers units; when `buffer >= min_chars`, applies TEXT hits

## Release APK / AAB

```bash
cp android/keystore.properties.example android/keystore.properties
# edit paths/passwords — file is gitignored
npm run android:release       # APK
npm run android:release:aab   # Play Bundle
```

Play Internal Testing: [docs/MOBILE_ANDROID_PLAY_CHECKLIST.md](../docs/MOBILE_ANDROID_PLAY_CHECKLIST.md)

## Script index

| Script | Purpose |
|--------|---------|
| `scripts/check_android_dev_env.sh` / `.ps1` | Node/JDK/SDK/adb |
| `scripts/setup_android_project.sh` | `cap add android` + plugin + MainActivity |
| `scripts/build_debug_apk.sh` | assembleDebug |
| `scripts/install_debug_apk.sh` | adb install |
| `scripts/run_smoke_device.sh` | launch + logcat |
| `scripts/api_smoke_staging.sh` | curl auth/status/claim |
| `scripts/apply_release_signing.sh` | Gradle signing wiring |
| `scripts/build_release_apk.sh` | assembleRelease / bundleRelease |
