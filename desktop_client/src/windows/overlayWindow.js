"use strict";

const { BrowserWindow, screen } = require("electron");
const path = require("path");
const config = require("../config");

/**
 * Always-on-top, click-through-capable, fully transparent corner overlay
 * showing the main waifu (Bongo-Cat-style). Loads the *existing* battle
 * page over HTTP with ?desktopClient=1 so webapp/app.js picks up the
 * desktop-theme.css `.desktop-overlay` styling (transparent background,
 * chrome hidden) — no new page/markup was created for this.
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
  win.loadURL(
    `${config.backendUrl}/webapp/${config.overlay.page}?desktopClient=1&desktopMode=overlay`
  );

  return win;
}

module.exports = { createOverlayWindow };
