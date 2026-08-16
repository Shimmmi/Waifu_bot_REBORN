"use strict";

const { app, ipcMain, BrowserWindow, session } = require("electron");
const config = require("./config");
const { waitForBackend } = require("./backend/waitForBackend");
const { createOverlayWindow } = require("./windows/overlayWindow");
const { openTabWindow } = require("./windows/appWindow");
const { createLoginWindow } = require("./windows/loginWindow");
const inputTracker = require("./input/inputTracker");
const steamworksClient = require("./steam/steamworksClient");
const desktopAuthStore = require("./desktopAuthStore");

let overlayWindow = null;
let loginWindow = null;
let inputTrackerHandle = null;
let gameBooted = false;

function createWindows() {
  overlayWindow = createOverlayWindow();

  overlayWindow.on("closed", () => {
    overlayWindow = null;
  });
}

function startInputTracker() {
  if (inputTrackerHandle) return;
  inputTrackerHandle = inputTracker.start({
    onFlush: (payload) => {
      for (const win of BrowserWindow.getAllWindows()) {
        win.webContents.send("hit-batch-sent", payload);
      }
    },
    onActivity: () => {
      for (const win of BrowserWindow.getAllWindows()) {
        win.webContents.send("input-activity");
      }
    },
  });
}

function hasUsableAuth() {
  if (desktopAuthStore.hasToken()) return true;
  // Dev/stage automation: steamTicketDev still bypasses the login screen.
  if (config.steamTicketDev) return true;
  return false;
}

function bootGameWindows() {
  if (gameBooted && overlayWindow && !overlayWindow.isDestroyed()) return;
  gameBooted = true;
  createWindows();
  startInputTracker();
}

function showLoginWindow() {
  if (loginWindow && !loginWindow.isDestroyed()) {
    loginWindow.focus();
    return loginWindow;
  }
  loginWindow = createLoginWindow();
  loginWindow.on("closed", () => {
    loginWindow = null;
  });
  return loginWindow;
}

function closeLoginWindow() {
  if (loginWindow && !loginWindow.isDestroyed()) {
    loginWindow.close();
  }
  loginWindow = null;
}

ipcMain.handle("open-tab", (event, page) => {
  const sender = BrowserWindow.fromWebContents(event.sender);
  const anchor =
    overlayWindow && !overlayWindow.isDestroyed() ? overlayWindow : sender;
  openTabWindow(anchor, String(page || "index.html"));
});

ipcMain.handle("close-window", (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win && !win.isDestroyed()) win.close();
});

ipcMain.handle("get-steam-ticket", () => steamworksClient.getAuthTicket());

ipcMain.handle("desktop-auth:get", () => desktopAuthStore.getToken());
ipcMain.handle("desktop-auth:set", (_event, token) => {
  desktopAuthStore.setToken(token);
  return true;
});
ipcMain.handle("desktop-auth:clear", () => {
  desktopAuthStore.clearToken();
  return true;
});
ipcMain.handle("desktop-auth:complete", () => {
  closeLoginWindow();
  bootGameWindows();
  return true;
});
ipcMain.handle("desktop-auth:required", () => {
  desktopAuthStore.clearToken();
  gameBooted = false;
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.close();
  }
  showLoginWindow();
  return true;
});

async function bootDesktopClient() {
  console.log(`[waifu-desktop] backend: ${config.backendUrl}`);
  steamworksClient.init();

  const ready = await waitForBackend(config.backendUrl);
  if (!ready) {
    console.error(
      "[waifu-desktop] backend unreachable — opening windows anyway; " +
        "pages may stay blank until you reload (see docs/STEAM_CLIENT_DEV_SETUP.md)."
    );
  }

  if (hasUsableAuth()) {
    bootGameWindows();
  } else {
    console.log("[waifu-desktop] no session — showing login window");
    showLoginWindow();
  }
}

app.whenReady().then(() => {
  if (process.env.WAIFU_APP_ENV === "dev") {
    session.defaultSession.clearCache().catch(() => {});
  }
  bootDesktopClient().catch((err) => {
    console.error("[waifu-desktop] boot failed:", err.message);
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      bootDesktopClient().catch((err) => {
        console.error("[waifu-desktop] boot failed:", err.message);
      });
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  inputTrackerHandle?.stop();
  steamworksClient.shutdown();
});
