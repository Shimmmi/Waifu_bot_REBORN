"use strict";

const config = require("../config");

/**
 * Global mouse-click / key-press counter -> batched POST to
 * /api/pc/hits/batch (see src/waifu_bot/api/pc_client_routes.py).
 *
 * Privacy: only *counts* are tracked, globally (works even when the app
 * isn't focused, like Bongo Cat) — never which key was pressed or where the
 * click landed. Nothing is logged or sent beyond a per-flush integer. This
 * also matters for antivirus/false-positive concerns: a global input hook
 * that only counts (never records keystrokes/content) is a materially
 * different — and easier to justify in a privacy notice — thing than a
 * keylogger, but code signing + a clear in-app disclosure are still
 * expected before a public Steam release (see plan, "антивирус"/privacy).
 *
 * Matches the *existing* backend pacing: FLUSH_INTERVAL_MS mirrors
 * SPAM_WINDOW_SECONDS (game/constants.py) — the actual damage-rate cap is
 * still enforced server-side by CombatService's Redis spam gate, this
 * interval just avoids flushing faster than the server would ever accept.
 *
 * Calibration (staging): FLUSH_INTERVAL_MS (3s) should stay in the same ballpark
 * as SPAM_WINDOW_SECONDS on the server. Lower to 1–2s only after measuring real
 * click cadence; overlay attack animation uses weapon attack_speed locally and
 * does not depend on this interval.
 */
const FLUSH_INTERVAL_MS = 3000;

// Throttle for the onActivity callback (drives instant overlay animations):
// key-mashing fires uiohook events every few ms, but the overlay only needs
// one "player is active, play a hit" signal per animation frame or so.
const ACTIVITY_THROTTLE_MS = 100;

let flushTimer = null;
let hookHandle = null;
let pendingHits = 0;
let onFlushCallback = null;
let onActivityCallback = null;
let lastActivityEmit = 0;

function buildAuthHeaders() {
  const headers = { "Content-Type": "application/json" };
  const desktopAuthStore = require("../desktopAuthStore");
  const sessionToken = desktopAuthStore.getToken();
  if (sessionToken) {
    headers["X-Desktop-Session"] = String(sessionToken);
    return headers;
  }
  if (config.steamTicketDev) {
    headers["X-Steam-Ticket-Dev"] = String(config.steamTicketDev);
  }
  // Этап 6: once the Steamworks SDK is wired into this (main) process, add
  // headers["X-Steam-Ticket"] = <real ticket> here — no IPC round-trip
  // needed since the SDK lives in the main process, same as this tracker.
  return headers;
}

async function flush() {
  const hitCount = pendingHits;
  pendingHits = 0;
  if (hitCount <= 0) return;

  let result = null;
  try {
    const res = await fetch(`${config.backendUrl}/api/pc/hits/batch`, {
      method: "POST",
      headers: buildAuthHeaders(),
      body: JSON.stringify({ hit_count: hitCount, client_window_ms: FLUSH_INTERVAL_MS }),
    });
    result = await res.json().catch(() => null);
    if (!res.ok) {
      console.warn("[input-tracker] hit batch rejected:", res.status, result);
    }
  } catch (err) {
    console.warn("[input-tracker] failed to flush hit batch:", err.message);
  }

  if (onFlushCallback) {
    try {
      onFlushCallback({ hitCount, result });
    } catch {
      /* ignore renderer notification errors */
    }
  }
}

function noteActivity() {
  pendingHits += 1;
  if (!onActivityCallback) return;
  const now = Date.now();
  if (now - lastActivityEmit < ACTIVITY_THROTTLE_MS) return;
  lastActivityEmit = now;
  try {
    onActivityCallback();
  } catch {
    /* ignore renderer notification errors */
  }
}

/**
 * @param {object} opts
 * @param {(payload: {hitCount: number, result: any}) => void} [opts.onFlush]
 *   Called after every flush attempt (even if it failed/was a no-op),
 *   e.g. to forward "hit-batch-sent" over IPC for an optional debug HUD.
 * @param {() => void} [opts.onActivity]
 *   Called on every raw click/keypress, throttled to ACTIVITY_THROTTLE_MS.
 *   Drives the overlay's instant animations (hit lunge, AFK reset) without
 *   waiting for the 3s server batch — see webapp/pages/overlay.js.
 * @returns {{ stop(): void }}
 */
function start(opts = {}) {
  onFlushCallback = opts.onFlush || null;
  onActivityCallback = opts.onActivity || null;

  // Lazy require: uiohook-napi ships a native module per platform/arch.
  // Keep the rest of the app usable (windows still open) even if it's
  // missing or fails to load on an unsupported setup.
  let uIOhook;
  try {
    ({ uIOhook } = require("uiohook-napi"));
  } catch (err) {
    console.error(
      "[input-tracker] uiohook-napi unavailable — clicks/keys will not be tracked:",
      err.message
    );
    return { stop() {} };
  }

  hookHandle = uIOhook;
  hookHandle.on("click", noteActivity);
  hookHandle.on("keydown", noteActivity);
  hookHandle.start();

  flushTimer = setInterval(flush, FLUSH_INTERVAL_MS);

  return {
    stop() {
      if (flushTimer) clearInterval(flushTimer);
      flushTimer = null;
      try {
        hookHandle?.stop();
      } catch {
        /* ignore */
      }
      hookHandle = null;
    },
  };
}

module.exports = { start, FLUSH_INTERVAL_MS };
