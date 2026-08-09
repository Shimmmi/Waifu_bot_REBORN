# Activity economy — balance calibration notes

Tunable via `game_config` (no APK rebuild):

| Key | Default | Role |
|-----|---------|------|
| `activity.chunk_mode` | `fill_cap` | `fill_cap` = spend min(buffer, length_cap); `exact_min` = spend min_chars each hit |
| `activity.length_cap` | `200` | Max units per hit (= TEXT length bonus cap) |
| `activity.max_hits_per_claim` | `20` | Caps SQL/combat work per claim |
| `activity.max_units_per_claim` | `2000` | Client units accepted per request |
| `activity.max_steps_per_day` | `20000` | UTC day cap (mobile) |
| `activity.max_clicks_per_day` | `50000` | UTC day cap (Steam) |
| `activity.max_step_rate_per_sec` | `4` | Anti-cheat vs elapsed time |

## Calibration goal (staging)

Compare for the same waifu level:

1. Typical Telegram day (message hits that land)
2. Steam day at daily click cap
3. Mobile day at daily step cap

Loot/MF for activity must remain sane if **every** player sits on the day cap (design to the cap, not to honest walking).

## Weapon speed fantasy

Faster weapons (low `attack_speed`) convert the same step budget into more hits when using `exact_min`; with `fill_cap`, speed mainly gates the **minimum** buffer to land a strike, while long walks produce fewer, longer “messages”.
