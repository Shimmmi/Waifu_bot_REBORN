# Steamworks onboarding checklist (Этап 6, manual)

This is the part of the Steam-client plan that genuinely cannot be done by
an agent or in CI: it requires a real payment, a legal/business identity,
and manual clicking through Valve's partner portal. Everything code-side
that can be prepared ahead of time already is (see `desktop_client/`,
`src/waifu_bot/services/auth_steam.py`) — this doc is the checklist for
whoever has the authority/payment method to do the rest.

## 1. Steamworks Partner account

1. Go to <https://partner.steamgames.com/> and sign in / create a Steam
   account for the studio (recommended: a separate account from any
   personal Steam account).
2. Register as a partner, pay the one-time **$100 USD** app fee (refunded if
   you ship & meet Valve's revenue threshold — see their docs for current
   terms). This is the step deferred until this stage on purpose (see plan
   §1.3) — everything up to here was buildable without it.
3. Create a new app ("App Admin" -> "Create a new app"). Note the **App ID**
   Valve assigns — replace the placeholder `480` in
   `desktop_client/steam_appid.txt` with it once you have it (480 is Valve's
   public "Spacewar" test app, only meant for local SDK bring-up before you
   have your own ID).

## 2. Web API key (for server-side ticket validation)

1. In the Partner site: Users & Permissions -> Manage Web API Keys ->
   create a key scoped to the new App ID.
2. Set on the backend (VPS `.env`, **not** committed):
   ```
   STEAM_WEB_API_KEY=<the key>
   STEAM_APP_ID=<the App ID>
   ```
   Once both are set, `services/auth_steam.validate_steam_ticket()` stops
   returning 501 and starts actually validating tickets against
   `ISteamUserAuth/AuthenticateUserTicket` — no code change needed, see that
   file's docstring.

## 3. Steamworks SDK in the desktop client

1. Download the Steamworks SDK from the partner site (needed regardless of
   which Node binding you use — some bindings vendor it, some don't).
2. In `desktop_client/`: `npm install steamworks.js` (actively-maintained
   N-API binding as of 2026; re-check this is still the best option before
   installing — `greenworks` is the older alternative).
3. Implement `desktop_client/src/steam/steamworksClient.js`'s `init()` /
   `getAuthTicket()` bodies against whichever package's actual API (they
   change between major versions; the scaffold has the exact call sites
   marked and links to `ISteamUserAuth/AuthenticateUserTicket` on the
   backend side for context).
4. Switch `webapp/app.js`'s `authHeaders()` (and its handful of call sites)
   to `await` the ticket instead of calling `window.waifuDesktop.getSteamTicket()`
   synchronously — see the comment in `desktop_client/src/preload.js` for
   exactly why this is a separate, deliberate follow-up step and not done
   as part of the scaffold.

## 4. Store page + build

1. Fill in the store page (screenshots, description, age rating questionnaire).
2. `electron-builder` config already lives in `desktop_client/package.json`
   ("build" section) — extend it with Steam-specific packaging once ready
   (this typically means: build normally with electron-builder, then hand
   the output off to **SteamPipe** (`steamcmd` + a depot/app build script)
   for the actual Steam upload — SteamPipe does not replace electron-builder,
   it distributes what electron-builder already produced).
3. **Do this build on your own machine or a dedicated CI runner — not the
   shared VPS** (see `desktop_client/README.md` and plan §1.4/§1.6: disk
   space and the lack of a display there rule it out for anything Electron).

## 5. Release

Coordinate with the `qa_release` stage of the plan: regression-test the
existing Telegram WebApp is unaffected, calibrate PC-hit pacing on staging,
have someone review the input tracker for antivirus-false-positive risk
(code signing helps a lot here — Steam builds should be signed), then ship
to a closed beta via Steam's playtest/beta-branch feature before a public
release.
