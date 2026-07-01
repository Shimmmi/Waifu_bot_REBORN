#!/usr/bin/env node
/**
 * Load app + dungeons IIFE bundles; verify shell globals and populateDungeonsPage bootstrap path.
 */
import fs from "fs";
import path from "path";
import vm from "vm";
import { URLSearchParams } from "url";
import { fileURLToPath } from "url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BUNDLE = path.join(ROOT, "src/waifu_bot/webapp/bundle");

const app = fs.readFileSync(path.join(BUNDLE, "app.min.js"), "utf8");
const dungeons = fs.readFileSync(path.join(BUNDLE, "dungeons.min.js"), "utf8");

function elStub() {
  return {
    style: {},
    textContent: "",
    innerHTML: "",
    hidden: false,
    dataset: {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    setAttribute: () => {},
    getAttribute: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    appendChild: () => {},
    addEventListener: () => {},
    remove: () => {},
    offsetWidth: 0,
    complete: false,
    naturalWidth: 0,
  };
}

const documentStub = {
  getElementById: () => elStub(),
  querySelector: () => null,
  querySelectorAll: () => [],
  body: { classList: { contains: () => false, toggle: () => {}, add: () => {}, remove: () => {} }, style: {} },
  addEventListener: () => {},
};

// Browser global === window; IIFE page bundles resolve bare shell names from window.*
const window = {
  WaifuApp: {},
  document: documentStub,
  localStorage: { getItem: () => null, setItem: () => {} },
  location: { search: "", pathname: "/webapp/dungeons.html" },
  Telegram: { WebApp: { initData: "", ready: () => {}, expand: () => {} } },
  console,
  setTimeout: (fn) => {
    fn();
    return 0;
  },
  clearTimeout: () => {},
  setInterval: () => 0,
  clearInterval: () => {},
  fetch: async () => ({ ok: false, status: 404, json: async () => ({}) }),
  URLSearchParams,
  document: null,
};
window.window = window;
window.document = documentStub;

vm.runInNewContext(app, window);

if (!window.GAME_STATIC_BASE) throw new Error("GAME_STATIC_BASE not on window");
if (!window.selectedPlusLevelByDungeonId) throw new Error("selectedPlusLevelByDungeonId not on window");
if (!window.dungeonPlusStatusById) throw new Error("dungeonPlusStatusById not on window");
if (typeof window.apiFetch !== "function") throw new Error("apiFetch not on window");

window.apiFetch = async (path) => {
  if (path.startsWith("/dungeons/plus/status")) {
    return { status: [], global_unlocked: false };
  }
  if (path.includes("/dungeons?")) {
    return { dungeons: [] };
  }
  if (path === "/dungeons/active" || path.startsWith("/dungeons/active")) {
    return { active: false };
  }
  if (path === "/abyss/status") {
    return { session_active: false };
  }
  throw new Error(`unexpected apiFetch: ${path}`);
};

vm.runInNewContext(dungeons, window);

if (typeof window.WaifuApp.buildMonsterImageUrls !== "function") {
  throw new Error("WaifuApp.buildMonsterImageUrls not registered");
}
const monsterUrls = window.WaifuApp.buildMonsterImageUrls("beast", "wolf", 2, null, "waifu-webapp-v34");
if (!monsterUrls.every((u) => u.includes("?v="))) {
  throw new Error(`buildMonsterImageUrls missing ?v= on all fallbacks: ${monsterUrls.join(", ")}`);
}
const bust = window.WaifuApp.monsterArtCacheBust(null, null);
if (!bust || !String(bust).includes("waifu-webapp-v")) {
  throw new Error(`monsterArtCacheBust global fallback expected, got: ${bust}`);
}

if (typeof window.WaifuApp.showTab !== "function") {
  throw new Error("WaifuApp.showTab not registered");
}
if (typeof window.WaifuApp.populateDungeonsPage !== "function") {
  throw new Error("WaifuApp.populateDungeonsPage not registered");
}

await window.WaifuApp.populateDungeonsPage({ act: 1, main_waifu: { level: 1 } });

console.log("OK: populateDungeonsPage bootstrap path");
