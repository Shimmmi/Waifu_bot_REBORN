"use strict";

const { app, ipcMain, BrowserWindow } = require("electron");
const config = require("./config");
const { waitForBackend } = require("./backend/waitForBackend");
const { createOverlayWindow } = require("./windows/overlayWindow");
const { createMainWindow, openTabWindow } = require("./windows/appWindow");
const inputTracker = require("./input/inputTracker");
const steamworksClient = require("./steam/steamworksClient");

let mainWindow = null;
let overlayWindow = null;
let inputTrackerHandle = null;

function createWindows() {
  mainWindow = createMainWindow();
  overlayWindow = createOverlayWindow();

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  overlayWindow.on("closed", () => {
    overlayWindow = null;
  });
}

ipcMain.handle("open-tab", (event, page) => {
  const parent = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  openTabWindow(parent, String(page || "index.html"));
});

ipcMain.handle("close-window", (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win && !win.isDestroyed()) win.close();
});

// Real Steam ticket for preload.js's window.waifuDesktop.getSteamTicket().
// Returns null (falls back to the X-Steam-Ticket-Dev stub) until Этап 6's
// manual Steamworks account setup is done — see steamworksClient.js.
ipcMain.handle("get-steam-ticket", () => steamworksClient.getAuthTicket());

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

  createWindows();
  startInputTracker();
}

app.whenReady().then(() => {
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
