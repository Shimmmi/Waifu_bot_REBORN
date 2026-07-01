"use strict";

const { contextBridge, ipcRenderer } = require("electron");
const config = require("./config");

/**
 * Bridge exposed to the (existing, unmodified) webapp/app.js as
 * `window.waifuDesktop`. Keep this surface tiny and side-effect free —
 * app.js only reads it, see isDesktopClient()/getDesktopSteamAuthHeader()
 * in webapp/app.js.
 */
contextBridge.exposeInMainWorld("waifuDesktop", {
  // Real Steamworks session ticket. Returns null until Этап 6 wires up the
  // Steamworks SDK (steamworks.js / greenworks) in the main process and an
  // IPC round-trip here; falls back to steamTicketDev below in the meantime.
  getSteamTicket: () => null,

  // Dev-only stub SteamID64 (see config.js / config.local.json). Only
  // accepted server-side when APP_ENV is dev/stage/testing.
  steamTicketDev: config.steamTicketDev,

  // Opens another webapp page (shop/tavern/guild_hall/...) as a draggable
  // window on top of the main window (see main.js "open-tab" handler).
  openTab: (page) => ipcRenderer.invoke("open-tab", page),

  // Wired up in Этап 5 (input/inputTracker.js): lets a renderer subscribe to
  // locally-batched click/keypress counts for a debug HUD, purely optional.
  onHitBatchSent: (callback) => {
    ipcRenderer.on("hit-batch-sent", (_event, payload) => callback(payload));
  },
});
