"use strict";

const { BrowserWindow, screen } = require("electron");
const path = require("path");
const config = require("../config");
const { loadUrlWithRetry } = require("./loadWithRetry");

/**
 * Always-on-top, fully transparent corner overlay showing the main waifu
 * (Bongo-Cat-style). Loads the dedicated companion HUD page
 * (webapp/overlay.html + pages/overlay.js): waifu portrait with CSS
 * animation states (sleep/idle/battle), HP + resources, monster strip
 * while a dungeon is active, and a menu that opens other webapp pages as
 * draggable windows via window.waifuDesktop.openTab().
 */
function createOverlayWindow() {
  const display = screen.getPrimaryDisplay();
  const { width: screenW, height: screenH } = display.workAreaSize;
  const { width, height } = config.overlay;

  const win = new BrowserWindow({
    width,
    height,
    x: screenW - width - 24,
    y: screenH - height - 24,
    frame: false,
    transparent: true,
    hasShadow: false,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    fullscreenable: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      backgroundThrottling: false,
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  // Whole overlay window is draggable via -webkit-app-region: drag set on
  // `.desktop-overlay body` in desktop-theme.css (with buttons/links excluded).
  // initialDelayMs: staggers this window's first request slightly after the
  // main window's (see loadWithRetry.js) to avoid two "first ever"
  // connections hitting a freshly-started backend at the exact same instant.
  loadUrlWithRetry(
    win,
    `${config.backendUrl}/webapp/${config.overlay.page}?desktopClient=1&desktopMode=overlay`,
    { label: "overlay", initialDelayMs: 500 }
  );

  return win;
}

module.exports = { createOverlayWindow };
