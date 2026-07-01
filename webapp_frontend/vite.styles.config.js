import { defineConfig } from "vite";
import { resolve } from "path";

const webappRoot = resolve(__dirname, "../src/waifu_bot/webapp");

/** Global stylesheet only. */
export default defineConfig({
  build: {
    outDir: resolve(webappRoot, "bundle"),
    emptyOutDir: false,
    cssMinify: true,
    rollupOptions: {
      input: resolve(webappRoot, "styles.css"),
      output: {
        assetFileNames: "styles.min.css",
      },
    },
  },
});
