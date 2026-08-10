/** Tavern page bundle. */
async function loadTavern(profile) {
  const p = profile || (await loadProfile({ lite: true }).catch(() => null));
  return loadTavernWithProfile(p || { act: 1 });
}

let tavernRosterLoaded = false;
let tavernRosterLoadPromise = null;

function resetTavernRosterCache() {
  tavernRosterLoaded = false;
  tavernRosterLoadPromise = null;
}

async function ensureTavernRosterLoaded() {
  if (tavernRosterLoaded) return;
  if (tavernRosterLoadPromise) return tavernRosterLoadPromise;
  tavernRosterLoadPromise = Promise.all([apiFetch("/tavern/squad"), apiFetch("/tavern/reserve")])
    .then(([squadRes, reserveRes]) => {
      tavernState.squad = Array.isArray(squadRes?.squad) ? squadRes.squad : [];
      tavernState.reserve = Array.isArray(reserveRes?.reserve) ? reserveRes.reserve : [];
      tavernRosterLoaded = true;
      tavernRosterLoadPromise = null;
    })
    .catch((err) => {
      tavernRosterLoadPromise = null;
      throw err;
    });
  return tavernRosterLoadPromise;
}

const tavernState = {
  act: 1,
  available: null,
  squad: [],
  reserve: [],
  perksMap: {},
  perksCatalog: {},
  lineup: { atk: [null, null, null], def: [null, null, null] },
  selectedWaifu: null,
  pendingHireSlot: null, // 1..4
  lastHiredResult: null, // result of last successful hire for result modal
  benchCap: 10,
  benchPage: 0,
  quickFeedMode: false,
  quickFeedTargetId: null,
  fodderSelectedIds: [],
  modalSeg: "overview",
  lineupPick: null, // { side, slot } when picking for empty ATK/DEF
  arenaSearchQ: "",
  arenaSearchTimer: null,
  drillManuals: {},
  mercGearBag: [],
  invPage: 0,
  invFilterSlot: "all", // all | weapon | charm | relic
  invSort: "type", // type | score | rarity
  exchangeItems: [],
  exchangeSelectedId: null,
};

const INV_PAGE_SIZE = 20;

const BENCH_PAGE_SIZE = 4;

/** Potential ★ fodder costs (target star after upgrade). */
const STAR_FODDER_COST = { 1: 2, 2: 4, 3: 7, 4: 12, 5: 18 };
const PERK_HARD_CAP_BY_STARS = { 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6 };
const PERK_SOFT_CAP_BY_STARS = {
  0: [1, 1, 1],
  1: [1, 2, 2],
  2: [2, 3, 3],
  3: [2, 3, 4],
  4: [3, 4, 5],
  5: [3, 5, 6],
};

function perkHardCap(stars) {
  const s = Math.max(0, Math.min(5, Number(stars) || 0));
  return PERK_HARD_CAP_BY_STARS[s] ?? 1;
}

function perkSoftCap(stars, tier) {
  const s = Math.max(0, Math.min(5, Number(stars) || 0));
  const t = Math.max(1, Math.min(3, Number(tier) || 1));
  return (PERK_SOFT_CAP_BY_STARS[s] || [1, 1, 1])[t - 1];
}

function fodderNeedForTarget(targetId) {
  const w = findRosterWaifu(targetId);
  const stars = Number(w?.potentialStars ?? w?.potential_stars ?? 0);
  if (stars >= 5) return 0;
  return STAR_FODDER_COST[stars + 1] || 99;
}

function isValidFodderCandidate(w, targetId) {
  if (!w || Number(w.id) === Number(targetId)) return false;
  if (w.expedition_id != null || w.expeditionId != null) return false;
  if (isOnLineup(w)) return false;
  const target = findRosterWaifu(targetId);
  const tStars = Number(target?.potentialStars ?? target?.potential_stars ?? 0);
  const fStars = Number(w?.potentialStars ?? w?.potential_stars ?? 0);
  if (fStars >= tStars + 1) return false;
  return true;
}

function toggleFodderSelection(w) {
  if (!tavernState.quickFeedMode || !tavernState.quickFeedTargetId) return;
  if (!isValidFodderCandidate(w, tavernState.quickFeedTargetId)) {
    showToast("Нельзя взять как корм", "error");
    return;
  }
  const id = Number(w.id);
  const cur = (tavernState.fodderSelectedIds || []).map(Number);
  const idx = cur.indexOf(id);
  if (idx >= 0) cur.splice(idx, 1);
  else cur.push(id);
  tavernState.fodderSelectedIds = cur;
  renderTavernSquad();
}

function cancelFodderPickMode() {
  tavernState.quickFeedMode = false;
  tavernState.quickFeedTargetId = null;
  tavernState.fodderSelectedIds = [];
  renderTavernSquad();
}

async function confirmFodderStars() {
  const targetId = Number(tavernState.quickFeedTargetId);
  const ids = (tavernState.fodderSelectedIds || []).map(Number);
  const need = fodderNeedForTarget(targetId);
  if (!targetId || ids.length < need) {
    showToast(`Нужно ${need} корма`, "error");
    return;
  }
  try {
    const res = await apiFetch("/tavern/fodder-stars", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_id: targetId, fodder_ids: ids }),
    });
    if (res?.error) {
      showToast(res.hint || res.error, "error");
      return;
    }
    cancelFodderPickMode();
    showToast(`★${res.potential_stars ?? ""}`, "info");
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Прорыв не удался", "error");
  }
}

function manualWalletCount(ptype, tier) {
  const bag = tavernState.drillManuals || {};
  const row = bag[ptype] || bag[String(ptype).toUpperCase()] || {};
  if (typeof row === "number") return tier === 2 ? Number(row) || 0 : 0;
  return Number(row[`t${tier}`] || 0);
}

function formatManualWalletChips() {
  const types = ["ATK", "DEF", "SUP"];
  return types
    .map((t) => {
      const a = manualWalletCount(t, 1);
      const b = manualWalletCount(t, 2);
      const c = manualWalletCount(t, 3);
      return `<span class="tavern-manual-chip">${t} T1:${a} T2:${b} T3:${c}</span>`;
    })
    .join("");
}

async function refreshDrillManuals() {
  try {
    const st = await apiFetch("/tavern/merc-status");
    tavernState.drillManuals = st.drill_manuals || {};
    tavernState.mercGearBag = Array.isArray(st.merc_gear_bag) ? st.merc_gear_bag : [];
  } catch (_) {
    /* keep cache */
  }
}

function invSlotIcon(slot) {
  if (slot === "charm") return "🔮";
  if (slot === "relic") return "📜";
  return "⚔";
}

function invEquipCandidates() {
  const lu = tavernState.lineup || { atk: [null, null, null] };
  const atkIds = new Set((lu.atk || []).filter(Boolean).map(Number));
  const atk = (lu.atk || []).map(findRosterWaifu).filter(Boolean);
  const bench = allRosterWaifus().filter((w) => !atkIds.has(Number(w.id)));
  return [...atk, ...bench];
}

async function equipBagItemOnWaifu(bagItemId, slot, waifuId) {
  const res = await apiFetch("/tavern/gear/equip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ waifu_id: waifuId, slot, bag_item_id: bagItemId }),
  });
  if (Array.isArray(res?.merc_gear_bag)) tavernState.mercGearBag = res.merc_gear_bag;
  await refreshDrillManuals().catch(() => {});
  await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
  return res;
}

function renderTavernInventoryTab() {
  const host = document.getElementById("tab-inventory");
  const invBox = document.getElementById("tavern-page-inv-list");
  if (!invBox || !host) return;
  const slotLabels = { weapon: "Оружие", charm: "Амулет", relic: "Реликвия" };
  const bag = (tavernState.mercGearBag || []).filter((g) => g && typeof g === "object");
  const filter = String(tavernState.invFilterSlot || "all");
  const sort = String(tavernState.invSort || "type");
  let rows = bag.map((g) => ({
    bagId: g.id,
    slot: g.slot || "weapon",
    itemName: g.name || "Предмет",
    score: Number(g.score ?? 0) || 0,
    rarity: Number(g.rarity ?? 0) || 0,
  }));
  if (filter !== "all") rows = rows.filter((r) => r.slot === filter);
  const slotOrder = { weapon: 0, charm: 1, relic: 2 };
  rows.sort((a, b) => {
    if (sort === "score") return b.score - a.score || String(a.itemName).localeCompare(String(b.itemName));
    if (sort === "rarity") return b.rarity - a.rarity || b.score - a.score;
    return (slotOrder[a.slot] ?? 9) - (slotOrder[b.slot] ?? 9) || b.score - a.score;
  });

  const totalPages = Math.max(1, Math.ceil(rows.length / INV_PAGE_SIZE) || 1);
  if (tavernState.invPage >= totalPages) tavernState.invPage = Math.max(0, totalPages - 1);
  if (tavernState.invPage < 0) tavernState.invPage = 0;
  const page = tavernState.invPage;
  const slice = rows.slice(page * INV_PAGE_SIZE, page * INV_PAGE_SIZE + INV_PAGE_SIZE);

  let toolbar = host.querySelector("#tavern-inv-toolbar");
  if (!toolbar) {
    toolbar = document.createElement("div");
    toolbar.id = "tavern-inv-toolbar";
    toolbar.className = "tavern-inv-toolbar";
    invBox.parentNode.insertBefore(toolbar, invBox);
  }
  toolbar.innerHTML = `
    <div class="tavern-inv-toolbar-row">
      <label class="tavern-inv-filter muted tiny">Тип
        <select id="tavern-inv-filter">
          <option value="all"${filter === "all" ? " selected" : ""}>все</option>
          <option value="weapon"${filter === "weapon" ? " selected" : ""}>оружие</option>
          <option value="charm"${filter === "charm" ? " selected" : ""}>амулет</option>
          <option value="relic"${filter === "relic" ? " selected" : ""}>реликвия</option>
        </select>
      </label>
      <label class="tavern-inv-filter muted tiny">Сорт
        <select id="tavern-inv-sort">
          <option value="type"${sort === "type" ? " selected" : ""}>тип</option>
          <option value="score"${sort === "score" ? " selected" : ""}>CR</option>
          <option value="rarity"${sort === "rarity" ? " selected" : ""}>редкость</option>
        </select>
      </label>
      <div class="tavern-inv-pager">
        <button type="button" class="tavern-btn tavern-btn-mini" id="tavern-inv-prev" ${page <= 0 ? "disabled" : ""} aria-label="Назад">‹</button>
        <span class="muted tiny">${page + 1}/${totalPages}</span>
        <button type="button" class="tavern-btn tavern-btn-mini" id="tavern-inv-next" ${page >= totalPages - 1 ? "disabled" : ""} aria-label="Вперёд">›</button>
      </div>
    </div>`;

  const tip = host.querySelector(".tab-inventory-tip") || host.querySelector("p.muted.tiny");
  if (tip) tip.textContent = "Сумка экипа · тап — надеть на наёмницу";

  if (!rows.length) {
    invBox.className = "tavern-inv-grid";
    invBox.innerHTML = `<div class="placeholder muted tiny" style="grid-column:1/-1">Сумка пуста — купите ящик в Обмене</div>`;
  } else {
    invBox.className = "tavern-inv-grid";
    invBox.innerHTML = slice
      .map(
        (r) => `<button type="button" class="tavern-inv-cell" data-inv-bag="${escapeHtml(String(r.bagId))}" data-inv-slot="${escapeHtml(String(r.slot))}">
        <span class="tavern-inv-cell-ico" aria-hidden="true">${invSlotIcon(r.slot)}</span>
        <span class="tavern-inv-cell-name ellip">${escapeHtml(String(r.itemName))}</span>
        <span class="tavern-inv-cell-score muted">CR ${escapeHtml(String(r.score))}</span>
      </button>`
      )
      .join("");
  }

  const filterEl = toolbar.querySelector("#tavern-inv-filter");
  const sortEl = toolbar.querySelector("#tavern-inv-sort");
  if (filterEl) {
    filterEl.onchange = () => {
      tavernState.invFilterSlot = filterEl.value || "all";
      tavernState.invPage = 0;
      renderTavernInventoryTab();
    };
  }
  if (sortEl) {
    sortEl.onchange = () => {
      tavernState.invSort = sortEl.value || "type";
      tavernState.invPage = 0;
      renderTavernInventoryTab();
    };
  }
  toolbar.querySelector("#tavern-inv-prev")?.addEventListener("click", () => {
    tavernState.invPage = Math.max(0, page - 1);
    renderTavernInventoryTab();
  });
  toolbar.querySelector("#tavern-inv-next")?.addEventListener("click", () => {
    tavernState.invPage = Math.min(totalPages - 1, page + 1);
    renderTavernInventoryTab();
  });

  invBox.querySelectorAll("[data-inv-bag]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const bagId = btn.getAttribute("data-inv-bag");
      const slot = btn.getAttribute("data-inv-slot") || "weapon";
      const cands = invEquipCandidates();
      if (!cands.length) {
        showToast("Нет наёмниц в ATK/скамейке", "error");
        return;
      }
      openInvEquipPicker(bagId, slot, cands);
    });
  });
}

function openInvEquipPicker(bagItemId, slot, candidates) {
  const existing = document.getElementById("tavern-inv-equip-picker");
  if (existing) existing.remove();
  const overlay = document.createElement("div");
  overlay.id = "tavern-inv-equip-picker";
  overlay.className = "tavern-inv-equip-overlay";
  overlay.innerHTML = `
    <div class="tavern-inv-equip-sheet" role="dialog" aria-modal="true">
      <div class="tavern-inv-equip-head">Надеть · ${escapeHtml(slot)}</div>
      <div class="tavern-inv-equip-list">
        ${candidates
          .map(
            (w) =>
              `<button type="button" class="tavern-inv-equip-opt" data-equip-waifu="${escapeHtml(String(w.id))}">
                <span class="ellip">${escapeHtml(String(w.name || `#${w.id}`))}</span>
                <span class="muted tiny">CR ${escapeHtml(String(hiredCr(w)))}</span>
              </button>`
          )
          .join("")}
      </div>
      <button type="button" class="tavern-btn tavern-btn-mini" data-inv-equip-cancel>Отмена</button>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) close();
  });
  overlay.querySelector("[data-inv-equip-cancel]")?.addEventListener("click", close);
  overlay.querySelectorAll("[data-equip-waifu]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wid = Number(btn.getAttribute("data-equip-waifu"));
      btn.disabled = true;
      try {
        await equipBagItemOnWaifu(bagItemId, slot, wid);
        showToast("Экипировано", "info");
        close();
        renderTavernInventoryTab();
      } catch (e) {
        const { detail } = parseHttpErrorDetail(e);
        showToast(detail || "Экип недоступен", "error");
        btn.disabled = false;
      }
    });
  });
}

function mercCoinIcon(extraClass = "") {
  const cls = extraClass ? ` merc-coin-ico ${extraClass}` : " merc-coin-ico";
  return `<span class="${cls.trim()}" title="Merc Coins" aria-label="Merc Coins">MC</span>`;
}

function arenaOpponentLabel(o) {
  if (o?.bot) return "Бот";
  const un = String(o?.username || "").trim().replace(/^@/, "");
  if (un) return `@${un}`;
  const dn = String(o?.display_name || "").trim();
  if (dn) return dn;
  return `Игрок ${o?.player_id ?? ""}`;
}

function showTavernError(message, kind = "info") {
  const box = document.getElementById("tavern-hire-error");
  if (!box) return;
  if (!message) {
    box.style.display = "none";
    box.textContent = "";
    box.classList.remove("danger");
    return;
  }
  box.style.display = "";
  box.textContent = String(message);
  if (kind === "danger") box.classList.add("danger");
  else box.classList.remove("danger");
}

const TAVERN_HEAL_GOLD_PER_HP = 2; // золото за 1 HP; при 0 HP (обморок) ×2
const TAVERN_POOL_MAX_DEFAULT = 10;

function tavernBenchCap() {
  const fromAvail = Number(tavernState.available?.bench_cap ?? tavernState.benchCap);
  if (Number.isFinite(fromAvail) && fromAvail > 0) return Math.min(24, Math.max(8, fromAvail));
  return TAVERN_POOL_MAX_DEFAULT;
}

function hiredCr(w) {
  const v = w?.combatRating ?? w?.combat_rating ?? w?.power;
  return v == null || v === "" ? "—" : v;
}

function hiredArchetypeLabel(w) {
  return String(w?.archetype_name || w?.archetypeName || w?.archetype_id || w?.archetypeId || "").trim();
}

function perkIdsCapped(w, max = 3) {
  const ids = Array.isArray(w?.perks) ? w.perks : [];
  return ids.slice(0, max);
}

function hiredWaifuHp(w) {
  const max = Number(w?.hpMax ?? w?.max_hp ?? 65);
  const cur = Number(w?.hpCurrent ?? w?.current_hp ?? max);
  return { cur, max };
}

function hiredWaifuIsHealing(w) {
  return Boolean(w?.healing || w?.resting) || w?.status === "healing" || w?.status === "resting";
}

function hiredWaifuHealCompleteAt(w) {
  return w?.heal_complete_at ?? w?.healCompleteAt ?? null;
}

function formatHealCountdown(secondsLeft) {
  const sec = Math.max(0, Math.floor(Number(secondsLeft) || 0));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function healSecondsRemaining(completeAtIso) {
  if (!completeAtIso) return 0;
  const end = new Date(completeAtIso).getTime();
  if (!Number.isFinite(end)) return 0;
  return Math.max(0, Math.ceil((end - Date.now()) / 1000));
}

let tavernHealTimerInterval = null;

function wireTavernHealTimers() {
  const tick = () => {
    const timers = document.querySelectorAll(".tavern-heal-timer[data-heal-complete-at]");
    if (!timers.length) {
      if (tavernHealTimerInterval) {
        clearInterval(tavernHealTimerInterval);
        tavernHealTimerInterval = null;
      }
      return;
    }
    let anyLeft = false;
    timers.forEach((el) => {
      const iso = el.getAttribute("data-heal-complete-at");
      const left = healSecondsRemaining(iso);
      if (left > 0) {
        anyLeft = true;
        el.textContent = `⏳ ${formatHealCountdown(left)}`;
      } else {
        el.textContent = "✓";
      }
    });
    if (!anyLeft && tavernHealTimerInterval) {
      clearInterval(tavernHealTimerInterval);
      tavernHealTimerInterval = null;
      loadTavernWithProfile(undefined, { innerRefresh: true })
        .then(({ squad, reserve }) => {
          tavernState.squad = squad || tavernState.squad;
          tavernState.reserve = reserve || tavernState.reserve;
          renderTavernHealList();
          renderTavernSquad();
        })
        .catch(() => {});
    }
  };
  tick();
  if (!tavernHealTimerInterval) {
    tavernHealTimerInterval = setInterval(tick, 1000);
  }
}

function hiredWaifuNameLines(name) {
  const parts = String(name || "Наёмница").trim().split(/\s+/);
  if (parts.length <= 1) return { first: parts[0] || "Наёмница", last: "" };
  return { first: parts[0], last: parts.slice(1).join(" ") };
}

/** Статус в пуле наёмниц: экспедиция / лечение / обморок (0 HP) / готова. */
function hiredWaifuPoolUiStatus(w) {
  const expId = w?.expedition_id ?? w?.expeditionId;
  if (w?.status === "expedition" || (expId != null && Number(expId) > 0)) {
    return { key: "traveling", label: "В пути" };
  }
  if (hiredWaifuIsHealing(w)) {
    return { key: "healing", label: "Лечение" };
  }
  const { cur } = hiredWaifuHp(w);
  if (cur <= 0) {
    return { key: "fainted", label: "В обмороке" };
  }
  return { key: "ready", label: "Готова" };
}

function sortTavernPool(squad, reserve) {
  const squadList = (squad || []).slice().sort((a, b) => {
    const pa = Number(a?.squad_position ?? 999);
    const pb = Number(b?.squad_position ?? 999);
    return pa - pb;
  });
  const reserveList = (reserve || []).slice().sort((a, b) => Number(a.id) - Number(b.id));
  return [...squadList, ...reserveList];
}

/** Слоты, оставшиеся сегодня (0–4) → фон вкладки найма. */
function tavernHireBackgroundUrl(remaining) {
  const rem = Math.max(0, Math.min(4, Number(remaining) || 0));
  const n = 4 - rem;
  const tavernBase = window.TAVERN_STATIC_BASE || "/static/game/ui/tavern";
  const root = `${tavernBase}/tavern.background`;
  return n === 0 ? `${root}.webp` : `${root}_${n}.webp`;
}

function getActiveTavernTab() {
  const active = document.querySelector(".tavern-tabs .tab.active");
  return active?.dataset?.tab || "hire";
}

function syncTavernPageBackgroundVisibility() {
  const pageBg = document.getElementById("tavern-page-bg");
  if (!pageBg) return;
  pageBg.style.display = getActiveTavernTab() === "hire" ? "" : "none";
}

function preloadTavernBg(url) {
  return new Promise((resolve) => {
    if (!url || typeof url !== "string") {
      resolve();
      return;
    }
    const img = new Image();
    img.onload = img.onerror = () => resolve();
    img.src = url;
  });
}

function setTavernPageLoading(on) {
  if (typeof document === "undefined" || !document.body?.classList?.contains("page-tavern")) return;
  const v = Boolean(on);
  document.body.classList.toggle("tavern-loading", v);
  const layer = document.getElementById("tavern-page-loading");
  if (layer) layer.setAttribute("aria-busy", v ? "true" : "false");
}

const TAVERN_BGM_MUTED_KEY = "waifu_tavern_bgm_muted";
const TAVERN_BGM_CONFIG_KEY = "waifu_tavern_bgm_config";
const TAVERN_BGM_VOLUME_KEY = "waifu_tavern_bgm_volume";
const TAVERN_BGM_DEFAULT_VOLUME = 0.7;

let tavernBgmAudio = null;
let tavernBgmFadeRaf = null;
let tavernBgmHooksBound = false;
let tavernBgmGestureArmed = false;
let tavernBgmPaused = false;
let tavernBgmPlaylists = [];
let tavernBgmActivePlaylistId = null;
let tavernBgmActivePlaylist = null;
let tavernBgmCatalog = [];
let tavernBgmActiveTracks = [];
let tavernBgmChats = [];
let tavernBgmPlayOrder = [];
let tavernBgmPlayOrderPos = 0;
let tavernBgmCurrentSourceIndex = -1;
let tavernBgmSelectedPlaylistId = null;
let tavernBgmSelectedPlaylist = null;
let tavernBgmVolumeOverlayOpen = false;
let tavernBgmAudioProgressCleanup = null;
let tavernBgmAddPlaylistTrackIds = new Set();
let tavernBgmVolumeOutsideHandler = null;
let tavernBgmVolumeRepositionHandler = null;

function formatTavernTrackTitle(t) {
  const title = String(t?.title || "").trim();
  const performer = String(t?.performer || "").trim();
  if (title && performer) return `${performer} — ${title}`;
  return title || performer || "Без названия";
}

function formatTavernTrackDuration(sec) {
  const n = Number(sec);
  if (!Number.isFinite(n) || n <= 0) return "";
  const m = Math.floor(n / 60);
  const s = Math.floor(n % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function readTavernBgmConfigLegacy() {
  try {
    const raw = localStorage.getItem(TAVERN_BGM_CONFIG_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    const chatId = Number(data?.chatId);
    const trackIds = Array.isArray(data?.trackIds)
      ? data.trackIds.map((id) => Number(id)).filter((id) => Number.isFinite(id))
      : [];
    if (!Number.isFinite(chatId) || !trackIds.length) return null;
    const repeat = String(data?.repeat || "all");
    const repeatOk = repeat === "off" || repeat === "one" || repeat === "all" ? repeat : "all";
    return {
      chatId,
      trackIds,
      shuffle: Boolean(data?.shuffle),
      repeat: repeatOk,
    };
  } catch (e) {
    return null;
  }
}

function getTavernBgmShuffle() {
  return Boolean(tavernBgmActivePlaylist?.shuffle);
}

function getTavernBgmRepeat() {
  const repeat = tavernBgmActivePlaylist?.repeat || "all";
  return repeat === "off" || repeat === "one" || repeat === "all" ? repeat : "all";
}

function tavernBgmAuthHeaders() {
  const headers = {};
  const initData = window.Telegram?.WebApp?.initData;
  if (initData) {
    headers["X-Telegram-Init-Data"] = initData;
  } else {
    const params = new URLSearchParams(window.location.search);
    const devPid = params.get("player_id");
    if (devPid) headers["X-Player-Id"] = devPid;
  }
  return headers;
}

function getTavernBgmStaticSources() {
  const tavernBase = window.TAVERN_STATIC_BASE || "/static/game/ui/tavern";
  return (window.TAVERN_BGM_TRACKS || []).map((name, i) => ({
    id: `static-${i}`,
    url: `${tavernBase}/audio/${name}`,
    title: name,
    performer: null,
    duration: null,
  }));
}

function getTavernBgmSources() {
  if (Array.isArray(tavernBgmActiveTracks) && tavernBgmActiveTracks.length) {
    return tavernBgmActiveTracks.slice();
  }
  return [];
}

async function fetchTavernBgmPlaylists() {
  const res = await apiFetch("/tavern/bgm/playlists");
  tavernBgmPlaylists = Array.isArray(res?.playlists) ? res.playlists : [];
  tavernBgmActivePlaylistId = Number.isFinite(Number(res?.active_playlist_id))
    ? Number(res.active_playlist_id)
    : null;
  return res;
}

async function loadTavernBgmConfig() {
  tavernBgmActiveTracks = [];
  tavernBgmActivePlaylist = null;
  try {
    const res = await apiFetch("/tavern/bgm/playlists/active");
    const pl = res?.playlist || null;
    tavernBgmActivePlaylist = pl;
    tavernBgmActivePlaylistId = pl?.id != null ? Number(pl.id) : null;
    tavernBgmActiveTracks = Array.isArray(pl?.tracks) ? pl.tracks.slice() : [];
    if (!tavernBgmActiveTracks.length) {
      tavernBgmActivePlaylist = null;
      tavernBgmActivePlaylistId = null;
    }
  } catch (e) {
    tavernBgmActiveTracks = [];
    tavernBgmActivePlaylist = null;
    tavernBgmActivePlaylistId = null;
  }
}

async function migrateTavernBgmLocalConfig() {
  const legacy = readTavernBgmConfigLegacy();
  if (!legacy) return;
  try {
    const res = await fetchTavernBgmPlaylists();
    if ((res?.playlists || []).length > 0) {
      localStorage.removeItem(TAVERN_BGM_CONFIG_KEY);
      return;
    }
    const created = await apiFetch("/tavern/bgm/playlists", {
      method: "POST",
      body: JSON.stringify({ chat_id: legacy.chatId, name: "Мой плейлист" }),
    });
    const id = Number(created?.playlist?.id);
    if (!Number.isFinite(id)) return;
    await apiFetch(`/tavern/bgm/playlists/${id}/tracks`, {
      method: "PUT",
      body: JSON.stringify({ track_ids: legacy.trackIds }),
    });
    await apiFetch(`/tavern/bgm/playlists/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ shuffle: legacy.shuffle, repeat: legacy.repeat }),
    });
    await apiFetch(`/tavern/bgm/playlists/${id}/activate`, { method: "POST" });
    localStorage.removeItem(TAVERN_BGM_CONFIG_KEY);
  } catch (e) {
    /* ignore migration errors */
  }
}

