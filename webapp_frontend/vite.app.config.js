import { defineConfig } from "vite";
import { resolve } from "path";

const webappRoot = resolve(__dirname, "../src/waifu_bot/webapp");

/** App shell (IIFE; exposes window.WaifuApp). */
export default defineConfig({
  build: {
    outDir: resolve(webappRoot, "bundle"),
    emptyOutDir: true,
    minify: "esbuild",
    rollupOptions: {
      input: resolve(webappRoot, "app.js"),
      output: {
        format: "iife",
        entryFileNames: "app.min.js",
        inlineDynamicImports: true,
      },
    },
  },
});
