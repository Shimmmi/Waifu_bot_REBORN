# Android / activity smoke checklist

## A. On laptop with Android SDK

```bash
git checkout feature/mobile-android && git pull
cd mobile_client
export WAIFU_MOBILE_BACKEND_URL=https://<staging>
npm run android:env
npm run android:setup    # if android/ not yet generated locally
npm run android:apk
npm run android:install
npm run android:smoke
```

Device DoD:

1. App opens; deny activity permission → no crash.
2. Dev login (`google_sub_dev` + link_code) → session stored.
3. Activity starter dagger present (`GET /api/activity/status`).
4. Start dungeon `economy=activity`.
5. Grant permission, walk, claim → hits when buffer ≥ min_chars.
6. Telegram WebApp on same player: telegram inventory/run unchanged.

## B. Backend-only (any machine with curl)

```bash
export WAIFU_MOBILE_BACKEND_URL=https://<staging>
export WAIFU_LINK_CODE=<code from Telegram POST /api/auth/link_code>
cd mobile_client && npm run android:api-smoke
```

Requires staging on `feature/mobile-android` with `alembic upgrade head` (0129).