function getTavernBgmVolume() {
  try {
    const raw = localStorage.getItem(TAVERN_BGM_VOLUME_KEY);
    if (raw == null || raw === "") return TAVERN_BGM_DEFAULT_VOLUME;
    const n = Number(raw);
    if (!Number.isFinite(n)) return TAVERN_BGM_DEFAULT_VOLUME;
    return Math.max(0, Math.min(1, n));
  } catch (e) {
    return TAVERN_BGM_DEFAULT_VOLUME;
  }
}

function setTavernBgmVolume(v) {
  const vol = Math.max(0, Math.min(1, Number(v)));
  try {
    localStorage.setItem(TAVERN_BGM_VOLUME_KEY, String(vol));
  } catch (e) {
    /* ignore */
  }
  applyTavernBgmVolumeToAudio();
  syncTavernBgmVolumeUi();
}

function applyTavernBgmVolumeToAudio() {
  if (!tavernBgmAudio || tavernBgmFadeRaf != null) return;
  tavernBgmAudio.volume = getTavernBgmVolume();
}

function syncTavernBgmVolumeUi() {
  const slider = document.getElementById("tavern-bgm-volume");
  const icon = document.getElementById("tavern-bgm-volume-icon");
  const volBtn = document.getElementById("tavern-bgm-volume-btn");
  const vol = getTavernBgmVolume();
  if (slider) slider.value = String(Math.round(vol * 100));
  const iconChar = vol <= 0.01 ? "🔇" : vol < 0.45 ? "🔈" : "🔊";
  if (icon) icon.textContent = iconChar;
  if (volBtn) volBtn.textContent = iconChar;
}

function positionTavernBgmVolumeOverlay() {
  const overlay = document.getElementById("tavern-bgm-volume-overlay");
  const btn = document.getElementById("tavern-bgm-volume-btn");
  if (!overlay || !btn || overlay.classList.contains("hidden")) return;
  const rect = btn.getBoundingClientRect();
  const overlayRect = overlay.getBoundingClientRect();
  const gap = 8;
  let left = rect.left + rect.width / 2 - overlayRect.width / 2;
  let top = rect.top - overlayRect.height - gap;
  const margin = 8;
  const maxLeft = window.innerWidth - overlayRect.width - margin;
  left = Math.max(margin, Math.min(left, maxLeft));
  if (top < margin) top = rect.bottom + gap;
  overlay.style.left = `${Math.round(left)}px`;
  overlay.style.top = `${Math.round(top)}px`;
}

function unbindTavernBgmVolumeOverlayListeners() {
  const modal = document.getElementById("tavern-bgm-player-modal");
  if (tavernBgmVolumeOutsideHandler && modal) {
    modal.removeEventListener("pointerdown", tavernBgmVolumeOutsideHandler, true);
    tavernBgmVolumeOutsideHandler = null;
  }
  if (tavernBgmVolumeRepositionHandler) {
    window.removeEventListener("resize", tavernBgmVolumeRepositionHandler);
    const sheet = document.querySelector(".tavern-bgm-modal-sheet");
    if (sheet) sheet.removeEventListener("scroll", tavernBgmVolumeRepositionHandler);
    tavernBgmVolumeRepositionHandler = null;
  }
}

function bindTavernBgmVolumeOverlayListeners() {
  unbindTavernBgmVolumeOverlayListeners();
  const modal = document.getElementById("tavern-bgm-player-modal");
  const overlay = document.getElementById("tavern-bgm-volume-overlay");
  const volBtn = document.getElementById("tavern-bgm-volume-btn");
  if (!modal || !overlay) return;

  tavernBgmVolumeOutsideHandler = (event) => {
    if (!tavernBgmVolumeOverlayOpen) return;
    const target = event.target;
    if (overlay.contains(target) || volBtn?.contains(target)) return;
    closeTavernBgmVolumeOverlay();
  };
  modal.addEventListener("pointerdown", tavernBgmVolumeOutsideHandler, true);

  tavernBgmVolumeRepositionHandler = () => positionTavernBgmVolumeOverlay();
  window.addEventListener("resize", tavernBgmVolumeRepositionHandler);
  const sheet = document.querySelector(".tavern-bgm-modal-sheet");
  if (sheet) sheet.addEventListener("scroll", tavernBgmVolumeRepositionHandler, { passive: true });
}

function toggleTavernBgmVolumeOverlay() {
  const overlay = document.getElementById("tavern-bgm-volume-overlay");
  if (!overlay) return;
  if (tavernBgmVolumeOverlayOpen) {
    closeTavernBgmVolumeOverlay();
    return;
  }
  tavernBgmVolumeOverlayOpen = true;
  overlay.classList.remove("hidden");
  requestAnimationFrame(() => {
    positionTavernBgmVolumeOverlay();
    requestAnimationFrame(() => positionTavernBgmVolumeOverlay());
  });
  bindTavernBgmVolumeOverlayListeners();
}

function closeTavernBgmVolumeOverlay() {
  tavernBgmVolumeOverlayOpen = false;
  const overlay = document.getElementById("tavern-bgm-volume-overlay");
  if (overlay) overlay.classList.add("hidden");
  unbindTavernBgmVolumeOverlayListeners();
}

function getTavernBgmTrackDurationSec() {
  const sources = getTavernBgmSources();
  const track = sources[tavernBgmCurrentSourceIndex];
  const meta = Number(track?.duration);
  if (Number.isFinite(meta) && meta > 0) return meta;
  const audioDur = Number(tavernBgmAudio?.duration);
  if (Number.isFinite(audioDur) && audioDur > 0) return audioDur;
  return 0;
}

function syncTavernBgmProgress() {
  const elapsedEl = document.getElementById("tavern-bgm-elapsed");
  const durationEl = document.getElementById("tavern-bgm-duration");
  const fill = document.getElementById("tavern-bgm-progress-fill");
  const progress = document.getElementById("tavern-bgm-progress");
  const current = Number(tavernBgmAudio?.currentTime) || 0;
  const total = getTavernBgmTrackDurationSec();
  if (elapsedEl) elapsedEl.textContent = formatTavernTrackDuration(current) || "0:00";
  if (durationEl) durationEl.textContent = total > 0 ? formatTavernTrackDuration(total) : "—";
  if (fill) fill.style.width = total > 0 ? `${(current / total) * 100}%` : "0%";
  if (progress && total > 0) {
    progress.setAttribute("aria-valuenow", String(Math.round((current / total) * 100)));
  }
}

function seekTavernBgmProgress(event) {
  const audio = tavernBgmAudio;
  const bar = document.getElementById("tavern-bgm-progress");
  if (!audio || !bar) return;
  const rect = bar.getBoundingClientRect();
  if (!rect.width) return;
  const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
  const total = getTavernBgmTrackDurationSec();
  if (!Number.isFinite(total) || total <= 0) return;
  audio.currentTime = ratio * total;
  syncTavernBgmProgress();
}

function bindTavernBgmAudioProgress(audio) {
  if (tavernBgmAudioProgressCleanup) {
    try {
      tavernBgmAudioProgressCleanup();
    } catch (e) {
      /* ignore */
    }
    tavernBgmAudioProgressCleanup = null;
  }
  const onTime = () => syncTavernBgmProgress();
  const onMeta = () => syncTavernBgmProgress();
  audio.addEventListener("timeupdate", onTime);
  audio.addEventListener("loadedmetadata", onMeta);
  tavernBgmAudioProgressCleanup = () => {
    audio.removeEventListener("timeupdate", onTime);
    audio.removeEventListener("loadedmetadata", onMeta);
  };
}

function onTavernBgmVolumeChange(value) {
  setTavernBgmVolume(Number(value) / 100);
}

function isTavernBgmMuted() {
  if (!window.WaifuApp?.isAdminUiEnabled?.()) return true;
  try {
    const v = localStorage.getItem(TAVERN_BGM_MUTED_KEY);
    if (v === null) return true;
    return v === "1";
  } catch (e) {
    return true;
  }
}

function setTavernBgmMuted(muted) {
  try {
    localStorage.setItem(TAVERN_BGM_MUTED_KEY, muted ? "1" : "0");
  } catch (e) {
    /* ignore */
  }
  syncTavernBgmMuteButton();
}

function syncTavernBgmMuteButton() {
  const btn = document.getElementById("tavern-bgm-toggle");
  if (!btn) return;
  const paused = isTavernBgmMuted();
  btn.classList.toggle("tavern-tab-bgm--muted", paused);
  btn.setAttribute("aria-pressed", paused ? "true" : "false");
  if (paused) {
    btn.textContent = "⏸";
    btn.title = "Продолжить";
    btn.setAttribute("aria-label", "Продолжить");
  } else {
    btn.textContent = "🔊";
    btn.title = "Пауза";
    btn.setAttribute("aria-label", "Пауза");
  }
}

function toggleTavernBgmMuted() {
  if (isTavernBgmMuted()) {
    setTavernBgmMuted(false);
    loadTavernBgmConfig().then(() => {
      if (isTavernBgmMuted()) return;
      if (tavernBgmAudio && tavernBgmPaused) {
        tavernBgmAudio
          .play()
          .then(() => {
            tavernBgmPaused = false;
            syncTavernBgmMuteButton();
            syncTavernBgmPlayerUi();
          })
          .catch(() => armTavernBgmUserGesture());
      } else if (!tavernBgmAudio) {
        startTavernBgm();
      }
      syncTavernBgmMuteButton();
      syncTavernBgmPlayerUi();
    });
  } else {
    setTavernBgmMuted(true);
    pauseTavernBgm();
    syncTavernBgmMuteButton();
    syncTavernBgmPlayerUi();
  }
}

function ensureTavernBgmPageHooks() {
  if (tavernBgmHooksBound || typeof window === "undefined") return;
  tavernBgmHooksBound = true;
  window.addEventListener("pagehide", () => {
    stopTavernBgm(400);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") stopTavernBgm(400);
  });
}

function cancelTavernBgmFade() {
  if (tavernBgmFadeRaf != null) {
    cancelAnimationFrame(tavernBgmFadeRaf);
    tavernBgmFadeRaf = null;
  }
}

function stopTavernBgm(fadeOutMs = 400) {
  cancelTavernBgmFade();
  const a = tavernBgmAudio;
  if (!a) {
    syncTavernBgmPlayerUi();
    return;
  }
  const startVol = Number(a.volume) || 0;
  const t0 = performance.now();
  const dur = Math.max(0, fadeOutMs);
  const finish = () => {
    try {
      a.pause();
    } catch (e) {
      /* ignore */
    }
    a.src = "";
    tavernBgmAudio = null;
    syncTavernBgmPlayerUi();
  };
  if (dur === 0 || startVol <= 0.01) {
    finish();
    return;
  }
  function tick(now) {
    const t = Math.min(1, (now - t0) / dur);
    a.volume = startVol * (1 - t);
    if (t >= 1) {
      tavernBgmFadeRaf = null;
      finish();
      return;
    }
    tavernBgmFadeRaf = requestAnimationFrame(tick);
  }
  tavernBgmFadeRaf = requestAnimationFrame(tick);
}

function fadeInTavernBgm(audio, durationMs) {
  cancelTavernBgmFade();
  const targetVol = getTavernBgmVolume();
  const t0 = performance.now();
  const dur = Math.max(200, durationMs);
  function tick(now) {
    if (!tavernBgmAudio || tavernBgmAudio !== audio) {
      tavernBgmFadeRaf = null;
      return;
    }
    const t = Math.min(1, (now - t0) / dur);
    audio.volume = targetVol * t;
    if (t >= 1) {
      tavernBgmFadeRaf = null;
      return;
    }
    tavernBgmFadeRaf = requestAnimationFrame(tick);
  }
  audio.volume = 0;
  tavernBgmFadeRaf = requestAnimationFrame(tick);
}

function buildTavernBgmPlayOrder(count, startSourceIndex = 0) {
  if (count <= 0) return [];
  const order = [];
  for (let i = 0; i < count; i += 1) order.push(i);
  if (getTavernBgmShuffle()) {
    for (let i = order.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }
  } else if (startSourceIndex > 0) {
    const rotated = [];
    for (let k = 0; k < count; k += 1) rotated.push((startSourceIndex + k) % count);
    return rotated;
  }
  if (getTavernBgmShuffle() && startSourceIndex >= 0 && order.includes(startSourceIndex)) {
    const pos = order.indexOf(startSourceIndex);
    order.splice(pos, 1);
    order.unshift(startSourceIndex);
  }
  return order;
}

function pickTavernBgmRandomIndex(n) {
  if (n <= 0) return -1;
  if (n === 1) return 0;
  let i = Math.floor(Math.random() * n);
  if (i === tavernBgmCurrentSourceIndex) i = (i + 1) % n;
  return i;
}

function syncTavernBgmPlaylistCaption() {
  const btn = document.getElementById("tavern-bgm-playlist-picker-btn");
  if (!btn) return;
  const name = String(tavernBgmActivePlaylist?.name || "").trim();
  const hasActive = Boolean(name && tavernBgmActiveTracks.length > 0);
  if (hasActive) {
    btn.textContent = name;
    btn.classList.add("tavern-bgm-playlist-picker-btn--active");
    btn.title = "Сменить плейлист";
  } else {
    btn.textContent = "Выбрать плейлист";
    btn.classList.remove("tavern-bgm-playlist-picker-btn--active");
    btn.title = "Выбрать плейлист";
  }
}

function isTavernBgmPlaylistPickerOpen() {
  const el = document.getElementById("tavern-bgm-playlist-picker");
  return Boolean(el && !el.classList.contains("hidden"));
}

function closeTavernBgmPlaylistPicker() {
  const el = document.getElementById("tavern-bgm-playlist-picker");
  if (el) el.classList.add("hidden");
}

