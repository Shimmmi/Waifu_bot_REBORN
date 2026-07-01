"use strict";

const { app, ipcMain, BrowserWindow } = require("electron");
const config = require("./config");
const { createOverlayWindow } = require("./windows/overlayWindow");
const { createMainWindow, openTabWindow } = require("./windows/appWindow");

let mainWindow = null;
let overlayWindow = null;

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

  // Этап 5 wiring point: once input/inputTracker.js exists, start it here,
  // e.g. require("./input/inputTracker").start({ backendUrl: config.backendUrl,
  // getAuthHeaders, overlayWindow }).

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindows();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
