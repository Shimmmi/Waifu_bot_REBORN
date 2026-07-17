# Google Play Internal Testing — closed beta checklist

## Store / policy

- [ ] App category: **Game** (not Health & Fitness)
- [ ] Data Safety: declare physical activity data used for gameplay progression
- [ ] Permission rationale UI before system `ACTIVITY_RECOGNITION` dialog
- [ ] IARC / age rating appropriate for waifu content (18+ if required)
- [ ] Screenshots/store listing avoid policy-violating suggestive imagery
- [ ] Privacy policy URL covering step counting (count only, not GPS route)

## Build

- [ ] Release keystore + Play App Signing enrolled
- [ ] `GOOGLE_CLIENT_ID` set on production/staging backend
- [ ] Cap sync against pinned backend URL or version gate
- [ ] Smoke: deny permission → app opens, no crash, damage from steps = 0

## Functional

- [ ] Link Telegram via `/api/auth/link_code` + Google login
- [ ] Starter dagger `attack_speed=3` granted in activity bag
- [ ] Start dungeon with `economy=activity`
- [ ] 2 steps → no hit; 3 steps → 1 TEXT hit
- [ ] Loot appears only in `economy=activity` inventory
- [ ] Telegram inventory/run unaffected
- [ ] Steam clicks on same API produce equivalent hits
