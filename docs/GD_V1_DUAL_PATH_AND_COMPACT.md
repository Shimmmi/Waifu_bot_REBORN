"""GD v1 dual-path with solo and compact group output (post-audit).

## Dual-path GD + Solo

While a GD v1 cycle is `active` in a Telegram chat:

- Registered players' messages still feed the GD Redis round buffer.
- By default the same messages also apply **solo dungeon / abyss damage** (dual-path).
- Optional `game_config.gd_v1_skip_group_solo_while_active=1` skips solo+Abyss in that chat
  while GD is active (guild raid and chat rewards unchanged).

Guild Raid takes priority when a player is in an active raid.

## Chat surface (anti-spam)

Each resolved GD round posts **one** compact group message (AI narrative + short status).
Full mechanical battle log and HP roster are sent as **DM** to registered participants
(respecting `group_dungeon` notification prefs) and remain available via WebApp
`GET /gd/cycles/{cycle_id}/battle-log`.

Idle (no player actions): combat is **skipped**, group gets a short template (no AI).
Two consecutive idle rounds → cycle `cancelled` (no victory rewards).
Three party wipes → same. Player stop: `POST /gd/stop` or `/gd_stop` (registered only).

## Entry

Only `/gd_join` (group), WebApp muster/join, or DM deep-link opens participation.
Per-chat cooldown: `gd_cooldown_after_finish_hours` (default 168h).

## WebApp muster and late-join

- `GET /gd/available-chats` — chats where **player ∩ bot** (heuristic: player seen + bot active).
- `POST /gd/muster` `{chat_id}` — open registration, auto-join starter, one invite post (rate-limited).
- `GET /gd/dungeons/joinable` — open cycles in those chats the player has not joined.
- `POST /gd/join` `{chat_id}` — registration join or **late join** into `active` (until `wave=done`).
- `POST /gd/stop` `{chat_id}` — end active run without victory rewards.
- DM: `/start gd_join_<chat_id>` or `/gd_join [chat_id]`.

Late join stores `gd_registrations.joined_at_round` and scales rewards via
`late_join_reward_stage_mult` (share + completion chest). Challenge level is **not** recalculated.
Presence floor does not apply to silent late joiners with zero contrib rounds.

## Balance (2p+)

- Trash count: 1 monster for party ≤2; else `1 + n//2`.
- Monster damage scaled down for small parties (`gd_monster_dmg_party_ref` / n, min floor).
- `gd_round_cycle_cap` default 5; boss HP grows with party size (`gd_boss_hp_party_mult`).

## Narrative

Preset `gd_narrative` (`AI_PRESET_GD`, model `openai/gpt-5.6-luna-pro`) — GD only.
Humor without grotesque; folding chronicle from last 1–2 round narratives.
"""