function renderTavernBgmPlaylistPickerList() {
  const box = document.getElementById("tavern-bgm-playlist-picker-list");
  if (!box) return;
  if (!tavernBgmPlaylists.length) {
    box.innerHTML = `<div class="muted tiny" style="padding:8px;text-align:center;">Нет плейлистов</div>
      <button type="button" class="tavern-bgm-text-btn tavern-bgm-text-btn--primary" style="width:100%;margin-top:8px;" onclick="WaifuApp.openTavernBgmPlaylistTabFromPicker()">Создать плейлист</button>`;
    return;
  }
  const activeId = Number(tavernBgmActivePlaylistId);
  box.innerHTML = tavernBgmPlaylists
    .map((p) => {
      const id = Number(p.id);
      const isActive = Number.isFinite(activeId) && id === activeId;
      const name = escapeHtml(String(p.name || "Плейлист"));
      const count = Number(p.track_count) || 0;
      return `<div class="tavern-bgm-playlist-picker-row${isActive ? " tavern-bgm-playlist-picker-row--active" : ""}" role="button" tabindex="0" onclick="WaifuApp.selectTavernBgmPlaylistFromPicker(${id})">
        <span class="tavern-bgm-playlist-picker-row-name">${name}</span>
        <span class="tavern-bgm-playlist-picker-row-meta">${count}</span>
        ${isActive ? '<span aria-hidden="true">✓</span>' : ""}
      </div>`;
    })
    .join("");
}

async function openTavernBgmPlaylistPicker() {
  closeTavernBgmVolumeOverlay();
  await fetchTavernBgmPlaylists();
  renderTavernBgmPlaylistPickerList();
  const el = document.getElementById("tavern-bgm-playlist-picker");
  if (el) el.classList.remove("hidden");
}

function onTavernBgmPlaylistPickerBackdropClick(event) {
  if (event.target.id === "tavern-bgm-playlist-picker") closeTavernBgmPlaylistPicker();
}

async function selectTavernBgmPlaylistFromPicker(playlistId) {
  const id = Number(playlistId);
  if (!Number.isFinite(id)) return;
  await loadTavernBgmPlaylistDetail(id);
  const ok = await applyTavernBgmPlaylistSilent(id, { restartPlayback: true });
  if (!ok) return;
  closeTavernBgmPlaylistPicker();
  const select = document.getElementById("tavern-bgm-playlist-select");
  if (select) select.value = String(id);
  syncTavernBgmPlayerUi();
}

function openTavernBgmPlaylistTabFromPicker() {
  closeTavernBgmPlaylistPicker();
  switchTavernBgmModalTab("playlist");
}

function syncTavernBgmNowPlaying() {
  const el = document.getElementById("tavern-bgm-now-playing");
  if (!el) return;
  const sources = getTavernBgmSources();
  if (tavernBgmCurrentSourceIndex < 0 || !sources[tavernBgmCurrentSourceIndex]) {
    el.textContent = "—";
    return;
  }
  el.textContent = formatTavernTrackTitle(sources[tavernBgmCurrentSourceIndex]);
}

function syncTavernBgmPlayerUi() {
  syncTavernBgmPlaylistCaption();
  syncTavernBgmNowPlaying();
  syncTavernBgmProgress();
  const playBtn = document.getElementById("tavern-bgm-play-btn");
  if (playBtn) {
    const playing = Boolean(tavernBgmAudio) && !tavernBgmPaused && !tavernBgmAudio.paused;
    playBtn.textContent = playing ? "⏸" : "▶";
    playBtn.title = playing ? "Пауза" : "Воспроизведение";
  }
  const shuffleBtn = document.getElementById("tavern-bgm-shuffle-btn");
  if (shuffleBtn) shuffleBtn.classList.toggle("tavern-bgm-ctrl-btn--active", getTavernBgmShuffle());
  const repeatBtn = document.getElementById("tavern-bgm-repeat-btn");
  if (repeatBtn) {
    const repeat = getTavernBgmRepeat();
    repeatBtn.classList.toggle("tavern-bgm-ctrl-btn--active", repeat !== "off");
    repeatBtn.textContent = repeat === "one" ? "🔂" : "🔁";
    repeatBtn.title =
      repeat === "one" ? "Повтор трека" : repeat === "all" ? "Повтор плейлиста" : "Без повтора";
  }
  const openBtn = document.getElementById("tavern-bgm-player-open");
  if (openBtn) {
    openBtn.classList.toggle("tavern-tab-bgm-player--active", Boolean(tavernBgmActiveTracks.length));
  }
}

function armTavernBgmUserGesture() {
  if (tavernBgmGestureArmed || typeof document === "undefined") return;
  if (isTavernBgmMuted()) return;
  tavernBgmGestureArmed = true;
  const unlock = () => {
    document.body.removeEventListener("pointerdown", unlock, true);
    tavernBgmGestureArmed = false;
    if (!isTavernBgmMuted()) startTavernBgm();
  };
  document.body.addEventListener("pointerdown", unlock, { once: true, capture: true });
}

function playTavernBgmSourceAt(sourceIndex, opts = {}) {
  const fadeIn = opts.fadeIn !== false;
  const sources = getTavernBgmSources();
  if (!sources.length || sourceIndex < 0 || sourceIndex >= sources.length) return;
  if (typeof document === "undefined" || !document.body?.classList?.contains("page-tavern")) return;
  if (isTavernBgmMuted()) return;

  ensureTavernBgmPageHooks();
  cancelTavernBgmFade();
  const prev = tavernBgmAudio;
  if (prev) {
    try {
      prev.pause();
    } catch (e) {
      /* ignore */
    }
    prev.src = "";
    tavernBgmAudio = null;
  }

  const src = sources[sourceIndex];
  const repeat = getTavernBgmRepeat();
  const a = new Audio();
  a.loop = repeat === "one";
  a.preload = "auto";
  a.volume = fadeIn ? 0 : getTavernBgmVolume();
  const fail = () => {
    a.removeEventListener("error", fail);
    try {
      a.pause();
    } catch (e) {
      /* ignore */
    }
    a.src = "";
    if (tavernBgmAudio === a) tavernBgmAudio = null;
    advanceTavernBgmTrack(true);
  };
  a.addEventListener("error", fail, { once: true });
  if (repeat !== "one") {
    a.addEventListener("ended", () => {
      if (tavernBgmAudio !== a) return;
      advanceTavernBgmTrack(false);
    });
  }
  a.src = src.url;
  a.load();
  bindTavernBgmAudioProgress(a);
  a.play()
    .then(() => {
      a.removeEventListener("error", fail);
      tavernBgmCurrentSourceIndex = sourceIndex;
      tavernBgmAudio = a;
      tavernBgmPaused = false;
      if (fadeIn) fadeInTavernBgm(a, 1200);
      syncTavernBgmPlayerUi();
    })
    .catch(() => {
      armTavernBgmUserGesture();
      syncTavernBgmPlayerUi();
    });
}

function advanceTavernBgmTrack(fromError = false) {
  const sources = getTavernBgmSources();
  const n = sources.length;
  if (!n) return;
  const repeat = getTavernBgmRepeat();
  if (n === 1) {
    if (repeat === "off" && !fromError) {
      stopTavernBgm(400);
      tavernBgmPaused = true;
    }
    return;
  }
  tavernBgmPlayOrderPos += 1;
  if (tavernBgmPlayOrderPos >= tavernBgmPlayOrder.length) {
    if (repeat === "off") {
      stopTavernBgm(400);
      tavernBgmPaused = true;
      syncTavernBgmPlayerUi();
      return;
    }
    tavernBgmPlayOrder = buildTavernBgmPlayOrder(n);
    tavernBgmPlayOrderPos = 0;
  }
  playTavernBgmSourceAt(tavernBgmPlayOrder[tavernBgmPlayOrderPos], { fadeIn: true });
}

function startTavernBgm() {
  if (typeof document === "undefined" || !document.body?.classList?.contains("page-tavern")) return;
  if (isTavernBgmMuted()) return;
  const sources = getTavernBgmSources();
  if (!sources.length) return;
  tavernBgmPaused = false;
  const n = sources.length;
  const startIdx =
    tavernBgmCurrentSourceIndex >= 0 && tavernBgmCurrentSourceIndex < n
      ? tavernBgmCurrentSourceIndex
      : pickTavernBgmRandomIndex(n);
  tavernBgmPlayOrder = buildTavernBgmPlayOrder(n, startIdx);
  tavernBgmPlayOrderPos = 0;
  playTavernBgmSourceAt(tavernBgmPlayOrder[0], { fadeIn: true });
}

function pauseTavernBgm() {
  if (!tavernBgmAudio) return;
  try {
    tavernBgmAudio.pause();
  } catch (e) {
    /* ignore */
  }
  tavernBgmPaused = true;
  syncTavernBgmPlayerUi();
}

function playTavernBgm() {
  if (isTavernBgmMuted()) return;
  if (tavernBgmAudio && tavernBgmPaused) {
    tavernBgmAudio.play()
      .then(() => {
        tavernBgmPaused = false;
        syncTavernBgmPlayerUi();
      })
      .catch(() => armTavernBgmUserGesture());
    return;
  }
  startTavernBgm();
}

function toggleTavernBgmPlayPause() {
  if (tavernBgmAudio && !tavernBgmPaused && !tavernBgmAudio.paused) pauseTavernBgm();
  else playTavernBgm();
}

function nextTavernBgmTrack() {
  const sources = getTavernBgmSources();
  if (!sources.length) return;
  if (!tavernBgmPlayOrder.length) tavernBgmPlayOrder = buildTavernBgmPlayOrder(sources.length);
  tavernBgmPlayOrderPos = (tavernBgmPlayOrderPos + 1) % tavernBgmPlayOrder.length;
  playTavernBgmSourceAt(tavernBgmPlayOrder[tavernBgmPlayOrderPos], { fadeIn: false });
}

function prevTavernBgmTrack() {
  const sources = getTavernBgmSources();
  if (!sources.length) return;
  if (!tavernBgmPlayOrder.length) tavernBgmPlayOrder = buildTavernBgmPlayOrder(sources.length);
  tavernBgmPlayOrderPos =
    (tavernBgmPlayOrderPos - 1 + tavernBgmPlayOrder.length) % tavernBgmPlayOrder.length;
  playTavernBgmSourceAt(tavernBgmPlayOrder[tavernBgmPlayOrderPos], { fadeIn: false });
}

async function setTavernBgmShuffleEnabled(enabled) {
  const shuffle = Boolean(enabled);
  const playlistId = tavernBgmActivePlaylistId;
  if (!playlistId) return;
  try {
    const res = await apiFetch(`/tavern/bgm/playlists/${playlistId}`, {
      method: "PATCH",
      body: JSON.stringify({ shuffle }),
    });
    if (res?.playlist) {
      tavernBgmActivePlaylist = { ...tavernBgmActivePlaylist, ...res.playlist };
      if (Array.isArray(tavernBgmActivePlaylist.tracks)) {
        /* keep tracks */
      } else if (tavernBgmActiveTracks.length) {
        tavernBgmActivePlaylist.tracks = tavernBgmActiveTracks.slice();
      }
    }
  } catch (e) {
    showToast("Не удалось сохранить настройку", "error");
    return;
  }
  syncTavernBgmPlayerUi();
}

function toggleTavernBgmShuffle() {
  setTavernBgmShuffleEnabled(!getTavernBgmShuffle());
  const sources = getTavernBgmSources();
  if (sources.length && tavernBgmAudio) {
    tavernBgmPlayOrder = buildTavernBgmPlayOrder(sources.length, tavernBgmCurrentSourceIndex);
    tavernBgmPlayOrderPos = Math.max(0, tavernBgmPlayOrder.indexOf(tavernBgmCurrentSourceIndex));
  }
}

async function setTavernBgmRepeatMode(repeat) {
  const mode = repeat === "off" || repeat === "one" || repeat === "all" ? repeat : "all";
  const playlistId = tavernBgmActivePlaylistId;
  if (!playlistId) return;
  try {
    const res = await apiFetch(`/tavern/bgm/playlists/${playlistId}`, {
      method: "PATCH",
      body: JSON.stringify({ repeat: mode }),
    });
    if (res?.playlist) {
      tavernBgmActivePlaylist = { ...tavernBgmActivePlaylist, ...res.playlist };
      if (tavernBgmActiveTracks.length && !Array.isArray(tavernBgmActivePlaylist.tracks)) {
        tavernBgmActivePlaylist.tracks = tavernBgmActiveTracks.slice();
      }
    }
  } catch (e) {
    showToast("Не удалось сохранить настройку", "error");
    return;
  }
  if (tavernBgmAudio) tavernBgmAudio.loop = mode === "one";
  syncTavernBgmPlayerUi();
}

function cycleTavernBgmRepeat() {
  const order = ["off", "one", "all"];
  const cur = getTavernBgmRepeat();
  const next = order[(order.indexOf(cur) + 1) % order.length];
  setTavernBgmRepeatMode(next);
}

async function refreshTavernBgmAddPlaylistTrackIds() {
  const val = document.getElementById("tavern-bgm-add-playlist-select")?.value;
  if (!val || val === "__new__") {
    tavernBgmAddPlaylistTrackIds = new Set();
    return;
  }
  try {
    const res = await apiFetch(`/tavern/bgm/playlists/${val}`);
    tavernBgmAddPlaylistTrackIds = new Set(
      (res?.playlist?.tracks || []).map((t) => Number(t.id))
    );
  } catch (e) {
    tavernBgmAddPlaylistTrackIds = new Set();
  }
}

function getTavernBgmAddChatId() {
  const fromSelect = Number(document.getElementById("tavern-bgm-add-chat-select")?.value);
  if (Number.isFinite(fromSelect)) return fromSelect;
  if (tavernBgmChats.length) return Number(tavernBgmChats[0].chat_id);
  return null;
}

async function createTavernBgmPlaylistWithPrompt(chatId, defaultName = "Новый плейлист") {
  const cid = Number(chatId);
  if (!Number.isFinite(cid)) {
    showToast("Сначала выберите чат", "error");
    return null;
  }
  const name = window.prompt("Название плейлиста", defaultName);
  if (!name || !String(name).trim()) return null;
  try {
    const res = await apiFetch("/tavern/bgm/playlists", {
      method: "POST",
      body: JSON.stringify({ chat_id: cid, name: String(name).trim() }),
    });
    const id = Number(res?.playlist?.id);
    if (!Number.isFinite(id)) return null;
    await refreshTavernBgmPlaylistsUi(id);
    const addSelect = document.getElementById("tavern-bgm-add-playlist-select");
    if (addSelect) addSelect.value = String(id);
    showToast("Плейлист создан", "success");
    return id;
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось создать плейлист", "error");
    return null;
  }
}

async function getTavernBgmAddPlaylistId() {
  const select = document.getElementById("tavern-bgm-add-playlist-select");
  const val = select?.value;
  const id = Number(val);
  if (Number.isFinite(id) && id > 0) return id;
  return createTavernBgmPlaylistWithPrompt(getTavernBgmAddChatId());
}

function syncTavernBgmPlaylistToolbar() {
  const filled = document.getElementById("tavern-bgm-playlist-toolbar-filled");
  const empty = document.getElementById("tavern-bgm-playlist-toolbar-empty");
  const hasPlaylists = tavernBgmPlaylists.length > 0;
  if (filled) filled.style.display = hasPlaylists ? "" : "none";
  if (empty) empty.style.display = hasPlaylists ? "none" : "";
  if (!hasPlaylists) {
    tavernBgmSelectedPlaylistId = null;
    tavernBgmSelectedPlaylist = null;
    const box = document.getElementById("tavern-bgm-playlist-tracks");
    if (box) box.innerHTML = `<div class="muted tiny">Создайте плейлист</div>`;
  }
}

function renderTavernBgmAddCatalog() {
  const box = document.getElementById("tavern-bgm-add-catalog");
  if (!box) return;
  const chatId = getTavernBgmAddChatId();
  const playlistTracks = tavernBgmAddPlaylistTrackIds;
  if (!tavernBgmCatalog.length) {
    box.innerHTML = `<div class="muted tiny">В этом чате пока нет сохранённых аудиозаписей</div>`;
    return;
  }
  box.innerHTML = tavernBgmCatalog
    .map((t) => {
      const id = Number(t.id);
      const added = playlistTracks.has(id);
      const dur = formatTavernTrackDuration(t.duration);
      const chatOk = Number.isFinite(chatId);
      return `
        <div class="tavern-bgm-track-row ${added ? "tavern-bgm-track-row--in-playlist" : ""}">
          <div class="tavern-bgm-track-info">
            <div class="tavern-bgm-track-title">${escapeHtml(formatTavernTrackTitle(t))}</div>
            <div class="tavern-bgm-track-meta">${dur ? escapeHtml(dur) : "—"}</div>
          </div>
          <button type="button" class="tavern-bgm-track-btn" title="Добавить в плейлист"
                  onclick="WaifuApp.addTrackToTavernBgmPlaylist(${id})" ${added || !chatOk ? "disabled" : ""}>+</button>
        </div>`;
    })
    .join("");
}

function renderTavernBgmPlaylistTracks() {
  const box = document.getElementById("tavern-bgm-playlist-tracks");
  if (!box) return;
  const tracks = Array.isArray(tavernBgmSelectedPlaylist?.tracks)
    ? tavernBgmSelectedPlaylist.tracks
    : [];
  if (!tavernBgmSelectedPlaylistId) {
    box.innerHTML = `<div class="muted tiny">Выберите плейлист</div>`;
    return;
  }
  if (!tracks.length) {
    box.innerHTML = `<div class="muted tiny">Плейлист пуст — добавьте треки на вкладке «Музыка»</div>`;
    return;
  }
  box.innerHTML = tracks
    .map((t) => {
      const id = Number(t.id);
      const dur = formatTavernTrackDuration(t.duration);
      return `
        <div class="tavern-bgm-track-row">
          <div class="tavern-bgm-track-info">
            <div class="tavern-bgm-track-title">${escapeHtml(formatTavernTrackTitle(t))}</div>
            <div class="tavern-bgm-track-meta">${dur ? escapeHtml(dur) : "—"}</div>
          </div>
          <button type="button" class="tavern-bgm-track-btn" title="Убрать из плейлиста"
                  onclick="WaifuApp.removeTrackFromTavernBgmPlaylist(${id})">−</button>
        </div>`;
    })
    .join("");
}

function populateTavernBgmPlaylistSelect(selectEl, preferredId) {
  if (!selectEl) return;
  if (!tavernBgmPlaylists.length) {
    selectEl.innerHTML = `<option value="">Нет плейлистов</option>`;
    return;
  }
  selectEl.innerHTML = tavernBgmPlaylists
    .map(
      (p) =>
        `<option value="${Number(p.id)}">${escapeHtml(String(p.name || "Плейлист"))} (${Number(p.track_count) || 0})</option>`
    )
    .join("");
  const pref = Number(preferredId);
  const hasPref = tavernBgmPlaylists.some((p) => Number(p.id) === pref);
  const selected = hasPref ? pref : Number(tavernBgmPlaylists[0].id);
  selectEl.value = String(selected);
}

function populateTavernBgmAddPlaylistSelect(chatId) {
  const select = document.getElementById("tavern-bgm-add-playlist-select");
  if (!select) return;
  const cid = Number(chatId);
  const forChat = tavernBgmPlaylists.filter((p) => Number(p.chat_id) === cid);
  if (!Number.isFinite(cid)) {
    select.innerHTML = `<option value="">Выберите чат</option>`;
    return;
  }
  const opts = forChat
    .map(
      (p) =>
        `<option value="${Number(p.id)}">${escapeHtml(String(p.name || "Плейлист"))}</option>`
    )
    .join("");
  select.innerHTML = `<option value="__new__">Создать новый</option>${opts}`;
  if (forChat.length) select.value = String(forChat[0].id);
  else select.value = "__new__";
}

async function loadTavernBgmAddCatalog(chatId) {
  const cid = Number(chatId);
  tavernBgmCatalog = [];
  if (!Number.isFinite(cid)) {
    renderTavernBgmAddCatalog();
    return;
  }
  const box = document.getElementById("tavern-bgm-add-catalog");
  if (box) box.innerHTML = `<div class="muted tiny">Загрузка…</div>`;
  try {
    const res = await apiFetch(`/tavern/bgm/tracks?chat_id=${encodeURIComponent(cid)}`);
    tavernBgmCatalog = Array.isArray(res?.tracks) ? res.tracks : [];
  } catch (e) {
    tavernBgmCatalog = [];
  }
  renderTavernBgmAddCatalog();
}

