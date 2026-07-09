"use strict";

/**
 * Persist desktop JWT (X-Desktop-Session) in the Electron userData dir.
 * Prefer safeStorage when available; fall back to plaintext file in userData.
 */
const fs = require("fs");
const path = require("path");
const { app, safeStorage } = require("electron");

const FILE_NAME = "desktop-session.bin";
const FILE_NAME_PLAIN = "desktop-session.txt";

function sessionPaths() {
  const dir = app.getPath("userData");
  return {
    encrypted: path.join(dir, FILE_NAME),
    plain: path.join(dir, FILE_NAME_PLAIN),
  };
}

function getToken() {
  const { encrypted, plain } = sessionPaths();
  try {
    if (fs.existsSync(encrypted) && safeStorage.isEncryptionAvailable()) {
      const buf = fs.readFileSync(encrypted);
      return safeStorage.decryptString(buf);
    }
    if (fs.existsSync(plain)) {
      return fs.readFileSync(plain, "utf8").trim() || null;
    }
  } catch (err) {
    console.warn("[desktop-auth] failed to read session:", err.message);
  }
  return null;
}

function setToken(token) {
  const value = String(token || "").trim();
  if (!value) {
    clearToken();
    return;
  }
  const { encrypted, plain } = sessionPaths();
  try {
    if (safeStorage.isEncryptionAvailable()) {
      fs.writeFileSync(encrypted, safeStorage.encryptString(value));
      if (fs.existsSync(plain)) fs.unlinkSync(plain);
      return;
    }
    fs.writeFileSync(plain, value, "utf8");
  } catch (err) {
    console.warn("[desktop-auth] failed to write session:", err.message);
  }
}

function clearToken() {
  const { encrypted, plain } = sessionPaths();
  try {
    if (fs.existsSync(encrypted)) fs.unlinkSync(encrypted);
    if (fs.existsSync(plain)) fs.unlinkSync(plain);
  } catch (err) {
    console.warn("[desktop-auth] failed to clear session:", err.message);
  }
}

function hasToken() {
  return Boolean(getToken());
}

module.exports = { getToken, setToken, clearToken, hasToken };
