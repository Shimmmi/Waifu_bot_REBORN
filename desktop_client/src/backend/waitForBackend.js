"use strict";

/**
 * Poll the staging backend from the Electron *main* process until HTTP
 * succeeds from the host OS (Windows/macOS/Linux), not just until the
 * Docker container reports "healthy" inside the VM.
 *
 * See docs/STEAM_CLIENT_DEV_SETUP.md "ERR_EMPTY_RESPONSE".
 */

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeBaseUrl(url) {
  return String(url || "").replace(/\/+$/, "");
}

/**
 * @param {string} url full URL to probe
 * @param {object} [opts]
 * @param {number} [opts.timeoutMs]
 * @param {string} [opts.bodyMustContain] if set, response body must include this substring
 * @returns {Promise<boolean>}
 */
async function probeUrl(url, { timeoutMs = 10_000, bodyMustContain = "" } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return false;
    if (!bodyMustContain) return true;
    const text = await res.text();
    return text.includes(bodyMustContain);
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Wait until backendUrl responds on /health (and optionally overlay.html).
 *
 * @param {string} backendUrl e.g. http://127.0.0.1:18000
 * @param {object} [opts]
 * @param {number} [opts.maxAttempts]
 * @param {number} [opts.intervalMs] base delay; grows slightly per attempt (cap 3s)
 * @param {boolean} [opts.probeOverlay] also GET /webapp/overlay.html
 * @returns {Promise<boolean>} true if ready
 */
async function waitForBackend(
  backendUrl,
  { maxAttempts = 60, intervalMs = 1000, probeOverlay = true } = {}
) {
  const base = normalizeBaseUrl(backendUrl);
  if (!base) {
    console.error("[waifu-desktop] waitForBackend: empty backendUrl");
    return false;
  }

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const healthOk = await probeUrl(`${base}/health`);
    let overlayOk = true;
    if (healthOk && probeOverlay) {
      overlayOk = await probeUrl(`${base}/webapp/overlay.html`, {
        bodyMustContain: "ov-menu-btn",
      });
    }

    if (healthOk && overlayOk) {
      if (attempt > 1) {
        console.log(`[waifu-desktop] backend ready (attempt ${attempt}/${maxAttempts})`);
      }
      return true;
    }

    if (attempt === 1 || attempt % 5 === 0) {
      console.warn(
        `[waifu-desktop] waiting for backend... (attempt ${attempt}/${maxAttempts})`
      );
    }

    if (attempt < maxAttempts) {
      const delay = Math.min(intervalMs + attempt * 200, 3000);
      await sleep(delay);
    }
  }

  console.error(
    `[waifu-desktop] backend still unreachable after ${maxAttempts} attempts. ` +
      "Run scripts/check_staging_backend.ps1 from repo root, or on Windows try " +
      "wsl --shutdown then restart Docker Desktop (see docs/STEAM_CLIENT_DEV_SETUP.md)."
  );
  return false;
}

module.exports = { waitForBackend, probeUrl };