async function populateTavernBgmAddChatSelect(preferredChatId) {
  const select = document.getElementById("tavern-bgm-add-chat-select");
  const hintEl = document.getElementById("tavern-bgm-add-chat-hint");
  if (!select) return;
  select.innerHTML = `<option value="">Загрузка…</option>`;
  if (hintEl) {
    hintEl.style.display = "none";
    hintEl.textContent = "";
  }
  try {
    const res = await apiFetch("/tavern/bgm/chats");
    tavernBgmChats = Array.isArray(res?.chats) ? res.chats : [];
    if (!tavernBgmChats.length) {
      select.innerHTML = `<option value="">Нет доступных чатов</option>`;
      if (hintEl && res?.hint) {
        hintEl.textContent = String(res.hint);
        hintEl.style.display = "";
      }
      tavernBgmCatalog = [];
      renderTavernBgmAddCatalog();
      return;
    }
    select.innerHTML = tavernBgmChats
      .map(
        (c) =>
          `<option value="${Number(c.chat_id)}">${escapeHtml(String(c.title || c.chat_id))} (${Number(c.track_count) || 0})</option>`
      )
      .join("");
    const pref = Number(preferredChatId);
    const hasPref = tavernBgmChats.some((c) => Number(c.chat_id) === pref);
    const selected = hasPref ? pref : Number(tavernBgmChats[0].chat_id);
    select.value = String(selected);
    populateTavernBgmAddPlaylistSelect(selected);
    await refreshTavernBgmAddPlaylistTrackIds();
    await loadTavernBgmAddCatalog(selected);
  } catch (e) {
    select.innerHTML = `<option value="">Ошибка загрузки</option>`;
  }
}

async function loadTavernBgmPlaylistDetail(playlistId) {
  const id = Number(playlistId);
  if (!Number.isFinite(id)) {
    tavernBgmSelectedPlaylist = null;
    tavernBgmSelectedPlaylistId = null;
    renderTavernBgmPlaylistTracks();
    return;
  }
  try {
    const res = await apiFetch(`/tavern/bgm/playlists/${id}`);
    tavernBgmSelectedPlaylist = res?.playlist || null;
    tavernBgmSelectedPlaylistId = id;
  } catch (e) {
    tavernBgmSelectedPlaylist = null;
    tavernBgmSelectedPlaylistId = null;
  }
  renderTavernBgmPlaylistTracks();
}

async function refreshTavernBgmPlaylistsUi(preferredPlaylistId) {
  await fetchTavernBgmPlaylists();
  const select = document.getElementById("tavern-bgm-playlist-select");
  populateTavernBgmPlaylistSelect(select, preferredPlaylistId || tavernBgmActivePlaylistId);
  const selectedId = Number(select?.value);
  await loadTavernBgmPlaylistDetail(selectedId);
  const addChatSelect = document.getElementById("tavern-bgm-add-chat-select");
  if (addChatSelect?.value) {
    populateTavernBgmAddPlaylistSelect(Number(addChatSelect.value));
    await refreshTavernBgmAddPlaylistTrackIds();
  }
  renderTavernBgmAddCatalog();
  syncTavernBgmPlaylistToolbar();
}

async function createTavernBgmPlaylistFromTab() {
  const id = await createTavernBgmPlaylistWithPrompt(getTavernBgmAddChatId());
  if (!id) return;
  await loadTavernBgmPlaylistDetail(id);
  await applyTavernBgmPlaylistSilent(id, { restartPlayback: false });
}

function switchTavernBgmModalTab(name) {
  closeTavernBgmVolumeOverlay();
  closeTavernBgmPlaylistPicker();
  const tab = name === "playlist" || name === "add" ? name : "player";
  document.querySelectorAll("#tavern-bgm-player-modal [data-bgm-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-bgm-tab") === tab);
  });
  const playerPanel = document.getElementById("tavern-bgm-tab-player");
  const playlistPanel = document.getElementById("tavern-bgm-tab-playlist");
  const addPanel = document.getElementById("tavern-bgm-tab-add");
  if (playerPanel) playerPanel.classList.toggle("tavern-bgm-tab-panel--hidden", tab !== "player");
  if (playlistPanel) playlistPanel.classList.toggle("tavern-bgm-tab-panel--hidden", tab !== "playlist");
  if (addPanel) addPanel.classList.toggle("tavern-bgm-tab-panel--hidden", tab !== "add");
}

async function openTavernBgmPlayer() {
  const modal = document.getElementById("tavern-bgm-player-modal");
  if (!modal) return;
  closeTavernBgmVolumeOverlay();
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  document.body.classList.add("tavern-modal-scroll-lock");
  await migrateTavernBgmLocalConfig();
  await loadTavernBgmConfig();
  await refreshTavernBgmPlaylistsUi(tavernBgmActivePlaylistId);
  const preferredChat =
    tavernBgmActivePlaylist?.chat_id ||
    tavernBgmPlaylists[0]?.chat_id ||
    readTavernBgmConfigLegacy()?.chatId;
  await populateTavernBgmAddChatSelect(preferredChat);
  switchTavernBgmModalTab(tavernBgmActiveTracks.length ? "player" : "add");
  syncTavernBgmVolumeUi();
  syncTavernBgmPlayerUi();
}

function closeTavernBgmPlayer() {
  const modal = document.getElementById("tavern-bgm-player-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "none";
  document.body.classList.remove("tavern-modal-scroll-lock");
  closeTavernBgmVolumeOverlay();
  closeTavernBgmPlaylistPicker();
}

function onTavernBgmModalBackdropClick(event) {
  if (event.target.id !== "tavern-bgm-player-modal") return;
  if (isTavernBgmPlaylistPickerOpen()) {
    closeTavernBgmPlaylistPicker();
    return;
  }
  closeTavernBgmPlayer();
}

async function applyTavernBgmPlaylistSilent(playlistId, opts = {}) {
  const id = Number(playlistId);
  if (!Number.isFinite(id)) return false;
  const tracks = Array.isArray(tavernBgmSelectedPlaylist?.tracks)
    ? tavernBgmSelectedPlaylist.tracks
    : [];
  if (!tracks.length) {
    showToast("Добавьте треки в плейлист", "error");
    return false;
  }
  try {
    const res = await apiFetch(`/tavern/bgm/playlists/${id}/activate`, { method: "POST" });
    tavernBgmActivePlaylist = res?.playlist || null;
    tavernBgmActivePlaylistId = id;
    tavernBgmActiveTracks = Array.isArray(res?.playlist?.tracks) ? res.playlist.tracks.slice() : [];
    tavernBgmCurrentSourceIndex = -1;
    tavernBgmPlayOrder = [];
    tavernBgmPlayOrderPos = 0;
    await fetchTavernBgmPlaylists();
    syncTavernBgmPlayerUi();
    const restart = opts.restartPlayback !== false;
    if (!isTavernBgmMuted() && tavernBgmActiveTracks.length && restart) startTavernBgm();
    return true;
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось применить плейлист", "error");
    return false;
  }
}

async function onTavernBgmPlaylistSelectChange() {
  const select = document.getElementById("tavern-bgm-playlist-select");
  const playlistId = Number(select?.value);
  await loadTavernBgmPlaylistDetail(playlistId);
  if (Number.isFinite(playlistId)) {
    await applyTavernBgmPlaylistSilent(playlistId, { restartPlayback: true });
  }
}

async function onTavernBgmAddChatChange() {
  const select = document.getElementById("tavern-bgm-add-chat-select");
  const chatId = Number(select?.value);
  populateTavernBgmAddPlaylistSelect(chatId);
  await refreshTavernBgmAddPlaylistTrackIds();
  await loadTavernBgmAddCatalog(chatId);
}

async function onTavernBgmAddPlaylistChange() {
  const select = document.getElementById("tavern-bgm-add-playlist-select");
  const val = select?.value;
  if (val === "__new__") {
    const id = await createTavernBgmPlaylistWithPrompt(getTavernBgmAddChatId());
    if (!id && tavernBgmPlaylists.length) select.value = String(tavernBgmPlaylists[0].id);
    return;
  }
  await refreshTavernBgmAddPlaylistTrackIds();
  renderTavernBgmAddCatalog();
}

async function addTrackToTavernBgmPlaylist(trackId) {
  const playlistId = await getTavernBgmAddPlaylistId();
  const id = Number(trackId);
  if (!Number.isFinite(playlistId) || playlistId <= 0) return;
  try {
    await apiFetch(`/tavern/bgm/playlists/${playlistId}/tracks`, {
      method: "POST",
      body: JSON.stringify({ track_id: id }),
    });
    await refreshTavernBgmPlaylistsUi(playlistId);
    const addSelect = document.getElementById("tavern-bgm-add-playlist-select");
    if (addSelect) addSelect.value = String(playlistId);
    if (tavernBgmActivePlaylistId === playlistId) {
      await loadTavernBgmPlaylistDetail(playlistId);
      await applyTavernBgmPlaylistSilent(playlistId, { restartPlayback: false });
    }
    showToast("Трек добавлен", "success");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось добавить трек", "error");
  }
}

async function removeTrackFromTavernBgmPlaylist(trackId) {
  const playlistId = tavernBgmSelectedPlaylistId;
  const id = Number(trackId);
  if (!Number.isFinite(playlistId)) return;
  try {
    await apiFetch(`/tavern/bgm/playlists/${playlistId}/tracks/${id}`, { method: "DELETE" });
    await refreshTavernBgmPlaylistsUi(playlistId);
    await loadTavernBgmPlaylistDetail(playlistId);
    if (tavernBgmActivePlaylistId === playlistId) {
      const tracksLeft = Array.isArray(tavernBgmSelectedPlaylist?.tracks)
        ? tavernBgmSelectedPlaylist.tracks.length
        : 0;
      if (tracksLeft) {
        await applyTavernBgmPlaylistSilent(playlistId, { restartPlayback: true });
      } else {
        await loadTavernBgmConfig();
        stopTavernBgm(400);
      }
    }
    syncTavernBgmPlayerUi();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось убрать трек", "error");
  }
}

async function renameTavernBgmPlaylist() {
  const playlistId = tavernBgmSelectedPlaylistId;
  if (!playlistId || !tavernBgmSelectedPlaylist) {
    showToast("Выберите плейлист", "error");
    return;
  }
  const name = window.prompt("Новое название", tavernBgmSelectedPlaylist.name || "");
  if (!name || !String(name).trim()) return;
  try {
    await apiFetch(`/tavern/bgm/playlists/${playlistId}`, {
      method: "PATCH",
      body: JSON.stringify({ name: String(name).trim() }),
    });
    await refreshTavernBgmPlaylistsUi(playlistId);
    if (tavernBgmActivePlaylistId === playlistId && tavernBgmActivePlaylist) {
      tavernBgmActivePlaylist.name = String(name).trim();
      syncTavernBgmPlaylistCaption();
    }
    showToast("Название сохранено", "success");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось переименовать", "error");
  }
}

async function deleteTavernBgmPlaylist() {
  const playlistId = tavernBgmSelectedPlaylistId;
  if (!playlistId) {
    showToast("Выберите плейлист", "error");
    return;
  }
  if (!window.confirm("Удалить этот плейлист?")) return;
  try {
    await apiFetch(`/tavern/bgm/playlists/${playlistId}`, { method: "DELETE" });
    if (tavernBgmActivePlaylistId === playlistId) {
      tavernBgmActivePlaylistId = null;
      tavernBgmActivePlaylist = null;
      tavernBgmActiveTracks = [];
      stopTavernBgm(400);
    }
    await refreshTavernBgmPlaylistsUi();
    await loadTavernBgmConfig();
    syncTavernBgmPlayerUi();
    showToast("Плейлист удалён", "success");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось удалить", "error");
  }
}

function openTavernBgmUploadPicker() {
  const chatId = Number(document.getElementById("tavern-bgm-add-chat-select")?.value);
  if (!Number.isFinite(chatId)) {
    showToast("Сначала выберите чат", "error");
    return;
  }
  document.getElementById("tavern-bgm-upload-input")?.click();
}

async function readAudioDurationSec(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.preload = "metadata";
    audio.src = url;
    const done = (sec) => {
      URL.revokeObjectURL(url);
      resolve(sec);
    };
    audio.addEventListener("loadedmetadata", () => {
      const d = Number(audio.duration);
      done(Number.isFinite(d) && d > 0 ? Math.round(d) : null);
    });
    audio.addEventListener("error", () => done(null));
    setTimeout(() => done(null), 8000);
  });
}

async function onTavernBgmUploadSelected(input) {
  const file = input?.files?.[0];
  if (input) input.value = "";
  if (!file) return;
  const chatId = Number(document.getElementById("tavern-bgm-add-chat-select")?.value);
  if (!Number.isFinite(chatId)) {
    showToast("Сначала выберите чат", "error");
    return;
  }
  const duration = await readAudioDurationSec(file);
  const fd = new FormData();
  fd.append("file", file);
  fd.append("chat_id", String(chatId));
  if (duration) fd.append("duration", String(duration));
  try {
    const res = await fetch("/api/tavern/bgm/upload", {
      method: "POST",
      headers: tavernBgmAuthHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "upload failed");
    }
    const data = await res.json();
    showToast("Трек загружен в чат", "success");
    await loadTavernBgmAddCatalog(chatId);
    const trackId = Number(data?.track?.id);
    const playlistVal = document.getElementById("tavern-bgm-add-playlist-select")?.value;
    if (Number.isFinite(trackId) && playlistVal && playlistVal !== "__new__") {
      await addTrackToTavernBgmPlaylist(trackId);
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить трек", "error");
  }
}

function firstAvailableTavernSlot(available) {
  const slots = available?.slots || [];
  for (let i = 1; i <= 4; i += 1) {
    const slotObj = slots.find((s) => Number(s?.slot) === i);
    if (slotObj?.available) return i;
  }
  return null;
}

function formatTavernHirePrice(available) {
  const price = Number(available?.price ?? 10000);
  if (available?.first_hire_free || price === 0) return "Бесплатно";
  return `🪙 ${price.toLocaleString("ru-RU")}`;
}

function onTavernHirePrimaryClick() {
  const slot = firstAvailableTavernSlot(tavernState.available);
  if (slot == null) {
    showToast("Все слоты найма на сегодня заняты", "error");
    return;
  }
  openTavernConfirmHire(slot);
}

function switchTavernTab(name) {
  if (name === "heal" || name === "upgrade") name = "squad";
  document.querySelectorAll(".tavern-tabs .tab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  ["hire", "squad", "arena", "exchange", "inventory", "heal", "upgrade"].forEach((t) => {
    const panel = document.getElementById(`tab-${t}`);
    if (!panel) return;
    const isActive = t === name;
    panel.classList.toggle("active", isActive);
    panel.style.display = isActive ? "" : "none";
  });
  const footer = document.getElementById("tavern-hire-footer");
  if (footer) footer.style.display = name === "hire" ? "flex" : "none";
  if (name === "hire") {
    loadMercStatusPity().catch(() => {});
  }
  if (name === "squad") {
    ensureTavernRosterLoaded()
      .then(() => {
        renderTavernSquad();
        renderTavernLineupBars();
      })
      .catch(() => {});
  }
  if (name === "arena") {
    renderTavernArena().catch((e) => {
      const { detail } = parseHttpErrorDetail(e);
      showToast(detail || "Ошибка арены", "error");
    });
  }
  if (name === "exchange") {
    renderTavernExchange().catch(() => {});
  }
  if (name === "inventory") {
    ensureTavernRosterLoaded()
      .then(() => refreshDrillManuals())
      .then(() => renderTavernInventoryTab())
      .catch(() => renderTavernInventoryTab());
  }
  syncTavernPageBackgroundVisibility();
}

function renderTavernHealList() {
  const container = document.getElementById("tavern-heal-list");
  if (!container) return;
  const squad = Array.isArray(tavernState.squad) ? tavernState.squad : [];
  const reserve = Array.isArray(tavernState.reserve) ? tavernState.reserve : [];
  const all = [...squad, ...reserve];
  const wounded = all.filter((w) => {
    if (hiredWaifuPoolUiStatus(w).key === "traveling") return false;
    if (hiredWaifuIsHealing(w)) return true;
    const { cur, max: maxHp } = hiredWaifuHp(w);
    return cur < maxHp;
  });
  if (wounded.length === 0) {
    container.innerHTML = '<p class="muted" style="font-style:italic;">Нет раненых наёмниц.</p>';
    container.className = "placeholder muted";
    if (tavernHealTimerInterval) {
      clearInterval(tavernHealTimerInterval);
      tavernHealTimerInterval = null;
    }
    return;
  }
  container.className = "tavern-heal-grid";
  container.innerHTML = wounded
    .map((w) => {
      const { cur, max: maxHp } = hiredWaifuHp(w);
      const pct = maxHp > 0 ? Math.round((cur / maxHp) * 100) : 0;
      const portrait = hiredWaifuImageUrl(w, "thumb");
      const portraitHtml = portrait
        ? `<img src="${escapeHtml(portrait)}" alt="" loading="lazy" decoding="async">`
        : `<span aria-hidden="true">🛡️</span>`;
      const name = escapeHtml(w.name || "Наёмница");
      const subHp = `❤ ${cur}/${maxHp}`;
      if (hiredWaifuIsHealing(w)) {
        const completeAt = hiredWaifuHealCompleteAt(w) || "";
        const left = healSecondsRemaining(completeAt);
        const timerText = left > 0 ? formatHealCountdown(left) : "0:00";
        return `
        <div class="tavern-heal-card tavern-heal-card--healing" aria-label="${name} на лечении">
          <div class="tavern-heal-card-portrait">${portraitHtml}</div>
          <div class="tavern-heal-card-info">
            <div class="tavern-heal-card-name">${name}</div>
            <div class="tavern-heal-card-sub">${subHp}</div>
            <div class="tavern-heal-card-hp"><div class="tavern-hp-bar-wrap"><div class="tavern-hp-bar" style="width:${pct}%"></div></div></div>
          </div>
          <div class="tavern-heal-timer" data-heal-complete-at="${escapeHtml(completeAt)}">⏳ ${timerText}</div>
        </div>`;
      }
      const need = maxHp - cur;
      const mult = cur === 0 ? 2 : 1;
      const cost = need * TAVERN_HEAL_GOLD_PER_HP * mult;
      return `
        <div class="tavern-heal-card" data-waifu-id="${w.id}" data-cost="${cost}" role="button" tabindex="0" aria-label="Лечить ${name} за ${cost} золота">
          <div class="tavern-heal-card-portrait">${portraitHtml}</div>
          <div class="tavern-heal-card-info">
            <div class="tavern-heal-card-name">${name}</div>
            <div class="tavern-heal-card-sub">${subHp}</div>
            <div class="tavern-heal-card-hp"><div class="tavern-hp-bar-wrap"><div class="tavern-hp-bar" style="width:${pct}%"></div></div></div>
          </div>
          <div class="tavern-heal-cost">🪙 ${cost}</div>
        </div>`;
    })
    .join("");

  async function healWaifu(card) {
    if (!card || card.dataset.healing === "1") return;
    const id = parseInt(card.dataset.waifuId, 10);
    if (!id) return;
    card.dataset.healing = "1";
    try {
      const res = await apiFetch(`/tavern/heal?hired_waifu_id=${encodeURIComponent(id)}`, { method: "POST" });
      if (res && res.success) {
        if (typeof res.gold_total === "number") profileState.gold = res.gold_total;
        const { squad: s, reserve: r } = await loadTavernWithProfile(undefined, { innerRefresh: true });
        tavernState.squad = s || tavernState.squad;
        tavernState.reserve = r || tavernState.reserve;
        renderTavernHealList();
        renderTavernSquad();
      }
    } catch (e) {
      showToast("Ошибка лечения: " + (e?.message || ""), "error");
    } finally {
      delete card.dataset.healing;
    }
  }

  container.querySelectorAll(".tavern-heal-card[data-waifu-id]").forEach((card) => {
    card.addEventListener("click", () => healWaifu(card));
    card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        healWaifu(card);
      }
    });
  });

  wireTavernHealTimers();
}

function perkLevelStars(level, maxLevel = 5, compact = false) {
  const lv = Math.max(1, Math.min(maxLevel, Number(level) || 1));
  if (compact) {
    return `<span class="tavern-upgrade-perk-stars tavern-upgrade-perk-stars--compact" title="Уровень ${lv}">${lv}</span>`;
  }
  return `<span class="tavern-upgrade-perk-stars" title="Уровень ${lv}">${"★".repeat(lv)}${"☆".repeat(maxLevel - lv)}</span>`;
}

function openTavernUpgradeLoading() {
  const modal = document.getElementById("tavern-upgrade-loading-modal");
  if (!modal) return;
  modal.style.display = "flex";
  modal.setAttribute("aria-busy", "true");
  setTavernWaifuModalPageScrollLocked(true);
}

function closeTavernUpgradeLoading() {
  const modal = document.getElementById("tavern-upgrade-loading-modal");
  if (!modal) return;
  modal.style.display = "none";
  modal.setAttribute("aria-busy", "false");
  setTavernWaifuModalPageScrollLocked(false);
}

