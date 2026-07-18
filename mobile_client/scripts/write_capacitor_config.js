#!/usr/bin/env node
/** Write capacitor.config.json from WAIFU_MOBILE_BACKEND_URL (default prod host). */
const fs = require("fs");
const path = require("path");

const backend = (process.env.WAIFU_MOBILE_BACKEND_URL || "https://shimmirpgbot.ru").replace(
  /\/$/,
  ""
);
const host = backend.replace(/^https?:\/\//, "").split("/")[0];

const config = {
  appId: "ru.shimmirpgbot.waifu.activity",
  appName: "Waifu Activity",
  webDir: "www",
  server: {
    url: `${backend}/webapp/mobile/login.html?mobileClient=1`,
    cleartext: false,
    allowNavigation: [host, "localhost", "10.0.2.2"],
  },
  android: {
    allowMixedContent: false,
  },
};

const out = path.join(__dirname, "..", "capacitor.config.json");
fs.writeFileSync(out, JSON.stringify(config, null, 2) + "\n");
console.log("Wrote", out, "→", config.server.url);
