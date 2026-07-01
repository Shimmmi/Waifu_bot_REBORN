import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

export default defineConfig({
  plugins: [vue()],
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: resolve(__dirname, "../src/waifu_bot/webapp/bundle"),
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, "src/mount.js"),
      name: "WaifuCombatIsland",
      formats: ["iife"],
      fileName: () => "combat-island.min.js",
    },
    rollupOptions: {
      output: {
        extend: true,
        inlineDynamicImports: true,
      },
    },
    minify: "esbuild",
  },
});
