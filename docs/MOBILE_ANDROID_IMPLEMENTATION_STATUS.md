# Mobile Android / Activity — implementation status

Branch: `feature/mobile-android`

## Done

| Stage | What |
|-------|------|
| 0 | Branch from `origin/feature/steam-client`; staging compose already present |
| 1 | `economy` on `inventory_items` + `dungeon_runs`; equip isolation by economy |
| 2 | `activity_item_templates` + starter dagger seed; `ensure_activity_starter_gear` |
| 3 | `POST /api/activity/input/claim` — units→TEXT hits, buffer, caps, fill_cap |
| 4 | Google login + link_code; SSE via `?desktopSession=` in WebApp |
| 5 | Unit tests: activity claim + PC batch delegate |
| 6 | `isMobileClient`, `mobile-theme.css`, `activity.html` |
| 7 | `mobile_client/` Capacitor scaffold + StepCounter Java plugin source |
| 8 | Steam `POST /api/pc/hits/batch` → activity claim (`steam_clicks`) |
| 9 | Balance keys documented in `MOBILE_ANDROID_BALANCE.md` |
| 10 | Play checklist `MOBILE_ANDROID_PLAY_CHECKLIST.md` |

## Needs human / device

- `npx cap add android` + register plugin on a machine with Android Studio
- Google Cloud OAuth client id + Play Console Internal Testing
- Visual QA of activity WebApp on a phone
- Staging calibration of day caps vs Telegram play
