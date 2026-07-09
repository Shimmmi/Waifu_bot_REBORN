"use strict";

/**
 * RO-style 2D paperdoll UI for Steam waifu generator (steam/waifu_generator.html).
 * Layer URLs come from RoPaperdollCompositor; this file owns the picker rows.
 * Depends on WaifuApp globals: waifuGeneratorState, WAIFU_RACES, WAIFU_GEN_* catalogs.
 */
(function () {
  const C = () => window.RoPaperdollCompositor;
  const LAYER_IDS = () => (C() && C().COSMETIC_LAYER_IDS) || [
    "base",
    "race_feature",
    "outfit",
    "hair",
    "eyes",
    "accessory",
  ];

  const ROWS = [
    { id: "hairColor", label: "Цвет волос", key: "hair_color", catalog: "hair" },
    { id: "hair", label: "Причёска", key: "hairstyle", catalog: "hairstyle" },
    { id: "eyes", label: "Тип глаз", key: "eye_shape", catalog: "eyeShape" },
    { id: "eyeColor", label: "Цвет глаз", key: "eye_colors", catalog: "eyes", multi: true },
    { id: "outfit", label: "Одежда", key: "outfit", catalog: "outfit" },
    { id: "raceFeature", label: "Особенность расы", key: "race_feature", catalog: "raceFeature" },
    { id: "accessory", label: "Аксессуар", key: "accessories", catalog: "accessory", single: true },
  ];

  function raceSlug(raceId) {
    if (C()) return C().raceSlug(raceId, window.WAIFU_RACES);
    const list = window.WAIFU_RACES || [];
    const r = list.find((x) => x.id === Number(raceId));
    return r?.slug || "human";
  }

  function catalogPairs(catalogKey, raceId) {
    const Cos = window.WAIFU_GEN_COSMETIC || {};
    if (catalogKey === "hair") return Cos.hair || [];
    if (catalogKey === "eyes") return Cos.eyes || [];
    if (catalogKey === "hairstyle") return Cos.hairstyle || [];
    if (catalogKey === "eyeShape") return window.WAIFU_GEN_EYE_SHAPES || [];
    if (catalogKey === "outfit") return window.WAIFU_GEN_OUTFITS || [];
    if (catalogKey === "accessory") return window.WAIFU_GEN_ACCS_MULTI || [];
    if (catalogKey === "raceFeature") {
      const map = window.WAIFU_GEN_RACE_FEATURES || {};
      return map[Number(raceId)] || map[raceSlug(raceId)] || [["default", "—"]];
    }
    return [];
  }

  function labelFor(row, state) {
    const pairs = catalogPairs(row.catalog, state.selectedRaceId);
    const key = row.key;
    let val;
    if (row.single || row.id === "accessory") {
      const acc = state.cosmetics.accessories || [];
      val = acc[0] || "none";
    } else if (row.multi) {
      val = (state.cosmetics.eye_colors || ["amber"])[0];
    } else {
      val = state.cosmetics[key];
    }
    const hit = pairs.find(([v]) => String(v) === String(val));
    return hit ? hit[1] : String(val || "—");
  }

  function layerUrl(layerId, state) {
    if (C()) return C().layerUrl(layerId, state);
    return "";
  }

  function cycleRow(rowId, delta) {
    const state = window.waifuGeneratorState;
    if (!state) return;
    const row = ROWS.find((r) => r.id === rowId);
    if (!row) return;
    const pairs = catalogPairs(row.catalog, state.selectedRaceId);
    if (!pairs.length) return;

    const getIdx = () => {
      if (row.single || row.id === "accessory") {
        const v = (state.cosmetics.accessories || [])[0] || "none";
        return Math.max(0, pairs.findIndex(([k]) => k === v));
      }
      if (row.multi) {
        const v = (state.cosmetics.eye_colors || ["amber"])[0];
        return Math.max(0, pairs.findIndex(([k]) => k === v));
      }
      const v = state.cosmetics[row.key];
      return Math.max(0, pairs.findIndex(([k]) => k === v));
    };

    let idx = getIdx();
    if (idx < 0) idx = 0;
    idx = (idx + delta + pairs.length) % pairs.length;
    const [nextVal] = pairs[idx];

    if (row.single || row.id === "accessory") {
      state.cosmetics.accessories = nextVal === "none" ? [] : [nextVal];
    } else if (row.multi) {
      state.cosmetics.eye_colors = [nextVal];
    } else {
      state.cosmetics[row.key] = nextVal;
    }

    if (row.id === "raceFeature") {
      state.cosmetics.race_feature = nextVal;
    }

    renderRows(state);
    renderStage(state);
  }

  function renderStage(state) {
    const stage = document.getElementById("steam-paperdoll-stage");
    if (!stage) return;
    if (C() && C().renderFlatStage) {
      C().renderFlatStage(stage, state, { layerClass: "steam-paperdoll-layer" });
      return;
    }
    LAYER_IDS().forEach((lid) => {
      let img = stage.querySelector(`[data-layer="${lid}"]`);
      if (!img) {
        img = document.createElement("img");
        img.className = "steam-paperdoll-layer";
        img.dataset.layer = lid;
        img.alt = "";
        img.draggable = false;
        stage.appendChild(img);
      }
      const url = layerUrl(lid, state);
      if (!url) {
        img.style.display = "none";
        img.removeAttribute("src");
        return;
      }
      img.style.display = "";
      img.onerror = () => {
        img.onerror = null;
        img.src = (C() && C().PLACEHOLDER) || "/static/game/waifu-gen/placeholder.svg";
      };
      if (img.getAttribute("src") !== url) img.src = url;
    });
  }

  function renderRows(state) {
    const root = document.getElementById("steam-paperdoll-rows");
    if (!root) return;
    root.innerHTML = ROWS.map(
      (row) => `<div class="steam-pd-row" data-row="${row.id}">
        <button type="button" class="steam-pd-arrow" data-dir="-1" data-row="${row.id}" aria-label="Назад">‹</button>
        <div class="steam-pd-row-label">
          <span class="steam-pd-row-title">${row.label}</span>
          <span class="steam-pd-row-value" id="steam-pd-val-${row.id}">${labelFor(row, state)}</span>
        </div>
        <button type="button" class="steam-pd-arrow" data-dir="1" data-row="${row.id}" aria-label="Вперёд">›</button>
      </div>`
    ).join("");

    root.querySelectorAll(".steam-pd-arrow").forEach((btn) => {
      btn.addEventListener("click", () => {
        cycleRow(btn.dataset.row, Number(btn.dataset.dir));
      });
    });
  }

  function init() {
    const state = window.waifuGeneratorState;
    if (!state) return;
    if (!state.cosmetics.race_feature) state.cosmetics.race_feature = "default";
    renderRows(state);
    renderStage(state);
  }

  function onRaceChanged() {
    const state = window.waifuGeneratorState;
    if (!state) return;
    const pairs = catalogPairs("raceFeature", state.selectedRaceId);
    state.cosmetics.race_feature = pairs[0]?.[0] || "default";
    renderRows(state);
    renderStage(state);
  }

  window.SteamWaifuPaperdoll = { init, renderStage, onRaceChanged, cycleRow };
})();