function tavernUpgradePerkGridHtml(w, perksMap, inExpedition) {
  const perks = (Array.isArray(w.perks) ? w.perks : []).filter(Boolean);
  const count = perks.length;
  if (!count) return "";
  const perkLevels = w.perkLevels || w.perk_levels || {};
  const points = Number(w.perkUpgradePoints ?? w.perk_upgrade_points ?? 0);
  const compact = count >= 5;
  const colsMod = ` tavern-upgrade-perk-grid--cols-${count}`;
  const cells = perks
    .map((pid) => {
      const lv = Number(perkLevels[pid] ?? 1);
      const maxLv = 5;
      const cost = lv;
      const canUpgrade = !inExpedition && lv < maxLv && points >= cost;
      const perkName = String(perksMap[pid] || pid);
      const readyCls = canUpgrade ? " tavern-upgrade-perk-hit--ready" : "";
      const ariaLabel = canUpgrade
        ? `Улучшить ${perkName} за ${cost} очк.`
        : `${perkName}, уровень ${lv}`;
      return `
      <div class="tavern-upgrade-perk-cell">
        <button type="button"
          class="tavern-upgrade-perk-hit${readyCls}"
          data-waifu-id="${w.id}"
          data-perk-id="${escapeHtml(String(pid))}"
          aria-label="${escapeHtml(ariaLabel)}"
          ${canUpgrade ? "" : "disabled tabindex=\"-1\""}>
          ${
            typeof perkIconHtml === "function"
              ? perkIconHtml(pid, { className: "tavern-upgrade-perk-ico-img", title: perkName })
              : `<span class="tavern-upgrade-perk-ico" aria-hidden="true">${PERK_ICONS[pid] || "✦"}</span>`
          }
          ${perkLevelStars(lv, maxLv, compact)}
        </button>
      </div>`;
    })
    .join("");
  return `<div class="tavern-upgrade-perk-grid${colsMod}" style="--perk-cols:${count}">${cells}</div>`;
}

function renderTavernUpgradeList() {
  const container = document.getElementById("tavern-upgrade-list");
  if (!container) return;
  const squad = Array.isArray(tavernState.squad) ? tavernState.squad : [];
  const reserve = Array.isArray(tavernState.reserve) ? tavernState.reserve : [];
  const all = [...squad, ...reserve];
  const perksMap = tavernState.perksMap || {};
  if (!all.length) {
    container.className = "placeholder muted";
    container.innerHTML =
      '<p style="font-style:italic;padding:8px 0;">Нет нанятых наёмниц. Очки улучшения перков даются за лвлап после экспедиции.</p>';
    return;
  }
  container.className = "tavern-upgrade-list";
  container.innerHTML = all
    .map((w) => {
      const points = Number(w.perkUpgradePoints ?? w.perk_upgrade_points ?? 0);
      const expId = w.expedition_id ?? w.expeditionId;
      const inExpedition = expId != null && Number(expId) > 0;
      const portrait = hiredWaifuImageUrl(w, "thumb");
      const portraitInner = portrait
        ? `<img src="${escapeHtml(portrait)}" alt="" loading="lazy" decoding="async">`
        : `<span aria-hidden="true">🛡️</span>`;
      const perkGrid = tavernUpgradePerkGridHtml(w, perksMap, inExpedition);
      return `
      <div class="tavern-upgrade-card">
        <div class="tavern-upgrade-card-portrait">
          ${portraitInner}
          <div class="tavern-upgrade-card-scrim" aria-hidden="true"></div>
          <div class="tavern-upgrade-card-overlay">
            <div class="tavern-upgrade-card-name">${escapeHtml(w.name || "Наёмница")}</div>
            <div class="tavern-upgrade-card-meta">
              <span class="tavern-upgrade-card-level">Ур. ${w.level ?? "—"}</span>
              <span class="tavern-upgrade-points-badge ${points > 0 ? "has-points" : ""}" title="Очки улучшения перков">
                <span class="tavern-upgrade-points-num">${points}</span>
                <span class="tavern-upgrade-points-label">очк.</span>
              </span>
            </div>
          </div>
        </div>
        ${perkGrid}
        ${inExpedition ? '<div class="muted tiny tavern-upgrade-exp-note">В экспедиции</div>' : ""}
      </div>`;
    })
    .join("");
  container.querySelectorAll(".tavern-upgrade-perk-hit--ready").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (btn.disabled || btn.dataset.upgrading === "1") return;
      const waifuId = parseInt(btn.dataset.waifuId, 10);
      const perkId = btn.dataset.perkId;
      if (!waifuId || !perkId) return;
      btn.dataset.upgrading = "1";
      openTavernUpgradeLoading();
      try {
        await apiFetch(
          `/tavern/upgrade-perk?waifu_id=${encodeURIComponent(waifuId)}&perk_id=${encodeURIComponent(perkId)}`,
          { method: "POST" }
        );
        const { squad: s, reserve: r } = await loadTavernWithProfile(undefined, { innerRefresh: true });
        tavernState.squad = s || tavernState.squad;
        tavernState.reserve = r || tavernState.reserve;
        renderTavernUpgradeList();
        renderTavernSquad();
      } catch (e) {
        const { detail } = parseHttpErrorDetail(e);
        showToast(detail || "Ошибка улучшения", "error");
      } finally {
        closeTavernUpgradeLoading();
        delete btn.dataset.upgrading;
      }
    });
  });
}

function buildTavernPerksMap(available) {
  const fromCatalog = tavernState.perksCatalog || {};
  const names = {};
  Object.keys(fromCatalog).forEach((id) => {
    names[id] = fromCatalog[id].name || id;
  });
  const perksList = Array.isArray(available?.perks) ? available.perks : [];
  perksList.forEach((x) => {
    if (x?.id) names[x.id] = x.name || x.id;
  });
  if (Object.keys(names).length) return names;
  return { ...(window.WaifuApp?.PERK_NAMES || window.PERK_NAMES || {}) };
}

async function ensureMercPerksCatalog() {
  if (tavernState.perksCatalog && Object.keys(tavernState.perksCatalog).length) {
    window.__mercPerksCatalog = tavernState.perksCatalog;
    return tavernState.perksCatalog;
  }
  try {
    const data = await apiFetch("/tavern/perks");
    const map = {};
    (data?.perks || []).forEach((p) => {
      if (!p?.id) return;
      map[p.id] = {
        name: p.name,
        flavor: p.flavor || "",
        effect: p.effect || "",
        type: p.type,
        rarity: p.rarity,
        tags: p.tags || [],
      };
    });
    tavernState.perksCatalog = map;
    window.__mercPerksCatalog = map;
    tavernState.perksMap = { ...buildTavernPerksMap(tavernState.available), ...Object.fromEntries(Object.entries(map).map(([k, v]) => [k, v.name])) };
  } catch (_) {
    tavernState.perksCatalog = tavernState.perksCatalog || {};
  }
  return tavernState.perksCatalog;
}

function mercPerkTip(pid) {
  const cat = tavernState.perksCatalog?.[pid] || window.__mercPerksCatalog?.[pid];
  const name =
    cat?.name ||
    tavernState.perksMap?.[pid] ||
    (typeof perkNameRu === "function" ? perkNameRu(pid) : null) ||
    pid;
  const flavor =
    cat?.flavor ||
    (typeof perkFlavorRu === "function" ? perkFlavorRu(pid) : null) ||
    "Специальное умение для операций.";
  const effect =
    cat?.effect ||
    (typeof perkEffectRu === "function" ? perkEffectRu(pid) : null) ||
    PERK_EFFECTS?.[pid] ||
    "";
  return { name, flavor, effect };
}

function allRosterWaifus() {
  return [...(tavernState.squad || []), ...(tavernState.reserve || [])];
}

function findRosterWaifu(id) {
  if (id == null) return null;
  return allRosterWaifus().find((w) => Number(w.id) === Number(id)) || null;
}

function rosterByIdMap() {
  const m = {};
  allRosterWaifus().forEach((w) => {
    m[Number(w.id)] = w;
  });
  return m;
}

function isOnLineup(w) {
  const a = w?.atkSlot ?? w?.atk_slot;
  const d = w?.defSlot ?? w?.def_slot;
  return (a != null && Number(a) >= 1) || (d != null && Number(d) >= 1);
}

function typePipsHtml(waifus) {
  const counts = { ATK: 0, DEF: 0, SUP: 0 };
  (waifus || []).forEach((w) => {
    const t = String(w?.archetype_id || w?.archetypeId || "").toLowerCase();
    // fallback: count perk types from catalog
    const perks = Array.isArray(w?.perks) ? w.perks : [];
    perks.forEach((pid) => {
      const tp = tavernState.perksCatalog?.[pid]?.type;
      if (tp === "ATK" || tp === "DEF" || tp === "SUP") counts[tp] += 1;
    });
    if (!perks.length) {
      if (t.includes("berserk") || t.includes("vanguard") || t.includes("duel")) counts.ATK += 1;
      else if (t.includes("citadel") || t.includes("bulwark") || t.includes("ward")) counts.DEF += 1;
      else counts.SUP += 1;
    }
  });
  const order = ["ATK", "DEF", "SUP"];
  const present = order.filter((k) => counts[k] > 0).slice(0, 3);
  if (!present.length) present.push("ATK");
  return `<span class="tavern-type-pips">${present.map((k) => `<span class="tavern-type-pip ${k.toLowerCase()}" title="${k}"></span>`).join("")}</span>`;
}

function scheduleTavernBgmStart() {
  const run = () => {
    if (isTavernBgmMuted()) {
      syncTavernBgmPlayerUi();
      return;
    }
    loadTavernBgmConfig().then(() => {
      syncTavernBgmPlayerUi();
      if (!isTavernBgmMuted()) startTavernBgm();
    });
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(run, { timeout: 2500 });
  } else {
    setTimeout(run, 0);
  }
}

async function loadTavernWithProfile(profile, opts = {}) {
  const inner = Boolean(opts.innerRefresh);
  if (!inner) {
    syncTavernBgmMuteButton();
    setTavernPageLoading(true);
  }
  let loadOk = false;
  try {
    const p = profile || (await loadProfile({ lite: true }));
    tavernState.act = Number(p?.act || 1);
    const loadRoster = inner || Boolean(opts.loadRoster);

    let available;
    if (loadRoster) {
      const availPromise =
        opts.preloadedAvailable != null && !inner
          ? Promise.resolve(opts.preloadedAvailable)
          : apiFetch("/tavern/available");
      const [availRes, squadRes, reserveRes] = await Promise.all([
        availPromise,
        apiFetch("/tavern/squad"),
        apiFetch("/tavern/reserve"),
      ]);
      available = availRes;
      tavernState.squad = Array.isArray(squadRes?.squad) ? squadRes.squad : [];
      tavernState.reserve = Array.isArray(reserveRes?.reserve) ? reserveRes.reserve : [];
      tavernRosterLoaded = true;
    } else if (opts.preloadedAvailable != null) {
      available = opts.preloadedAvailable;
    } else {
      available = await apiFetch("/tavern/available");
    }

    tavernState.available = available;
    tavernState.perksMap = buildTavernPerksMap(available);
    if (available?.bench_cap != null) tavernState.benchCap = Number(available.bench_cap) || tavernState.benchCap;
    await ensureMercPerksCatalog().catch(() => {});

    renderTavernHire(p, available);
    if (loadRoster) {
      await renderTavernLineupBars();
      renderTavernSquad();
    }

    loadOk = true;
    return { available, squad: tavernState.squad, reserve: tavernState.reserve };
  } finally {
    if (!inner) {
      setTavernPageLoading(false);
      syncTavernBgmMuteButton();
      if (loadOk && !isTavernBgmMuted()) {
        scheduleTavernBgmStart();
      } else {
        syncTavernBgmPlayerUi();
      }
    }
  }
}

function renderTavernHire(profile, available) {
  const act = Number(profile?.act || tavernState.act || 1);
  const scene = document.getElementById("tavern-scene");
  if (scene) {
    ["act-1", "act-2", "act-3", "act-4", "act-5"].forEach((c) => scene.classList.remove(c));
    scene.classList.add(`act-${Math.max(1, Math.min(5, act))}`);
  }

  const remaining = Number(available?.remaining ?? 0);
  const freeSlot = firstAvailableTavernSlot(available);
  const priceLabel = formatTavernHirePrice(available);

  const pageBg = document.getElementById("tavern-page-bg");
  if (pageBg) {
    pageBg.src = tavernHireBackgroundUrl(remaining);
  }
  syncTavernPageBackgroundVisibility();

  const hireBtn = document.getElementById("tavern-hire-primary-btn");
  if (hireBtn) {
    if (freeSlot != null) {
      hireBtn.textContent = `Нанять — ${priceLabel}`;
      hireBtn.disabled = false;
      hireBtn.setAttribute("aria-label", `Нанять наёмницу. Осталось слотов: ${remaining}`);
    } else {
      hireBtn.textContent = "Слоты заняты";
      hireBtn.disabled = true;
      hireBtn.setAttribute("aria-label", "Все слоты найма на сегодня заняты");
    }
  }
}

function renderWaifuCardHtml(w, opts = {}) {
  const empty = !w;
  if (empty) {
    return `
      <div class="tavern-waifu-card tavern-empty">
        <div class="tavern-waifu-head">
          <div style="display:flex; gap:10px; align-items:center; min-width:0;">
            <div class="tavern-portrait" aria-hidden="true">—</div>
            <div style="min-width:0;">
              <div class="tavern-waifu-name">Пусто</div>
              <div class="tavern-waifu-sub">Свободный слот</div>
            </div>
          </div>
          <div class="tag">—</div>
        </div>
        <div class="tavern-mini-stats">
          <div class="pill"><span class="muted">CR</span><strong>—</strong></div>
          <div class="pill"><span class="muted">Перки</span><strong>—</strong></div>
        </div>
      </div>
    `;
  }

  const clsId = Number(w?.class ?? w?.class_ ?? w?.["class"]);
  const raceId = Number(w?.race);
  const rarity = Number(w?.rarity ?? 1);
  const lvl = w?.level ?? "—";
  const atk = w?.atkSlot ?? w?.atk_slot;
  const def = w?.defSlot ?? w?.def_slot;
  const tag =
    atk != null ? `ATK ${atk}` : def != null ? `DEF ${def}` : w?.squad_position != null ? `#${w.squad_position}` : "скамья";
  const nm = String(w?.name || "Вайфу");
  const arch = hiredArchetypeLabel(w);
  const sub = `lvl ${lvl} · ${rarityLabel(rarity)} · ${className(clsId)} / ${raceName(raceId)}${arch ? ` · ${arch}` : ""}`;
  const extra = String(opts?.extraClass || "").trim();
  const cls = `${"tavern-waifu-card"}${extra ? ` ${extra}` : ""}`;
  const power = hiredCr(w);
  const perksCount = perkIdsCapped(w).length;
  const portraitUrl = hiredWaifuImageUrl(w, "thumb");
  const portraitContent = portraitUrl
    ? `<img src="${escapeHtml(portraitUrl)}" alt="" loading="lazy" decoding="async" style="width:100%;height:100%;object-fit:cover;" />`
    : waifuPortraitEmoji(w);
  return `
    <div class="${cls}">
      <div class="tavern-waifu-head">
        <div style="display:flex; gap:10px; align-items:center; min-width:0;">
          <div class="tavern-portrait" aria-hidden="true">${portraitContent}</div>
          <div style="min-width:0;">
            <div class="tavern-waifu-name">${nm}</div>
            <div class="tavern-waifu-sub">${sub}</div>
          </div>
        </div>
        <div class="tag">${tag}</div>
      </div>
      <div class="tavern-mini-stats">
        <div class="pill"><span class="muted">CR</span><strong>${power}</strong></div>
        <div class="pill"><span class="muted">Перки</span><strong>${perksCount}</strong></div>
      </div>
    </div>
  `;
}

function renderLineupSlotEl(side, slotNum, waifuId, opts = {}) {
  const w = findRosterWaifu(waifuId);
  const el = document.createElement("button");
  el.type = "button";
  el.className = `tavern-lineup-slot${w ? " filled" : ""}`;
  el.setAttribute("data-side", side);
  el.setAttribute("data-slot", String(slotNum));
  if (w) {
    const url = hiredWaifuImageUrl(w, "thumb");
    const img = url
      ? `<img src="${escapeHtml(url)}" alt="" loading="lazy" decoding="async" />`
      : `<span class="tavern-lineup-portrait-fallback" aria-hidden="true">${waifuPortraitEmoji(w)}</span>`;
    el.innerHTML = `${img}<span class="tavern-lineup-overlay"><span class="tavern-lineup-name">${escapeHtml(String(w.name || "—"))}</span><span class="tavern-lineup-cr muted">CR ${escapeHtml(String(hiredCr(w)))}</span></span>`;
    el.onclick = () => openTavernWaifuModal(w);
  } else {
    el.innerHTML = `<span class="tavern-lineup-empty"><span style="font-size:18px">＋</span><span>${side.toUpperCase()} ${slotNum}</span></span>`;
    el.onclick = () => {
      tavernState.lineupPick = { side, slot: slotNum };
      if (opts.fromArena) {
        if (typeof switchTavernTab === "function") switchTavernTab("squad");
        else renderTavernSquad();
      } else {
        renderTavernSquad();
      }
    };
  }
  return el;
}

function renderTavernLineupRowsFromState() {
  const lu = tavernState.lineup || { atk: [null, null, null], def: [null, null, null] };
  const atkBox = document.getElementById("tavern-lineup-atk-slots");
  const defBox = document.getElementById("tavern-lineup-def-slots");
  if (atkBox) {
    atkBox.innerHTML = "";
    for (let i = 0; i < 3; i += 1) atkBox.appendChild(renderLineupSlotEl("atk", i + 1, lu.atk?.[i]));
  }
  if (defBox) {
    defBox.innerHTML = "";
    for (let i = 0; i < 3; i += 1) defBox.appendChild(renderLineupSlotEl("def", i + 1, lu.def?.[i]));
  }
  const atkUnits = (lu.atk || []).map(findRosterWaifu).filter(Boolean);
  const crSum = atkUnits.reduce((s, w) => s + (Number(hiredCr(w)) || 0), 0);
  const meta = document.getElementById("tavern-atk-meta");
  if (meta) meta.innerHTML = `CR ${crSum || "—"} ${typePipsHtml(atkUnits)}`;
  const capLabel = document.getElementById("tavern-bench-cap-label");
  if (capLabel) {
    const bench = allRosterWaifus().filter((w) => !isOnLineup(w));
    const total = allRosterWaifus().length;
    const cap = tavernBenchCap();
    capLabel.textContent = `${total}/${cap} · запас ${bench.length}`;
  }
}

