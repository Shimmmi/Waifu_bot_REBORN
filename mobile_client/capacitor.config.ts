import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Dev / Internal Testing: load remote WebApp from the game backend.
 * Point `server.url` at your staging/prod PUBLIC_BASE_URL + /webapp/...
 * For store release (P1), switch to bundled `webDir` and drop server.url.
 */
const backend =
  process.env.WAIFU_MOBILE_BACKEND_URL || "https://shimmirpgbot.ru";

const config: CapacitorConfig = {
  appId: "ru.shimmirpgbot.waifu.activity",
  appName: "Waifu Activity",
  webDir: "www",
  server: {
    url: `${backend}/webapp/activity.html?mobileClient=1&economy=activity`,
    cleartext: false,
    allowNavigation: [backend.replace(/^https?:\/\//, ""), "localhost", "10.0.2.2"],
  },
  android: {
    allowMixedContent: false,
  },
};

export default config;
