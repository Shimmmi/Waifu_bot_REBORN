---
name: Monster Affix System Fix
overview: "The elite/affix system is architecturally complete on the backend but has three critical gaps: elite roll fires too late (lazy, on first hit — so monster names appear unchanged until the first attack), defense/evasion affix stat modifiers are not wired into combat damage, and the frontend has zero awareness of elite status."
todos:
  - id: move-elite-roll
    content: "Move elite roll to dungeon creation: _roll_monster_from_template() in dungeon.py pre-rolls affixes using player luck so names are set at start"
    status: completed
  - id: wire-defense-evade
    content: Wire defense_add / evade_add into combat damage in process_message_damage()
    status: completed
  - id: enrich-active-dungeon
    content: Add is_elite, elite_color, applied_affixes to /dungeons/active response
    status: completed
  - id: frontend-elite-ui
    content: Update renderSoloActiveProgress() UI and continueBattle() log for elite reveal
    status: completed
isProject: false
---

# Monster Affix System Fix

## Diagnosis

Current state confirmed by DB inspection:

- 803 `dungeon_run_monsters`, all with `applied_affix_ids IS NULL` — the elite roll has never persisted
- Active run 110: positions 1-2 defeated via old code (before the `/dungeons/continue` fix), position 3 is current but unhit
- `monster_affixes` table: 48 affixes fully seeded and valid
- `_roll_elite_for_monster()` in `[services/combat.py](src/waifu_bot/services/combat.py)` (line 430) is implemented correctly — it fires on first hit but has never actually run on committed data yet

```mermaid
flowchart TD
    DungeonStart["Dungeon starts\n_roll_monster_from_template()"] -->|"name = 'Зомби 3', applied_affix_ids = NULL"| DB[("dungeon_run_monsters")]
    DB --> PageLoad["/dungeons/active\nShows 'Зомби 3'"]
    PageLoad --> FirstHit["Player first hits monster\nprocess_message_damage()"]
    FirstHit --> EliteRoll["_roll_elite_for_monster()\n6% chance"]
    EliteRoll -->|"94% - not elite"| SetEmpty["applied_affix_ids = []"]
    EliteRoll -->|"6% - elite!"| SetAffixes["name updated, stats boosted\napplied_affix_ids = [id1, ...]"]
    SetEmpty --> Committed["session.commit()\nBut UI already showing old name"]
    SetAffixes --> Committed
    Committed -->|"elite_spawn returned in JSON\nbut frontend ignores it"| NoUIUpdate["Frontend: no change displayed"]
```



**Root causes:**

1. Elite roll fires on first hit, not at dungeon creation — initial UI always shows unmodified name
2. `defense_add` and `evade_add` affix fields are stored but never read in combat damage calculation
3. Frontend has no handling for `elite_spawn` in the `continueBattle()` response, and `/dungeons/active` does not return `is_elite`/`elite_color`/affix names
4. Behavior flags (`BERSERK`, `REGEN`, `REFLECT`, etc.) — defined in data, not yet executable

---

## Fix Plan

### 1. Move elite roll to dungeon creation time

File: `[services/dungeon.py](src/waifu_bot/services/dungeon.py)`, method `_roll_monster_from_template()` (around line 357).

After creating the `DungeonRunMonster` record, call a synchronous version of the affix picker using the player's luck stat (passed in from `start_dungeon`). This way the name and stats are set at dungeon start — the player sees the modified name immediately on the dungeon card.

Key change: remove the lazy sentinel pattern for new runs (set `applied_affix_ids` at creation, never `None`). The lazy path in `_roll_elite_for_monster` can remain as a fallback for legacy monsters.

Luck needs to be passed into `_roll_monster_from_template` — currently only `template` and `position` are passed.

### 2. Wire `defense_add` and `evade_add` into combat damage

File: `[services/combat.py](src/waifu_bot/services/combat.py)`, `process_message_damage()`.

After fetching `run_monster`, load its applied affixes and compute:

- `monster_defense_pct`: sum of `defense_add` from affixes — reduces incoming player damage
- `monster_evade_pct`: sum of `evade_add` — gives the monster a chance to dodge attacks

Apply `monster_defense_pct` to the damage formula before hitting the monster:

```python
if monster_defense_pct > 0:
    damage = int(damage * (1 - monster_defense_pct / 100))
```

Apply `monster_evade_pct` as a dodge roll before applying damage.

### 3. Add elite status to `/dungeons/active` response

File: `[api/routes.py](src/waifu_bot/api/routes.py)`, `active_dungeon` endpoint (line 1524).

After fetching `get_active_dungeon()`, if it's a run-based monster, query its affix records and add:

- `is_elite: bool`
- `elite_color: str | None` (`"blue"`, `"gold"`, `"red"`)
- `applied_affixes: list[str]` — affix names for display

Alternatively, enrich directly in `dungeon_service.get_active_dungeon()`.

### 4. Update frontend UI for elite monsters

Files: `[webapp/app.js](src/waifu_bot/webapp/app.js)`, `[webapp/styles.css](src/waifu_bot/webapp/styles.css)`.

In `renderSoloActiveProgress()`: add an elite color indicator (left border or badge) based on `active.elite_color`. Show affix names as small chips below the monster name.

In `continueBattle()`: if the response contains `elite_spawn`, add a log message showing the elite reveal.

Example UI addition in `renderSoloActiveProgress`:

```js
const eliteBadge = active.is_elite
  ? `<span class="elite-badge elite-${active.elite_color}">${active.applied_affixes?.join(' ') ?? ''}</span>`
  : '';
```

CSS classes `.elite-badge`, `.elite-blue`, `.elite-gold`, `.elite-red` with corresponding border/text colors.

---

## Scope boundary

Behavior flags (`BERSERK`, `REGEN`, `REFLECT`, `SPLIT`, `UNDYING`, `CURSE`, `BUFF_NEXT`, `ANTI_CRIT`) are out of scope for this fix — the data model is complete, but the combat execution logic for each flag is a separate multi-session task. The plan covers what makes affixes visually and mechanically observable (stat affixes + UI display).