function renderTavernSquad() {
  const box = document.getElementById("tavern-squad-grid");
  if (!box) return;

  renderTavernLineupRowsFromState();

  const roster = sortTavernPool(tavernState.squad, tavernState.reserve);
  const bench = roster.filter((w) => !isOnLineup(w));
  const poolMax = tavernBenchCap();
  const feedBanner = document.getElementById("tavern-quick-feed-banner");
  if (feedBanner) {
    feedBanner.style.display = tavernState.quickFeedMode || tavernState.lineupPick ? "" : "none";
    if (tavernState.lineupPick) {
      feedBanner.textContent = `Выбор для ${tavernState.lineupPick.side.toUpperCase()} ${tavernState.lineupPick.slot} — тап по скамейке`;
    } else if (tavernState.quickFeedMode) {
      const need = fodderNeedForTarget(tavernState.quickFeedTargetId);
      const have = (tavernState.fodderSelectedIds || []).length;
      feedBanner.innerHTML = `Прорыв ★: нужно <strong>${need}</strong>, выбрано <strong>${have}</strong> · тап по корму · <button type="button" class="tavern-btn tavern-btn-mini" id="tavern-fodder-confirm-btn"${have < need ? " disabled" : ""}>Прорвать</button> <button type="button" class="tavern-btn tavern-btn-mini" id="tavern-fodder-cancel-btn">Отмена</button>`;
    } else {
      feedBanner.textContent = "";
    }
  }

  // Hire empties only pad the last page.
  const totalPages = Math.max(1, Math.ceil(bench.length / BENCH_PAGE_SIZE) || 1);
  if (tavernState.benchPage >= totalPages) tavernState.benchPage = Math.max(0, totalPages - 1);
  if (tavernState.benchPage < 0) tavernState.benchPage = 0;
  const page = tavernState.benchPage;
  const pageSlice = bench.slice(page * BENCH_PAGE_SIZE, page * BENCH_PAGE_SIZE + BENCH_PAGE_SIZE);
  const isLastPage = page >= totalPages - 1;
  const hireEmptyBudget = Math.max(0, Math.min(BENCH_PAGE_SIZE - pageSlice.length, poolMax - roster.length));
  const emptySlots = isLastPage ? hireEmptyBudget : 0;

  box.innerHTML = "";

  const renderCard = (w) => {
    const rarity = Number(w?.rarity ?? 1);
    const rCls = rarityClass(rarity);
    const cr = hiredCr(w);
    const pips = typePipsHtml([w]);
    const url = hiredWaifuImageUrl(w, "full");
    const portraitLayer = url
      ? `<img class="squad-mtg-bg-img" src="${escapeHtml(url)}" alt="" loading="lazy" decoding="async" />`
      : "";
    const bgCls = url ? "squad-mtg-bg" : "squad-mtg-bg squad-mtg-bg--placeholder";
    const uiSt = hiredWaifuPoolUiStatus(w);
    const statusCls = `squad-mtg-card--${uiSt.key}`;
    const fodderSel = (tavernState.fodderSelectedIds || []).map(Number).includes(Number(w.id));
    const slot = document.createElement("div");
    slot.className = `squad-slot occupied${fodderSel ? " squad-slot--fodder-sel" : ""}`;
    slot.setAttribute("role", "button");
    slot.tabIndex = 0;
    slot.innerHTML = `
      <div class="squad-mtg-card ${rCls} ${statusCls}">
        <div class="${bgCls}" role="img" aria-label="">${portraitLayer}</div>
        <div class="squad-mtg-scrim-top" aria-hidden="true"></div>
        <div class="squad-mtg-scrim-bottom" aria-hidden="true"></div>
        <div class="squad-mtg-status-hatch" aria-hidden="true"></div>
        <div class="squad-mtg-cr squad-mtg-cr--bench" aria-label="CR">CR ${escapeHtml(String(cr))}</div>
        <div class="squad-mtg-bottom">
          <div class="squad-mtg-cr-row">${pips}</div>
        </div>
      </div>`;
    const open = () => {
      if (tavernState.lineupPick) {
        const { side, slot: sn } = tavernState.lineupPick;
        tavernState.lineupPick = null;
        tavernSetLineup(side, sn, w.id);
        return;
      }
      if (tavernState.quickFeedMode && tavernState.quickFeedTargetId) {
        toggleFodderSelection(w);
        return;
      }
      openTavernWaifuModal(w);
    };
    slot.onclick = open;
    slot.onkeydown = (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        open();
      }
    };
    box.appendChild(slot);
  };

  pageSlice.forEach(renderCard);

  for (let i = 0; i < emptySlots; i += 1) {
    const empty = document.createElement("div");
    empty.className = "squad-slot";
    empty.innerHTML = `<span style="font-size:24px;opacity:.3">＋</span><span style="font-size:11px;">Нанять</span>`;
    empty.onclick = () => switchTavernTab("hire");
    box.appendChild(empty);
  }

  if (!bench.length && !emptySlots) {
    box.innerHTML = `<div class="placeholder muted">Скамейка пуста — все в ATK/DEF или наймите новых</div>`;
  }

  const pager = document.getElementById("tavern-bench-pager");
  const pageLabel = document.getElementById("tavern-bench-page-label");
  const prevBtn = document.getElementById("tavern-bench-prev");
  const nextBtn = document.getElementById("tavern-bench-next");
  if (pager) {
    const showPager = totalPages > 1;
    pager.hidden = !showPager;
    if (pageLabel) pageLabel.textContent = `${page + 1}/${totalPages}`;
    if (prevBtn && !prevBtn.dataset.wired) {
      prevBtn.dataset.wired = "1";
      prevBtn.onclick = () => {
        tavernState.benchPage = Math.max(0, tavernState.benchPage - 1);
        renderTavernSquad();
      };
    }
    if (nextBtn && !nextBtn.dataset.wired) {
      nextBtn.dataset.wired = "1";
      nextBtn.onclick = () => {
        tavernState.benchPage += 1;
        renderTavernSquad();
      };
    }
    if (prevBtn) prevBtn.disabled = page <= 0;
    if (nextBtn) nextBtn.disabled = page >= totalPages - 1;
  }

  const fodConfirm = document.getElementById("tavern-fodder-confirm-btn");
  if (fodConfirm) {
    fodConfirm.onclick = (ev) => {
      ev.stopPropagation();
      confirmFodderStars().catch(() => {});
    };
  }
  const fodCancel = document.getElementById("tavern-fodder-cancel-btn");
  if (fodCancel) {
    fodCancel.onclick = (ev) => {
      ev.stopPropagation();
      cancelFodderPickMode();
    };
  }
}

function openTavernConfirmHire(slot) {
  const id = Number(slot || 0);
  if (!Number.isFinite(id) || id < 1 || id > 4) return;
  const available = tavernState.available;
  const priceLabel = formatTavernHirePrice(available);
  tavernState.pendingHireSlot = id;
  const priceEl = document.getElementById("confirm-price");
  if (priceEl) priceEl.textContent = priceLabel;
  const modal = document.getElementById("modal-confirm-hire");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function closeTavernConfirmHire() {
  tavernState.pendingHireSlot = null;
  const modal = document.getElementById("modal-confirm-hire");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function setGenOverlay(show, label, detail, pct) {
  const overlay = document.getElementById("gen-overlay");
  const labelEl = document.getElementById("gen-stage-label");
  const detailEl = document.getElementById("gen-stage-detail");
  const fillEl = document.getElementById("gen-progress-fill");
  if (overlay) {
    overlay.classList.toggle("hidden", !show);
    overlay.style.display = show ? "flex" : "none";
  }
  if (labelEl && label != null) labelEl.textContent = label || "";
  if (detailEl && detail != null) detailEl.textContent = detail || "";
  if (fillEl && pct != null) fillEl.style.width = String(pct) + "%";
}

async function confirmTavernHire() {
  const slot = tavernState.pendingHireSlot;
  if (!slot) return;
  closeTavernConfirmHire();
  showTavernError("");
  setGenOverlay(true, "Призыв наёмницы...", "Ожидание ответа сервера", 20);
  try {
    const result = await apiFetch(`/tavern/hire?slot=${encodeURIComponent(slot)}`, { method: "POST" });
    setGenOverlay(true, "Параметры получены", "Добавление в запас...", 70);
    await loadProfile().catch(() => {});
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true }).catch(() => {});
    setGenOverlay(true, "✦ Наёмница готова ✦", "", 100);
    await new Promise((r) => setTimeout(r, 400));
    tavernState.lastHiredResult = result;
    showTavernHireResultModal(result);
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showTavernError(detail || "Ошибка найма", "danger");
  } finally {
    setGenOverlay(false, "", "", 0);
  }
}

function toggleHireResultFlip(ev) {
  if (ev) ev.stopPropagation();
  const inner = document.getElementById("hire-result-flip-inner");
  if (inner) inner.classList.toggle("is-flipped");
}

function showTavernHireResultModal(result) {
  const name = result?.waifu_name || "Вайфу";
  const rarity = Number(result?.waifu_rarity ?? 1);
  const flipInner = document.getElementById("hire-result-flip-inner");
  const bg = document.getElementById("result-card-bg");
  const rFrame = ["rarity-common", "rarity-uncommon", "rarity-rare", "rarity-epic", "rarity-legendary"];
  if (flipInner) {
    flipInner.classList.remove("is-flipped");
    rFrame.forEach((c) => flipInner.classList.remove(c));
    flipInner.classList.add(rarityClass(rarity));
  }
  setText("result-name", name);
  const newWaifu = (tavernState.reserve || []).find((w) => w.id === result?.waifu_id);
  const raceId = Number(newWaifu?.race ?? 0);
  const classId = Number(newWaifu?.class ?? newWaifu?.class_ ?? 0);
  setText("result-meta", `${raceName(raceId)} · ${className(classId)}${hiredArchetypeLabel(newWaifu) ? ` · ${hiredArchetypeLabel(newWaifu)}` : ""}`);
  const bioText =
    result?.bio ||
    newWaifu?.bio ||
    "Новая наёмница присоединилась к вашему отряду. Управляйте ею во вкладке «Отряд».";
  setText("result-bio-back", bioText);
  const statsEl = document.getElementById("result-hire-stats");
  if (statsEl) {
    statsEl.textContent = newWaifu
      ? `Ур. ${newWaifu.level ?? "—"} · CR ${hiredCr(newWaifu)}`
      : "—";
  }
  const perksEl = document.getElementById("result-perks");
  const perkIds = perkIdsCapped(newWaifu, 3);
  const perksMap = tavernState.perksMap || {};
  if (perksEl) {
    perksEl.innerHTML = perkIds.length
      ? perkIds.map((pid) => `<span class="perk-badge">${perksMap[pid] || pid}</span>`).join("")
      : "<span class=\"muted tiny\" style=\"opacity:.75;\">—</span>";
  }
  if (bg) {
    bg.classList.remove("hire-result-bg--placeholder");
    const url = result?.image_url || hiredWaifuImageUrl(newWaifu);
    if (url) {
      bg.style.backgroundImage = `url(${JSON.stringify(String(url))})`;
    } else {
      bg.style.backgroundImage = "none";
      bg.classList.add("hire-result-bg--placeholder");
    }
  }
  const modal = document.getElementById("modal-hire-result");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function closeTavernHireResult() {
  const modal = document.getElementById("modal-hire-result");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
  const flipInner = document.getElementById("hire-result-flip-inner");
  if (flipInner) flipInner.classList.remove("is-flipped");
  tavernState.lastHiredResult = null;
}

function goToSquadTab() {
  closeTavernHireResult();
  switchTavernTab("squad");
}

async function hireFromTavern(slot) {
  openTavernConfirmHire(slot);
}

/** Опыт до следующего уровня наёмницы (порт exp_to_next_level_hired). */
function expToNextForHiredLevel(level) {
  const lvl = Math.max(1, Number(level) || 1);
  const n = lvl - 1;
  return 50 + n * 50 + n * n * 5;
}

function hideTavernPerkTip(root) {
  const wrap = root || document.getElementById("tavern-waifu-modal-body");
  const tip = wrap?.querySelector?.("#tavern-perk-tip");
  if (tip) {
    tip.hidden = true;
    tip.classList.remove("tavern-perk-tip--open");
    tip.style.left = "";
    tip.style.top = "";
    tip.style.transform = "";
  }
}

function setTavernWaifuModalPageScrollLocked(locked) {
  if (document.body?.classList?.contains("page-tavern")) {
    document.body.classList.toggle("tavern-modal-scroll-lock", Boolean(locked));
  }
}

function openTavernWaifuModal(w, opts = {}) {
  tavernState.selectedWaifu = w || null;
  const m = document.getElementById("tavern-waifu-modal");
  const body = document.getElementById("tavern-waifu-modal-body");
  if (!m || !body || !w) return;
  const initialSeg = opts.seg || tavernState.modalSeg || "overview";

  const clsId = Number(w?.class ?? w?.class_ ?? w?.["class"]);
  const raceId = Number(w?.race);
  const rarity = Number(w?.rarity ?? 1);
  const rCls = rarityClass(rarity);
  const nm = String(w?.name || "Вайфу");
  const perksMap = tavernState.perksMap || {};
  const perkIds = perkIdsCapped(w, 3);
  const level = Number(w?.level ?? 1);
  const expInLevel = Math.max(0, Number(w?.expCurrent ?? w?.exp_current ?? 0));
  const expNeed = Math.max(
    1,
    Number(w?.expToNext ?? w?.exp_to_next ?? expToNextForHiredLevel(level))
  );
  const expPct = Math.min(100, Math.round((expInLevel / expNeed) * 100));
  const xpBarHtml =
    level >= 1 && level < 50
      ? `<div class="waifu-mtg-xp full-bar-row"><div class="full-bar-label"><span>Опыт</span><span>${expInLevel}/${expNeed}</span></div><div class="full-bar"><div class="full-bar-fill" style="width:${expPct}%;background:linear-gradient(90deg,#c8922a,#e8b84b);"></div></div></div>`
      : level >= 50
        ? `<div class="waifu-mtg-xp waifu-mtg-xp--max">Макс. уровень</div>`
        : "";
  const bioText = (w?.bio && String(w.bio).trim()) ? String(w.bio).trim() : "Биография не задана.";
  const arch = hiredArchetypeLabel(w);
  const stars = Number(w?.potentialStars ?? w?.potential_stars ?? 0);
  const typeBar = `${escapeHtml(raceName(raceId))} · ${escapeHtml(className(clsId))} · ${escapeHtml(rarityLabel(rarity))} · CR ${escapeHtml(String(hiredCr(w)))}${stars ? ` · ★${stars}` : ""}${arch ? ` · ${escapeHtml(arch)}` : ""}`;
  const imgUrl = hiredWaifuImageUrl(w, "full");
  const portraitInner = imgUrl
    ? `<img class="waifu-mtg-art-img" src="${escapeHtml(imgUrl)}" alt="" loading="lazy" decoding="async" />`
    : `<div class="waifu-mtg-art-placeholder" aria-hidden="true">${waifuPortraitEmoji(w)}</div>`;
  const adminArtBtn =
    typeof isAdminUiEnabled === "function" && isAdminUiEnabled() && Number(w?.id) > 0
      ? `<span class="hired-waifu-art-generate-btn" role="button" tabindex="0" data-waifu-id="${escapeHtml(String(w.id))}" title="Сгенерировать портрет (admin)" aria-label="Сгенерировать портрет наёмницы">${typeof ITEM_ART_GEN_SVG === "string" ? ITEM_ART_GEN_SVG : "🖼"}</span>`
      : "";

  const perkCells = perkIds.length
    ? perkIds
        .map((pid) => {
          const p = String(pid);
          const icon = PERK_ICONS[p] || "✦";
          const label = String(perksMap[p] || p);
          const ico =
            typeof perkIconHtml === "function"
              ? perkIconHtml(p, { className: "waifu-mtg-perk-ico-img", title: label })
              : `<span class="waifu-mtg-perk-ico" aria-hidden="true">${icon}</span>`;
          return `<button type="button" class="waifu-mtg-perk-cell" data-perk-id="${escapeHtml(p)}" aria-label="${escapeHtml(label)}">${ico}</button>`;
        })
        .join("")
    : `<div class="waifu-mtg-no-perks">Нет перков</div>`;

  const gearSlotHtml = (() => {
    const slots = [
      { key: "weapon", label: "Оружие", g: w.gear_weapon || w.gearWeapon },
      { key: "charm", label: "Амулет", g: w.gear_charm || w.gearCharm },
      { key: "relic", label: "Реликвия", g: w.gear_relic || w.gearRelic },
    ];
    const bag = tavernState.mercGearBag || [];
    return slots
      .map((s) => {
        const g = s.g && typeof s.g === "object" ? s.g : null;
        const title = g ? escapeHtml(g.name || s.label) : escapeHtml(s.label);
        const sub = g ? `score ${g.score ?? g.rarity ?? 0}` : "пусто";
        const bagOpts = bag
          .filter((it) => String(it?.slot || "") === s.key)
          .map(
            (it) =>
              `<option value="${escapeHtml(String(it.id))}">${escapeHtml(String(it.name || s.key))} · ${escapeHtml(String(it.score ?? 0))}</option>`
          )
          .join("");
        const equipCtl = g
          ? `<button type="button" class="tavern-btn tavern-btn-mini" data-gear-unequip="${s.key}">Снять</button>`
          : bagOpts
            ? `<div class="tavern-gear-bag-pick"><select data-gear-bag-select="${s.key}"><option value="">Из сумки…</option>${bagOpts}</select>
               <button type="button" class="tavern-btn tavern-btn-mini" data-gear-equip-bag="${s.key}">Экип</button></div>`
            : `<span class="muted tiny">Сумка пуста</span>`;
        return `<div class="tavern-gear-slot-oncard" data-gear-slot="${s.key}">
          <div><strong>${title}</strong></div>
          <div class="muted tiny">${sub}</div>
          ${equipCtl}
        </div>`;
      })
      .join("");
  })();

  const lineupGridHtml = (() => {
    const lu = tavernState.lineup || { atk: [null, null, null], def: [null, null, null] };
    const cell = (side, i) => {
      const id = lu[side]?.[i];
      const u = id ? findRosterWaifu(id) : null;
      const mine = u && Number(u.id) === Number(w.id);
      const label = u ? escapeHtml(String(u.name || `#${u.id}`).split(" ")[0]) : "—";
      return `<button type="button" class="tavern-modal-lineup-cell${mine ? " is-mine" : ""}" data-lineup-side="${side}" data-lineup-slot="${i + 1}">
        <span class="tiny muted">${side.toUpperCase()} ${i + 1}</span>
        <span class="ellip">${label}</span>
      </button>`;
    };
    return `<div class="tavern-modal-lineup-grid">
      ${[0, 1, 2].map((i) => cell("atk", i)).join("")}
      ${[0, 1, 2].map((i) => cell("def", i)).join("")}
    </div>
    <div class="tavern-waifu-lineup-actions" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;">
      <button type="button" class="tavern-btn tavern-btn-mini" id="tavern-btn-clear-lineup">Со скамейки</button>
    </div>`;
  })();

  const hard = perkHardCap(stars);
  const needNext = stars >= 5 ? 0 : STAR_FODDER_COST[stars + 1] || 0;
  const buildTrainHtml = () => {
    const catalog = tavernState.perksCatalog || {};
    const perkLevels = w.perkLevels || w.perk_levels || {};
    const trainPerkRows = perkIds
      .map((pid) => {
        const p = String(pid);
        const tip = typeof mercPerkTip === "function" ? mercPerkTip(p) : { name: perksMap[p] || p };
        const lv = Number(perkLevels[p] ?? 1);
        const meta = catalog[p] || {};
        const ptype = String(meta.type || meta.perk_type || meta.perkType || "ATK").toUpperCase();
        let prefer = null;
        for (let t = 1; t <= 3; t += 1) {
          if (lv < perkSoftCap(stars, t) && lv < hard) {
            prefer = t;
            break;
          }
        }
        const chips = [1, 2, 3]
          .map((t) => {
            const soft = perkSoftCap(stars, t);
            const blocked = lv >= soft || lv >= hard;
            const have = manualWalletCount(ptype, t);
            const active = prefer === t && !blocked;
            return `<button type="button" class="tavern-tier-chip${active ? " is-ready" : ""}" data-apply-perk="${escapeHtml(p)}" data-tier="${t}" ${blocked || have < 1 ? "disabled" : ""} title="${ptype} T${t} · soft ${soft}">T${t} (${have})</button>`;
          })
          .join("");
        return `<div class="tavern-train-perk-row">
          <div class="tavern-train-perk-meta"><strong>${escapeHtml(tip.name || p)}</strong> · ур. ${lv}/${hard} · ${ptype}</div>
          <div class="tavern-train-perk-actions">${chips}</div>
        </div>`;
      })
      .join("") || `<div class="muted tiny">Нет перков</div>`;
    return `<div class="tavern-train-stage">
      <div class="tavern-train-head">★ ${stars}/5 · CR ${escapeHtml(String(hiredCr(w)))} · XP ${expInLevel}/${expNeed}</div>
      <div class="tavern-train-potential">
        <div>Потенциал: до следующей ★ нужно <strong>${needNext || "—"}</strong> корма</div>
        <button type="button" class="tavern-btn tavern-btn-primary tavern-btn-mini" id="tavern-btn-quick-feed"${stars >= 5 ? " disabled" : ""}>Выбрать корм</button>
      </div>
      <div class="tavern-train-perks">${trainPerkRows}</div>
      <div class="tavern-manual-wallet">${formatManualWalletChips()}</div>
      <button type="button" class="tavern-btn tavern-btn-mini" id="tavern-btn-convert-manual">Конверт → T2 учебник</button>
    </div>`;
  };

  const portraitCard = (lowerOverlay, { flip = true } = {}) => {
    const tipBlock = flip
      ? `<div class="tavern-perk-tip" id="tavern-perk-tip" role="dialog" aria-modal="true" hidden>
                <div class="tavern-perk-tip-name" id="tavern-perk-tip-name"></div>
                <div class="tavern-perk-tip-desc" id="tavern-perk-tip-desc"></div>
                <div class="tavern-perk-tip-diff" id="tavern-perk-tip-diff"></div>
                <button type="button" class="tavern-perk-tip-close tavern-btn-mini">Понятно</button>
              </div>`
      : "";
    const front = `<div class="waifu-mtg-card ${rCls}">
            <div class="waifu-mtg-art${adminArtBtn ? " waifu-mtg-art--admin" : ""}">
              <span class="item-art-admin-wrap hired-waifu-art-admin-wrap">${portraitInner}${adminArtBtn}</span>
              <div class="waifu-mtg-art-scrim" aria-hidden="true"></div>
              <header class="waifu-mtg-header-row">
                <h2 class="waifu-mtg-name">${escapeHtml(nm)}</h2>
                <div class="waifu-mtg-lvl-badge" title="Уровень"><span class="waifu-mtg-lvl-num">${escapeHtml(String(level))}</span></div>
              </header>
              <div class="waifu-mtg-lower-overlay">${lowerOverlay}</div>
              ${tipBlock}
            </div>
          </div>`;
    if (!flip) return `<div class="waifu-mtg-flip-scene"><div class="waifu-mtg-face waifu-mtg-face--front">${front}</div></div>`;
    return `
    <div class="waifu-mtg-flip-scene">
      <div class="waifu-mtg-flip-inner" id="waifu-mtg-flip-inner">
        <div class="waifu-mtg-face waifu-mtg-face--front">${front}</div>
        <div class="waifu-mtg-face waifu-mtg-face--back">
          <div class="waifu-mtg-card ${rCls} waifu-mtg-card--backface">
            <div class="waifu-mtg-bio-back-head">
              <span class="waifu-mtg-bio-back-title">${escapeHtml(nm)}</span>
              <button type="button" class="waifu-mtg-bio-chip" data-flip-to="front">Перки</button>
            </div>
            <div class="waifu-mtg-bio-back-text"></div>
          </div>
        </div>
      </div>
    </div>`;
  };

  const overviewLower = `
    <div class="waifu-mtg-typebar">${typeBar}</div>
    <div class="waifu-mtg-perks-head">
      <span class="waifu-mtg-perks-label">Перки</span>
      <button type="button" class="waifu-mtg-bio-chip" data-flip-to="back">BIO</button>
    </div>
    <div class="waifu-mtg-perk-grid">${perkCells}</div>`;

  const gearLower = `
    <div class="waifu-mtg-typebar">${typeBar}</div>
    <div class="waifu-mtg-perks-head"><span class="waifu-mtg-perks-label">Шмот</span></div>
    <div class="waifu-mtg-gear-oncard">${gearSlotHtml}</div>`;

  body.innerHTML = `
    <div class="tavern-waifu-mtg-wrap">
      <div id="tavern-waifu-card-stage" data-mode="overview"></div>
      ${xpBarHtml}
      <div class="tavern-waifu-seg-tabs" id="tavern-waifu-seg-tabs" role="tablist">
        <button type="button" class="tavern-seg-tab" data-seg="overview" role="tab">Обзор</button>
        <button type="button" class="tavern-seg-tab" data-seg="gear" role="tab">Шмот</button>
        <button type="button" class="tavern-seg-tab" data-seg="lineup" role="tab">Состав</button>
        <button type="button" class="tavern-seg-tab" data-seg="train" role="tab">Прокачка</button>
      </div>
    </div>
  `;

  const stage = body.querySelector("#tavern-waifu-card-stage");

  const wirePortraitCommon = () => {
    const bioBack = body.querySelector(".waifu-mtg-bio-back-text");
    if (bioBack) bioBack.textContent = bioText;
    const flipInner = body.querySelector("#waifu-mtg-flip-inner");
    body.querySelectorAll("[data-flip-to]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        hideTavernPerkTip(body);
        const to = btn.getAttribute("data-flip-to");
        if (!flipInner) return;
        if (to === "back") flipInner.classList.add("is-flipped");
        else flipInner.classList.remove("is-flipped");
      });
    });
    const tipEl = body.querySelector("#tavern-perk-tip");
    const tipName = body.querySelector("#tavern-perk-tip-name");
    const tipDesc = body.querySelector("#tavern-perk-tip-desc");
    const tipDiff = body.querySelector("#tavern-perk-tip-diff");
    const tipClose = body.querySelector(".tavern-perk-tip-close");
    body.querySelectorAll(".waifu-mtg-perk-cell").forEach((cell) => {
      cell.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const pid = cell.getAttribute("data-perk-id") || "";
        if (!tipEl || !tipName || !tipDesc || !tipDiff) return;
        const tip = mercPerkTip(pid);
        tipName.textContent = tip.name;
        tipDesc.textContent = tip.flavor;
        tipDiff.textContent = tip.effect;
        tipEl.hidden = false;
        tipEl.classList.add("tavern-perk-tip--open");
      });
    });
    if (tipClose) {
      tipClose.addEventListener("click", (ev) => {
        ev.stopPropagation();
        hideTavernPerkTip(body);
      });
    }
    const backFace = body.querySelector(".waifu-mtg-face--back");
    if (backFace && flipInner) {
      backFace.addEventListener("click", () => {
        if (!flipInner.classList.contains("is-flipped")) return;
        hideTavernPerkTip(body);
        flipInner.classList.remove("is-flipped");
      });
    }
    const adminGenBtn = body.querySelector(".hired-waifu-art-generate-btn");
    if (adminGenBtn) {
      const activate = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        handleHiredWaifuArtGenerateClick(adminGenBtn);
      };
      adminGenBtn.addEventListener("click", activate);
      adminGenBtn.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") activate(ev);
      });
    }
  };

  const wireGearActions = () => {
    body.querySelectorAll("[data-gear-unequip]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const slot = btn.getAttribute("data-gear-unequip");
        try {
          const res = await apiFetch("/tavern/gear/equip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ waifu_id: w.id, slot, item: null }),
          });
          if (Array.isArray(res?.merc_gear_bag)) tavernState.mercGearBag = res.merc_gear_bag;
          showToast("Снято в сумку", "info");
          await refreshDrillManuals().catch(() => {});
          await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
          const fresh = findRosterWaifu(w.id) || { ...w, [`gear_${slot}`]: null };
          openTavernWaifuModal(fresh, { seg: "gear" });
          renderTavernInventoryTab();
        } catch (e) {
          const { detail } = parseHttpErrorDetail(e);
          showToast(detail || "Не удалось снять", "error");
        }
      });
    });
    body.querySelectorAll("[data-gear-equip-bag]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const slot = btn.getAttribute("data-gear-equip-bag");
        const sel = body.querySelector(`[data-gear-bag-select="${slot}"]`);
        const bagItemId = sel?.value;
        if (!bagItemId) {
          showToast("Выберите предмет из сумки", "error");
          return;
        }
        try {
          const res = await apiFetch("/tavern/gear/equip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ waifu_id: w.id, slot, bag_item_id: bagItemId }),
          });
          showToast("Экипировано", "info");
          await refreshDrillManuals();
          await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
          const fresh = findRosterWaifu(w.id) || { ...w, [`gear_${slot}`]: res.item };
          openTavernWaifuModal(fresh, { seg: "gear" });
        } catch (e) {
          const { detail } = parseHttpErrorDetail(e);
          showToast(detail || "Экип недоступен", "error");
        }
      });
    });
  };

  const wireLineupActions = () => {
    body.querySelectorAll("[data-lineup-side]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const side = btn.getAttribute("data-lineup-side");
        const slot = Number(btn.getAttribute("data-lineup-slot"));
        tavernSetLineup(side, slot, w.id);
      });
    });
    const clearBtn = body.querySelector("#tavern-btn-clear-lineup");
    if (clearBtn) {
      clearBtn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const atk = w?.atkSlot ?? w?.atk_slot;
        const def = w?.defSlot ?? w?.def_slot;
        if (atk != null) await tavernSetLineup("atk", Number(atk), null);
        if (def != null) await tavernSetLineup("def", Number(def), null);
      });
    }
  };

  const wireTrainActions = () => {
    const feedBtn = body.querySelector("#tavern-btn-quick-feed");
    if (feedBtn) {
      feedBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        tavernState.quickFeedMode = true;
        tavernState.quickFeedTargetId = Number(w.id);
        tavernState.fodderSelectedIds = [];
        closeTavernWaifuModal();
        switchTavernTab("squad");
        renderTavernSquad();
      });
    }
    body.querySelectorAll("[data-apply-perk]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const perkId = btn.getAttribute("data-apply-perk");
        const tier = Number(btn.getAttribute("data-tier") || 2);
        try {
          const res = await apiFetch("/tavern/apply-manual", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ waifu_id: w.id, perk_id: perkId, tier }),
          });
          if (res?.error) {
            showToast(res.hint || res.error, "error");
            return;
          }
          showToast(`Перк → ${res.level}`, "info");
          await refreshDrillManuals();
          await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
          const fresh = findRosterWaifu(w.id) || w;
          openTavernWaifuModal(fresh, { seg: "train" });
        } catch (e) {
          const { detail } = parseHttpErrorDetail(e);
          showToast(detail || "Не удалось применить", "error");
        }
      });
    });
    const conv = body.querySelector("#tavern-btn-convert-manual");
    if (conv) {
      conv.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        if (!window.confirm(`Конвертировать «${nm}» в T2 учебник? Наёмница исчезнет.`)) return;
        try {
          const res = await apiFetch("/tavern/convert-manual", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ waifu_id: w.id }),
          });
          if (res?.error) {
            showToast(res.hint || res.error, "error");
            return;
          }
          showToast(`+T2 ${res.manual_type || ""}`, "info");
          closeTavernWaifuModal();
          await refreshDrillManuals();
          await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
        } catch (e) {
          const { detail } = parseHttpErrorDetail(e);
          showToast(detail || "Конверт не удался", "error");
        }
      });
    }
  };

  const showSeg = (seg) => {
    const mode = ["overview", "gear", "lineup", "train"].includes(seg) ? seg : "overview";
    tavernState.modalSeg = mode;
    if (stage) stage.setAttribute("data-mode", mode);
    body.querySelectorAll("[data-seg]").forEach((b) => b.classList.toggle("active", b.getAttribute("data-seg") === mode));
    if (!stage) return;
    if (mode === "overview") {
      stage.innerHTML = portraitCard(overviewLower);
      wirePortraitCommon();
    } else if (mode === "gear") {
      stage.innerHTML = portraitCard(gearLower, { flip: false });
      wirePortraitCommon();
      wireGearActions();
    } else if (mode === "lineup") {
      stage.innerHTML = `<div class="tavern-modal-lineup-stage">${lineupGridHtml}</div>`;
      wireLineupActions();
    } else if (mode === "train") {
      stage.innerHTML = buildTrainHtml();
      wireTrainActions();
    }
  };

  body.querySelectorAll("[data-seg]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      showSeg(btn.getAttribute("data-seg"));
    });
  });

  const boot = async () => {
    if (initialSeg === "train" || initialSeg === "gear") await refreshDrillManuals();
    showSeg(initialSeg);
  };
  boot();

  setTavernWaifuModalPageScrollLocked(true);
  m.style.display = "grid";
}

