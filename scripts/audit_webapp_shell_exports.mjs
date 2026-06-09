#!/usr/bin/env node
/**
 * Fail if page IIFE bundles reference app.js top-level symbols not exported via exportWebAppShellGlobals().
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEBAPP = path.join(ROOT, "src/waifu_bot/webapp");
const APP_JS = path.join(WEBAPP, "app.js");
const PAGE_SCRIPTS = ["pages/dungeons.js", "pages/tavern.js"].map((p) => path.join(WEBAPP, p));

const BUILTINS = new Set([
  "undefined",
  "null",
  "true",
  "false",
  "window",
  "document",
  "console",
  "JSON",
  "Math",
  "Number",
  "String",
  "Array",
  "Object",
  "Date",
  "Promise",
  "Set",
  "Map",
  "URLSearchParams",
  "EventSource",
  "fetch",
  "Image",
  "localStorage",
  "location",
  "Telegram",
  "clearTimeout",
  "setTimeout",
  "clearInterval",
  "setInterval",
  "encodeURIComponent",
  "decodeURIComponent",
  "parseInt",
  "parseFloat",
  "isNaN",
  "Error",
  "RegExp",
  "Intl",
  "HTMLElement",
  "Node",
  "requestAnimationFrame",
  "cancelAnimationFrame",
  "alert",
  "confirm",
  "Blob",
  "FormData",
  "URL",
  "CustomEvent",
  "MutationObserver",
  "IntersectionObserver",
  "performance",
  "navigator",
  "history",
  "screen",
  "atob",
  "btoa",
  "self",
  "globalThis",
]);

function topLevelDecls(source) {
  const decls = new Set();
  for (const m of source.matchAll(/^(?:async )?function (\w+)|^const (\w+)|^let (\w+)|^var (\w+)/gm)) {
    decls.add(m[1] || m[2] || m[3] || m[4]);
  }
  return decls;
}

function exportedFromApp(source) {
  const exported = new Set();
  const block = source.match(/function exportWebAppShellGlobals\(\)\s*\{[\s\S]*?Object\.assign\(window,\s*\{([\s\S]*?)\}\)/);
  if (!block) {
    throw new Error("exportWebAppShellGlobals not found in app.js");
  }
  for (const m of block[1].matchAll(/^\s*(\w+)\s*,?/gm)) {
    exported.add(m[1]);
  }
  return exported;
}

function localDecls(source) {
  return topLevelDecls(source);
}

function missingExports(pagePath, pageSource, appDecls, exported, local) {
  const missing = new Set();
  // Bare identifiers only (skip property access: foo.bar / foo?.bar)
  for (const m of pageSource.matchAll(/(?<![.\w])([A-Za-z_][A-Za-z0-9_]*)\b/g)) {
    const id = m[1];
    if (BUILTINS.has(id) || local.has(id) || !appDecls.has(id) || exported.has(id)) continue;
    missing.add(id);
  }
  return [...missing].sort();
}

const appSource = fs.readFileSync(APP_JS, "utf8");
const appDecls = topLevelDecls(appSource);
const exported = exportedFromApp(appSource);

let failed = false;
for (const pagePath of PAGE_SCRIPTS) {
  const rel = path.relative(ROOT, pagePath);
  const pageSource = fs.readFileSync(pagePath, "utf8");
  const local = localDecls(pageSource);
  const missing = missingExports(pagePath, pageSource, appDecls, exported, local);
  if (missing.length) {
    failed = true;
    console.error(`ERROR: ${rel} references app.js symbols not in exportWebAppShellGlobals:`);
    for (const id of missing) console.error(`  - ${id}`);
  }
}

if (failed) {
  process.exit(1);
}

console.log("OK: page scripts only use exported app.js shell globals");
