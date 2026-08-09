#!/usr/bin/env node
/**
 * Bump APK version and sync into Android build.gradle + bridge getAppVersion().
 * versionName: 0.0001, 0.0002, ...  (versionCode as integer 1, 2, ...)
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const VERSION_FILE = path.join(ROOT, "build_version.json");
const GRADLE = path.join(ROOT, "android", "app", "build.gradle");
const BRIDGE_SRC = path.join(ROOT, "src", "bridge.js");
const BRIDGE_WWW = path.join(ROOT, "www", "bridge.js");
const BRIDGE_LOADER = path.join(
  ROOT,
  "android",
  "app",
  "src",
  "main",
  "java",
  "ru",
  "shimmirpgbot",
  "waifu",
  "activity",
  "BridgeLoader.java"
);

const bump = process.argv.includes("--bump");
const noBump = process.argv.includes("--no-bump");

function readVersion() {
  if (!fs.existsSync(VERSION_FILE)) {
    return { versionCode: 1, versionName: "0.0001" };
  }
  return JSON.parse(fs.readFileSync(VERSION_FILE, "utf8"));
}

function formatName(code) {
  return `0.${String(code).padStart(4, "0")}`;
}

let ver = readVersion();
if (bump && !noBump) {
  ver.versionCode = Number(ver.versionCode || 0) + 1;
  ver.versionName = formatName(ver.versionCode);
  fs.writeFileSync(VERSION_FILE, JSON.stringify(ver, null, 2) + "\n");
} else {
  ver.versionName = formatName(ver.versionCode);
}

if (fs.existsSync(GRADLE)) {
  let g = fs.readFileSync(GRADLE, "utf8");
  g = g.replace(/versionCode\s+\d+/, `versionCode ${ver.versionCode}`);
  g = g.replace(/versionName\s+"[^"]*"/, `versionName "${ver.versionName}"`);
  fs.writeFileSync(GRADLE, g);
}

function patchBridgeJs(file) {
  if (!fs.existsSync(file)) return;
  let s = fs.readFileSync(file, "utf8");
  if (s.includes("getAppVersion")) {
    s = s.replace(
      /getAppVersion\(\)\s*\{\s*return\s*"[^"]*"\s*;\s*\}/,
      `getAppVersion() { return "${ver.versionName}"; }`
    );
  } else {
    s = s.replace(
      /setDesktopSessionToken\(token\)\s*\{/,
      `getAppVersion() { return "${ver.versionName}"; },\n    setDesktopSessionToken(token) {`
    );
  }
  fs.writeFileSync(file, s);
}

patchBridgeJs(BRIDGE_SRC);
patchBridgeJs(BRIDGE_WWW);

if (fs.existsSync(BRIDGE_LOADER)) {
  let java = fs.readFileSync(BRIDGE_LOADER, "utf8");
  if (java.includes("getAppVersion:function")) {
    java = java.replace(
      /getAppVersion:function\(\)\{return"[^"]*"\}/,
      `getAppVersion:function(){return"${ver.versionName}"}`
    );
  } else {
    java = java.replace(
      "getDesktopSessionToken:rs,setDesktopSessionToken:ws,",
      `getDesktopSessionToken:rs,setDesktopSessionToken:ws,` +
        `getAppVersion:function(){return"${ver.versionName}"},`
    );
  }
  fs.writeFileSync(BRIDGE_LOADER, java);
}

console.log(`[version] ${ver.versionName} (code ${ver.versionCode})${bump ? " [bumped]" : ""}`);
