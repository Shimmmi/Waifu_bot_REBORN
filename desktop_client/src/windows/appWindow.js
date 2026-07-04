"use strict";

const { BrowserWindow } = require("electron");
const path = require("path");
const config = require("../config");
const { loadUrlWithRetry } = require("./loadWithRetry");

const TAB_W = 420;
const TAB_H = 700;
const TAB_OFFSET_GAP = 16;

/**
 * Main application window (shop/tavern/guild hall/... — same pages as the
 * Telegram WebApp, loaded over HTTP with ?desktopClient=1). Normal window
 * chrome; "tabs" (other webapp pages) open as separate draggable windows on
 * top of this one via openTabWindow(), per the original request ("вкладки
 * открывать поверх основного окна, возможность drag по экрану").
 */
function createMainWindow() {
  const { width, height, page } = config.mainWindow;

  const win = new BrowserWindow({
    width,
    height,
    minWidth: width,
    maxWidth: width,
    minHeight: height,
    maxHeight: height,
    resizable: false,
    backgroundColor: "#0f172a",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  loadUrlWithRetry(win, `${config.backendUrl}/webapp/${page}?desktopClient=1&desktopMode=window`, {
    label: "main-window",
  });
  return win;
}

/**
 * Opens another webapp page as a small draggable window on top of the
 * main window (e.g. shop.html, tavern.html, guild_hall.html), instead of
 * navigating the main window away from the current page.
 */
function openTabWindow(anchorWindow, page) {
  let x;
  let y;
  if (anchorWindow && !anchorWindow.isDestroyed()) {
    const bounds = anchorWindow.getBounds();
    x = Math.max(0, bounds.x - TAB_W - TAB_OFFSET_GAP);
    y = bounds.y;
  }

  const win = new BrowserWindow({
    width: TAB_W,
    height: TAB_H,
    x,
    y,
    minWidth: TAB_W,
    maxWidth: TAB_W,
    minHeight: TAB_H,
    maxHeight: TAB_H,
    resizable: false,
    frame: false,
    backgroundColor: "#0f172a",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  loadUrlWithRetry(win, `${config.backendUrl}/webapp/${page}?desktopClient=1&desktopMode=window`, {
    label: "tab",
  });
  return win;
}

module.exports = { createMainWindow, openTabWindow };
