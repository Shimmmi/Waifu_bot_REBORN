"use strict";

/**
 * Shared RO paperdoll layer URLs + DOM compositor.
 * Used by Steam waifu generator and overlay (no app.js dependency).
 */
(function (global) {
  const BASE = "/static/game/waifu-gen";
  const PLACEHOLDER = `${BASE}/placeholder.svg`;

  /** Cosmetic layers bottom → top (before equip overlays). */
  const COSMETIC_LAYER_IDS = ["base", "race_feature", "outfit", "hair", "eyes", "accessory"];

  /**
   * Full paint order including equip (rings/amulets never included).
   * weapon/offhand attach to hand bones when skeleton is present.
   */
  const PAINT_ORDER = [
    "base",
    "race_feature",
    "outfit",
    "equip_costume",
    "hair",
    "eyes",
    "accessory",
    "equip_offhand",
    "equip_weapon",
  ];

  const RACE_ID_TO_SLUG = {
    1: "human",
    2: "elf",
    3: "beastman",
    4: "angel",
    5: "vampire",
    6: "demon",
    7: "fey",
  };

  function raceSlug(raceId, racesList) {
    const list = racesList || global.WAIFU_RACES || [];
    const r = list.find((x) => x.id === Number(raceId));
    if (r?.slug) return r.slug;
    return RACE_ID_TO_SLUG[Number(raceId)] || "human";
  }

  function normalizeCosmetics(cosmetics, raceId) {
    const c = cosmetics && typeof cosmetics === "object" ? cosmetics : {};
    const race = raceId != null ? Number(raceId) : Number(c.race) || 1;
    return {
      hair_color: c.hair_color || "blonde",
      hairstyle: c.hairstyle || "long_straight",
      eye_shape: c.eye_shape || "cute",
      eye_colors: Array.isArray(c.eye_colors) && c.eye_colors.length ? c.eye_colors : ["amber"],
      outfit: c.outfit || "robes",
      accessories: Array.isArray(c.accessories) ? c.accessories : [],
      race_feature: c.race_feature || "default",
      race,
      class: c.class != null ? Number(c.class) : undefined,
    };
  }

  function cosmeticLayerUrl(layerId, cosmetics, raceId) {
    const c = normalizeCosmetics(cosmetics, raceId);
    const rs = raceSlug(c.race != null ? c.race : raceId);
    switch (layerId) {
      case "base":
        return `${BASE}/paperdoll/base/${rs}/body.webp`;
      case "race_feature":
        return `${BASE}/paperdoll/race-feature/${rs}/${c.race_feature || "default"}.webp`;
      case "outfit":
        return `${BASE}/paperdoll/outfit/${c.outfit || "robes"}.webp`;
      case "hair": {
        const style = c.hairstyle || "long_straight";
        const color = c.hair_color || "blonde";
        return `${BASE}/paperdoll/hair/${style}_${color}.webp`;
      }
      case "eyes": {
        const shape = c.eye_shape || "cute";
        const ec = (c.eye_colors && c.eye_colors[0]) || "amber";
        return `${BASE}/paperdoll/eyes/${shape}_${ec}.webp`;
      }
      case "accessory": {
        const acc = (c.accessories || [])[0] || "none";
        if (acc === "none") return "";
        return `${BASE}/paperdoll/accessory/${acc}.webp`;
      }
      default:
        return "";
    }
  }

  /** Primary URL + optional legacy fallback (e.g. hair without color). */
  function cosmeticLayerUrls(layerId, cosmetics, raceId) {
    const primary = cosmeticLayerUrl(layerId, cosmetics, raceId);
    if (!primary) return [];
    if (layerId === "hair") {
      const c = normalizeCosmetics(cosmetics, raceId);
      const style = c.hairstyle || "long_straight";
      const legacy = `${BASE}/paperdoll/hair/${style}.webp`;
      if (legacy !== primary) return [primary, legacy];
    }
    return [primary];
  }

  /** @deprecated use cosmeticLayerUrl — kept for generator compatibility */
  function layerUrl(layerId, state) {
    return cosmeticLayerUrl(layerId, state?.cosmetics, state?.selectedRaceId);
  }

  function equipLayerUrl(kind, equippedVisuals) {
    const ev = equippedVisuals || {};
    if (kind === "equip_costume") return ev.costume?.sprite || "";
    if (kind === "equip_weapon") return ev.weapon?.sprite || "";
    if (kind === "equip_offhand") return ev.offhand?.sprite || "";
    return "";
  }

  function setImgSrc(img, url, fallbackUrls) {
    if (!url) {
      img.style.display = "none";
      img.removeAttribute("src");
      return;
    }
    img.style.display = "";
    const chain = Array.isArray(fallbackUrls) ? fallbackUrls.filter(Boolean) : [];
    let idx = 0;
    img.onerror = () => {
      if (idx < chain.length) {
        const next = chain[idx++];
        if (img.getAttribute("src") !== next) img.src = next;
        return;
      }
      img.onerror = null;
      img.src = PLACEHOLDER;
    };
    if (img.getAttribute("src") !== url) img.src = url;
  }

  function applyCosmeticLayer(img, layerId, cosmetics, raceId) {
    const urls = cosmeticLayerUrls(layerId, cosmetics, raceId);
    if (!urls.length) {
      setImgSrc(img, "");
      return;
    }
    setImgSrc(img, urls[0], urls.slice(1));
  }

  /**
   * Flat stage (generator): inject/update layer <img>s in paint order (cosmetics only by default).
   */
  function renderFlatStage(stageEl, state, options) {
    if (!stageEl) return;
    const opts = options || {};
    const includeEquip = Boolean(opts.includeEquip);
    const equipped = opts.equippedVisuals || null;
    const ids = includeEquip ? PAINT_ORDER : COSMETIC_LAYER_IDS;
    ids.forEach((lid) => {
      let img = stageEl.querySelector(`:scope > [data-layer="${lid}"], :scope [data-layer="${lid}"]`);
      if (!img || img.closest(".ov-bone")) {
        // Prefer direct children for flat stage
        img = stageEl.querySelector(`:scope > [data-layer="${lid}"]`);
      }
      if (!img) {
        img = document.createElement("img");
        img.className = opts.layerClass || "steam-paperdoll-layer";
        img.dataset.layer = lid;
        img.alt = "";
        img.draggable = false;
        stageEl.appendChild(img);
      }
      if (lid.startsWith("equip_")) {
        const url = includeEquip ? equipLayerUrl(lid, equipped) : "";
        setImgSrc(img, url);
      } else {
        applyCosmeticLayer(img, lid, state?.cosmetics, state?.selectedRaceId);
      }
    });
  }

  /**
   * Ensure bone tree exists under rootEl. Returns map of bone/attach nodes.
   */
  function ensureSkeleton(rootEl) {
    if (!rootEl) return null;
    let rootBone = rootEl.querySelector(':scope > .ov-bone[data-bone="root"]');
    if (rootBone) {
      return {
        root: rootBone,
        hip: rootBone.querySelector('[data-bone="hip"]'),
        torso: rootBone.querySelector('[data-bone="torso"]'),
        head: rootBone.querySelector('[data-bone="head"]'),
        arm_r: rootBone.querySelector('[data-bone="arm_r"]'),
        arm_l: rootBone.querySelector('[data-bone="arm_l"]'),
        hand_r: rootBone.querySelector('[data-attach="hand_r"]'),
        hand_l: rootBone.querySelector('[data-attach="hand_l"]'),
      };
    }

    function bone(name) {
      const d = document.createElement("div");
      d.className = "ov-bone";
      d.dataset.bone = name;
      return d;
    }
    function attach(name) {
      const d = document.createElement("div");
      d.className = "ov-attach";
      d.dataset.attach = name;
      return d;
    }

    rootBone = bone("root");
    const hip = bone("hip");
    const torso = bone("torso");
    const head = bone("head");
    const armR = bone("arm_r");
    const armL = bone("arm_l");
    const handR = attach("hand_r");
    const handL = attach("hand_l");
    armR.appendChild(handR);
    armL.appendChild(handL);
    torso.appendChild(head);
    torso.appendChild(armR);
    torso.appendChild(armL);
    hip.appendChild(torso);
    rootBone.appendChild(hip);
    rootEl.appendChild(rootBone);

    return {
      root: rootBone,
      hip,
      torso,
      head,
      arm_r: armR,
      arm_l: armL,
      hand_r: handR,
      hand_l: handL,
    };
  }

  function layerParent(bones, layerId) {
    if (!bones) return null;
    switch (layerId) {
      case "base":
      case "outfit":
      case "equip_costume":
        return bones.torso || bones.hip || bones.root;
      case "race_feature":
      case "hair":
      case "eyes":
      case "accessory":
        return bones.head || bones.torso || bones.root;
      case "equip_weapon":
        return bones.hand_r || bones.arm_r || bones.torso || bones.root;
      case "equip_offhand":
        return bones.hand_l || bones.arm_l || bones.torso || bones.root;
      default:
        return bones.torso || bones.root;
    }
  }

  /**
   * Overlay compositor: skeleton + cosmetic + equip layers.
   * @param {HTMLElement} rootEl - .ov-paperdoll
   * @param {{ cosmetics, raceId, equippedVisuals, showWeapon }} opts
   */
  function renderOverlayPaperdoll(rootEl, opts) {
    if (!rootEl) return false;
    const options = opts || {};
    const cosmetics = options.cosmetics;
    if (!cosmetics || typeof cosmetics !== "object") return false;

    const bones = ensureSkeleton(rootEl);
    const equipped = options.equippedVisuals || null;
    const showWeapon = options.showWeapon !== false;

    PAINT_ORDER.forEach((lid) => {
      const parent = layerParent(bones, lid);
      if (!parent) return;
      let img = parent.querySelector(`:scope > img[data-layer="${lid}"]`);
      if (!img) {
        img = document.createElement("img");
        img.className = "ov-paperdoll-layer";
        img.dataset.layer = lid;
        img.alt = "";
        img.draggable = false;
        parent.appendChild(img);
      }
      if (lid === "equip_weapon") {
        setImgSrc(img, showWeapon ? equipLayerUrl(lid, equipped) : "");
      } else if (lid.startsWith("equip_")) {
        setImgSrc(img, equipLayerUrl(lid, equipped));
      } else {
        applyCosmeticLayer(img, lid, cosmetics, options.raceId);
      }
    });

    rootEl.classList.add("ov-paperdoll--active");
    rootEl.dataset.hasLayers = "1";
    return true;
  }

  function clearOverlayPaperdoll(rootEl) {
    if (!rootEl) return;
    rootEl.classList.remove("ov-paperdoll--active");
    rootEl.dataset.hasLayers = "0";
    rootEl.querySelectorAll("img.ov-paperdoll-layer").forEach((img) => {
      img.style.display = "none";
      img.removeAttribute("src");
    });
  }

  global.RoPaperdollCompositor = {
    BASE,
    PLACEHOLDER,
    COSMETIC_LAYER_IDS,
    LAYER_IDS: COSMETIC_LAYER_IDS,
    PAINT_ORDER,
    raceSlug,
    normalizeCosmetics,
    cosmeticLayerUrl,
    cosmeticLayerUrls,
    layerUrl,
    equipLayerUrl,
    setImgSrc,
    applyCosmeticLayer,
    renderFlatStage,
    ensureSkeleton,
    renderOverlayPaperdoll,
    clearOverlayPaperdoll,
  };
})(typeof window !== "undefined" ? window : globalThis);