function patchHiredWaifuImageUrlInState(waifuId, imageUrl) {
  const id = Number(waifuId);
  if (!Number.isFinite(id) || id < 1 || !imageUrl) return;
  const apply = (list) => {
    if (!Array.isArray(list)) return;
    for (const row of list) {
      if (Number(row?.id) === id) {
        row.imageUrl = imageUrl;
        row.image_url = imageUrl;
      }
    }
  };
  apply(tavernState.squad);
  apply(tavernState.reserve);
  if (Number(tavernState.selectedWaifu?.id) === id) {
    tavernState.selectedWaifu.imageUrl = imageUrl;
    tavernState.selectedWaifu.image_url = imageUrl;
  }
}

async function handleHiredWaifuArtGenerateClick(el) {
  if (!el || (typeof isAdminUser === "function" && !isAdminUser())) return;
  const waifuId = parseInt(el.getAttribute("data-waifu-id") || "", 10);
  if (!Number.isFinite(waifuId) || waifuId < 1) return;
  el.classList.add("is-loading");
  el.setAttribute("aria-busy", "true");
  if (typeof setItemArtGenBusy === "function") setItemArtGenBusy(true);
  try {
    const payload = await apiFetch(
      `/admin/hired-waifu-art/generate?waifu_id=${encodeURIComponent(waifuId)}`,
      { method: "POST" }
    );
    const newUrl = String(payload?.image_url || "").trim();
    if (!newUrl) throw new Error("no_image_url");
    patchHiredWaifuImageUrlInState(waifuId, newUrl);
    const wrap = el.closest(".hired-waifu-art-admin-wrap");
    let busted = newUrl;
    try {
      const u = new URL(newUrl, window.location.origin);
      u.searchParams.set("v", String(Date.now()));
      u.searchParams.set("variant", "full");
      busted = u.pathname + u.search;
    } catch {
      busted = `${newUrl.split("?")[0]}?variant=full&v=${Date.now()}`;
    }
    if (wrap) {
      wrap.innerHTML = `<img class="waifu-mtg-art-img" src="${escapeHtml(busted)}" alt="" loading="lazy" decoding="async" />${el.outerHTML}`;
      const btn = wrap.querySelector(".hired-waifu-art-generate-btn");
      if (btn) {
        btn.classList.remove("is-loading");
        btn.removeAttribute("aria-busy");
        const reactivate = (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          handleHiredWaifuArtGenerateClick(btn);
        };
        btn.addEventListener("click", reactivate);
        btn.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") reactivate(ev);
        });
      }
    }
    showToast("Портрет сохранён");
    renderTavernSquad();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Ошибка генерации портрета", "error");
  } finally {
    el.classList.remove("is-loading");
    el.removeAttribute("aria-busy");
    if (typeof setItemArtGenBusy === "function") setItemArtGenBusy(false);
  }
}

function closeTavernWaifuModal() {
  const body = document.getElementById("tavern-waifu-modal-body");
  hideTavernPerkTip(body);
  const flip = document.getElementById("waifu-mtg-flip-inner");
  if (flip) flip.classList.remove("is-flipped");
  const m = document.getElementById("tavern-waifu-modal");
  if (m) m.style.display = "none";
  setTavernWaifuModalPageScrollLocked(false);
  tavernState.selectedWaifu = null;
}

function closeTavernSlotModal() {
  const body = document.getElementById("tavern-slot-modal-body");
  if (body) {
    body.classList.remove("tavern-slot-modal-grid-body");
    body.innerHTML = "";
  }
  const m = document.getElementById("tavern-slot-modal");
  if (m) m.style.display = "none";
}

function openAddToSquadPicker(slotPosition) {
  const reserve = tavernState.reserve || [];
  if (reserve.length === 0) {
    switchTavernTab("hire");
    return;
  }
  tavernState.pendingSquadSlot = slotPosition;
  renderSquadPickerModal(reserve, slotPosition);
  const modal = document.getElementById("modal-squad-picker");
  if (modal) modal.classList.remove("hidden");
}

function closeSquadPickerModal() {
  const modal = document.getElementById("modal-squad-picker");
  if (modal) modal.classList.add("hidden");
  tavernState.pendingSquadSlot = null;
}

function renderSquadPickerModal(available, slotPosition) {
  const listEl = document.getElementById("squad-picker-list");
  const subEl = document.querySelector("#modal-squad-picker .modal-subtitle");
  if (subEl) subEl.textContent = `Выберите наёмницу из запаса для слота #${slotPosition}`;
  if (!listEl) return;
  const perksMap = tavernState.perksMap || {};
  listEl.innerHTML = available.map((u) => {
    const { cur, max: hpMax } = hiredWaifuHp(u);
    const hpPct = hpMax > 0 ? Math.round((cur / hpMax) * 100) : 100;
    const statusOk = cur > 0;
    const clsId = Number(u?.class ?? u?.class_ ?? 0);
    const perkPips = (u.perks || [])
      .slice(0, 3)
      .map((pid) => {
        const tip =
          (typeof perkFlavorRu === "function" ? perkFlavorRu(pid) : null) ||
          PERK_FLAVOR?.[pid] ||
          PERK_DESCS?.[pid] ||
          "";
        const shortName = (perksMap[pid] || (typeof perkNameRu === "function" ? perkNameRu(pid) : pid) || "?")
          .toString()
          .split(" ")[0];
        return `<span class="perk-pip" title="${escapeHtml(tip)}">${escapeHtml(shortName)}</span>`;
      })
      .join("");
    return `
      <div class="squad-picker-card ${statusOk ? "" : "squad-picker-card--weak"}" data-waifu-id="${u.id}" role="button" tabindex="0">
        <div class="squad-picker-icon">${waifuPortraitEmoji(u)}</div>
        <div class="squad-picker-info">
          <div class="squad-picker-name">${String(u?.name || "Вайфу")}</div>
          <div class="squad-picker-meta">${className(clsId)} · Ур.${u?.level ?? "—"}</div>
          <div class="squad-picker-bars">
            <div class="mini-bar" style="width:80px"><div class="mini-bar-fill hp" style="width:${hpPct}%"></div></div>
          </div>
        </div>
        <div class="squad-picker-perks">${perkPips}</div>
      </div>`;
  }).join("");
  listEl.querySelectorAll(".squad-picker-card").forEach((card) => {
    const waifuId = Number(card.dataset.waifuId);
    card.addEventListener("click", () => pickForSquad(waifuId));
  });
}

async function pickForSquad(waifuId) {
  const slot = tavernState.pendingSquadSlot;
  if (!slot || !waifuId) return;
  try {
    await apiFetch(`/tavern/squad/add?waifu_id=${encodeURIComponent(waifuId)}&slot=${encodeURIComponent(slot)}`, { method: "POST" });
    closeSquadPickerModal();
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true }).catch(() => {});
    renderTavernSquad();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showTavernError(detail || "Ошибка добавления в отряд", "danger");
  }
}

function openTavernSlotModal(w) {
  const m = document.getElementById("tavern-slot-modal");
  const body = document.getElementById("tavern-slot-modal-body");
  if (!m || !body || !w) return;

  const subtitle = document.getElementById("tavern-slot-modal-subtitle");
  if (subtitle) subtitle.textContent = `Поставить в слот: ${w?.name || "—"}`;

  const squadByPos = new Map();
  (tavernState.squad || []).forEach((x) => {
    const pos = Number(x?.squad_position);
    if (Number.isFinite(pos) && pos >= 1 && pos <= 6) squadByPos.set(pos, x);
  });

  body.innerHTML = "";
  body.classList.add("tavern-slot-modal-grid-body");

  const grid = document.createElement("div");
  grid.className = "tavern-slot-pick-grid";
  for (let pos = 1; pos <= 6; pos += 1) {
    const cur = squadByPos.get(pos) || null;
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "tavern-slot-pick-cell" + (cur ? " tavern-slot-pick-cell--filled" : " tavern-slot-pick-cell--empty");
    const url = cur?.image_url ? String(cur.image_url) : "";
    const portraitHtml = cur
      ? url
        ? `<img class="tavern-slot-pick-img" src="${escapeHtml(url)}" alt="" />`
        : `<span class="tavern-slot-pick-emoji">${waifuPortraitEmoji(cur)}</span>`
      : `<span class="tavern-slot-pick-plus" aria-hidden="true">＋</span>`;
    const nameLine = cur ? escapeHtml(String(cur.name || "—")) : "Свободно";
    const hint = cur
      ? `<span class="tavern-slot-pick-hint">Заменит слот → в запас</span>`
      : `<span class="tavern-slot-pick-hint">Пустой слот</span>`;
    cell.innerHTML = `
      <span class="tavern-slot-pick-num">#${pos}</span>
      <div class="tavern-slot-pick-portrait">${portraitHtml}</div>
      <div class="tavern-slot-pick-name">${nameLine}</div>
      ${hint}
    `;
    cell.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      try {
        await apiFetch(`/tavern/squad/add?waifu_id=${encodeURIComponent(w.id)}&slot=${encodeURIComponent(pos)}`, {
          method: "POST",
        });
        closeTavernSlotModal();
        closeTavernWaifuModal();
        await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true }).catch(() => {});
      } catch (e) {
        const { detail } = parseHttpErrorDetail(e);
        showTavernError(detail || "Ошибка формирования отряда", "danger");
        closeTavernSlotModal();
      }
    });
    grid.appendChild(cell);
  }
  body.appendChild(grid);

  m.style.display = "grid";
}

