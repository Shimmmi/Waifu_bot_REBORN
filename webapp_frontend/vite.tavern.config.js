import { defineConfig } from "vite";
import { resolve } from "path";

const webappRoot = resolve(__dirname, "../src/waifu_bot/webapp");

/** Tavern page — IIFE isolates minified top-level bindings from app.min.js. */
export default defineConfig({
  build: {
    outDir: resolve(webappRoot, "bundle"),
    emptyOutDir: false,
    minify: "esbuild",
    rollupOptions: {
      input: resolve(webappRoot, "pages/tavern.js"),
      output: {
        format: "iife",
        name: "WaifuTavernPage",
        entryFileNames: "tavern.min.js",
        inlineDynamicImports: true,
      },
    },
  },
});
