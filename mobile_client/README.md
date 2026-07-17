# Waifu Mobile Client (Android / Activity)

Capacitor shell for the **activity** economy: pedometer steps map 1:1 to TEXT characters (`attack_speed` / `min_chars` gates hits). Shared inventory/skills with the Steam client; Telegram inventory stays separate.

## Prerequisites

- Android Studio + JDK 17
- Node.js 20+
- Backend on `feature/mobile-android` (or merged) with migration `0121_activity_economy`
- Staging or prod HTTPS URL in `WAIFU_MOBILE_BACKEND_URL`

## Quick start (developer machine — not the VPS)

```bash
cd mobile_client
npm install
# optional: export WAIFU_MOBILE_BACKEND_URL=https://your-staging.example
npx cap add android   # first time only
# Copy native/android/WaifuStepCounterPlugin.java into the Android app package
# and register the plugin in MainActivity.
npx cap sync android
npx cap open android
```

Dev WebView loads:

`{BACKEND}/webapp/activity.html?mobileClient=1&economy=activity`

Inject `src/bridge.js` early (Capacitor `appendUserAgent` / custom HTML bootstrap) so `window.waifuMobile` exists before `app.js`.

## Auth

1. In Telegram WebApp: `POST /api/auth/link_code` → show code to user.
2. In APK: Google Sign-In → `POST /api/auth/mobile/google` with `{ id_token, link_code }`.
3. Store returned `desktop_session` via `waifuMobile.setDesktopSessionToken`.
4. All API calls use `X-Desktop-Session` (already wired in `app.js` for mobile client).

Dev/stage without Google Cloud OAuth:

```json
POST /api/auth/mobile/google
{ "google_sub_dev": "test-google-sub-1", "link_code": "ABCD1234" }
```

## Combat loop

1. Start an **activity** dungeon: `POST /api/dungeons/{id}/start?economy=activity`
2. Walk; onResume / «Забрать» → `POST /api/activity/input/claim` `{ "source": "mobile_steps", "units", "client_counter_total" }`
3. Server buffers units; when `buffer >= min_chars`, applies TEXT hits (fill_cap up to 200).

## Play Internal Testing

See [docs/MOBILE_ANDROID_PLAY_CHECKLIST.md](../docs/MOBILE_ANDROID_PLAY_CHECKLIST.md).
