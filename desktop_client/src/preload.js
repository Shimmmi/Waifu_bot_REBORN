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
  // Real Steamworks session ticket. Kept synchronous (always null) on
  // purpose: webapp/app.js's authHeaders()/getDesktopSteamAuthHeader() call
  // this synchronously from several non-async call sites, and
  // steamworksClient.getAuthTicket() is itself still unimplemented (Этап 6
  // needs a real Steamworks Partner account + App ID first, see
  // docs/STEAM_STEAMWORKS_SETUP.md). The real ticket IS already reachable
  // from the main process via ipcRenderer.invoke("get-steam-ticket") —
  // switching to it requires making authHeaders() (webapp/app.js) and its
  // call sites async first; tracked as a follow-up, not done silently here.
  getSteamTicket: () => null,
  getSteamTicketAsync: () => ipcRenderer.invoke("get-steam-ticket"),

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
