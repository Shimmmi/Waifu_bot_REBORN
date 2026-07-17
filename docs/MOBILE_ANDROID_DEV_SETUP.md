# Mobile Android (Activity) — developer setup

Branch: `feature/mobile-android` (from `feature/steam-client`).

## Backend

```bash
# apply migration
alembic upgrade head   # includes 0121_activity_economy

# optional staging stack (already in repo)
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

Env:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` | Google Sign-In audience check (prod) |
| `DESKTOP_SESSION_SECRET` | JWT for `X-Desktop-Session` (shared with Steam desktop) |
| `APP_ENV=stage` | enables `google_sub_dev` / Steam ticket stubs |

## Key API

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/auth/link_code` | Telegram player → one-time code |
| POST | `/api/auth/mobile/google` | Google login + optional link_code → desktop_session |
| GET | `/api/activity/status` | buffer, min_chars, grants starter dagger |
| POST | `/api/activity/input/claim` | `{source, units, client_counter_total}` |
| POST | `/api/dungeons/{id}/start?economy=activity` | activity run |
| GET | `/api/inventory?economy=activity` | activity bag |
| POST | `/api/pc/hits/batch` | Steam clicks → same activity claim |

## Combat model

- 1 step (mobile) = 1 click (Steam) = 1 TEXT character
- Weapon `attack_speed` → `min_chars` (dagger 3 ⇒ need ≥3 units)
- Chunk mode default `fill_cap` (spend up to 200 units per hit)
- No media types / no tap-to-hit on mobile

## Client

See [mobile_client/README.md](../mobile_client/README.md).

WebApp: `activity.html?mobileClient=1&economy=activity`
