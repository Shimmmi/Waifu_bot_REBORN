"use strict";

const { contextBridge, ipcRenderer } = require("electron");
const config = require("./config");

/**
 * Mutable bag for sync session token reads from authHeaders().
 * contextBridge freezes the exposed API object, but nested object
 * properties remain mutable.
 */
const sessionState = { token: null };

function mirrorSessionToLocalStorage(token) {
  try {
    if (typeof localStorage === "undefined") return;
    if (token) localStorage.setItem("waifuDesktopSession", String(token));
    else localStorage.removeItem("waifuDesktopSession");
  } catch {
    /* ignore */
  }
}

const sessionReady = ipcRenderer
  .invoke("desktop-auth:get")
  .then((token) => {
    sessionState.token = token ? String(token) : null;
    mirrorSessionToLocalStorage(sessionState.token);
    return sessionState.token;
  })
  .catch(() => {
    sessionState.token = null;
    return null;
  });

/**
 * Bridge exposed to webapp as `window.waifuDesktop`.
 */
contextBridge.exposeInMainWorld("waifuDesktop", {
  // Real Steamworks session ticket — always null until Этап 6.
  getSteamTicket: () => null,
  getSteamTicketAsync: () => ipcRenderer.invoke("get-steam-ticket"),

  // Dev-only stub SteamID64 (config.local.json). Accepted only in
  // APP_ENV=dev|stage|testing.
  steamTicketDev: config.steamTicketDev,

  // Interim desktop JWT (email / Telegram) for X-Desktop-Session.
  getDesktopSessionToken: () => sessionState.token,
  getDesktopSessionTokenAsync: async () => {
    const token = await sessionReady;
    if (token != null) return token;
    const fresh = await ipcRenderer.invoke("desktop-auth:get");
    sessionState.token = fresh ? String(fresh) : null;
    mirrorSessionToLocalStorage(sessionState.token);
    return sessionState.token;
  },
  whenDesktopSessionReady: () => sessionReady,
  setDesktopSessionToken: async (token) => {
    const value = token ? String(token) : null;
    await ipcRenderer.invoke("desktop-auth:set", value);
    sessionState.token = value;
    mirrorSessionToLocalStorage(value);
    return true;
  },
  clearDesktopSession: async () => {
    await ipcRenderer.invoke("desktop-auth:clear");
    sessionState.token = null;
    mirrorSessionToLocalStorage(null);
    return true;
  },
  notifyAuthComplete: () => ipcRenderer.invoke("desktop-auth:complete"),
  requireAuth: () => ipcRenderer.invoke("desktop-auth:required"),

  openTab: (page) => ipcRenderer.invoke("open-tab", page),

  onHitBatchSent: (callback) => {
    ipcRenderer.on("hit-batch-sent", (_event, payload) => callback(payload));
  },

  onInputActivity: (callback) => {
    ipcRenderer.on("input-activity", () => callback());
  },

  closeWindow: () => ipcRenderer.invoke("close-window"),
});
