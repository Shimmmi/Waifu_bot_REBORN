# Steam client — implementation status (feature/steam-client)

Status snapshot of what was actually built vs. what still needs a human with
a display/payment method/Steam account. See the full step-by-step plan for
the original design; this doc tracks *implementation* state, not the plan
itself (which is not modified by this branch).

## What's done (code, tested where testable in a headless CI-like environment)

| Этап | What | Verified how |
|---|---|---|
| VPS hygiene | Freed ~7.7 GB (docker builder cache, journal, missing `logrotate` package was installed + enabled + run) | `df -h` before/after (89% → 67% used) |
| 0 | `feature/steam-client` branch, `docker-compose.staging.yml`, `scripts/staging_seed_from_prod_dump.sh` | Manual review; compose file not started in this environment (no reason to run a second Postgres/Redis pair here) |
| 1 | `player_identity_links` table + `player_synthetic_id_seq`, `services/auth_steam.py`, `X-Steam-Ticket(-Dev)` in `get_player_id`, `POST /api/auth/link_identity/steam` | Unit tests (mocked session) **and** a real throwaway Postgres: migration up/down, FK/unique constraint, `resolve_or_create_player_for_steam` create + idempotency, `link_steam_identity_to_player` conflict (409) |
| 2 | `POST /api/pc/hits/batch` | Unit tests (mocked `CombatService`) |
| 3 | `isDesktopClient()` branch in `webapp/app.js`, `webapp/desktop-theme.css` | `node --check` (syntax), manual read-through against `battle.html`'s real DOM (no visual render available here) |
| 4 | `desktop_client/` Electron shell (main window + transparent overlay + tab windows) | `node --check` on every file; **not** `npm install`-ed or run (no display in this environment, see `desktop_client/README.md`) |
| 5 | `desktop_client/src/input/inputTracker.js` (uiohook-napi, batched flush) | `node --check`; dry-run confirmed graceful degradation when `uiohook-napi` isn't installed |
| 6 | `desktop_client/src/steam/steamworksClient.js` scaffold, `steam_appid.txt`, `docs/STEAM_STEAMWORKS_SETUP.md` | Code review; intentionally a no-op until a real Steamworks account exists |

Full regression check: `pytest tests/unit` — same 12 pre-existing failures
before and after this branch (armory_service/elite_split/guild_raid_muster/
item_codex/legendary_distribution/tavern_first_hire_free — all unrelated to
auth/combat/webapp, confirmed by running them against the pre-Steam commit
too). **Zero new failures.** `git diff` against the sync point is +1599/-2
across 28 files, and both deleted lines are non-behavioral (a docstring
sentence, and an `if` turned into `if/else` that still does the same thing
for the existing branch).

## What's NOT done here (needs a human, on their own machine, outside this session)

- **Steamworks Partner account + $100 fee** — see `docs/STEAM_STEAMWORKS_SETUP.md`.
  Until then `STEAM_WEB_API_KEY`/`STEAM_APP_ID` are unset and
  `validate_steam_ticket()` answers 501; only the dev stub
  (`X-Steam-Ticket-Dev`) works, and only when `APP_ENV` is `dev|stage|testing`.
- **`npm install` + visual testing of desktop_client/** — this VPS is
  headless and shouldn't carry the Electron/native-module toolchain anyway
  (see plan §1.4/§1.6). Needs a real desktop to confirm the overlay actually
  looks right, window dragging behaves, etc.
- **Calibrating `MAX_HITS_PER_REQUEST` / `FLUSH_INTERVAL_MS`** against real
  click cadence from a real mouse/keyboard — current values are conservative
  defaults matching the backend's existing `SPAM_WINDOW_SECONDS`, not yet
  measured against actual play.
- **Antivirus/code-signing review** for the global input hook before any
  public distribution — `uiohook-napi` is a legitimate, widely-used library,
  but an unsigned binary with a global input hook is a classic AV false
  positive trigger.
- **electron-builder actual build + SteamPipe upload** — depends on the
  Steamworks account existing first.

## How to pick this up

1. `git checkout feature/steam-client` on your own machine (not the VPS).
2. `cd desktop_client && npm install && cp config.json config.local.json`.
3. Point `config.local.json`'s `backendUrl` at a running backend (either
   `docker-compose.staging.yml` here, or a plain local `uvicorn` run).
4. Set `steamTicketDev` in `config.local.json` to any string, `npm run dev`.
5. Iterate on the overlay/window visuals — this is the first point where
   actual human eyes are needed.
