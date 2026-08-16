# Mobile day-1 / Play checklist

## Funnel (staging)

1. Install debug APK (`WAIFU_MOBILE_BACKEND_URL=https://stage.shimmirpgbot.ru`).
2. App opens **login** (`/webapp/mobile/login.html`).
3. In Telegram WebApp (staging): open `/webapp/mobile_link.html` → **Получить код**.
4. In APK: paste code → **Войти с привязкой** (stage: `google_sub_dev` field).
5. Shell loads → allow Activity Recognition → walk → **Забрать урон**.
6. Profile tab: inventory `client=mobile`; toast/note if channel remap ran.

## Soft-cap

UI shows soft-cap hint around ~10k accepted units/day. Hard caps remain in `game_config` (`activity.max_steps_per_day`). Balance on the **cap**, not honest walking — see `MOBILE_ANDROID_BALANCE.md`.

## Privacy / Play

- Declare `ACTIVITY_RECOGNITION` usage in Play Console / privacy policy before Internal Testing.
- Production Google Sign-In needs OAuth client + SHA-1; staging may use `google_sub_dev`.

## Auth regression

Claim without session must redirect to login (not raw `401 Missing Telegram init data` in UI).
