#!/usr/bin/env node
/** Ensures www/ exists for Capacitor sync when not using remote server.url. */
const fs = require("fs");
const path = require("path");
const www = path.join(__dirname, "..", "www");
if (!fs.existsSync(www)) fs.mkdirSync(www, { recursive: true });
const index = path.join(www, "index.html");
if (!fs.existsSync(index)) {
  fs.writeFileSync(
    index,
    "<!DOCTYPE html><html><body><p>Waifu Activity placeholder</p></body></html>\n"
  );
}
console.log("www ready");
