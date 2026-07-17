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
