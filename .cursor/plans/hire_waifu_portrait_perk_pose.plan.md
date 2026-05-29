---
name: Hire waifu portrait perk and pose
overview: Extend hired waifu image prompt with one randomly chosen perk visual (EN) and a random dynamic pose; pass waifu.perks from tavern.
todos:
  - id: perk-map
    content: Add _PERK_PORTRAIT_VISUAL_EN (all perk ids from expedition_data) and _HIRE_PORTRAIT_POSE_EN pool
    status: pending
  - id: prompt-build
    content: In generate_hire_waifu_image pick random perk, join prompt parts, log chosen perk_id
    status: pending
  - id: tavern-call
    content: Pass waifu.perks from tavern.hire_waifu into generate_hire_waifu_image
    status: pending
isProject: false
---

# Hire waifu portrait: random perk + pose (implementation plan)

See Russian details in the synced plan; implementation targets:

- [`src/waifu_bot/services/expedition_events_ai.py`](src/waifu_bot/services/expedition_events_ai.py) — dicts + `generate_hire_waifu_image(..., perk_ids=...)`
- [`src/waifu_bot/services/tavern.py`](src/waifu_bot/services/tavern.py) — pass `waifu.perks`
- Source of perk ids: [`src/waifu_bot/game/expedition_data.py`](src/waifu_bot/game/expedition_data.py) `PERKS` / `PERK_BY_ID`
