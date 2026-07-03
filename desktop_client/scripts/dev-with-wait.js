"use strict";

/**
 * npm run dev:wait — poll backend from main process, then launch Electron.
 */
const { spawn } = require("child_process");
const path = require("path");
const config = require("../src/config");
const { waitForBackend } = require("../src/backend/waitForBackend");

async function main() {
  console.log(`[waifu-desktop] dev:wait — backend: ${config.backendUrl}`);
  const ok = await waitForBackend(config.backendUrl);
  if (!ok) {
    process.exit(1);
  }

  const electronBin = require("electron");
  const env = { ...process.env, WAIFU_APP_ENV: process.env.WAIFU_APP_ENV || "dev" };
  const child = spawn(electronBin, ["."], {
    cwd: path.join(__dirname, ".."),
    env,
    stdio: "inherit",
  });
  child.on("exit", (code) => process.exit(code == null ? 0 : code));
}

main().catch((err) => {
  console.error("[waifu-desktop] dev:wait failed:", err.message);
  process.exit(1);
});