function openTavernDismissConfirm() {
  const w = tavernState.selectedWaifu;
  if (!w?.id) return;
  const nm = String(w?.name || "наёмницу").trim() || "наёмницу";
  const textEl = document.getElementById("confirm-dismiss-text");
  if (textEl) textEl.textContent = `Уволить «${nm}»?`;
  const modal = document.getElementById("modal-confirm-dismiss");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function closeTavernDismissConfirm() {
  const modal = document.getElementById("modal-confirm-dismiss");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

async function confirmTavernDismiss() {
  const w = tavernState.selectedWaifu;
  if (!w?.id) return;
  const btn = document.getElementById("btn-confirm-dismiss");
  if (btn?.dataset.dismissing === "1") return;
  if (btn) btn.dataset.dismissing = "1";
  try {
    const res = await apiFetch(`/tavern/dismiss?waifu_id=${encodeURIComponent(w.id)}`, { method: "POST" });
    if (!res?.success) throw new Error(res?.hint || res?.error || "dismiss_failed");
    closeTavernDismissConfirm();
    closeTavernWaifuModal();
    tavernState.selectedWaifu = null;
    try {
      await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
      renderTavernHealList();
      renderTavernUpgradeList();
      showToast(res.hint || "Наёмница уволена");
    } catch (refreshErr) {
      showToast("Наёмница уволена, но не удалось обновить список", "error");
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Ошибка увольнения", "error");
  } finally {
    if (btn) delete btn.dataset.dismissing;
  }
}

function dismissTavernWaifu() {
  openTavernDismissConfirm();
}

/** Кнопка 🔄 (admin-only): принудительное обновление слотов найма. */
async function refreshTavernPage() {
  await adminRefreshTavern();
}

async function adminRefreshTavern() {
  showTavernError("");
  try {
    const response = await apiFetch(`/admin/tavern/refresh`, { method: "POST" });
    tavernState.available = response;
    tavernState.perksMap = buildTavernPerksMap(response);
    renderTavernHire({ act: tavernState.act }, response);
    await loadProfile().catch(() => {});
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true }).catch(() => {});
    showTavernError("Слоты найма обновлены.", "info");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showTavernError(detail || "Ошибка обновления слотов", "danger");
  }
}

async function loadMercStatusPity() {
  try {
    const st = await apiFetch("/tavern/merc-status");
    if (st?.drill_manuals) tavernState.drillManuals = st.drill_manuals;
    let bar = document.getElementById("tavern-pity-meter");
    if (!bar) {
      const hire = document.getElementById("tab-hire");
      if (!hire) return;
      bar = document.createElement("div");
      bar.id = "tavern-pity-meter";
      bar.style.cssText = "padding:8px 4px;font-size:12px;opacity:.9;";
      hire.insertBefore(bar, hire.firstChild);
    }
    const pl = st.pity_legendary ?? 0;
    const hard = st.pity_legendary_hard ?? 50;
    bar.innerHTML = `Легендарный контракт: <b>${pl}/${hard}</b>` +
      (st.debut_legendary_done ? "" : ` · <button type="button" class="tavern-btn" onclick="WaifuApp.openDebutLegendary && WaifuApp.openDebutLegendary()">Выбрать легенду</button>`);
    if (!st.debut_legendary_done && st.debut_options?.length) {
      window.__debutOptions = st.debut_options;
    }
  } catch (_) {}
}

async function openDebutLegendary() {
  const opts = window.__debutOptions || [];
  if (!opts.length) {
    try {
      const st = await apiFetch("/tavern/merc-status");
      window.__debutOptions = st.debut_options || [];
    } catch (_) {}
  }
  const list = window.__debutOptions || [];
  if (!list.length) {
    showToast("Debut недоступен", "error");
    return;
  }
  const labels = list.map((o, i) => `${i + 1}. ${o.name}`).join("\n");
  const raw = window.prompt(`Выберите легенду (1–${list.length}):\n${labels}`, "1");
  if (raw == null) return;
  const idx = Math.max(0, Math.min(list.length - 1, (parseInt(raw, 10) || 1) - 1));
  const pick = list[idx];
  try {
    await apiFetch("/tavern/debut-legendary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template_id: pick.id }),
    });
    showToast(`Легенда: ${pick.name}`, "info");
    await loadMercStatusPity();
    await ensureTavernRosterLoaded().catch(() => {});
    renderTavernSquad();
  } catch (e) {
    showToast("Не удалось взять легенду", "error");
  }
}

function _rosterNameById(id) {
  if (id == null) return "—";
  const all = [...(tavernState.squad || []), ...(tavernState.reserve || [])];
  const w = all.find((x) => Number(x.id) === Number(id));
  return w?.name ? String(w.name) : `#${id}`;
}

async function renderTavernLineupBars() {
  try {
    const lu = await apiFetch("/tavern/lineup");
    tavernState.lineup = {
      atk: Array.isArray(lu?.atk) ? lu.atk : [null, null, null],
      def: Array.isArray(lu?.def) ? lu.def : [null, null, null],
    };
    // sync local atk/def slots onto roster for bench filtering
    const byId = rosterByIdMap();
    allRosterWaifus().forEach((w) => {
      w.atk_slot = null;
      w.def_slot = null;
      w.atkSlot = null;
      w.defSlot = null;
    });
    (tavernState.lineup.atk || []).forEach((id, i) => {
      const w = byId[Number(id)];
      if (w) {
        w.atk_slot = i + 1;
        w.atkSlot = i + 1;
      }
    });
    (tavernState.lineup.def || []).forEach((id, i) => {
      const w = byId[Number(id)];
      if (w) {
        w.def_slot = i + 1;
        w.defSlot = i + 1;
      }
    });
    renderTavernLineupRowsFromState();
  } catch (e) {
    const { detail, status } = parseHttpErrorDetail(e);
    if (status === 404) {
      showToast("Lineup API недоступен — задеплойте сервер", "error");
    } else if (detail) {
      showToast(detail, "error");
    }
  }
}

async function tavernSetLineup(side, slot, waifuId) {
  try {
    const res = await apiFetch("/tavern/lineup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ side, slot, waifu_id: waifuId }),
    });
    if (res?.error) {
      showToast(res.hint || res.error, "error");
      return;
    }
    closeTavernWaifuModal();
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
    await renderTavernLineupBars();
    renderTavernSquad();
  } catch (e) {
    const { detail, status } = parseHttpErrorDetail(e);
    if (status === 404) {
      showToast("Сервер без /tavern/lineup — нужен деплой merc-overhaul", "error");
    } else {
      showToast(detail || "Не удалось назначить слот", "error");
    }
  }
}

async function copyAtkToDef() {
  const atk = tavernState.lineup?.atk || [null, null, null];
  try {
    for (let i = 0; i < 3; i += 1) {
      const res = await apiFetch("/tavern/lineup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ side: "def", slot: i + 1, waifu_id: atk[i] ?? null }),
      });
      if (res?.error) throw new Error(res.hint || res.error);
    }
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
    await renderTavernLineupBars();
    renderTavernSquad();
  } catch (e) {
    const { detail, status } = parseHttpErrorDetail(e);
    showToast(status === 404 ? "Нужен деплой /tavern/lineup" : detail || "Не удалось скопировать", "error");
  }
}

async function tavernQuickFeedApply(targetId, fodderIdOrIds) {
  const ids = Array.isArray(fodderIdOrIds) ? fodderIdOrIds : [fodderIdOrIds];
  try {
    const res = await apiFetch("/tavern/fodder-stars", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_id: targetId, fodder_ids: ids.map(Number) }),
    });
    if (res?.error) {
      showToast(res.hint || res.error, "error");
      return;
    }
    tavernState.quickFeedMode = false;
    tavernState.quickFeedTargetId = null;
    tavernState.fodderSelectedIds = [];
    showToast(`★${res.potential_stars ?? res.stars ?? ""}`, "info");
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Quick Feed не удался", "error");
  }
}

function closeArenaResult() {
  const modal = document.getElementById("modal-arena-result");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function openArenaResult(res) {
  const body = document.getElementById("tavern-arena-result-body");
  const modal = document.getElementById("modal-arena-result");
  if (!body || !modal) {
    console.info("arena result", res);
    return;
  }
  const win = res.winner === "attacker" ? "Победа" : "Поражение";
  const lines = (res.log || []).slice(0, 8).join("\n");
  body.textContent = `${win} (${res.rating_delta > 0 ? "+" : ""}${res.rating_delta})\n\n${lines}`;
  modal.classList.remove("hidden");
  modal.style.display = "flex";
}

function wireArenaSearchInput() {
  const input = document.getElementById("tavern-arena-search");
  if (!input || input.dataset.wired) return;
  input.dataset.wired = "1";
  input.value = tavernState.arenaSearchQ || "";
  input.addEventListener("input", () => {
    tavernState.arenaSearchQ = input.value || "";
    if (tavernState.arenaSearchTimer) clearTimeout(tavernState.arenaSearchTimer);
    tavernState.arenaSearchTimer = setTimeout(() => {
      loadArenaOpponentsList().catch(() => {});
    }, 280);
  });
}

function renderArenaOpponentsList(opponents, { searching = false } = {}) {
  const opp = document.getElementById("tavern-arena-opponents");
  if (!opp) return;
  const list = opponents || [];
  if (!list.length) {
    opp.innerHTML = `<div class="placeholder muted">${searching ? "Никого не найдено" : "Нет соперников"}</div>`;
    return;
  }
  const rows = list
    .map(
      (o) => `<div class="tavern-arena-opp">
        <span class="tavern-arena-opp-name">${escapeHtml(arenaOpponentLabel(o))}</span>
        <span class="tavern-arena-opp-rating">${escapeHtml(String(o.rating ?? "—"))}</span>
        <button type="button" class="tavern-btn tavern-btn-primary" onclick="WaifuApp.tavernArenaAttack(${o.player_id || "null"}, ${o.bot ? "true" : "false"})">Атака</button>
      </div>`
    )
    .join("");
  opp.innerHTML = `<div class="tavern-arena-opp-head"><span>Игрок</span><span style="text-align:right">Рейт</span><span></span></div>${rows}`;
}

async function loadArenaOpponentsList() {
  const opp = document.getElementById("tavern-arena-opponents");
  if (!opp) return;
  const q = String(tavernState.arenaSearchQ || "").trim();
  const url = q ? `/arena/opponents?q=${encodeURIComponent(q)}` : "/arena/opponents";
  const { opponents } = await apiFetch(url);
  renderArenaOpponentsList(opponents, { searching: Boolean(q) });
}

async function renderTavernArena() {
  const header = document.getElementById("tavern-arena-header");
  const opp = document.getElementById("tavern-arena-opponents");
  const hist = document.getElementById("tavern-arena-history");
  const defRow = document.getElementById("tavern-arena-def");
  if (!header || !opp) return;
  wireArenaSearchInput();
  header.textContent = "Загрузка арены…";
  opp.innerHTML = `<div class="placeholder muted">Загрузка соперников…</div>`;
  try {
    await ensureMercPerksCatalog().catch(() => {});
    await ensureTavernRosterLoaded().catch(() => {});
    await renderTavernLineupBars().catch(() => {});
    const st = await apiFetch("/arena/status");
    header.textContent = st.unlocked
      ? `Рейтинг ${st.arena_rating} · Тикеты ${st.arena_tickets}/${st.tickets_daily ?? 5}`
      : `Арена откроется с акта ${st.unlock_act}`;
    if (defRow) {
      const defs = tavernState.lineup?.def || [null, null, null];
      defRow.innerHTML = "";
      for (let i = 0; i < 3; i += 1) {
        defRow.appendChild(renderLineupSlotEl("def", i + 1, defs[i], { fromArena: true }));
      }
    }
    if (!st.unlocked) {
      opp.innerHTML = `<div class="placeholder muted">Доступно с акта ${st.unlock_act}. Rest не блокирует атаку.</div>`;
      if (hist) hist.innerHTML = "";
      return;
    }
    await loadArenaOpponentsList();
    try {
      const h = await apiFetch("/arena/history?limit=5");
      if (hist) {
        hist.innerHTML =
          "<div style='margin-bottom:6px;opacity:.7;'>История</div>" +
          ((h.matches || []).length
            ? (h.matches || [])
                .map(
                  (m) =>
                    `<div>${m.winner === "attacker" ? "W" : "L"} ${m.rating_delta > 0 ? "+" : ""}${m.rating_delta}</div>`
                )
                .join("")
            : "<div class='muted tiny'>Пока пусто</div>");
      }
    } catch (_) {
      if (hist) hist.innerHTML = "";
    }
  } catch (e) {
    const { detail, status } = parseHttpErrorDetail(e);
    header.textContent = "Арена недоступна";
    opp.innerHTML = `<div class="placeholder muted">${escapeHtml(status === 404 ? "API арены не задеплоен" : detail || "Ошибка загрузки")}</div>`;
    showToast(detail || "Ошибка арены", "error");
  }
}

async function tavernArenaAttack(defenderId, bot) {
  try {
    const res = await apiFetch("/arena/attack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ defender_id: defenderId, bot: !!bot }),
    });
    openArenaResult(res);
    await renderTavernArena();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Атака не удалась", "error");
  }
}

async function renderTavernExchange() {
  const wallet = document.getElementById("tavern-exchange-wallet");
  const list = document.getElementById("tavern-exchange-list");
  const data = await apiFetch("/tavern/exchange");
  if (data?.wallet?.drill_manuals) {
    tavernState.drillManuals = data.wallet.drill_manuals;
  }
  if (Array.isArray(data?.wallet?.merc_gear_bag)) {
    tavernState.mercGearBag = data.wallet.merc_gear_bag;
  }
  if (wallet) {
    const w = data.wallet || {};
    const bagN = (w.merc_gear_bag || tavernState.mercGearBag || []).length;
    wallet.innerHTML = `${mercCoinIcon()} ${Number(w.merc_coins || 0)} · Contracts ${Number(w.merc_contracts || 0)} · Dust ${Number(w.merc_dust || 0)} · Bag ${bagN}
      <div class="tavern-manual-wallet" style="margin-top:6px;">${formatManualWalletChips()}</div>`;
  }
  if (!list) return;
  const items = data.items || [];
  tavernState.exchangeItems = items;
  if (!items.length) {
    list.innerHTML = `<div class="placeholder muted">Пусто</div>`;
    return;
  }
  list.innerHTML = `<div class="tavern-exchange-grid">${items
    .map((it) => {
      const id = String(it.id || "");
      const icon = String(it.icon || "📦");
      const cost = Number(it.cost_coins ?? 0);
      return `<button type="button" class="tavern-exchange-card" data-exchange-id="${escapeHtml(id)}" aria-label="${escapeHtml(String(it.name || id))}">
        <div class="tavern-exchange-art" aria-hidden="true">${escapeHtml(icon)}</div>
        <div class="tavern-exchange-price">${mercCoinIcon()} ${escapeHtml(String(cost))}</div>
      </button>`;
    })
    .join("")}</div>`;
  list.querySelectorAll("[data-exchange-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openTavernExchangeItemModal(btn.getAttribute("data-exchange-id"));
    });
  });
}

function openTavernExchangeItemModal(itemId) {
  const item = (tavernState.exchangeItems || []).find((x) => String(x.id) === String(itemId));
  if (!item) return;
  tavernState.exchangeSelectedId = String(item.id);
  const modal = document.getElementById("modal-exchange-item");
  const art = document.getElementById("exchange-item-art");
  const title = document.getElementById("exchange-item-title");
  const desc = document.getElementById("exchange-item-desc");
  const cost = document.getElementById("exchange-item-cost");
  const buyBtn = document.getElementById("exchange-item-buy-btn");
  if (art) art.textContent = String(item.icon || "📦");
  if (title) title.textContent = String(item.name || item.id);
  if (desc) desc.textContent = String(item.description || "Товар обмена за Merc Coins.");
  if (cost) cost.innerHTML = `${mercCoinIcon()} ${Number(item.cost_coins ?? 0)}`;
  if (buyBtn) {
    buyBtn.disabled = false;
    buyBtn.onclick = () => tavernExchangeBuy(String(item.id));
  }
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function closeTavernExchangeItemModal() {
  tavernState.exchangeSelectedId = null;
  const modal = document.getElementById("modal-exchange-item");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

const EXCHANGE_HELP_HTML = `
  <h4>Merc Coins (MC)</h4>
  <p>Основная валюта обмена. Добывается за завершённые <strong>операции</strong> (недельная доска). Здесь тратится на расходники и лут.</p>
  <h4>Контракты найма</h4>
  <p>Один контракт = один найм без золота. Удобно копить с Ops и тратить в пики найма.</p>
  <h4>Пыль и потенциал ★</h4>
  <p>Пыль нужна для прокачки потенциала наёмниц. Выше ★ — выше потолок уровней перков и сильнее юнит.</p>
  <h4>Учебники ATK / DEF / SUP</h4>
  <p><strong>T1 заметки</strong>, <strong>T2 учебники</strong>, <strong>T3 доктрины</strong> — расходники для уровней перков в карточке наёмницы. Тип должен совпадать с перком (ATK/DEF/SUP). Часть T1 можно конвертировать в T2 в карточке.</p>
  <h4>Ящики снаряжения</h4>
  <p>Случайный экип (weapon / charm / relic) нужного тира попадает в <strong>сумку</strong>. Надевается из инвентаря/карточки наёмницы и повышает CR.</p>
  <h4>Тикеты арены</h4>
  <p>Тратятся на атаку в async-арене 3v3. Можно купить здесь или получать по дневному лимиту.</p>
  <h4>Как покупать</h4>
  <p>Тап по иконке товара → описание и кнопка «Купить». На сетке показывается только цена поверх арта.</p>
`;

function openTavernExchangeHelp() {
  const body = document.getElementById("exchange-help-body");
  if (body) body.innerHTML = EXCHANGE_HELP_HTML;
  const modal = document.getElementById("modal-exchange-help");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function closeTavernExchangeHelp() {
  const modal = document.getElementById("modal-exchange-help");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

async function tavernExchangeBuy(itemId) {
  const buyBtn = document.getElementById("exchange-item-buy-btn");
  if (buyBtn) buyBtn.disabled = true;
  try {
    const res = await apiFetch("/tavern/exchange/buy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_id: itemId }),
    });
    if (res?.item) {
      showToast(`${res.item.name || "Предмет"} · T${res.item.tier || "?"} → сумка`, "info");
      if (Array.isArray(res.merc_gear_bag)) tavernState.mercGearBag = res.merc_gear_bag;
    } else {
      showToast("Куплено", "success");
    }
    if (res?.wallet?.drill_manuals) tavernState.drillManuals = res.wallet.drill_manuals;
    if (Array.isArray(res?.wallet?.merc_gear_bag)) tavernState.mercGearBag = res.wallet.merc_gear_bag;
    closeTavernExchangeItemModal();
    await renderTavernExchange();
  } catch (_) {
    showToast("Не хватает монет", "error");
    if (buyBtn) buyBtn.disabled = false;
  }
}

async function openTavernCodex() {
  const data = await apiFetch("/tavern/codex");
  const lines = (data.legendaries || [])
    .map((l) => (l.unlocked ? `★ ${l.name}` : `☆ ???`))
    .join("\n");
  window.alert("Кодекс легенд\n\n" + lines);
}

Object.assign(window.WaifuApp, {
  loadTavern,
  loadTavernWithProfile,
  switchTavernTab,
  onTavernHirePrimaryClick,
  toggleHireResultFlip,
  hireFromTavern,
  openTavernConfirmHire,
  closeTavernConfirmHire,
  confirmTavernHire,
  closeTavernHireResult,
  goToSquadTab,
  openTavernWaifuModal,
  closeTavernWaifuModal,
  openTavernDismissConfirm,
  closeTavernDismissConfirm,
  confirmTavernDismiss,
  dismissTavernWaifu,
  closeTavernSlotModal,
  openAddToSquadPicker,
  closeSquadPickerModal,
  pickForSquad,
  openDebutLegendary,
  renderTavernArena,
  tavernArenaAttack,
  closeArenaResult,
  copyAtkToDef,
  renderTavernExchange,
  tavernExchangeBuy,
  openTavernExchangeItemModal,
  closeTavernExchangeItemModal,
  openTavernExchangeHelp,
  closeTavernExchangeHelp,
  openTavernCodex,
  loadMercStatusPity,
  tavernSetLineup,
  tavernQuickFeedApply,
  adminRefreshTavern,
  refreshTavernPage,
  toggleTavernBgmMuted,
  openTavernBgmPlayer,
  closeTavernBgmPlayer,
  onTavernBgmModalBackdropClick,
  openTavernBgmPlaylistPicker,
  closeTavernBgmPlaylistPicker,
  onTavernBgmPlaylistPickerBackdropClick,
  selectTavernBgmPlaylistFromPicker,
  openTavernBgmPlaylistTabFromPicker,
  switchTavernBgmModalTab,
  onTavernBgmVolumeChange,
  toggleTavernBgmVolumeOverlay,
  seekTavernBgmProgress,
  onTavernBgmPlaylistSelectChange,
  onTavernBgmAddChatChange,
  onTavernBgmAddPlaylistChange,
  addTrackToTavernBgmPlaylist,
  removeTrackFromTavernBgmPlaylist,
  renameTavernBgmPlaylist,
  deleteTavernBgmPlaylist,
  createTavernBgmPlaylistFromTab,
  openTavernBgmUploadPicker,
  onTavernBgmUploadSelected,
  toggleTavernBgmPlayPause,
  playTavernBgm,
  pauseTavernBgm,
  nextTavernBgmTrack,
  prevTavernBgmTrack,
  toggleTavernBgmShuffle,
  cycleTavernBgmRepeat,
});
