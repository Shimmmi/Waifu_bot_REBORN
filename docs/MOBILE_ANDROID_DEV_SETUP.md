# Mobile Android (Activity) — developer setup

## Branch policy (critical)

| Track | Branch | Purpose |
|-------|--------|---------|
| Android / activity | **`feature/mobile-android`** | Capactor APK, activity API, dual economy |
| Telegram prod | `main` / `webapp-perf-prod` / etc. | Do not land activity migrations here casually |
| Steam desktop | `feature/steam-client` (ancestor) | Electron; combat aligned via activity claim |

**Rule:** all Android/activity commits stay on `feature/mobile-android` until an explicit merge PR. Cherry-picks into Telegram branches only when approved.

```bash
git fetch origin
git checkout feature/mobile-android
git pull origin feature/mobile-android
```

Remote: `origin/feature/mobile-android` (created for isolation from Telegram).

## Backend

```bash
# on staging DB only — never apply 0121 to prod Telegram by accident
alembic upgrade head   # includes 0121_activity_economy

docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

Env:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` | Google Sign-In audience (prod) |
| `DESKTOP_SESSION_SECRET` | JWT for `X-Desktop-Session` |
| `APP_ENV=stage` | enables `google_sub_dev` stubs |
| `WAIFU_MOBILE_BACKEND_URL` | used by Capacitor `server.url` / smoke scripts |

## Local APK toolchain (laptop, not VPS)

1. Install Android Studio + JDK 17 + Node 20+.
2. Set `ANDROID_HOME` (or `ANDROID_SDK_ROOT`).
3. Clone repo, checkout `feature/mobile-android`.
4. Follow [mobile_client/README.md](../mobile_client/README.md):

```bash
cd mobile_client
export WAIFU_MOBILE_BACKEND_URL=https://<staging-host>
npm run android:env
npm run android:setup
npm run android:apk
npm run android:install
```

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
