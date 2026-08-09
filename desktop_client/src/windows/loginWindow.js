"use strict";

const { BrowserWindow } = require("electron");
const path = require("path");
const config = require("../config");
const { loadUrlWithRetry } = require("./loadWithRetry");

const LOGIN_W = 420;
const LOGIN_H = 520;

/**
 * Compact Electron login window (email / Telegram) before overlay boots.
 */
function createLoginWindow() {
  const win = new BrowserWindow({
    width: LOGIN_W,
    height: LOGIN_H,
    minWidth: LOGIN_W,
    maxWidth: LOGIN_W,
    minHeight: LOGIN_H,
    maxHeight: LOGIN_H,
    resizable: false,
    frame: false,
    backgroundColor: "#0b1220",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  loadUrlWithRetry(
    win,
    `${config.backendUrl}/webapp/steam/login.html?desktopClient=1&desktopMode=window`,
    { label: "login" }
  );
  return win;
}

module.exports = { createLoginWindow };
