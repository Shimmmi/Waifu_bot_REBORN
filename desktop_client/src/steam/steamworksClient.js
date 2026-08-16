"use strict";

/**
 * Steamworks SDK wrapper — SCAFFOLD ONLY (Этап 6).
 *
 * A real Steamworks Partner account (one-time $100 fee) and an App ID are
 * required before any of this can actually talk to Steam; that step is a
 * manual, paid, human action outside what an agent/CI can do — see
 * docs/STEAM_STEAMWORKS_SETUP.md for the exact checklist. Until then this
 * module is intentionally a safe no-op: `isAvailable()` is false, and
 * `getAuthTicket()` returns null so callers (preload.js / input tracker)
 * keep using the X-Steam-Ticket-Dev stub instead.
 *
 * Once a real account + App ID exist:
 *   1. npm install steamworks.js (or greenworks — steamworks.js is the
 *      actively-maintained N-API binding as of 2026) in desktop_client/.
 *   2. Replace steam_appid.txt's placeholder (480 = Valve's public
 *      "Spacewar" test app, used for local SDK bring-up) with the real App ID.
 *   3. Fill in init()/getAuthTicket() below using that package's API.
 *   4. Wire preload.js's getSteamTicket() to call this module via IPC from
 *      the main process (this module MUST run in main, not a renderer).
 */

let sdk = null;
let initialized = false;

function isAvailable() {
  return initialized && sdk !== null;
}

/**
 * Attempts to initialize the Steamworks SDK. Safe to call even without the
 * `steamworks.js` package installed or a real App ID — resolves to false
 * instead of throwing, so main.js can call this unconditionally.
 */
function init() {
  try {
    // eslint-disable-next-line global-require
    sdk = require("steamworks.js");
  } catch {
    console.warn(
      "[steamworks] steamworks.js not installed — Steam auth/overlay disabled, " +
        "using X-Steam-Ticket-Dev stub instead (see docs/STEAM_STEAMWORKS_SETUP.md)"
    );
    return false;
  }

  try {
    sdk.init();
    initialized = true;
    return true;
  } catch (err) {
    console.warn("[steamworks] init() failed (no valid steam_appid.txt / Steam not running?):", err.message);
    sdk = null;
    initialized = false;
    return false;
  }
}

/**
 * Returns a fresh Steam session ticket (base64/hex string) for the
 * backend's X-Steam-Ticket header (see services/auth_steam.py
 * validate_steam_ticket, which calls ISteamUserAuth/AuthenticateUserTicket).
 * Returns null when the SDK isn't available.
 */
function getAuthTicket() {
  if (!isAvailable()) return null;
  try {
    // Exact call depends on the installed binding's API, e.g.:
    //   const { ticket } = sdk.auth.getSessionTicket();
    //   return ticket.toString("hex");
    // Left unimplemented until the package is actually installed against a
    // real App ID (see class doc above).
    return null;
  } catch (err) {
    console.warn("[steamworks] getAuthTicket() failed:", err.message);
    return null;
  }
}

function shutdown() {
  if (!isAvailable()) return;
  try {
    sdk.shutdown?.();
  } catch {
    /* ignore */
  }
  sdk = null;
  initialized = false;
}

module.exports = { init, isAvailable, getAuthTicket, shutdown };
