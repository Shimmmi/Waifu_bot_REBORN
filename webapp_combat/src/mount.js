import { createApp } from "vue";
import CombatIsland from "./CombatIsland.vue";

/**
 * Mount Vue combat island into #solo-combat-island (dungeons page).
 * Exposes window.WaifuCombatIsland for SSE updates from dungeons.js.
 */
export function mountCombatIsland(selector = "#solo-combat-island") {
  const el = typeof selector === "string" ? document.querySelector(selector) : selector;
  if (!el) return null;
  const app = createApp(CombatIsland);
  const vm = app.mount(el);
  const api = {
    applyPayload: (payload) => vm.applyPayload(payload),
    setBaseline: (baseline) => vm.setBaseline(baseline),
    unmount: () => app.unmount(),
  };
  window.WaifuCombatIsland = api;
  return api;
}

if (typeof window !== "undefined") {
  window.WaifuCombatIslandMount = mountCombatIsland;
}
