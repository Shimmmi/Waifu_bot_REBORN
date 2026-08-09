"use strict";

/**
 * Chromium net error codes worth retrying automatically — all "backend not
 * reachable yet" conditions rather than real page errors (a 404/500 loads
 * fine as far as Chromium is concerned; those aren't retried here).
 *
 * This exists because `docker compose up -d` returns as soon as the api
 * container process forks, well before Uvicorn (imports + 14 background
 * task loops) actually accepts HTTP connections, and Docker Desktop for
 * Windows can also transiently reset the port for a few seconds right
 * after a (re)start. Racing `npm run dev` against that produces
 * ERR_EMPTY_RESPONSE even on an otherwise-healthy setup — see
 * docs/STEAM_CLIENT_DEV_SETUP.md "ERR_EMPTY_RESPONSE". Retrying the load a
 * few times makes the client self-heal instead of requiring the user to
 * manually reload once the backend catches up.
 */
const RETRYABLE_ERROR_CODES = new Set([
  -100, // ERR_CONNECTION_CLOSED
  -101, // ERR_CONNECTION_RESET
  -102, // ERR_CONNECTION_REFUSED
  -105, // ERR_NAME_NOT_RESOLVED
  -109, // ERR_ADDRESS_UNREACHABLE
  -118, // ERR_CONNECTION_TIMED_OUT
  -324, // ERR_EMPTY_RESPONSE
]);

/**
 * Loads `url` into `win`, auto-retrying on transient connection failures
 * instead of leaving the window stuck on Chromium's default error page.
 *
 * The retry budget is intentionally generous (~2 minutes total by default):
 * on Docker Desktop for Windows, the container's own healthcheck (curl
 * against localhost *inside* the container) can report "healthy" seconds
 * before the separate host-side port-forward (vpnkit/WinNAT, the thing that
 * actually makes 127.0.0.1:18000 reachable from the Windows side) finishes
 * (re)binding after a container rebuild — those are two independent moving
 * parts. A short retry budget can still run out before that catches up.
 *
 * @param {import("electron").BrowserWindow} win
 * @param {string} url
 * @param {object} [opts]
 * @param {number} [opts.maxAttempts]
 * @param {number} [opts.intervalMs] base delay; grows slightly with each
 *   attempt (capped at 3s) so a long-stuck backend isn't hammered forever.
 * @param {string} [opts.label] short tag for console messages, e.g. "overlay"
 * @param {number} [opts.initialDelayMs] delay before the *first* loadURL
 *   call. Windows only creates all BrowserWindows back-to-back in the same
 *   tick, so their first navigation requests land on the backend within
 *   milliseconds of each other; on Docker Desktop for Windows this has been
 *   observed to make one window's very first connection fail with
 *   ERR_EMPTY_RESPONSE (and then keep failing) while a window created a
 *   moment earlier succeeds outright — staggering avoids two "first ever"
 *   connections hitting the host port-forward at the same instant.
 */
function loadUrlWithRetry(
  win,
  url,
  { maxAttempts = 60, intervalMs = 1000, label = "", initialDelayMs = 0 } = {}
) {
  let attempt = 0;
  const tag = label ? `[${label}] ` : "";

  win.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription, _validatedURL, isMainFrame) => {
      if (!isMainFrame || win.isDestroyed()) return;
      if (errorCode === -3) return; // ERR_ABORTED - superseded by our own retry loadURL()

      if (!RETRYABLE_ERROR_CODES.has(errorCode)) {
        console.warn(`${tag}failed to load ${url}: ${errorDescription} (${errorCode})`);
        return;
      }

      attempt += 1;
      if (attempt === 1 || attempt % 5 === 0) {
        console.warn(
          `${tag}backend not reachable yet (${errorDescription}), retrying... (attempt ${attempt}/${maxAttempts})`
        );
      }
      if (attempt > maxAttempts) {
        console.error(
          `${tag}backend still unreachable after ${maxAttempts} attempts - giving up. ` +
            "This usually means the api container itself is down (check `docker compose ... logs api`), " +
            "not just slow to warm up. On Windows, if `docker compose ... ps` shows api as healthy but this " +
            "keeps failing, the host-side port-forward may be stuck — try `wsl --shutdown` then restart Docker " +
            "Desktop (see docs/STEAM_CLIENT_DEV_SETUP.md 'ERR_EMPTY_RESPONSE'), then press Ctrl+R in this window."
        );
        return;
      }
      const delay = Math.min(intervalMs + attempt * 200, 3000);
      setTimeout(() => {
        if (!win.isDestroyed()) win.loadURL(url);
      }, delay);
    }
  );

  if (initialDelayMs > 0) {
    setTimeout(() => {
      if (!win.isDestroyed()) win.loadURL(url);
    }, initialDelayMs);
  } else {
    win.loadURL(url);
  }
}

module.exports = { loadUrlWithRetry };
