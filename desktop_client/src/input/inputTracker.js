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
 */
const FLUSH_INTERVAL_MS = 3000;

let flushTimer = null;
let hookHandle = null;
let pendingHits = 0;
let onFlushCallback = null;

function buildAuthHeaders() {
  const headers = { "Content-Type": "application/json" };
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

/**
 * @param {object} opts
 * @param {(payload: {hitCount: number, result: any}) => void} [opts.onFlush]
 *   Called after every flush attempt (even if it failed/was a no-op),
 *   e.g. to forward "hit-batch-sent" over IPC for an optional debug HUD.
 * @returns {{ stop(): void }}
 */
function start(opts = {}) {
  onFlushCallback = opts.onFlush || null;

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
  hookHandle.on("click", () => {
    pendingHits += 1;
  });
  hookHandle.on("keydown", () => {
    pendingHits += 1;
  });
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
