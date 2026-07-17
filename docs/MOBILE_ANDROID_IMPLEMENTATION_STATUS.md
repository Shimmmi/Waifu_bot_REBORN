# Mobile Android / Activity — implementation status

Branch: **`feature/mobile-android`** → `origin/feature/mobile-android`

## Done

| Stage | What |
|-------|------|
| Backend activity economy | migration 0121, claim API, Google link-code, Steam align |
| WebApp mobile hooks | `activity.html`, `mobile-theme.css`, `isMobileClient` |
| Git isolation | branch pushed; Telegram branches untouched |
| Capacitor android/ | generated + StepCounter plugin + BridgeLoader + ACTIVITY_RECOGNITION |
| Local tooling | `android:env/setup/apk/install/smoke/api-smoke/release` scripts |
| Release signing | `apply_release_signing.sh` + `keystore.properties.example` |
| Docs | DEV_SETUP, BALANCE, PLAY_CHECKLIST, SMOKE |

## Needs human laptop (Android SDK)

- `npm run android:apk` / `android:install` / device smoke (this VPS has no `ANDROID_HOME`)
- Point `WAIFU_MOBILE_BACKEND_URL` at staging with 0121 applied
- Google Cloud OAuth + Play Internal Testing when ready for closed beta

## Quick start on laptop

See [mobile_client/README.md](../mobile_client/README.md) and [MOBILE_ANDROID_SMOKE.md](MOBILE_ANDROID_SMOKE.md).
