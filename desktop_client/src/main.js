"use strict";

const { app, ipcMain, BrowserWindow } = require("electron");
const config = require("./config");
const { createOverlayWindow } = require("./windows/overlayWindow");
const { createMainWindow, openTabWindow } = require("./windows/appWindow");
const inputTracker = require("./input/inputTracker");

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

app.whenReady().then(() => {
  console.log(`[waifu-desktop] backend: ${config.backendUrl}`);
  createWindows();

  inputTrackerHandle = inputTracker.start({
    onFlush: (payload) => {
      for (const win of BrowserWindow.getAllWindows()) {
        win.webContents.send("hit-batch-sent", payload);
      }
    },
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindows();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  inputTrackerHandle?.stop();
});
