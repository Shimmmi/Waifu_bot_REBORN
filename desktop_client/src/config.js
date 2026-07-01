"use strict";

/**
 * Resolves runtime config for the desktop client.
 *
 * Precedence: environment variables > config.local.json (gitignored, for a
 * developer's own machine) > config.json (committed defaults) > hardcoded
 * fallback (local dev server).
 */
const fs = require("fs");
const path = require("path");

function readJsonIfExists(filePath) {
  try {
    if (fs.existsSync(filePath)) {
      return JSON.parse(fs.readFileSync(filePath, "utf8"));
    }
  } catch (err) {
    console.warn(`[config] failed to read ${filePath}:`, err.message);
  }
  return null;
}

function loadFileConfig() {
  const local = readJsonIfExists(path.join(__dirname, "..", "config.local.json"));
  const base = readJsonIfExists(path.join(__dirname, "..", "config.json"));
  return { ...(base || {}), ...(local || {}) };
}

const fileConfig = loadFileConfig();

const config = {
  // Backend base URL serving both the FastAPI JSON API and the /webapp/*.html
  // pages (same origin — see main.py static mount). Point this at your
  // staging stack (docker-compose.staging.yml, default http://127.0.0.1:18000)
  // while developing, and at the production origin for real builds.
  backendUrl:
    process.env.WAIFU_BACKEND_URL || fileConfig.backendUrl || "http://127.0.0.1:8000",

  // Dev-only stub SteamID64, forwarded as X-Steam-Ticket-Dev (see api/deps.py).
  // Server only accepts this header when APP_ENV is dev/stage/testing — safe
  // to leave set in a local config.local.json.
  steamTicketDev: process.env.WAIFU_STEAM_TICKET_DEV || fileConfig.steamTicketDev || null,

  // Overlay window geometry (bottom-right corner, Bongo-Cat-style).
  overlay: {
    width: Number(process.env.WAIFU_OVERLAY_WIDTH) || fileConfig.overlay?.width || 260,
    height: Number(process.env.WAIFU_OVERLAY_HEIGHT) || fileConfig.overlay?.height || 340,
    page: fileConfig.overlay?.page || "battle.html",
  },

  mainWindow: {
    width: fileConfig.mainWindow?.width || 480,
    height: fileConfig.mainWindow?.height || 820,
    page: fileConfig.mainWindow?.page || "index.html",
  },
};

module.exports = config;
