// Basic Telegram WebApp bootstrap + shared UI helpers + API/SSE wiring
const tg = window.Telegram?.WebApp;
const API_BASE = "/api";

function applyTheme() {
  const scheme = tg?.colorScheme || "dark";
  document.documentElement.classList.remove("theme-light", "theme-dark");
  document.documentElement.classList.add(scheme === "light" ? "theme-light" : "theme-dark");
}

function setActiveNav(page) {
  document.querySelectorAll(".nav a").forEach((link) => {
    if (link.dataset.page === page) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
}

function getInitData() {
  const fromTelegram = tg?.initData || tg?.initDataUnsafe?.query_id ? tg.initData : null;
  const fromQuery = new URLSearchParams(window.location.search).get("initData");
  return fromTelegram || fromQuery || "";
}

function authHeaders() {
  const initData = getInitData();
  const headers = {};
  if (initData) headers["X-Telegram-Init-Data"] = initData;
  return headers;
}

async function apiFetch(path, options = {}) {
  const opts = { ...options };
  opts.headers = { ...(options.headers || {}), ...authHeaders() };
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text || "failed"}`);
  }
  if (res.status === 204) return null;
  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (ct.includes("application/json")) return res.json();
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setHTML(id, value) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = value;
}

const STAT_META = {
  strength: { icon: "💪", short: "СИЛ" },
  agility: { icon: "🎯", short: "ЛОВ" },
  intelligence: { icon: "🧠", short: "ИНТ" },
  endurance: { icon: "🛡️", short: "ВЫН" },
  charm: { icon: "🎭", short: "ОБА" },
  luck: { icon: "🍀", short: "УДЧ" },
  hp_flat: { icon: "❤️", short: "HP" },
  hp_percent: { icon: "❤️", short: "HP" },
  defense_flat: { icon: "🛡️", short: "DEF" },
  defense_percent: { icon: "🛡️", short: "DEF" },
  crit_chance_flat: { icon: "🎯", short: "CRIT" },
  crit_chance_percent: { icon: "🎯", short: "CRIT" },
  merchant_discount_flat: { icon: "🪙", short: "СКИДКА" },
  merchant_discount_percent: { icon: "🪙", short: "СКИДКА" },
  melee_damage_flat: { icon: "⚔️", short: "DMG" },
  ranged_damage_flat: { icon: "🏹", short: "DMG" },
  magic_damage_flat: { icon: "🪄", short: "DMG" },
  damage_flat: { icon: "⚔️", short: "DMG" },
  damage_percent: { icon: "⚔️", short: "DMG" },
};

function statMeta(stat) {
  const key = String(stat || "").trim();
  return STAT_META[key] || { icon: "✨", short: key || "—" };
}

function formatBonusValue(stat, value) {
  const v = safeNumber(value, 0);
  const isPercent =
    String(stat || "").endsWith("_percent") ||
    String(stat || "").includes("chance_percent") ||
    String(stat || "").endsWith("_pct");
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v}${isPercent ? "%" : ""}`;
}

function bonusClass(value) {
  const v = safeNumber(value, 0);
  if (v > 0) return "bonus-pos";
  if (v < 0) return "bonus-neg";
  return "bonus-zero";
}

function classIcon(classId) {
  const id = Number(classId);
  // ids are aligned with WAIFU_CLASSES
  return (
    {
      1: "🛡️", // Рыцарь
      2: "⚔️", // Воин
      3: "🏹", // Лучник
      4: "🪄", // Маг
      5: "🗡️", // Ассасин
      6: "⚕️", // Хилер
      7: "💰", // Торговец
    }[id] || "🎭"
  );
}

function raceIcon(raceId) {
  const id = Number(raceId);
  // ids are aligned with WAIFU_RACES
  return (
    {
      1: "🧑", // Человек
      2: "🧝", // Эльф
      3: "🐺", // Зверолюд
      4: "😇", // Ангел
      5: "🧛", // Вампир
      6: "😈", // Демон
      7: "🧚", // Фея
    }[id] || "🧬"
  );
}

const PROFILE_STAT_ORDER = ["strength", "agility", "intelligence", "endurance", "charm", "luck"];

const PROFILE_STAT_LABELS = {
  strength: "Сила",
  agility: "Ловкость",
  intelligence: "Интеллект",
  endurance: "Выносливость",
  charm: "Обаяние",
  luck: "Удача",
};

const PROFILE_STAT_TOOLTIPS = {
  strength: "Увеличивает урон ближнего боя, запас HP и силу критических атак.",
  agility: "Повышает урон дальнего боя, шанс уклонения и шанс критической атаки.",
  intelligence: "Усиливает магический урон, активные навыки и бонус к получаемому опыту.",
  endurance: "Даёт больше максимального HP, снижает входящий урон и повышает максимум энергии.",
  charm: "Улучшает торговлю и снижает стоимость найма и тренировок.",
  luck: "Повышает шанс критов, шанс добычи предметов и количество золота с монстров.",
};

function profileStatValue(waifu, statKey) {
  return safeNumber(waifu?.[statKey], 0);
}

function profileStatBase(waifu, statKey) {
  return safeNumber(waifu?.[`base_${statKey}`], 10);
}

function profileStatEquipmentBonus(waifu, statKey) {
  return safeNumber(waifu?.[`bonus_${statKey}`], 0);
}

function profileStatRaceBonus(waifu, statKey) {
  return safeNumber(WAIFU_RACE_BONUSES?.[Number(waifu?.race)]?.[statKey], 0);
}

function profileStatClassBonus(waifu, statKey) {
  return safeNumber(WAIFU_CLASS_BONUSES?.[Number(waifu?.class ?? waifu?.class_)]?.[statKey], 0);
}

function profileDamageRange(score) {
  const base = Math.max(0, safeNumber(score, 0));
  const min = Math.max(0, Math.floor(base * 0.9));
  const max = Math.max(min, Math.ceil(base * 1.1));
  return `${min}–${max}`;
}

function profileFormatPercent(value, digits = 1) {
  const num = safeNumber(value, 0);
  const fixed = Number(num.toFixed(digits));
  return `${fixed}%`;
}

function getProfileIndicators(waifu, details = null) {
  const d = details || profileState?.currentDetails || null;
  const endurance = profileStatValue(waifu, "endurance");
  const charm = profileStatValue(waifu, "charm");
  const luck = profileStatValue(waifu, "luck");
  const intelligence = profileStatValue(waifu, "intelligence");

  const hpMax = safeNumber(d?.hp_max ?? waifu?.max_hp, 0);
  const melee = safeNumber(d?.melee_damage, 0);
  const ranged = safeNumber(d?.ranged_damage, 0);
  const magic = safeNumber(d?.magic_damage, 0);
  const crit = safeNumber(d?.crit_chance, 0);
  const dodge = safeNumber(d?.dodge_chance, 0);
  const merchantDiscount = safeNumber(d?.merchant_discount, 0);
  const buyMultiplier = Math.max(0.5, 1 - merchantDiscount / 100);
  const sellMultiplier = Math.min(0.9, 0.5 + merchantDiscount / 125);
  const expBonus = intelligence * 0.5;
  const goldBonus = luck * 0.4;
  const energyMax = safeNumber(waifu?.max_energy, 0);
  const energyRegenHour = 60;
  const incomingReduction = Math.min(60, endurance * 0.3);

  return {
    hpMax,
    meleeRange: profileDamageRange(melee),
    rangedRange: profileDamageRange(ranged),
    magicRange: profileDamageRange(magic),
    critChance: profileFormatPercent(crit, 2),
    dodgeChance: profileFormatPercent(dodge, 2),
    expBonus: profileFormatPercent(expBonus, 1),
    goldBonus: profileFormatPercent(goldBonus, 1),
    merchant: `${charm} · покупка ${Math.round(buyMultiplier * 100)}% · продажа ${Math.round(sellMultiplier * 100)}%`,
    energy: `${energyMax} · реген ${energyRegenHour}/час`,
    incomingReduction: profileFormatPercent(incomingReduction, 1),
  };
}

function profileStatBonusLines(statKey, waifu, details = null) {
  const total = profileStatValue(waifu, statKey);
  const indicators = getProfileIndicators(waifu, details);
  switch (statKey) {
    case "strength":
      return [
        `+${total} к урону ближнего боя`,
        `+${total * 5} к HP`,
        `+${total * 2}% к урону критических атак`,
      ];
    case "agility":
      return [
        `+${total} к урону дальнего боя`,
        `+${profileFormatPercent(total * 0.2, 1)} к шансу уклонения`,
        `+${profileFormatPercent(total * 0.4, 1)} к шансу критической атаки`,
      ];
    case "intelligence":
      return [
        `+${total} к урону магических атак`,
        `+${total * 2} к урону активных навыков`,
        `+${profileFormatPercent(total * 0.5, 1)} к получаемому опыту`,
      ];
    case "endurance":
      return [
        `+${total * 10} к максимальному HP`,
        `-${profileFormatPercent(total * 0.3, 1)} к получаемому урону`,
        `+${total} к максимальной энергии`,
      ];
    case "charm":
      return [
        `+${total} к Торговле`,
        `-${profileFormatPercent(Math.max(0, (total - 10) * 0.5), 1)} к стоимости найма`,
        `-${profileFormatPercent(Math.max(0, (total - 10) * 0.35), 1)} к стоимости тренировок`,
      ];
    case "luck":
      return [
        `+${profileFormatPercent(total * 0.2, 1)} к шансу критической атаки`,
        `+${profileFormatPercent(total * 0.5, 1)} к шансу выпадения предметов`,
        `+${profileFormatPercent(total * 0.4, 1)} к золоту с монстров`,
      ];
    default:
      return [indicators.incomingReduction];
  }
}

function profileStatSources(waifu, statKey) {
  const total = profileStatValue(waifu, statKey);
  const base = 10;
  const race = profileStatRaceBonus(waifu, statKey);
  const cls = profileStatClassBonus(waifu, statKey);
  const equipment = profileStatEquipmentBonus(waifu, statKey);
  const other = total - base - race - cls - equipment;
  return { base, race, classBonus: cls, equipment, other, total };
}

function renderStatsStrip(targetId, waifu) {
  const box = document.getElementById(targetId);
  if (!box || !waifu) return;
  box.innerHTML = PROFILE_STAT_ORDER.map((statKey) => {
    const meta = statMeta(statKey);
    const isOpen = profileState?.activeTooltipStat === statKey;
    const label = PROFILE_STAT_LABELS[statKey] || meta.short;
    return `
      <button class="profile-stat-row ${isOpen ? "active" : ""}" type="button" onclick="WaifuApp.toggleProfileStatTooltip('${statKey}')">
        <div class="profile-stat-row-main">
          <span class="profile-stat-row-left">
            <span class="profile-stat-icon" aria-hidden="true">${meta.icon}</span>
            <span>${label}</span>
          </span>
          <strong>${profileStatValue(waifu, statKey)}</strong>
        </div>
        <div class="profile-stat-tooltip">${PROFILE_STAT_TOOLTIPS[statKey] || "Описание характеристики появится позже."}</div>
      </button>
    `;
  }).join("");
}

function renderStatsBreakdown(targetId, waifu, details = null) {
  const box = document.getElementById(targetId);
  if (!box || !waifu) return;

  const pts = safeNumber(waifu?.stat_points, 0);
  const ptsEl = document.getElementById("profile-stat-points");
  if (ptsEl) ptsEl.textContent = `ОХ: ${pts}`;

  box.innerHTML = PROFILE_STAT_ORDER.map((statKey) => {
    const meta = statMeta(statKey);
    const label = PROFILE_STAT_LABELS[statKey] || meta.short;
    const sources = profileStatSources(waifu, statKey);
    const bonusLines = profileStatBonusLines(statKey, waifu, details);
    const isOpen = profileState?.activeAccordion === statKey;
    const plusDisabled = pts <= 0 ? "disabled" : "";

    return `
      <div class="profile-accordion ${isOpen ? "active" : ""}">
        <button class="profile-accordion-head" type="button" onclick="WaifuApp.toggleProfileStatAccordion('${statKey}')">
          <span class="profile-accordion-head-left">
            <span class="profile-stat-icon" aria-hidden="true">${meta.icon}</span>
            <span>${meta.short} - ${label}</span>
          </span>
          <span style="display:inline-flex; align-items:center; gap:10px;">
            <strong class="profile-accordion-total">${sources.total}</strong>
            <span class="profile-accordion-arrow">${isOpen ? "▲" : "▼"}</span>
          </span>
        </button>
        <div class="profile-accordion-body">
          <div class="profile-accordion-section">
            <div class="muted tiny">Источники</div>
            <div class="profile-accordion-sources">
              <div class="profile-accordion-row"><span>База</span><strong>${sources.base}</strong></div>
              <div class="profile-accordion-row"><span>Раса</span><strong>${sources.race >= 0 ? `+${sources.race}` : sources.race}</strong></div>
              <div class="profile-accordion-row"><span>Класс</span><strong>${sources.classBonus >= 0 ? `+${sources.classBonus}` : sources.classBonus}</strong></div>
              <div class="profile-accordion-row"><span>Экипировка</span><strong>${sources.equipment >= 0 ? `+${sources.equipment}` : sources.equipment}</strong></div>
              <div class="profile-accordion-row"><span>Навыки</span><strong>${sources.other >= 0 ? `+${sources.other}` : sources.other}</strong></div>
              <div class="profile-accordion-row"><span>Итого</span><strong>${sources.total}</strong></div>
            </div>
            <div style="display:flex; justify-content:flex-end; margin-top:2px;">
              <button class="stat-plus-btn" ${plusDisabled} title="Потратить 1 ОХ" onclick="event.stopPropagation(); WaifuApp.spendStatPoint('${statKey}')">+</button>
            </div>
          </div>
          <div class="profile-accordion-section">
            <div class="muted tiny">Бонусы от значения</div>
            <div class="profile-bonus-list">
              ${bonusLines.map((line) => `<div class="profile-bonus-item">${line}</div>`).join("")}
            </div>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

async function spendStatPoint(statKey) {
  const key = String(statKey || "").trim().toLowerCase();
  if (!key) return;
  try {
    await apiFetch(`/waifu/stats/spend?stat=${encodeURIComponent(key)}`, { method: "POST" });
  } catch (e) {
    console.warn("spendStatPoint failed:", e);
    return;
  }
  // Refresh profile to update stats/points and derived details.
  const p = await loadProfile().catch(() => null);
  if (p) await populateProfile(p).catch(() => {});
}

function safeNumber(n, fallback = 0) {
  const v = Number(n);
  return Number.isFinite(v) ? v : fallback;
}

function clamp01(x) {
  return Math.max(0, Math.min(1, x));
}

function expForLevel(level) {
  const lvl = Number(level);
  if (!Number.isFinite(lvl) || lvl <= 1) return 0;
  return Math.floor(50 * Math.pow(lvl, 2));
}

function totalExpForLevel(level) {
  const lvl = Number(level);
  if (!Number.isFinite(lvl) || lvl <= 1) return 0;
  let total = 0;
  for (let l = 2; l <= lvl; l += 1) total += expForLevel(l);
  return total;
}

// ── Attic (ОЧ) renderers ─────────────────────────────────────────────────────

/** Update the active-dungeon chip in the shared ОЧ header. */
function renderAtticDungeon(active) {
  const chip = document.getElementById("attic-dungeon-chip");
  const label = document.getElementById("attic-dungeon-label");
  if (!chip || !label) return;
  if (active?.active) {
    const hpPct = active.monster_max_hp > 0
      ? Math.round((active.monster_current_hp / active.monster_max_hp) * 100)
      : 0;
    label.textContent = `${active.dungeon_name || "Бой"} · ${hpPct}%`;
    chip.classList.remove("chip-ghost");
    chip.classList.add("chip-active");
  } else {
    label.textContent = "Нет боя";
    chip.classList.add("chip-ghost");
    chip.classList.remove("chip-active");
  }
}

/** Update the expeditions chip in the shared ОЧ header. */
function renderAtticExpeditions(expeditions) {
  const chip = document.getElementById("attic-expedition-chip");
  const label = document.getElementById("attic-expedition-label");
  if (!chip || !label) return;
  const list = Array.isArray(expeditions) ? expeditions : [];
  const claimable = list.filter((e) => e?.completed);
  const running = list.filter((e) => e?.active && !e?.completed);
  if (claimable.length) {
    label.textContent = `${claimable.length} ★`;
    chip.classList.remove("chip-ghost");
    chip.classList.add("chip-active");
  } else if (running.length) {
    label.textContent = `${running.length}`;
    chip.classList.remove("chip-ghost");
    chip.classList.add("chip-active");
  } else {
    label.textContent = "";
    chip.classList.add("chip-ghost");
    chip.classList.remove("chip-active");
  }
}

/** Fire-and-forget refresh of both dynamic ОЧ chips (dungeon + expeditions). */
function refreshAtticChips() {
  apiFetch("/dungeons/active").then(renderAtticDungeon).catch(() => {});
  apiFetch("/expeditions/active")
    .then((r) => renderAtticExpeditions(r?.active ?? []))
    .catch(() => {});
}

// ─────────────────────────────────────────────────────────────────────────────

function populateFromProfile(profile) {
  if (!profile) return;

  // Shared ОЧ badges — populated on every page that has these IDs in its DOM
  if (profile.act != null) setText("badge-act", profile.act);
  if (profile.gold != null) setText("badge-gold", profile.gold);

  const w = profile.main_waifu;
  if (w) {
    if (w.level != null) setText("badge-level", w.level);
    if (w.energy != null && w.max_energy != null) setText("badge-energy", `${w.energy}/${w.max_energy}`);

    // Legacy IDs kept for back-compat (silently skipped when not in DOM)
    if (w.name) setText("waifu-name", w.name);
    if (w.name) setText("profile-name", w.name);
    if (w.level != null) setText("profile-level", w.level);
    if (w.energy != null && w.max_energy != null) setText("profile-energy", `${w.energy}/${w.max_energy}`);

    const clsId = Number(w.class_ ?? w.class);
    const raceId = Number(w.race);
    const clsEl = document.getElementById("profile-class-icon");
    if (clsEl) {
      clsEl.textContent = classIcon(clsId);
      clsEl.title = className(clsId);
    }
    const raceEl = document.getElementById("profile-race-icon");
    if (raceEl) {
      raceEl.textContent = raceIcon(raceId);
      raceEl.title = raceName(raceId);
    }

    // XP progress — profile tab bar + ОЧ mini-bar (attic-xp-fill)
    if (w.level != null && w.experience != null) {
      const lvl = Number(w.level);
      const xp = Number(w.experience);
      const nextTotal = totalExpForLevel(lvl + 1);
      const curTotal = totalExpForLevel(lvl);
      const span = Math.max(1, nextTotal - curTotal);
      const into = Math.max(0, xp - curTotal);
      const pct = Math.round(clamp01(into / span) * 100);
      setText("profile-xp-text", `${xp} / ${nextTotal}`);
      const fill = document.getElementById("profile-xp-fill");
      if (fill) fill.style.width = `${pct}%`;
      const atticFill = document.getElementById("attic-xp-fill");
      if (atticFill) atticFill.style.width = `${pct}%`;
    }
  }

  // Async: update dynamic ОЧ chips on every page load/refresh
  refreshAtticChips();
}

function appendEvent(text) {
  const log = document.getElementById("event-log");
  if (log) {
    const div = document.createElement("div");
    const ts = new Date().toLocaleTimeString();
    div.textContent = `[${ts}] ${text}`;
    log.prepend(div);
  } else {
    console.debug("[SSE]", text);
  }
}

let sse;
let dungeonPlusStatusById = {};
let selectedPlusLevel = 0;

// Ensure global namespace exists before any assignments below (SSE handlers, plus selector, etc.)
window.WaifuApp = window.WaifuApp || {};
function connectSSE() {
  const initData = getInitData();
  if (!initData) return;
  if (sse) sse.close();
  const url = `${API_BASE}/sse/stream?initData=${encodeURIComponent(initData)}`;
  sse = new EventSource(url);
  sse.onmessage = (ev) => {
    const data = ev?.data;
    if (typeof data === "string") {
      try {
        const obj = JSON.parse(data);
        if (obj && typeof window.WaifuApp?.onSseEvent === "function") {
          window.WaifuApp.onSseEvent(obj);
          return;
        }
      } catch {
        // ignore JSON errors
      }
    }
    appendEvent(data);
  };
  sse.onerror = () => {
    appendEvent("SSE connection lost, retrying...");
    setTimeout(connectSSE, 3000);
  };
}

const WAIFU_RACES = [
  { id: 1, name: "Человек" },
  { id: 2, name: "Эльф" },
  { id: 3, name: "Зверолюд" },
  { id: 4, name: "Ангел" },
  { id: 5, name: "Вампир" },
  { id: 6, name: "Демон" },
  { id: 7, name: "Фея" },
];

const WAIFU_CLASSES = [
  { id: 1, name: "Рыцарь" },
  { id: 2, name: "Воин" },
  { id: 3, name: "Лучник" },
  { id: 4, name: "Маг" },
  { id: 5, name: "Ассасин" },
  { id: 6, name: "Хилер" },
  { id: 7, name: "Торговец" },
];

const WAIFU_RACE_BONUSES = {
  1: {},
  2: { agility: 2, intelligence: 2, luck: 1 },
  3: { strength: 2, agility: 2, endurance: 1 },
  4: { charm: 2, intelligence: 1, luck: 1 },
  5: { strength: 1, endurance: 2, charm: 1, luck: 1 },
  6: { strength: 2, intelligence: 1, luck: 1 },
  7: { agility: 2, charm: 2, luck: 2 },
};

const WAIFU_CLASS_BONUSES = {
  1: { strength: 2, endurance: 2 },
  2: { strength: 2, agility: 1, endurance: 1 },
  3: { agility: 3, luck: 1 },
  4: { intelligence: 3, luck: 1 },
  5: { agility: 2, strength: 1, luck: 1 },
  6: { intelligence: 2, charm: 2 },
  7: { charm: 2, luck: 2 },
};

const profileState = {
  selectedSlot: null,
  selectedItem: null,
  equipSlotChoice: null,
  equippedBySlot: {},
  currentProfile: null,
  currentDetails: null,
  inventory: [],
  viewMode: "expanded",
  inventoryPage: 1,
  inventorySort: "equipability",
  inventorySortDir: "desc",
  inventoryFilters: { weapon: true, armor: true, accessory: true },
  activeTooltipStat: null,
  activeAccordion: null,
  infoTab: "indicators",
  sellConfirm: false,
};

const EQUIPMENT_SLOT_NAMES = {
  1: "Оружие 1",
  2: "Оружие 2",
  3: "Костюм",
  4: "Кольцо 1",
  5: "Кольцо 2",
  6: "Амулет",
};

const SLOT_TYPE_TO_SLOTS = {
  weapon_1h: [1, 2],
  weapon_2h: [1, 2],
  offhand: [2],
  costume: [3],
  ring: [4, 5],
  amulet: [6],
};

const PROFILE_SLOT_LAYOUT = {
  left: [1, 3, 4],
  right: [2, 6, 5],
};

function readProfileInventoryMode() {
  try {
    return sessionStorage.getItem("profileInventoryMode") === "compact" ? "compact" : "expanded";
  } catch {
    return "expanded";
  }
}

function writeProfileInventoryMode(mode) {
  try {
    sessionStorage.setItem("profileInventoryMode", mode === "compact" ? "compact" : "expanded");
  } catch {
    // ignore unavailable storage
  }
}

function getProfileBagCapacity(level) {
  const lvl = safeNumber(level, 1);
  if (lvl >= 40) return { pages: 6, cells: 72 };
  if (lvl >= 30) return { pages: 5, cells: 60 };
  if (lvl >= 20) return { pages: 4, cells: 48 };
  if (lvl >= 10) return { pages: 3, cells: 36 };
  return { pages: 2, cells: 24 };
}

function getProfileBagPageSize() {
  return profileState.viewMode === "compact" ? 24 : 12;
}

function getProfileItemCategory(item) {
  const slotType = String(item?.slot_type || "").toLowerCase();
  if (slotType.includes("weapon")) return "weapon";
  if (slotType.includes("costume") || slotType.includes("armor") || slotType.includes("offhand")) return "armor";
  if (slotType.includes("ring") || slotType.includes("amulet")) return "accessory";
  return "accessory";
}

function getProfileStatBonusTotal(item) {
  let total = 0;
  if (item?.base_stat_value != null) total += Math.abs(safeNumber(item.base_stat_value, 0));
  (item?.affixes || []).forEach((affix) => {
    total += Math.abs(safeNumber(affix?.value, 0));
  });
  return total;
}

function getProfileEquippedItem(slot) {
  const direct = profileState.equippedBySlot?.[Number(slot)] || null;
  if (direct) return direct;
  const weapon1 = profileState.equippedBySlot?.[1];
  if (Number(slot) === 2 && weapon1?.slot_type === "weapon_2h") return weapon1;
  return null;
}

function isProfileUpgradeItem(item) {
  const slotType = String(item?.slot_type || "").toLowerCase();
  const lvl = safeNumber(item?.level, 0);
  if (!slotType || lvl <= 0) return false;
  const slots = SLOT_TYPE_TO_SLOTS[slotType] || [];
  const equippedLevels = slots
    .map((slot) => safeNumber(getProfileEquippedItem(slot)?.level, 0))
    .filter((value) => value > 0);
  if (!equippedLevels.length) return false;
  if (slotType === "weapon_2h") return lvl > Math.max(...equippedLevels);
  return lvl > Math.min(...equippedLevels);
}

function compareProfileInventoryItems(a, b) {
  const sortKey = profileState.inventorySort || "equipability";
  const dir = profileState.inventorySortDir === "asc" ? 1 : -1;

  const rarityA = safeNumber(a?.rarity, 1);
  const rarityB = safeNumber(b?.rarity, 1);
  const levelA = safeNumber(a?.level, 0);
  const levelB = safeNumber(b?.level, 0);
  const equipA = a?.can_equip === false ? 0 : 1;
  const equipB = b?.can_equip === false ? 0 : 1;

  let result = 0;
  if (sortKey === "level") result = levelA - levelB || rarityA - rarityB;
  if (sortKey === "rarity") result = rarityA - rarityB || levelA - levelB;
  if (sortKey === "equipability") result = equipA - equipB || levelA - levelB || rarityA - rarityB;
  if (result === 0) {
    const nameA = String(a?.display_name || a?.name || "").toLowerCase();
    const nameB = String(b?.display_name || b?.name || "").toLowerCase();
    result = nameA.localeCompare(nameB, "ru");
  }
  return result * dir;
}

const shopState = {
  act: 1,
  offers: [],
  selectedSlot: null,
  selectedOffer: null,
  sellSelected: new Set(),
};

const ADMIN_USER_ID = 305174198;

function isAdminUser() {
  try {
    const u = tg?.initDataUnsafe?.user;
    return u && Number(u.id) === ADMIN_USER_ID;
  } catch {
    return false;
  }
}

async function loadProfile() {
  const initData = getInitData();
  const qs = initData ? `?initData=${encodeURIComponent(initData)}` : "";
  const profile = await apiFetch(`/profile${qs}`);
  populateFromProfile(profile);
  return profile;
}

async function bootstrapPage(page, afterLoad) {
  await initPage(page);
  let profile = null;
  try {
    profile = await loadProfile();
  } catch (err) {
    console.error("Failed to load profile:", err);
  }

  if (typeof afterLoad === "function") {
    try {
      await afterLoad(profile || { act: 1 });
    } catch (err) {
      console.error("Failed to bootstrap page:", err);
    }
  }

  return profile;
}

async function loadShop(act) {
  const data = await apiFetch(`/shop/inventory?act=${act}`);
  shopState.act = act;
  shopState.offers = Array.isArray(data?.items) ? data.items : [];

  const grid = document.getElementById("shop-items");
  if (!grid) return data;

  grid.classList.remove("placeholder");
  grid.innerHTML = "";

  // Render exactly 9 slots if possible (3x3), else render whatever came back.
  const offers = shopState.offers;
  const bySlot = new Map();
  offers.forEach((o, idx) => {
    const slot = Number(o.slot || o.offer_slot || o.shop_slot || idx + 1);
    if (!Number.isFinite(slot)) return;
    bySlot.set(slot, { ...o, __slot: slot });
  });

  const slots = [];
  for (let s = 1; s <= 9; s += 1) {
    slots.push(bySlot.get(s) || null);
  }

  slots.forEach((offer, idx) => {
    const slot = idx + 1;
    const card = document.createElement("div");
    const isSold = Boolean(offer?.sold);
    const rarityClass =
      offer?.rarity === 2
        ? "rarity-uncommon"
        : offer?.rarity === 3
          ? "rarity-rare"
          : offer?.rarity === 4
            ? "rarity-epic"
            : offer?.rarity === 5
              ? "rarity-legendary"
              : "rarity-common";

    const isEmpty = !offer || isSold;
    card.className = `item-card ${isEmpty ? "empty" : ""} ${rarityClass}`.trim();
    card.dataset.slot = String(slot);
    const nm = String(offer?.display_name || offer?.name || "").trim() || (isSold ? "Продано" : `Слот ${slot}`);
    const iconHtml = offer ? itemArtHtml(offer) : "🎁";
    card.innerHTML = `
      <div class="item-icon">${iconHtml}</div>
      <div class="item-level">${offer && !isSold ? `lvl ${offer.level ?? "?"}` : "—"}</div>
      ${offer?.price != null && !isSold ? `<div class="item-price">🪙 ${offer.price}</div>` : ""}
      <div class="item-name">${nm}</div>
    `;
    card.title = offer ? `${nm} (слот ${slot})` : `Пусто (слот ${slot})`;
    card.onclick = () => {
      if (!offer || isSold) return;
      openShopOffer(slot);
      // visual selection
      grid.querySelectorAll(".item-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
    };
    grid.appendChild(card);
  });

  return data;
}

async function loadTavern(profile) {
  const p = profile || (await loadProfile().catch(() => null));
  return loadTavernWithProfile(p || { act: 1 });
}

const tavernState = {
  act: 1,
  available: null,
  squad: [],
  reserve: [],
  selectedWaifu: null,
  selectedContext: null, // "reserve" | "squad"
};

const expeditionState = {
  slots: [],
  active: [],
  squad: [],
  waifus: [],
  selectedSlot: null,
  selectedDuration: 60,
  selectedWaifus: new Set(),
  selectedSquadIds: [],
  durationMinutes: 60,
};

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

function switchTavernTab(name) {
  document.querySelectorAll(".tavern-tabs .tab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  ["hire", "squad"].forEach((t) => {
    const panel = document.getElementById(`tab-${t}`);
    if (!panel) return;
    const isActive = t === name;
    panel.classList.toggle("active", isActive);
    panel.style.display = isActive ? "" : "none";
  });
}

async function loadTavernWithProfile(profile) {
  const p = profile || (await loadProfile());
  tavernState.act = Number(p?.act || 1);

  const [available, squadRes, reserveRes] = await Promise.all([
    apiFetch("/tavern/available"),
    apiFetch("/tavern/squad"),
    apiFetch("/tavern/reserve"),
  ]);

  tavernState.available = available;
  tavernState.squad = Array.isArray(squadRes?.squad) ? squadRes.squad : [];
  tavernState.reserve = Array.isArray(reserveRes?.reserve) ? reserveRes.reserve : [];

  renderTavernHire(p, available);
  renderTavernSquad();
  return { available, squad: tavernState.squad, reserve: tavernState.reserve };
}

function renderTavernHire(profile, available) {
  const act = Number(profile?.act || tavernState.act || 1);
  const scene = document.getElementById("tavern-scene");
  if (scene) {
    ["act-1", "act-2", "act-3", "act-4", "act-5"].forEach((c) => scene.classList.remove(c));
    scene.classList.add(`act-${Math.max(1, Math.min(5, act))}`);
  }

  const total = Number(available?.total ?? 4);
  const remaining = Number(available?.remaining ?? 0);
  setText("tavern-count", `${remaining}/${total}`);

  const squadCount = Array.isArray(tavernState.squad) ? tavernState.squad.length : 0;
  setText("tavern-squad-count", `${squadCount}/6`);

  const price = Number(available?.price ?? 10000);
  for (let i = 1; i <= 4; i += 1) {
    const slotEl = document.getElementById(`tavern-slot-${i}`);
    const priceEl = document.getElementById(`tavern-price-${i}`);
    if (priceEl) priceEl.textContent = `🪙 ${price}`;
    const slotObj = (available?.slots || []).find((s) => Number(s?.slot) === i);
    const isAvail = slotObj ? Boolean(slotObj.available) : false;
    if (slotEl) {
      // Per spec: hired slot disappears
      slotEl.style.display = isAvail ? "" : "none";
      slotEl.disabled = !isAvail;
    }
  }
}

function waifuPortraitEmoji(w) {
  const race = raceIcon(w?.race);
  const cls = classIcon(w?.class ?? w?.class_ ?? w?.["class"]);
  return `${race}${cls}`;
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
          <div class="pill"><span class="muted">Мощь</span><strong>—</strong></div>
          <div class="pill"><span class="muted">Перки</span><strong>—</strong></div>
        </div>
      </div>
    `;
  }

  const clsId = Number(w?.class ?? w?.class_ ?? w?.["class"]);
  const raceId = Number(w?.race);
  const rarity = Number(w?.rarity ?? 1);
  const lvl = w?.level ?? "—";
  const pos = w?.squad_position != null ? Number(w.squad_position) : null;
  const tag = pos != null ? `#${pos}` : "запас";
  const nm = String(w?.name || "Вайфу");
  const sub = `lvl ${lvl} · ${rarityLabel(rarity)} · ${className(clsId)} / ${raceName(raceId)}`;
  const extra = String(opts?.extraClass || "").trim();
  const cls = `${"tavern-waifu-card"}${extra ? ` ${extra}` : ""}`;
  const power = w?.power ?? "—";
  const perksCount = Array.isArray(w?.perks) ? w.perks.length : 0;
  return `
    <div class="${cls}">
      <div class="tavern-waifu-head">
        <div style="display:flex; gap:10px; align-items:center; min-width:0;">
          <div class="tavern-portrait" aria-hidden="true">${waifuPortraitEmoji(w)}</div>
          <div style="min-width:0;">
            <div class="tavern-waifu-name">${nm}</div>
            <div class="tavern-waifu-sub">${sub}</div>
          </div>
        </div>
        <div class="tag">${tag}</div>
      </div>
      <div class="tavern-mini-stats">
        <div class="pill"><span class="muted">Мощь</span><strong>${power}</strong></div>
        <div class="pill"><span class="muted">Перки</span><strong>${perksCount}</strong></div>
      </div>
    </div>
  `;
}

function renderTavernSquad() {
  const box = document.getElementById("tavern-squad-grid");
  if (!box) return;

  const squadByPos = new Map();
  (tavernState.squad || []).forEach((w) => {
    const pos = Number(w?.squad_position);
    if (Number.isFinite(pos) && pos >= 1 && pos <= 6) squadByPos.set(pos, w);
  });

  box.innerHTML = "";
  for (let pos = 1; pos <= 6; pos += 1) {
    const w = squadByPos.get(pos) || null;
    const wrap = document.createElement("div");
    wrap.innerHTML = renderWaifuCardHtml(w);
    const card = wrap.firstElementChild;
    if (card) {
      card.onclick = () => {
        if (!w) return;
        openTavernWaifuModal(w, "squad");
      };
      box.appendChild(card);
    }
  }

  const reserve = document.getElementById("tavern-reserve");
  if (!reserve) return;
  const items = Array.isArray(tavernState.reserve) ? tavernState.reserve : [];
  if (!items.length) {
    reserve.innerHTML = `<div class="muted">Запас пуст.</div>`;
    return;
  }
  reserve.innerHTML = "";
  items.forEach((w) => {
    const wrap = document.createElement("div");
    wrap.innerHTML = renderWaifuCardHtml(w, { extraClass: "tavern-reserve-card" });
    const card = wrap.firstElementChild;
    if (card) {
      card.onclick = () => openTavernWaifuModal(w, "reserve");
      reserve.appendChild(card);
    }
  });
}

async function hireFromTavern(slot) {
  showTavernError("");
  const id = Number(slot || 0);
  if (!Number.isFinite(id) || id < 1 || id > 4) return;
  const btn = document.getElementById(`tavern-slot-${id}`);
  if (btn) btn.disabled = true;
  try {
    await apiFetch(`/tavern/hire?slot=${encodeURIComponent(id)}`, { method: "POST" });
    await loadProfile().catch(() => {});
    await loadTavernWithProfile({ act: tavernState.act }).catch(() => {});
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showTavernError(detail || "Ошибка найма", "danger");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openTavernWaifuModal(w, context) {
  tavernState.selectedWaifu = w || null;
  tavernState.selectedContext = context || null;
  const m = document.getElementById("tavern-waifu-modal");
  const body = document.getElementById("tavern-waifu-modal-body");
  if (!m || !body || !w) return;

  const clsId = Number(w?.class ?? w?.class_ ?? w?.["class"]);
  const raceId = Number(w?.race);
  const rarity = Number(w?.rarity ?? 1);
  setText("tavern-waifu-modal-title", String(w?.name || "Вайфу"));
  setText(
    "tavern-waifu-modal-subtitle",
    `lvl ${w?.level ?? "—"} · ${rarityLabel(rarity)} · ${className(clsId)} / ${raceName(raceId)}`
  );

  body.innerHTML = `
    <div class="detail-row"><span class="muted">Портрет</span><strong>${waifuPortraitEmoji(w)}</strong></div>
    <div class="details-grid" style="margin-top:0;">
      <div class="detail-row"><span class="muted">Мощь</span><strong>${w?.power ?? "—"}</strong></div>
      <div class="detail-row"><span class="muted">Перки</span><strong>${Array.isArray(w?.perks) && w.perks.length ? w.perks.join(", ") : "—"}</strong></div>
    </div>
  `;

  const action = document.getElementById("tavern-waifu-modal-action");
  if (action) {
    if (context === "reserve") {
      action.textContent = "В отряд";
      action.style.display = "";
    } else if (context === "squad") {
      action.textContent = "В запас";
      action.style.display = "";
    } else {
      action.style.display = "none";
    }
  }

  m.style.display = "grid";
}

function closeTavernWaifuModal() {
  const m = document.getElementById("tavern-waifu-modal");
  if (m) m.style.display = "none";
  tavernState.selectedWaifu = null;
  tavernState.selectedContext = null;
}

function closeTavernSlotModal() {
  const m = document.getElementById("tavern-slot-modal");
  if (m) m.style.display = "none";
}

function openTavernSlotModal(w) {
  const m = document.getElementById("tavern-slot-modal");
  const body = document.getElementById("tavern-slot-modal-body");
  if (!m || !body || !w) return;

  const subtitle = document.getElementById("tavern-slot-modal-subtitle");
  if (subtitle) subtitle.textContent = `Кого ставим: ${w?.name || "—"}`;

  const squadByPos = new Map();
  (tavernState.squad || []).forEach((x) => {
    const pos = Number(x?.squad_position);
    if (Number.isFinite(pos) && pos >= 1 && pos <= 6) squadByPos.set(pos, x);
  });

  body.innerHTML = "";
  for (let pos = 1; pos <= 6; pos += 1) {
    const cur = squadByPos.get(pos) || null;
    const row = document.createElement("div");
    row.className = "list-item";
    row.innerHTML = `
      <div style="display:flex; justify-content:space-between; gap:10px; align-items:center;">
        <div style="min-width:0;">
          <strong>Слот #${pos}</strong>
          <div class="muted tiny">${cur ? `занято: ${cur.name}` : "свободно"}</div>
        </div>
        <button class="primary" style="width:auto; padding:10px 12px;">Выбрать</button>
      </div>
    `;
    const btn = row.querySelector("button");
    if (btn) {
      btn.onclick = async (ev) => {
        ev.stopPropagation();
        try {
          await apiFetch(`/tavern/squad/add?waifu_id=${encodeURIComponent(w.id)}&slot=${encodeURIComponent(pos)}`, {
            method: "POST",
          });
          closeTavernSlotModal();
          closeTavernWaifuModal();
          await loadTavernWithProfile({ act: tavernState.act }).catch(() => {});
        } catch (e) {
          const { detail } = parseHttpErrorDetail(e);
          showTavernError(detail || "Ошибка формирования отряда", "danger");
          closeTavernSlotModal();
        }
      };
    }
    body.appendChild(row);
  }

  m.style.display = "grid";
}

async function tavernWaifuModalAction() {
  const w = tavernState.selectedWaifu;
  const ctx = tavernState.selectedContext;
  if (!w || !w.id) return;
  if (ctx === "reserve") {
    openTavernSlotModal(w);
    return;
  }
  if (ctx === "squad") {
    try {
      await apiFetch(`/tavern/squad/remove?waifu_id=${encodeURIComponent(w.id)}`, { method: "POST" });
      closeTavernWaifuModal();
      await loadTavernWithProfile({ act: tavernState.act }).catch(() => {});
    } catch (e) {
      const { detail } = parseHttpErrorDetail(e);
      showTavernError(detail || "Ошибка", "danger");
    }
  }
}

async function adminRefreshTavern() {
  try {
    await apiFetch(`/admin/tavern/refresh`, { method: "POST" });
    await loadTavernWithProfile({ act: tavernState.act }).catch(() => {});
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showTavernError(detail || "Admin refresh failed", "danger");
  }
}

async function loadDungeons(act) {
  const data = await apiFetch(`/dungeons?act=${act}`);
  const soloList = document.getElementById("solo-dungeons");
  const townList = document.getElementById("dungeon-list");
  const list = soloList || townList;
  if (!list) return data;

  list.innerHTML = "";
  data.dungeons.forEach((d) => {
    if (soloList) {
      const card = document.createElement("div");
      card.className = "dungeon-card";
      card.innerHTML = `
        <div class="dungeon-header"><h3>${d.name}</h3></div>
        <div class="dungeon-body">
          <div class="dungeon-info">
            <div>Акт: <strong>${d.act}</strong></div>
            <div>Уровень: <strong>${d.level}</strong></div>
            <div>Тип: <strong>${d.dungeon_type}</strong></div>
          </div>
          <button class="dungeon-start-btn" onclick="WaifuApp.startDungeon(${d.id})">Старт</button>
        </div>
      `;
      list.appendChild(card);
    } else {
      const li = document.createElement("div");
      li.className = "list-item";
      li.innerHTML = `<strong>${d.name}</strong> — акт ${d.act}, ур. ${d.level}, тип ${d.dungeon_type}
        <div><button onclick="WaifuApp.startDungeon(${d.id})">Старт</button></div>`;
      list.appendChild(li);
    }
  });
  return data;
}

function dungeonThemeByNumber(dungeonNumber) {
  const n = Number(dungeonNumber);
  return (
    {
      1: { title: "Пещера", emoji: "🕳️" },
      2: { title: "Лес", emoji: "🌲" },
      3: { title: "Руины", emoji: "🏚️" },
      4: { title: "Склеп", emoji: "⚰️" },
      5: { title: "Бездна", emoji: "🌀" },
    }[n] || { title: "Подземелье", emoji: "🏰" }
  );
}

function dungeonTypeLabel(type) {
  const t = Number(type);
  return (
    {
      1: "Одиночное",
      2: "Экспедиция",
      3: "Групповое",
    }[t] || `Тип ${t || "—"}`
  );
}

function safeInt(x, fallback = 0) {
  const v = Number.parseInt(String(x), 10);
  return Number.isFinite(v) ? v : fallback;
}

let dungeonsFinishBlockedMsg = null;

function showDungeonsError(message, kind = "info") {
  const box = document.getElementById("dungeons-error");
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

function parseHttpErrorDetail(err) {
  const msg = String(err?.message || err || "");
  // "HTTP 400: {json}" -> try to parse json and extract detail
  const idx = msg.indexOf(":");
  if (idx === -1) return { raw: msg, detail: msg };
  const tail = msg.slice(idx + 1).trim();
  try {
    const obj = JSON.parse(tail);
    const detail = obj?.detail != null ? String(obj.detail) : tail;
    return { raw: msg, detail };
  } catch {
    return { raw: msg, detail: tail || msg };
  }
}

function renderSoloDungeonTile(d, waifuLevel) {
  const lvlReq = safeInt(d?.level, 1);
  const baseCanEnter = safeInt(waifuLevel, 0) >= lvlReq;
  const pl = Number(selectedPlusLevel || 0);
  const st = dungeonPlusStatusById?.[Number(d?.id)];
  const unlocked = Number(st?.unlocked_plus_level || 0);
  const isPlusLocked = pl > 0 && pl > unlocked;
  const canEnter = pl > 0 ? !isPlusLocked : baseCanEnter;
  const theme = dungeonThemeByNumber(d?.dungeon_number);
  const mMin = safeInt(d?.obstacle_min, null);
  const mMax = safeInt(d?.obstacle_max, null);
  const mFixed = safeInt(d?.obstacle_count, 1);
  const monstersLabel =
    mMin != null && mMax != null && mMax >= mMin && (mMin !== mMax)
      ? `${mMin}–${mMax}`
      : String(mFixed);
  const lockedClass = canEnter ? "" : "locked";
  const btnText =
    pl > 0
      ? isPlusLocked
        ? `🔒 +${pl}`
        : `⚔️ Старт +${pl}`
      : baseCanEnter
        ? "⚔️ Старт"
        : `🔒 Ур. ${lvlReq}+`;
  return `
    <div class="dungeon-tile ${lockedClass}">
      <div class="dungeon-hero" title="${theme.title}">
        <div class="dungeon-badge">Акт ${d.act} · ${theme.title}</div>
        <div class="dungeon-emoji" aria-hidden="true">${theme.emoji}</div>
      </div>
      <div class="dungeon-body2">
        <div class="dungeon-name2">${d.name || "Подземелье"}</div>
        <div class="dungeon-meta2">
          <div>Тип: <strong>${dungeonTypeLabel(d.dungeon_type)}</strong></div>
          <div>Мин. ур.: <strong>${lvlReq}</strong></div>
          <div>Монстров: <strong>${monstersLabel}</strong></div>
        </div>
        <div class="dungeon-actions2">
          <button class="dungeon-start2" ${canEnter ? "" : "disabled"} onclick="WaifuApp.startDungeon(${d.id}, ${pl})">${btnText}</button>
        </div>
      </div>
    </div>
  `;
}

async function renderSoloDungeonsForAct(profile) {
  const box = document.getElementById("solo-dungeons");
  if (!box) return;
  window.__lastProfileForDungeons = profile;
  const waifuLevel = profile?.main_waifu?.level ?? 0;
  const act = safeInt(profile?.act, 1);

  const res = await apiFetch(`/dungeons?act=${act}&type=1`).catch(() => ({ dungeons: [] }));
  const dungeons = Array.isArray(res?.dungeons) ? res.dungeons : [];
  const subtitle = `5 данжей · доступно: ${dungeons.filter((d) => safeInt(waifuLevel, 0) >= safeInt(d?.level, 1)).length}`;
  const tiles = dungeons.length
    ? dungeons.map((d) => renderSoloDungeonTile(d, waifuLevel)).join("")
    : `<div class="placeholder">Нет данжей для акта ${act}.</div>`;

  box.innerHTML = `
    <div class="act-block">
      <div class="act-head">
        <div class="act-title">Акт ${act}</div>
        <div class="act-subtitle">${subtitle}</div>
      </div>
      <div class="dungeon-grid">
        ${tiles}
      </div>
    </div>
  `;
}

function buildStageDots(pos, total) {
  if (!pos || !total) return "";
  const dots = [];
  for (let i = 1; i <= total; i++) {
    const isBoss = i === total;
    const isDone = i < pos;
    const isActive = i === pos;
    let cls = "stage-dot2";
    if (isBoss) cls += " boss";
    if (isDone) cls += " done";
    else if (isActive) cls += " active";
    const title = isBoss ? (isDone ? "Босс (побеждён)" : isActive ? "Босс (текущий)" : "Босс") : isDone ? `Монстр ${i} (побеждён)` : isActive ? `Монстр ${i} (текущий)` : `Монстр ${i}`;
    dots.push(`<div class="${cls}" title="${title}"></div>`);
  }
  return `<div class="stage-dots" aria-label="Прогресс: ${pos}/${total}">${dots.join("")}</div>`;
}

function renderSoloActiveProgress(active) {
  const host = document.getElementById("solo-active");
  const list = document.getElementById("solo-dungeons");
  if (!host || !list) return;

  if (!active?.active) {
    host.style.display = "none";
    list.style.display = "";
    host.innerHTML = "";
    return;
  }

  const hpCur = safeNumber(active.monster_current_hp, 0);
  const hpMax = Math.max(1, safeNumber(active.monster_max_hp, 1));
  const dealt = safeNumber(active.damage_done, Math.max(0, hpMax - hpCur));
  const monPct = Math.round(clamp01(hpCur / hpMax) * 100);
  const log = Array.isArray(active.battle_log) ? active.battle_log.slice(-6) : [];
  const pos = safeNumber(active.monster_position, null);
  const total = safeNumber(active.total_monsters, null);
  const lastDmg = active.last_damage != null ? safeNumber(active.last_damage, null) : null;
  const lastCrit = active.last_is_crit === true;
  const pl = safeNumber(active.plus_level, 0);

  const waifuHpCur = safeNumber(active.waifu_current_hp, null);
  const waifuHpMax = Math.max(1, safeNumber(active.waifu_max_hp, 1));
  const waifuPct = waifuHpCur != null ? Math.round(clamp01(waifuHpCur / waifuHpMax) * 100) : null;
  const isUnconscious = waifuHpCur === 0;

  // Recovery timer: if API provides recovery_seconds_left use it; otherwise show generic msg
  const recoverySec = active.recovery_seconds_left != null ? safeNumber(active.recovery_seconds_left, null) : null;
  const recoveryText = recoverySec != null
    ? `Восстановление через ~${Math.ceil(recoverySec)} сек`
    : "Восстановление через пассивную регенерацию";

  const stageDots = buildStageDots(pos, total);

  const unconsciousBanner = isUnconscious ? `
    <div class="unconscious-banner">
      <div class="unconscious-icon">💀</div>
      <div>
        <div>Без сознания — атаки заблокированы</div>
        <div class="unconscious-timer">${recoveryText}</div>
      </div>
    </div>` : "";

  const waifuHpSection = waifuHpCur != null ? `
    <div class="detail-row">
      <span class="muted">HP персонажа</span>
      <strong style="color:${isUnconscious ? "#f87171" : "inherit"}">${waifuHpCur}/${waifuHpMax}</strong>
    </div>
    <div class="bar" aria-label="HP персонажа" style="--bar-color:${isUnconscious ? "#ef4444" : "#10b981"}">
      <div style="width:${waifuPct}%; background:linear-gradient(90deg, ${isUnconscious ? "#ef4444,#f87171" : "#10b981,#34d399"});"></div>
    </div>` : "";

  host.style.display = "";
  list.style.display = "none";
  host.innerHTML = `
    <div class="solo-active-card">
      <div class="solo-active-head">
        <div class="solo-active-title">🏰 ${active.dungeon_name || "Активное подземелье"}${pl > 0 ? ` <span class="muted">+${pl}</span>` : ""}</div>
        <button class="icon-btn" title="Покинуть подземелье" aria-label="Покинуть подземелье" onclick="WaifuApp.openExitDungeonConfirm()">✕</button>
      </div>

      ${stageDots ? `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">${stageDots}${pos && total ? `<span class="muted tiny">${pos}/${total}</span>` : ""}</div>` : ""}

      ${unconsciousBanner}

      <div>
        <div class="detail-row" style="margin-bottom:6px;">
          <span class="muted">🐉 ${active.monster_name || "Монстр"} · lvl ${active.monster_level ?? "—"}</span>
          <strong>${hpCur}/${hpMax}</strong>
        </div>
        <div class="bar" aria-label="HP монстра">
          <div style="width:${monPct}%;"></div>
        </div>
      </div>

      ${waifuHpSection}

      <div class="solo-active-meta">
        ${lastDmg != null ? `<div class="meta-tag">Последний удар: <strong>${lastDmg}</strong>${lastCrit ? ' <span style="color:#fbbf24">★крит</span>' : ""}</div>` : ""}
        ${dealt > 0 ? `<div class="meta-tag">Нанесено: <strong>${dealt}</strong></div>` : ""}
      </div>

      ${
        log.length
          ? `<div class="detail-row"><span class="muted">Лог</span><strong style="font-size:12px;">${log.join(" · ")}</strong></div>`
          : ""
      }

    </div>
  `;
}

function renderSoloActiveFallback(reason) {
  const host = document.getElementById("solo-active");
  const list = document.getElementById("solo-dungeons");
  if (!host || !list) return;
  host.style.display = "";
  list.style.display = "none";
  host.innerHTML = `
    <div class="solo-active-card">
      <div class="solo-active-head">
        <div class="solo-active-title">🏰 Активное подземелье</div>
        <div style="display:flex; align-items:center; gap:8px;">
          <div class="muted tiny">Прогресс недоступен</div>
          <button class="icon-btn" title="Покинуть подземелье" aria-label="Покинуть подземелье" onclick="WaifuApp.openExitDungeonConfirm()">✕</button>
        </div>
      </div>
      <div class="detail-row">
        <span class="muted">Причина</span>
        <strong>${String(reason || "—")}</strong>
      </div>
      <div style="margin-top:6px;">
        <button class="btn" onclick="WaifuApp.refreshSoloActive()">🔄 Обновить</button>
      </div>
    </div>
  `;
}

async function refreshSoloActive() {
  if (!dungeonsFinishBlockedMsg) showDungeonsError("");
  try {
    const active = await apiFetch("/dungeons/active");
    renderAtticDungeon(active);
    if (active?.active) renderSoloActiveProgress(active);
    else {
      renderSoloActiveProgress({ active: false });
      showDungeonsError("Активного подземелья нет (active:false).");
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    renderSoloActiveFallback(detail || "Ошибка загрузки /dungeons/active");
    showDungeonsError(`Не удалось загрузить прогресс: ${detail || "ошибка"}`);
  }
}

async function populateDungeonsPage(profile) {
  const p = profile || (await loadProfile());
  // attic: show act in compact header
  if (p?.act != null) setText("badge-act", p.act);
  showDungeonsError("");

  // Load Dungeon+ status for the global selector (per-dungeon unlock caps)
  try {
    const st = await apiFetch("/dungeons/plus/status");
    dungeonPlusStatusById = {};
    for (const r of st?.status || []) {
      dungeonPlusStatusById[Number(r.dungeon_id)] = r;
    }
    initPlusSelect(Boolean(st?.global_unlocked), dungeonPlusStatusById);
  } catch {
    initPlusSelect(false, {});
  }

  // Page-scoped SSE handler: refresh progress, show reward modal on completion.
  let refreshTimer;
  window.WaifuApp.onSseEvent = (evt) => {
    if (!evt || evt.type !== "battle") return;
    // Debounced refresh of active progress
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => {
      refreshSoloActive().catch?.(() => {});
    }, 250);
    const payload = evt.payload || {};
    if (payload.finish_blocked) {
      const msg = payload.message || "Не хватает здоровья для победы.";
      dungeonsFinishBlockedMsg = msg;
      showDungeonsError(msg, "danger");
      return;
    }
    // clear once we receive any normal battle payload
    if (dungeonsFinishBlockedMsg && (payload.damage != null || payload.monster_defeated || payload.dungeon_completed)) {
      dungeonsFinishBlockedMsg = null;
      showDungeonsError("");
    }
    if (payload.dungeon_completed) {
      dungeonsFinishBlockedMsg = null;
      openRewardModal(payload);
    }
  };

  // First render list for current act, then overlay active-progress if needed.
  await renderSoloDungeonsForAct(p);
  try {
    const active = await apiFetch("/dungeons/active");
    renderSoloActiveProgress(active);
  } catch (e) {
    // Don't break page if active endpoint fails.
    const { detail } = parseHttpErrorDetail(e);
    renderSoloActiveProgress({ active: false });
    showDungeonsError(`Не удалось проверить активный данж: ${detail || "ошибка"}`);
  }
}

let plusBottomSheetUnlocked = false;
let plusBottomSheetMaxUnlocked = 0;

function initPlusSelect(globalUnlocked, statusById) {
  plusBottomSheetUnlocked = globalUnlocked;
  let maxUnlocked = 0;
  for (const k of Object.keys(statusById || {})) {
    const u = Number(statusById[k]?.unlocked_plus_level || 0);
    if (u > maxUnlocked) maxUnlocked = u;
  }
  plusBottomSheetMaxUnlocked = maxUnlocked;
  const cur = Math.min(selectedPlusLevel, maxUnlocked);
  if (cur !== selectedPlusLevel) selectedPlusLevel = cur;
  const lbl = document.getElementById("badge-plus-label");
  if (lbl) lbl.textContent = cur > 0 ? `+${cur}` : "0";
  applyPlusChipStyle(cur, Math.max(1, maxUnlocked));
}

const PLUS_LEVEL_DESCS = [
  "Стандартная сложность. Нет штрафов.",
  "+1: Монстры +15% HP/урон. Награды +10%.",
  "+2: Монстры +30% HP/урон. Награды +22%, шанс редкости ↑.",
  "+3: Монстры +50% HP/урон. Награды +38%, шанс редкости ↑↑.",
  "+4: Монстры +70% HP/урон. Награды +58%, шанс легендарки ↑.",
  "+5: Монстры +100% HP/урон. Награды ×2, шанс легендарки ↑↑.",
];

window.WaifuApp.openPlusBottomSheet = () => {
  const bs = document.getElementById("plus-bottomsheet");
  const list = document.getElementById("plus-options-list");
  if (!bs || !list) return;
  const max = plusBottomSheetUnlocked ? Math.max(0, plusBottomSheetMaxUnlocked) : 0;
  list.innerHTML = "";
  for (let i = 0; i <= Math.max(0, max); i++) {
    const hue = max > 0 ? Math.round(120 * (1 - i / Math.max(1, max))) : 120;
    const bgColor = `hsla(${hue},70%,45%,0.22)`;
    const borderColor = `hsla(${hue},60%,55%,0.50)`;
    const desc = PLUS_LEVEL_DESCS[i] || `+${i}: повышенная сложность.`;
    const btn = document.createElement("button");
    btn.className = "plus-option" + (i === selectedPlusLevel ? " selected" : "");
    btn.innerHTML = `
      <div class="plus-option-badge" style="background:${bgColor};border-color:${borderColor};color:#fff;">
        ${i === 0 ? "0" : `+${i}`}
      </div>
      <div class="plus-option-info">
        <div class="plus-option-label">${i === 0 ? "Обычная" : `Сложность +${i}`}</div>
        <div class="plus-option-desc">${desc}</div>
      </div>`;
    btn.addEventListener("click", () => {
      selectedPlusLevel = i;
      const lbl = document.getElementById("badge-plus-label");
      if (lbl) lbl.textContent = i > 0 ? `+${i}` : "0";
      applyPlusChipStyle(i, Math.max(1, max));
      window.WaifuApp.closePlusBottomSheet();
      const p = window.__lastProfileForDungeons || null;
      if (p) renderSoloDungeonsForAct(p).catch?.(() => {});
    });
    list.appendChild(btn);
  }
  bs.style.display = "flex";
  document.body.style.overflow = "hidden";
};

window.WaifuApp.closePlusBottomSheet = () => {
  const bs = document.getElementById("plus-bottomsheet");
  if (bs) bs.style.display = "none";
  document.body.style.overflow = "";
};

function applyPlusChipStyle(plusLevel, maxLevel) {
  const chip = document.getElementById("badge-plus-chip");
  if (!chip) return;
  const pl = Math.max(0, Number(plusLevel || 0));
  const max = Math.max(1, Number(maxLevel || 1));
  const t = Math.max(0, Math.min(1, pl / max)); // 0..1
  const hue = Math.round(120 * (1 - t)); // green(120) -> red(0)
  chip.style.setProperty("--plus-hue", String(hue));
}

function rarityLabel(r) {
  const v = Number(r);
  return (
    {
      1: "Обычный",
      2: "Необычный",
      3: "Редкий",
      4: "Эпический",
      5: "Легендарный",
    }[v] || `Rarity ${v || "—"}`
  );
}

function rarityClass(r) {
  const v = Number(r);
  return (
    {
      1: "rarity-common",
      2: "rarity-uncommon",
      3: "rarity-rare",
      4: "rarity-epic",
      5: "rarity-legendary",
    }[v] || "rarity-common"
  );
}

function slotTypeLabel(slotType) {
  const st = String(slotType || "").toLowerCase();
  if (!st) return "—";
  return (
    {
      weapon_1h: "Оружие (1H)",
      weapon_2h: "Оружие (2H)",
      offhand: "Оффхенд / Щит",
      costume: "Доспех",
      armor: "Доспех",
      ring: "Кольцо",
      amulet: "Амулет",
    }[st] || st
  );
}

function attackTypeLabel(atk) {
  const a = String(atk || "").toLowerCase();
  if (!a) return "—";
  return (
    {
      melee: "Ближний бой (СИЛ)",
      ranged: "Дальний бой (ЛОВ)",
      magic: "Магия (ИНТ)",
    }[a] || a
  );
}

function weaponTypeLabel(wt) {
  const w = String(wt || "").toLowerCase();
  if (!w) return "—";
  return (
    {
      axe: "Топор",
      sword: "Меч",
      bow: "Лук",
      staff: "Посох",
      wand: "Жезл",
      dagger: "Кинжал",
      mace: "Булава",
      hammer: "Молот",
    }[w] || w
  );
}

function itemIconForSlotType(slotType) {
  const st = String(slotType || "");
  if (st.includes("weapon")) return "⚔️";
  if (st.includes("offhand")) return "🛡️";
  if (st.includes("costume")) return "🥋";
  if (st.includes("ring")) return "💍";
  if (st.includes("amulet")) return "🧿";
  return "🎁";
}

function buildRewardItemCard(item) {
  const rc = rarityClass(item.rarity);
  const icon = itemIconForSlotType(item.slot_type);
  return `
    <div class="reward-item-card ${rc}">
      <div class="reward-item-top">
        <div class="reward-item-icon">${icon}</div>
        <div style="display:grid;gap:2px;min-width:0;">
          <div class="reward-item-name ${rc}">${item.name || "Предмет"}</div>
          <div class="muted tiny">lvl ${item.level ?? "—"} · ${rarityLabel(item.rarity)}</div>
        </div>
      </div>
      <div class="reward-kv">
        <div class="reward-pill"><span class="muted">Слот</span><strong>${slotTypeLabel(item.slot_type)}</strong></div>
      </div>
    </div>`;
}

function openRewardModal(payload) {
  const m = document.getElementById("reward-modal");
  const body = document.getElementById("reward-modal-body");
  const sub = document.getElementById("reward-modal-subtitle");
  if (!m || !body) return;

  if (sub) sub.textContent = "Победа над боссом!";

  // EXP breakdown
  const expMobs  = payload.exp_from_monsters  ?? payload.experience_gained ?? null;
  const expBoss  = payload.exp_from_boss       ?? null;
  const expTotal = payload.total_experience_gained ?? (expMobs != null && expBoss != null ? expMobs + expBoss : expMobs);

  // Gold breakdown
  const goldMobs  = payload.gold_from_monsters  ?? payload.gold_gained ?? null;
  const goldBoss  = payload.gold_from_boss       ?? null;
  const goldTotal = payload.total_gold_gained ?? (goldMobs != null && goldBoss != null ? goldMobs + goldBoss : goldMobs);

  // Items — support both single item_dropped and array items_dropped
  const itemsRaw = Array.isArray(payload.items_dropped) ? payload.items_dropped
    : payload.item_dropped ? [payload.item_dropped]
    : [];
  const guaranteedItem = payload.guaranteed_item || null;
  if (guaranteedItem && !itemsRaw.find((i) => i.id === guaranteedItem.id)) {
    itemsRaw.push({ ...guaranteedItem, _guaranteed: true });
  }

  // Combat stats
  const dmgDealt    = payload.total_damage_dealt    ?? payload.damage_done    ?? null;
  const dmgReceived = payload.total_damage_received ?? payload.damage_received ?? null;

  const fmt = (v) => v != null ? Number(v).toLocaleString() : "—";

  // EXP section
  const expBreakdown = expMobs != null || expBoss != null ? `
    <div class="reward-breakdown">
      ${expMobs != null ? `<div class="reward-breakdown-row"><span class="muted">За монстров</span><span>+${fmt(expMobs)} ✨</span></div>` : ""}
      ${expBoss != null ? `<div class="reward-breakdown-row"><span class="muted">За босса</span><span>+${fmt(expBoss)} ✨</span></div>` : ""}
      <div class="reward-breakdown-row total"><span>Итого опыт</span><strong>+${fmt(expTotal)} ✨</strong></div>
    </div>` : `<div class="reward-pill"><span class="muted">✨ Опыт</span><strong>+${fmt(expTotal)}</strong></div>`;

  // Gold section
  const goldBreakdown = goldMobs != null || goldBoss != null ? `
    <div class="reward-breakdown">
      ${goldMobs != null ? `<div class="reward-breakdown-row"><span class="muted">За монстров</span><span>+${fmt(goldMobs)} 🪙</span></div>` : ""}
      ${goldBoss != null ? `<div class="reward-breakdown-row"><span class="muted">Бонус за босса</span><span>+${fmt(goldBoss)} 🪙</span></div>` : ""}
      <div class="reward-breakdown-row total"><span>Итого золото</span><strong>+${fmt(goldTotal)} 🪙</strong></div>
    </div>` : `<div class="reward-pill"><span class="muted">🪙 Золото</span><strong>+${fmt(goldTotal)}</strong></div>`;

  // Items section
  const itemsHtml = itemsRaw.length
    ? `<div class="reward-items-list">
        ${itemsRaw.map((it) => buildRewardItemCard(it)).join("")}
       </div>`
    : `<div class="reward-item-card"><div class="muted tiny">🎁 Предметы не выпали</div></div>`;

  // Combat summary
  const combatHtml = (dmgDealt != null || dmgReceived != null) ? `
    <div class="reward-combat-grid">
      <div class="reward-combat-cell">
        <div class="reward-combat-val" style="color:#f97316;">${fmt(dmgDealt)}</div>
        <div class="reward-combat-label">⚔️ Нанесено урона</div>
      </div>
      <div class="reward-combat-cell">
        <div class="reward-combat-val" style="color:#f87171;">${fmt(dmgReceived)}</div>
        <div class="reward-combat-label">🛡️ Получено урона</div>
      </div>
    </div>` : "";

  body.innerHTML = `
    <div class="reward-grid">
      <div class="reward-section-title">✨ Опыт</div>
      ${expBreakdown}
      <div class="reward-section-title" style="margin-top:4px;">🪙 Золото</div>
      ${goldBreakdown}
      ${itemsRaw.length ? `<div class="reward-section-title" style="margin-top:4px;">🎁 Предметы</div>${itemsHtml}` : itemsHtml}
      ${combatHtml ? `<div class="reward-section-title" style="margin-top:4px;">📊 Боевая сводка</div>${combatHtml}` : ""}
    </div>
  `;
  m.style.display = "grid";
}

function openInventoryFromReward() {
  // Jump straight to profile inventory; profile page will read ?tab=
  window.location.href = "./profile.html?tab=inventory";
}

async function closeRewardModal() {
  const m = document.getElementById("reward-modal");
  if (m) m.style.display = "none";
  // Refresh page state after completion (new act unlock, inventory changes, etc.)
  try {
    const p = await loadProfile();
    await populateDungeonsPage(p);
  } catch {
    // ignore
  }
}

async function startDungeon(dungeonId, plusLevel = 0) {
  let res;
  try {
    const pl = Math.max(0, Number(plusLevel || 0));
    res = await apiFetch(`/dungeons/${dungeonId}/start?plus_level=${encodeURIComponent(pl)}`, { method: "POST" });
  } catch (e) {
    const { detail, raw } = parseHttpErrorDetail(e);
    // If already active: show progress card instead of throwing unhandled promise
    if (raw.includes("dungeon_already_active") || detail.includes("dungeon_already_active")) {
      // ensure solo tab visible
      showTab("solo");
      try {
        const active = await apiFetch("/dungeons/active");
        if (active?.active) {
          renderSoloActiveProgress(active);
          showDungeonsError("У вас уже есть активное подземелье. Показал прогресс ниже.");
        } else {
          renderSoloActiveFallback("API вернул active:false");
          showDungeonsError("У вас уже есть активное подземелье, но прогресс не получен (active:false).");
        }
      } catch (err2) {
        const { detail: d2 } = parseHttpErrorDetail(err2);
        renderSoloActiveFallback(d2 || "Ошибка загрузки /dungeons/active");
        showDungeonsError(`У вас уже есть активное подземелье, но прогресс не загрузился: ${d2 || "ошибка"}`);
      }
      return;
    }
    if (detail.includes("dungeon_already_completed")) {
      showDungeonsError("Это подземелье уже пройдено.");
      return;
    }
    if (detail.includes("dungeon_plus_locked")) {
      showDungeonsError("Dungeon+ откроется после прохождения Подземелья №5 в 5 акте.");
      return;
    }
    if (detail.includes("dungeon_plus_level_locked")) {
      showDungeonsError("Этот уровень Dungeon+ ещё не открыт для данного подземелья.");
      return;
    }
    if (detail.toLowerCase().includes("level requirement")) {
      showDungeonsError(detail.replace("Level requirement not met.", "Недостаточный уровень."));
      return;
    }
    if (detail.toLowerCase().includes("no main waifu")) {
      showDungeonsError("Сначала создайте основную вайфу.");
      return;
    }
    // Generic 400/other errors
    showDungeonsError(detail || "Ошибка старта подземелья.");
    return;
  }
  appendEvent(`Данж ${dungeonId} стартован: ${res.monster_name} HP ${res.monster_hp}`);
  // refresh progress for this screen as well
  try {
    const active = await apiFetch("/dungeons/active");
    renderSoloActiveProgress(active);
  } catch {
    // ignore
  }
  showDungeonsError("");
}

async function loadActiveDungeon() {
  const data = await apiFetch("/dungeons/active");

  // Town widget
  const townBox = document.getElementById("dungeon-active");
  if (townBox) {
    townBox.innerHTML = data?.active
      ? `<div class="list-item"><strong>${data.dungeon_name}</strong><br/>Монстр: ${data.monster_name} · HP ${data.monster_current_hp} / ${data.monster_max_hp}</div>`
      : '<div class="muted">Активного данжа нет</div>';
  }

  // Dungeons screen widget
  const activeSection = document.getElementById("active-dungeon-section");
  const listSection = document.getElementById("dungeon-list-section");
  const content = document.getElementById("active-dungeon-content");
  if (activeSection && content) {
    if (data?.active) {
      activeSection.style.display = "";
      if (listSection) listSection.style.display = "";

      const log = Array.isArray(data.battle_log) ? data.battle_log.slice(-6) : [];
      const logHtml = log.length
        ? `<div class="active-dungeon-info"><span>Лог</span><strong>${log.join(" · ")}</strong></div>`
        : "";

      content.innerHTML = `
        <div class="active-dungeon-info"><span>Данж</span><strong>${data.dungeon_name}</strong></div>
        <div class="active-dungeon-info"><span>Монстр</span><strong>${data.monster_name} (lvl ${data.monster_level})</strong></div>
        <div class="active-dungeon-info"><span>HP монстра</span><strong>${data.monster_current_hp}/${data.monster_max_hp}</strong></div>
        <div class="active-dungeon-info"><span>Вайфу</span><strong>${data.waifu_name} (lvl ${data.waifu_level})</strong></div>
        <div class="active-dungeon-info"><span>HP вайфу</span><strong>${data.waifu_current_hp}/${data.waifu_max_hp}</strong></div>
        ${logHtml}
      `;
    } else {
      activeSection.style.display = "none";
    }
  }

  return data;
}

function continueActiveDungeon() {
  // Open battle screen for current dungeon combat
  window.location.href = "./battle.html";
}

async function exitDungeon() {
  await apiFetch("/dungeons/exit", { method: "POST" });
  // refresh dungeons screen solo tab if present
  const profile = await loadProfile().catch(() => null);
  if (profile) await renderSoloDungeonsForAct(profile);
  renderSoloActiveProgress({ active: false });
  await loadActiveDungeon();
}

function openExitDungeonConfirm() {
  const modal = document.getElementById("exit-dungeon-modal");
  if (modal) modal.style.display = "grid";
}

function closeExitDungeonConfirm() {
  const modal = document.getElementById("exit-dungeon-modal");
  if (modal) modal.style.display = "none";
}

async function confirmExitDungeon() {
  closeExitDungeonConfirm();
  await exitDungeon();
}

async function adminExitDungeon() {
  return exitDungeon();
}

async function loadBattle() {
  const data = await apiFetch("/dungeons/active");

  if (!data?.active) {
    setText("battle-title", "БИТВА: Нет активного подземелья");
    setText("enemy-name", "ПРОТИВНИК: —");
    setText("waifu-battle-name", "ВАША ВАЙФУ: —");
    setHTML("battle-log-content", '<div class="muted tiny">Нет активного подземелья.</div>');
    const btn = document.getElementById("battle-continue-btn");
    if (btn) btn.disabled = true;
    return data;
  }

  setText("battle-title", `БИТВА: ${data.dungeon_name}`);
  setText("enemy-name", `ПРОТИВНИК: ${data.monster_name}`);
  setText(
    "enemy-stats",
    `Атака: ${data.monster_damage} | Защита: ${data.monster_defense} | Тип: ${data.monster_type}`
  );
  setText("waifu-battle-name", `ВАША ВАЙФУ: ${data.waifu_name}`);
  setText(
    "waifu-stats",
    `Атака: ${data.waifu_attack_min}-${data.waifu_attack_max} | Защита: ${data.waifu_defense}`
  );

  const enemyHp = safeNumber(data.monster_current_hp, 0);
  const enemyHpMax = Math.max(1, safeNumber(data.monster_max_hp, 1));
  const waifuHp = safeNumber(data.waifu_current_hp, 0);
  const waifuHpMax = Math.max(1, safeNumber(data.waifu_max_hp, 1));
  const waifuEnergy = safeNumber(data.waifu_current_energy, 0);
  const waifuEnergyMax = Math.max(1, safeNumber(data.waifu_max_energy, 1));

  const enemyFill = document.getElementById("enemy-hp-fill");
  if (enemyFill) enemyFill.style.width = `${Math.round(clamp01(enemyHp / enemyHpMax) * 100)}%`;
  setText("enemy-hp-text", `HP: ${enemyHp}/${enemyHpMax}`);

  const waifuFill = document.getElementById("waifu-hp-fill");
  if (waifuFill) waifuFill.style.width = `${Math.round(clamp01(waifuHp / waifuHpMax) * 100)}%`;
  setText("waifu-hp-text", `HP: ${waifuHp}/${waifuHpMax}`);

  const energyFill = document.getElementById("waifu-energy-fill");
  if (energyFill) energyFill.style.width = `${Math.round(clamp01(waifuEnergy / waifuEnergyMax) * 100)}%`;
  setText("waifu-energy-text", `Энергия: ${waifuEnergy}/${waifuEnergyMax}`);

  const logs = Array.isArray(data.battle_log) ? data.battle_log : [];
  const logHtml = logs.length
    ? logs.map((l) => `<div class="muted tiny">${String(l)}</div>`).join("")
    : '<div class="muted tiny">Битва начата...</div>';
  setHTML("battle-log-content", logHtml);

  const btn = document.getElementById("battle-continue-btn");
  if (btn) btn.disabled = false;

  return data;
}

function appendBattleLog(text) {
  const log = document.getElementById("battle-log-content");
  if (log) {
    const div = document.createElement("div");
    div.className = "muted tiny";
    div.textContent = text;
    log.prepend(div);
  } else {
    appendEvent(text);
  }
}

async function continueBattle() {
  const btn = document.getElementById("battle-continue-btn");
  if (btn) btn.disabled = true;
  try {
    const res = await apiFetch("/dungeons/continue", { method: "POST" });
    if (res?.error === "no_energy") {
      appendBattleLog("⚡ Недостаточно энергии для атаки.");
      return;
    }
    if (res?.error) {
      appendBattleLog(`Ошибка: ${res.message || res.error}`);
      return;
    }
    const dmg = res?.damage ?? null;
    const crit = res?.is_crit;
    if (dmg != null) {
      appendBattleLog(crit ? `⚔️ Удар ${dmg} (крит!)` : `⚔️ Удар ${dmg}`);
    }
    if (res?.experience_gained) appendBattleLog(`✨ +${res.experience_gained} опыта`);
    if (res?.dungeon_completed) {
      window.location.href = "./dungeons.html";
      return;
    }
    const after = await loadBattle();
    if (!after?.active) {
      window.location.href = "./dungeons.html";
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function exitBattle() {
  await exitDungeon();
  window.location.href = "./dungeons.html";
}

function switchShopTab(name) {
  document.querySelectorAll(".tabs .tab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    if (panel.id?.startsWith("tab-")) panel.classList.toggle("active", panel.id === `tab-${name}`);
  });

  // Lazy load sell inventory when entering sell tab on shop page.
  if (window.location.pathname.endsWith("/shop.html") && name === "sell") {
    loadSellInventory().catch(console.error);
  }
}

function switchProfileTab(name) {
  document.querySelectorAll(".profile-tabs .tab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll("main .tab-panel").forEach((panel) => {
    if (panel.id?.startsWith("tab-")) panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

let gdSessionRefreshTimer = null;

function getGdChatIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const chatId = params.get("chat_id");
  if (chatId === null || chatId === "") return null;
  const n = Number(chatId);
  return Number.isFinite(n) ? n : null;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function loadActiveGdDungeons() {
  const container = document.getElementById("gd-dungeons-list");
  if (!container) return;
  try {
    const data = await apiFetch("/gd/dungeons/active");
    const dungeons = data?.dungeons || [];
    renderGdDungeonsList(container, dungeons);
  } catch (e) {
    console.error("loadActiveGdDungeons:", e);
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🏰</div>
        <h3>Ошибка загрузки</h3>
        <p>Не удалось загрузить список подземелий.</p>
      </div>`;
  }
}

function renderGdDungeonsList(container, dungeons) {
  container.innerHTML = "";
  if (dungeons.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🏰</div>
        <h3>Нет активных подземелий</h3>
        <p>Присоединяйтесь к групповому чату и запустите подземелье командой /gd_start</p>
      </div>`;
    return;
  }
  dungeons.forEach((dungeon) => {
    const card = createGdDungeonCard(dungeon);
    container.appendChild(card);
  });
}

function createGdDungeonCard(dungeon) {
  const hpBarWidth = `${Math.max(0, Math.min(100, dungeon.hp_percent || 0))}%`;
  const card = document.createElement("div");
  card.className = "dungeon-card gd-dungeon-card";
  card.dataset.dungeonId = dungeon.id;
  card.innerHTML = `
    <div class="dungeon-header">
      <span class="dungeon-name">${escapeHtml(dungeon.dungeon_name || "—")}</span>
      <span class="dungeon-stage">${dungeon.stage || 1}/4</span>
    </div>
    <div class="dungeon-monster">
      <span class="monster-name">${escapeHtml(dungeon.monster_name || "—")}</span>
      <div class="hp-bar">
        <div class="hp-fill" style="width: ${hpBarWidth}"></div>
      </div>
      <div class="hp-text">${Number(dungeon.hp_current || 0).toLocaleString()} / ${Number(dungeon.hp_max || 0).toLocaleString()}</div>
    </div>
    <div class="dungeon-stats">
      <span class="stat">⚔️ ${Number(dungeon.total_damage || 0).toLocaleString()} урона</span>
      <span class="stat">👥 Этап ${dungeon.joined_at_stage || 1}</span>
    </div>`;
  card.addEventListener("click", () => openDungeonDetails(dungeon));
  return card;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function renderStageProgress(currentStage) {
  let html = "";
  for (let i = 1; i <= 4; i++) {
    const status = i < currentStage ? "completed" : i === currentStage ? "active" : "pending";
    html += `<div class="stage-dot ${status}">${i}</div>`;
  }
  return html;
}

function renderDungeonDetails(dungeon) {
  const effects = dungeon.active_effects?.length
    ? dungeon.active_effects.map((e) => `<div class="effect-badge">${escapeHtml(e.name || "")} (+${e.value || 0}%)</div>`).join("")
    : '<div class="no-effects">Нет активных эффектов</div>';
  return `
    <div class="dungeon-details">
      <h2>${escapeHtml(dungeon.dungeon_name || "—")}</h2>
      <div class="details-section">
        <h3>Текущий этап</h3>
        <div class="stage-progress">${renderStageProgress(dungeon.stage || 1)}</div>
      </div>
      <div class="details-section">
        <h3>Противник</h3>
        <div class="monster-details">
          <div class="monster-info">
            <span class="monster-name">${escapeHtml(dungeon.monster_name || "—")}</span>
            <div class="hp-bar-large">
              <div class="hp-fill" style="width: ${dungeon.hp_percent || 0}%"></div>
            </div>
            <div class="hp-stats">
              <span>${Number(dungeon.hp_current || 0).toLocaleString()} / ${Number(dungeon.hp_max || 0).toLocaleString()} HP</span>
              <span>${100 - (dungeon.hp_percent || 0)}% осталось</span>
            </div>
          </div>
        </div>
      </div>
      <div class="details-section">
        <h3>Ваш вклад</h3>
        <div class="contribution-stats">
          <div class="stat-row">
            <span>⚔️ Нанесено урона:</span>
            <span>${Number(dungeon.total_damage || 0).toLocaleString()}</span>
          </div>
          <div class="stat-row">
            <span>👥 Присоединились на этапе:</span>
            <span>${dungeon.joined_at_stage || 1}/4</span>
          </div>
          <div class="stat-row">
            <span>⏱️ Время в подземелье:</span>
            <span>${formatDuration(dungeon.duration_seconds || 0)}</span>
          </div>
        </div>
      </div>
      <div class="details-section">
        <h3>Активные эффекты</h3>
        <div class="effects-list">${effects}</div>
      </div>
      <div class="modal-actions">
        <button type="button" class="btn-primary gd-open-chat" data-chat-id="${dungeon.chat_id || ""}">Перейти в чат</button>
      </div>
    </div>`;
}

function openDungeonDetails(dungeon) {
  const modal = document.createElement("div");
  modal.className = "modal-overlay gd-modal-overlay";
  modal.innerHTML = `
    <div class="modal-content gd-modal-content">
      <button type="button" class="modal-close" aria-label="Закрыть">&times;</button>
      ${renderDungeonDetails(dungeon)}
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeGdModal(modal);
  });
  modal.querySelector(".modal-close").addEventListener("click", () => closeGdModal(modal));
  const openChatBtn = modal.querySelector(".gd-open-chat");
  if (openChatBtn && dungeon.chat_id) {
    openChatBtn.addEventListener("click", () => {
      const url = `https://t.me/c/${String(dungeon.chat_id).replace(/^-100/, "")}`;
      // В WebApp открываем ссылку внутри Telegram (без внешнего браузера); WebApp при этом может свернуться — это поведение клиента
      if (tg && typeof tg.openTelegramLink === "function") {
        tg.openTelegramLink(url);
      } else {
        window.open(url, "_blank");
      }
    });
  }
}

function closeGdModal(modal) {
  if (!modal) return;
  modal.classList.add("closing");
  setTimeout(() => modal.remove(), 300);
}

async function updateGdSessionUI() {
  const chatId = getGdChatIdFromUrl();
  const card = document.getElementById("gd-session-status");
  const infoBlock = document.querySelector("#tab-group .gd-info");
  if (!card) return;
  if (chatId === null) {
    card.style.display = "none";
    if (infoBlock) infoBlock.style.display = "";
    return;
  }
  try {
    const data = await apiFetch(`/gd/session/${chatId}`);
    if (!data?.active) {
      card.style.display = "none";
      if (infoBlock) infoBlock.style.display = "";
      return;
    }
    // Hide info block while session is active
    if (infoBlock) infoBlock.style.display = "none";
    card.style.display = "";

    const dungeonName = data.dungeon_name || "—";
    const stage = Math.max(1, Number(data.current_stage) || 1);
    const totalStages = Math.max(stage, Number(data.total_stages) || 4);
    const hp = Math.max(0, Number(data.current_monster_hp) || 0);
    const maxHp = Math.max(1, Number(data.stage_base_hp) || 1);
    const monsterName = data.monster_name || "—";
    const pct = Math.min(100, Math.round((hp / maxHp) * 100));

    // Build stage dots
    const stageDots = buildStageDots(stage, totalStages);

    // Participants
    const participants = Array.isArray(data.participants) ? data.participants : [];
    const totalMsgs = participants.reduce((s, p) => s + (Number(p.messages) || 0), 0);
    const participantsHtml = participants.length
      ? `<div style="font-size:12px;font-weight:800;color:var(--muted);margin:8px 0 4px;">Участники</div>
         <div class="gd-participants">
           ${participants.map((p) => {
             const msgs = Number(p.messages) || 0;
             const pct2 = totalMsgs > 0 ? Math.round((msgs / totalMsgs) * 100) : 0;
             return `<div class="gd-participant-row">
               <span class="gd-participant-name">${escapeHtml(p.name || p.username || "—")}</span>
               <span class="gd-participant-contrib">${msgs} сообщ. · ${pct2}%</span>
             </div>`;
           }).join("")}
         </div>`
      : "";

    card.innerHTML = `
      <h3 class="gd-session-title">${escapeHtml(dungeonName)}</h3>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:4px 0;">
        ${stageDots}
        <span class="muted tiny">${stage}/${totalStages}</span>
      </div>
      <div class="gd-session-monster">
        <span>${escapeHtml(monsterName)}</span>
        <span>${hp.toLocaleString()} / ${maxHp.toLocaleString()}</span>
      </div>
      <div class="gd-session-hp-bar"><div class="gd-hp-fill" style="width:${pct}%"></div></div>
      ${participantsHtml}
    `;
  } catch {
    card.style.display = "none";
    if (infoBlock) infoBlock.style.display = "";
  }
}

function showExpeditionError(msg) {
  const box = document.getElementById("expedition-error");
  if (!box) return;
  if (!msg) {
    box.style.display = "none";
    box.textContent = "";
    return;
  }
  box.style.display = "";
  box.textContent = String(msg);
}

async function loadExpeditionTab() {
  showExpeditionError("");
  try {
    const [slotsRes, activeRes, squadRes] = await Promise.all([
      apiFetch("/expeditions/slots"),
      apiFetch("/expeditions/active"),
      apiFetch("/tavern/squad"),
    ]);
    expeditionState.slots = Array.isArray(slotsRes?.slots) ? slotsRes.slots : [];
    expeditionState.active = Array.isArray(activeRes?.active) ? activeRes.active : [];
    expeditionState.squad = Array.isArray(squadRes?.squad) ? squadRes.squad : [];
    renderExpeditionActive();
    renderExpeditionSlots();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showExpeditionError(detail || "Ошибка загрузки экспедиций");
  }
}

function formatExpeditionTime(seconds) {
  if (seconds == null || seconds <= 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

let expeditionTimerId = null;

function renderExpeditionActive() {
  const box = document.getElementById("expedition-active-list");
  if (!box) return;
  const list = expeditionState.active || [];
  if (!list.length) {
    box.innerHTML = `<div class="muted">Нет активных экспедиций.</div>`;
    if (expeditionTimerId) {
      clearInterval(expeditionTimerId);
      expeditionTimerId = null;
    }
    return;
  }
  box.innerHTML = list
    .map((a) => {
      const canClaim = Boolean(a.can_claim);
      const sec = a.seconds_left != null ? a.seconds_left : 0;
      const timeStr = canClaim ? "Завершена" : formatExpeditionTime(sec);
      return `
        <div class="expedition-active-card" data-id="${a.id}">
          <div class="expedition-active-head">
            <strong>${a.expedition_name || "—"}</strong>
            <span class="tag">${a.duration_minutes} мин</span>
          </div>
          <div class="expedition-active-meta">
            <span>Шанс: <strong>${a.chance ?? "—"}%</strong></span>
            <span>Награда: 🪙${a.reward_gold ?? 0} · ✨${a.reward_experience ?? 0}</span>
          </div>
          <div class="expedition-active-time">${canClaim ? "Готово к получению" : `Осталось: ${timeStr}`}</div>
          <div class="expedition-active-actions">
            ${canClaim ? `<button class="primary" onclick="WaifuApp.claimExpedition(${a.id})">Забрать награду</button>` : ""}
            <button class="secondary" onclick="WaifuApp.cancelExpedition(${a.id})">Отменить (50%)</button>
          </div>
        </div>
      `;
    })
    .join("");
  const hasRunning = list.some((a) => !a.can_claim);
  if (hasRunning && !expeditionTimerId) {
    expeditionTimerId = setInterval(() => {
      if (document.getElementById("tab-expedition")?.style.display !== "none") {
        loadExpeditionTab().catch(() => {});
      }
    }, 5000);
  } else if (!hasRunning && expeditionTimerId) {
    clearInterval(expeditionTimerId);
    expeditionTimerId = null;
  }
}

function renderExpeditionSlots() {
  const box = document.getElementById("expedition-slots-list");
  if (!box) return;
  const slots = expeditionState.slots || [];
  if (!slots.length) {
    box.innerHTML = `<div class="muted">Нет слотов на сегодня.</div>`;
    return;
  }
  box.innerHTML = slots
    .map((s) => {
      const aff = (s.affixes || []).length;
      return `
        <div class="expedition-slot-card" data-id="${s.id}">
          <div class="expedition-slot-name">${s.name || "—"}</div>
          <div class="expedition-slot-meta">
            <span>Ур. ${s.base_level ?? "—"}</span>
            <span>Сложности: ${aff}</span>
            <span>🪙 ${s.base_gold ?? 0} · ✨ ${s.base_experience ?? 0}</span>
          </div>
          <button class="primary" onclick="WaifuApp.openExpeditionStartModal(${s.id})">Отправить отряд</button>
        </div>
      `;
    })
    .join("");
}

function openExpeditionStartModal(slotId) {
  const slot = (expeditionState.slots || []).find((s) => Number(s.id) === Number(slotId));
  if (!slot) return;
  expeditionState.selectedSlot = slot;
  expeditionState.selectedSquadIds = [];
  expeditionState.durationMinutes = 60;

  const m = document.getElementById("expedition-start-modal");
  if (!m) return;
  setText("expedition-start-title", slot.name || "Экспедиция");
  setText("expedition-start-subtitle", `Ур. ${slot.base_level} · до 3 вайфу из отряда таверны`);

  const pick = document.getElementById("expedition-squad-pick");
  if (pick) {
    const squad = expeditionState.squad || [];
    if (!squad.length) {
      pick.innerHTML = `<div class="muted">Сформируйте отряд в таверне (1–3 вайфу в отряде).</div>`;
    } else {
      pick.innerHTML = squad
        .map(
          (w) => `
          <label class="expedition-squad-option">
            <input type="checkbox" value="${w.id}" data-waifu-id="${w.id}">
            <span>${w.name || "—"} (lvl ${w.level ?? "—"})</span>
          </label>
        `
        )
        .join("");
      pick.querySelectorAll("input[type=checkbox]").forEach((cb) => {
        cb.addEventListener("change", () => {
          const checked = Array.from(pick.querySelectorAll("input[type=checkbox]:checked")).map(
            (c) => Number(c.dataset.waifuId)
          );
          if (checked.length > 3) {
            cb.checked = false;
            expeditionState.selectedSquadIds = checked.filter((id) => id !== Number(cb.dataset.waifuId));
          } else {
            expeditionState.selectedSquadIds = checked;
          }
        });
      });
    }
  }

  const durSel = document.getElementById("expedition-duration-select");
  if (durSel) {
    const opts = [15, 30, 45, 60, 75, 90, 105, 120];
    durSel.innerHTML = opts.map((m) => `<option value="${m}" ${m === 60 ? "selected" : ""}>${m} мин</option>`).join("");
    durSel.onchange = () => {
      expeditionState.durationMinutes = Number(durSel.value);
    };
  }

  const preview = document.getElementById("expedition-preview");
  if (preview) preview.innerHTML = `<div class="muted tiny">Шанс и награда рассчитываются при отправке.</div>`;

  m.style.display = "grid";
}

function closeExpeditionStartModal() {
  const m = document.getElementById("expedition-start-modal");
  if (m) m.style.display = "none";
  expeditionState.selectedSlot = null;
  expeditionState.selectedSquadIds = [];
}

async function submitExpeditionStart() {
  const slot = expeditionState.selectedSlot;
  if (!slot) return;
  const pick = document.getElementById("expedition-squad-pick");
  const ids = pick
    ? Array.from(pick.querySelectorAll("input[type=checkbox]:checked")).map((c) => Number(c.dataset.waifuId))
    : expeditionState.selectedSquadIds;
  if (!ids.length || ids.length > 3) {
    showExpeditionError("Выберите от 1 до 3 вайфу из отряда таверны.");
    return;
  }
  const duration = expeditionState.durationMinutes || 60;
  try {
    const res = await apiFetch("/expeditions/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expedition_slot_id: Number(slot.id),
        squad_waifu_ids: ids,
        duration_minutes: duration,
      }),
    });
    closeExpeditionStartModal();
    showExpeditionError("");
    showDungeonsError(`Экспедиция отправлена. Шанс: ${res.chance}%. ${res.success ? "Успех!" : "Провал."} Завершение: ${res.ends_at || ""}`);
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showExpeditionError(detail || "Ошибка запуска экспедиции");
  }
}

async function claimExpedition(activeId) {
  try {
    const res = await apiFetch(`/expeditions/claim?active_id=${activeId}`, { method: "POST" });
    showDungeonsError(`Награда: 🪙 +${res.gold_gained} · ✨ +${res.experience_gained}`);
    await loadProfile().catch(() => {});
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showDungeonsError(detail || "Ошибка получения награды", "danger");
  }
}

async function cancelExpedition(activeId) {
  try {
    const res = await apiFetch(`/expeditions/cancel?active_id=${activeId}`, { method: "POST" });
    showDungeonsError(`Отменено. Получено: 🪙 +${res.gold_gained} · ✨ +${res.experience_gained}`);
    await loadProfile().catch(() => {});
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showDungeonsError(detail || "Ошибка отмены", "danger");
  }
}

async function adminRefreshExpeditions() {
  try {
    await apiFetch("/admin/expeditions/refresh", { method: "POST" });
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showExpeditionError(detail || "Ошибка обновления слотов");
  }
}

function showTab(name) {
  const tabs = document.getElementById("dungeon-tabs");
  if (!tabs) return;
  tabs.querySelectorAll(".tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === name));
  ["solo", "expedition", "group"].forEach((t) => {
    const panel = document.getElementById(`tab-${t}`);
    if (!panel) return;
    const isActive = t === name;
    panel.classList.toggle("active", isActive);
    panel.style.display = isActive ? "" : "none";
  });
  if (name === "expedition") {
    loadExpeditionTab().catch(() => {});
  }
  if (name === "group") {
    loadActiveGdDungeons().catch(() => {});
    updateGdSessionUI().catch(() => {});
    if (gdSessionRefreshTimer) clearInterval(gdSessionRefreshTimer);
    gdSessionRefreshTimer = setInterval(() => {
      if (document.getElementById("tab-group")?.style.display !== "none") {
        loadActiveGdDungeons().catch(() => {});
        updateGdSessionUI().catch(() => {});
      }
    }, 5000);
  } else {
    if (gdSessionRefreshTimer) {
      clearInterval(gdSessionRefreshTimer);
      gdSessionRefreshTimer = null;
    }
  }
}

function showExpeditionError(message, tone = "danger") {
  const box = document.getElementById("expedition-error");
  if (!box) return;
  if (!message) {
    box.style.display = "none";
    box.textContent = "";
    return;
  }
  box.classList.remove("success", "warning", "danger");
  box.classList.add(tone);
  box.textContent = message;
  box.style.display = "block";
}

async function loadExpeditionTab() {
  showExpeditionError("");
  const [slots, active] = await Promise.all([apiFetch("/expeditions/slots"), apiFetch("/expeditions/active")]);
  expeditionState.slots = Array.isArray(slots?.slots) ? slots.slots : [];
  expeditionState.active = Array.isArray(active?.active) ? active.active : [];
  renderExpeditionSlots();
  renderExpeditionActive();
}

function renderExpeditionSlots() {
  const wrap = document.getElementById("expedition-slots");
  if (!wrap) return;
  if (!expeditionState.slots.length) {
    wrap.innerHTML = `<div class="placeholder">Экспедиций пока нет.</div>`;
    return;
  }
  wrap.innerHTML = "";
  expeditionState.slots.forEach((slot) => {
    const affixes = Array.isArray(slot.affixes) ? slot.affixes : [];
    const card = document.createElement("div");
    card.className = "card";
    card.style.marginBottom = "12px";
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
        <div style="min-width:0;">
          <div style="font-weight:800;">${slot.name || "Экспедиция"}</div>
          <div class="muted tiny">Уровень: ${slot.base_level ?? "—"} · Сложность: ${slot.base_difficulty ?? "—"}</div>
          <div class="muted tiny">Сложности: ${affixes.length ? affixes.join(", ") : "—"}</div>
          <div class="muted tiny">Базовые награды: 🪙 ${slot.base_gold ?? 0} · ✨ ${slot.base_experience ?? 0}</div>
        </div>
        <button class="primary" style="width:auto;">Выбрать</button>
      </div>
    `;
    const btn = card.querySelector("button");
    if (btn) {
      btn.onclick = () => openExpeditionModal(slot);
    }
    wrap.appendChild(card);
  });
}

function renderExpeditionActive() {
  const wrap = document.getElementById("expedition-active");
  if (!wrap) return;
  if (!expeditionState.active.length) {
    wrap.innerHTML = `<div class="muted">Нет активных экспедиций.</div>`;
    return;
  }
  wrap.innerHTML = "";
  expeditionState.active.forEach((run) => {
    const mins = Math.ceil((run.remaining_seconds || 0) / 60);
    const card = document.createElement("div");
    card.className = "list-item";
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; gap:10px; align-items:center;">
        <div>
          <strong>${run.dungeon_name || "Экспедиция"}</strong>
          <div class="muted tiny">Осталось: ${mins} мин · Шанс: ${run.chance ?? "—"}%</div>
        </div>
        <div class="tag">${run.cancelled ? "отменена" : run.claimed ? "завершена" : "в пути"}</div>
      </div>
    `;
    wrap.appendChild(card);
  });
}

async function openExpeditionModal(slot) {
  expeditionState.selectedSlot = slot;
  expeditionState.selectedDuration = 60;
  expeditionState.selectedWaifus = new Set();
  const modal = document.getElementById("expedition-modal");
  const body = document.getElementById("expedition-modal-body");
  if (!modal || !body) return;
  setText("expedition-modal-title", slot?.name || "Экспедиция");
  setText("expedition-modal-subtitle", `Сложность: ${slot?.base_difficulty ?? "—"}`);

  let waifuPayload = { waifus: [] };
  try {
    waifuPayload = await apiFetch("/expeditions/waifus");
  } catch (e) {
    showExpeditionError("Не удалось загрузить список вайфу.");
  }
  expeditionState.waifus = Array.isArray(waifuPayload?.waifus) ? waifuPayload.waifus : [];

  const durationOptions = [15, 30, 45, 60, 75, 90, 105, 120]
    .map((m) => `<option value="${m}">${m} мин</option>`)
    .join("");

  const waifuRows = expeditionState.waifus
    .map(
      (w) => `
      <label class="list-item" style="cursor:pointer;">
        <div style="display:flex; gap:10px; align-items:center; width:100%;">
          <input type="checkbox" data-waifu-id="${w.id}" />
          <div style="min-width:0;">
            <strong>${w.name}</strong>
            <div class="muted tiny">Мощь: ${w.power ?? "—"} · Перки: ${Array.isArray(w.perks) ? w.perks.length : 0}</div>
          </div>
        </div>
      </label>
    `
    )
    .join("");

  body.innerHTML = `
    <div class="detail-row"><span class="muted">Длительность</span>
      <select id="expedition-duration" class="chip-select">${durationOptions}</select>
    </div>
    <div style="margin-top:10px; font-weight:700;">Отряд (1–3)</div>
    <div id="expedition-waifu-list">${waifuRows || `<div class="muted">Нет доступных вайфу.</div>`}</div>
  `;

  const durationSelect = document.getElementById("expedition-duration");
  if (durationSelect) {
    durationSelect.value = String(expeditionState.selectedDuration);
    durationSelect.onchange = (e) => {
      expeditionState.selectedDuration = Number(e.target.value || 60);
    };
  }
  const checkboxes = body.querySelectorAll("input[type='checkbox'][data-waifu-id]");
  checkboxes.forEach((box) => {
    box.addEventListener("change", () => {
      const id = Number(box.getAttribute("data-waifu-id"));
      if (!id) return;
      if (box.checked) {
        expeditionState.selectedWaifus.add(id);
      } else {
        expeditionState.selectedWaifus.delete(id);
      }
      if (expeditionState.selectedWaifus.size > 3) {
        box.checked = false;
        expeditionState.selectedWaifus.delete(id);
      }
    });
  });

  modal.style.display = "grid";
}

function closeExpeditionModal() {
  const modal = document.getElementById("expedition-modal");
  if (modal) modal.style.display = "none";
}

async function startExpedition() {
  const slot = expeditionState.selectedSlot;
  if (!slot) return;
  const waifuIds = Array.from(expeditionState.selectedWaifus);
  if (waifuIds.length < 1) {
    showExpeditionError("Выберите хотя бы одну вайфу.");
    return;
  }
  try {
    await apiFetch(
      `/expeditions/start?slot_id=${encodeURIComponent(slot.id)}&duration_minutes=${encodeURIComponent(expeditionState.selectedDuration)}&squad_ids=${waifuIds
        .map(encodeURIComponent)
        .join("&squad_ids=")}`,
      { method: "POST" }
    );
    closeExpeditionModal();
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showExpeditionError(detail || "Не удалось отправить экспедицию.");
  }
}

function closeShopModal() {
  const m = document.getElementById("shop-modal");
  if (m) m.style.display = "none";
  shopState.selectedSlot = null;
  shopState.selectedOffer = null;
  const grid = document.getElementById("shop-items");
  if (grid) grid.querySelectorAll(".item-card").forEach((c) => c.classList.remove("selected"));
}

function openShopOffer(slot) {
  const offer = shopState.offers.find((o, idx) => {
    const s = Number(o.slot || o.offer_slot || o.shop_slot || idx + 1);
    return s === slot;
  });
  shopState.selectedSlot = slot;
  shopState.selectedOffer = offer || null;

  const m = document.getElementById("shop-modal");
  if (!m) return;

  const nm = String(offer?.display_name || offer?.name || "").trim() || `Слот ${slot}`;
  setText("shop-modal-name", nm);
  setText("shop-modal-rarity", offer?.rarity != null ? rarityLabel(offer.rarity) : "—");
  setText("shop-modal-level", offer?.level != null ? `lvl ${offer.level}` : "—");
  setText("shop-modal-price", offer?.price != null ? String(offer.price) : "—");

  const body = document.getElementById("shop-modal-body");
  if (body) {
    if (!offer) {
      body.innerHTML = `<div class="muted">Пустой слот.</div>`;
    } else if (offer?.sold) {
      body.innerHTML = `<div class="muted">Этот предмет уже продан.</div>`;
    } else {
      const parts = [];
      if (offer?.tier != null) parts.push(`<div><span class="muted">Tier</span> <strong>${offer.tier}</strong></div>`);
      parts.push(renderWeaponStatsHtml(offer));
      parts.push(renderItemBonusesHtml(offer));
      body.innerHTML = parts.filter(Boolean).join("") || `<div class="muted">Нет деталей предмета.</div>`;
    }
  }

  const buyBtn = document.getElementById("shop-modal-buy");
  if (buyBtn) buyBtn.disabled = !offer || Boolean(offer?.sold) || offer?.price == null;
  m.style.display = "grid";
}

async function confirmBuy() {
  if (!shopState.selectedSlot) return;
  const act = shopState.act || 1;
  try {
    await apiFetch(`/shop/buy?act=${act}&slot=${shopState.selectedSlot}`, { method: "POST" });
  } catch (e) {
    const body = document.getElementById("shop-modal-body");
    if (body) body.innerHTML = `<div class="muted">Ошибка покупки: ${String(e?.message || e)}</div>`;
    return;
  }
  await loadProfile().catch(console.error);
  await loadShop(act).catch(console.error);
  closeShopModal();
}

async function refreshShopDebug() {
  const act = shopState.act || 1;
  await apiFetch(`/shop/refresh?act=${act}`, { method: "GET" });
  await loadShop(act);
}

async function adminAddGold() {
  try {
    await apiFetch(`/admin/add-gold?amount=10000`, { method: "POST" });
    await loadProfile().catch(console.error);
  } catch (e) {
    console.warn("adminAddGold failed:", e);
  }
}

async function loadSellInventory() {
  const box = document.getElementById("sell-inventory");
  if (!box) return;

  const data = await apiFetch(`/inventory?equipped=false&limit=100&offset=0`);
  const items = Array.isArray(data?.items) ? data.items : [];
  shopState.sellSelected = new Set();

  box.classList.remove("placeholder");
  box.innerHTML = "";
  items.forEach((it) => {
    const card = document.createElement("div");
    card.className = "item-card";
    card.dataset.id = String(it.id);
    const nm = String(it?.display_name || "").trim() || String(it?.name || "Предмет");
    const iconHtml = itemImageUrl(it) ? `<img src="${itemImageUrl(it)}" alt="" />` : "📦";
    card.innerHTML = `
      <div class="item-icon">${iconHtml}</div>
      <div class="item-level">lvl ${it.level ?? "?"}</div>
      <div class="item-name">${nm}</div>
    `;
    card.title = `${nm} (id ${it.id})`;
    card.onclick = () => {
      const id = it.id;
      if (shopState.sellSelected.has(id)) {
        shopState.sellSelected.delete(id);
        card.classList.remove("selected");
      } else {
        shopState.sellSelected.add(id);
        card.classList.add("selected");
      }
      const hint = document.getElementById("sell-result");
      if (hint) hint.textContent = `Выбрано: ${shopState.sellSelected.size}`;
    };
    box.appendChild(card);
  });

  const hint = document.getElementById("sell-result");
  if (hint) hint.textContent = `Выбрано: 0`;
}

async function sellSelected() {
  const ids = Array.from(shopState.sellSelected || []);
  if (!ids.length) return;
  let res;
  try {
    res = await apiFetch(`/inventory/sell`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inventory_item_ids: ids }),
    });
  } catch (e) {
    const hint = document.getElementById("sell-result");
    if (hint) hint.textContent = `Ошибка продажи: ${String(e?.message || e)}`;
    return;
  }
  const hint = document.getElementById("sell-result");
  if (hint) hint.textContent = `Продано: ${ids.length} · +${res?.gold_received ?? "?"} золота`;
  await loadProfile().catch(console.error);
  await loadSellInventory().catch(console.error);
}

async function gambleShop() {
  const act = shopState.act || 1;
  const res = await apiFetch(`/shop/gamble?act=${act}`, { method: "POST" });
  const out = document.getElementById("shop-gamble-result");
  if (out) out.textContent = res?.item?.name || res?.name || "Готово";
  await loadProfile().catch(console.error);
  await loadShop(act).catch(console.error);
}

function closeSlotModal() {
  const m = document.getElementById("slot-modal");
  if (m) m.style.display = "none";
  profileState.selectedSlot = null;
}

function closeItemModal() {
  const m = document.getElementById("item-modal");
  if (m) m.style.display = "none";
  profileState.selectedItem = null;
  profileState.sellConfirm = false;
}

function raceName(id) {
  return WAIFU_RACES.find((r) => r.id === Number(id))?.name || String(id ?? "—");
}

function className(id) {
  return WAIFU_CLASSES.find((c) => c.id === Number(id))?.name || String(id ?? "—");
}

function renderStatsGrid(targetId, waifu) {
  const box = document.getElementById(targetId);
  if (!box || !waifu) return;
  const pairs = [
    ["СИЛ", waifu.strength],
    ["ЛОВ", waifu.agility],
    ["ИНТ", waifu.intelligence],
    ["ВЫН", waifu.endurance],
    ["ОБА", waifu.charm],
    ["УДЧ", waifu.luck],
  ];
  box.innerHTML = pairs
    .map(
      ([k, v]) => `<div class="stat-card"><span class="muted">${k}</span><strong>${v ?? "—"}</strong></div>`
    )
    .join("");
}

function renderItemBonusesHtml(item) {
  if (!item) return "";

  const lines = [];
  if (item.base_stat && item.base_stat_value != null) {
    const m = statMeta(item.base_stat);
    const cls = bonusClass(item.base_stat_value);
    lines.push(
      `<div><span aria-hidden="true">${m.icon}</span> <span class="muted">${m.short}</span> <strong><span class="${cls}">${formatBonusValue(
        item.base_stat,
        item.base_stat_value
      )}</span></strong></div>`
    );
  }

  const aff = Array.isArray(item.affixes) ? item.affixes : [];
  aff.forEach((a) => {
    const m = statMeta(a.stat);
    const cls = bonusClass(a.value);
    const v = a?.is_percent ? `${safeNumber(a.value, 0)}%` : formatBonusValue(a.stat, a.value);
    lines.push(
      `<div><span aria-hidden="true">${m.icon}</span> <span class="muted">${m.short}</span> <strong><span class="${cls}">${v}</span></strong></div>`
    );
  });

  if (!lines.length) return "";
  return `<div class="muted tiny" style="margin-top:10px;">Бонусы</div><div class="affixes">${lines.join("")}</div>`;
}

function itemArtEmoji(item) {
  const st = String(item?.slot_type || "");
  const wt = String(item?.weapon_type || "");
  if (st.includes("ring")) return "💍";
  if (st.includes("amulet")) return "📿";
  if (st.includes("costume")) return "🧥";
  if (st.includes("offhand")) return "🛡️";
  if (st.includes("weapon")) {
    if (wt.includes("bow")) return "🏹";
    if (wt.includes("staff") || wt.includes("wand")) return "🪄";
    if (wt.includes("dagger")) return "🗡️";
    if (wt.includes("axe")) return "🪓";
    if (wt.includes("hammer") || wt.includes("mace")) return "🔨";
    return "⚔️";
  }
  return "📦";
}

function itemImageUrl(item) {
  // Prefer server-provided absolute/relative URL (DB-driven mapping).
  const direct = String(item?.image_url || "").trim();
  if (direct) return direct;

  const tierRaw = item?.tier != null ? Number(item.tier) : 1;
  const tier = Number.isFinite(tierRaw) ? Math.min(10, Math.max(1, Math.floor(tierRaw))) : 1;

  // Tiered .webp by art_key (e.g. weapon_sword_2h)
  const artKey = String(item?.art_key || "").trim();
  if (artKey) {
    return `/webapp/assets/items_webp/${encodeURIComponent(artKey)}/t${tier}.webp`;
  }

  // Legacy svg placeholders by image_key
  const key = String(item?.image_key || "").trim();
  if (!key) return "";
  return `/webapp/assets/items/${encodeURIComponent(key)}.svg`;
}

function itemArtHtml(item) {
  // If we are using tiered webp, add fallback to svg on 404.
  const tierRaw = item?.tier != null ? Number(item.tier) : 1;
  const tier = Number.isFinite(tierRaw) ? Math.min(10, Math.max(1, Math.floor(tierRaw))) : 1;
  const artKey = String(item?.art_key || "").trim();
  const svgKey = String(item?.image_key || "").trim();
  const direct = String(item?.image_url || "").trim();

  const webpUrl = direct
    ? direct
    : artKey
      ? `/webapp/assets/items_webp/${encodeURIComponent(artKey)}/t${tier}.webp`
      : "";
  const svgUrl = svgKey ? `/webapp/assets/items/${encodeURIComponent(svgKey)}.svg` : "";

  if (webpUrl) {
    const onErr = svgUrl
      ? `this.onerror=null;this.src='${svgUrl}';`
      : `this.onerror=null;this.remove();`;
    return `<img src="${webpUrl}" alt="" onerror="${onErr}" />`;
  }

  const url = itemImageUrl(item);
  if (url) return `<img src="${url}" alt="" />`;
  return `${itemArtEmoji(item)}`;
}

function composeItemDisplayName(item) {
  const base = String(item?.name || "Предмет");
  const aff = Array.isArray(item?.affixes) ? item.affixes : [];
  const prefix = aff.find((a) => String(a?.kind || "") === "affix")?.name;
  const suffix = aff.find((a) => String(a?.kind || "") === "suffix")?.name;
  const p = prefix ? `${prefix} ` : "";
  const s = suffix ? ` ${suffix}` : "";
  return `${p}${base}${s}`.trim();
}

function renderWeaponStatsHtml(item) {
  const hasDmg = item?.damage_min != null || item?.damage_max != null;
  const hasSpeed = item?.attack_speed != null;
  const hasType = item?.attack_type != null || item?.weapon_type != null;
  if (!hasDmg && !hasSpeed && !hasType) return "";

  const dmgMin = item?.damage_min != null ? Number(item.damage_min) : null;
  const dmgMax = item?.damage_max != null ? Number(item.damage_max) : null;
  const dmg =
    dmgMin != null && dmgMax != null
      ? `${dmgMin}–${dmgMax}`
      : dmgMin != null
        ? `${dmgMin}+`
        : dmgMax != null
          ? `0–${dmgMax}`
          : "—";

  const speed = item?.attack_speed != null ? Number(item.attack_speed) : null;
  const at = item?.attack_type ? attackTypeLabel(item.attack_type) : "—";
  const wt = item?.weapon_type ? weaponTypeLabel(item.weapon_type) : "—";

  return `
    <div class="muted tiny" style="margin-top:10px;">Параметры</div>
    <div class="detail-row"><span class="muted">Урон</span><strong>${dmg}</strong></div>
    <div class="detail-row"><span class="muted">Скорость атаки</span><strong>${speed != null ? `${speed} (мин. символов)` : "—"}</strong></div>
    <div class="detail-row"><span class="muted">Тип атаки</span><strong>${at}</strong></div>
    <div class="detail-row"><span class="muted">Тип оружия</span><strong>${wt}</strong></div>
  `;
}

function renderProfilePortrait(waifu) {
  setText("profile-portrait-name", waifu?.name || "—");
  setText("profile-portrait-race", raceName(waifu?.race));
  setText("profile-portrait-class", className(waifu?.class ?? waifu?.class_));

  const portraitEl = document.getElementById("profile-portrait-media");
  if (!portraitEl) return;
  const portraitUrl =
    String(waifu?.portrait_url || waifu?.image_url || waifu?.sprite_url || waifu?.avatar_url || "").trim();
  portraitEl.innerHTML = portraitUrl
    ? `<img src="${escapeHtml(portraitUrl)}" alt="${escapeHtml(String(waifu?.name || "Портрет"))}" />`
    : escapeHtml(waifuPortraitEmoji(waifu) || "👤");
}

function renderProfileHeroBars(waifu, details = null) {
  const d = details || profileState.currentDetails || null;
  const hpCur = safeNumber(d?.hp_current ?? waifu?.current_hp, 0);
  const hpMax = Math.max(1, safeNumber(d?.hp_max ?? waifu?.max_hp, 1));
  setText("profile-hp-text", `${hpCur}/${hpMax}`);
  const hpFill = document.getElementById("profile-hp-fill");
  if (hpFill) hpFill.style.width = `${Math.round(clamp01(hpCur / hpMax) * 100)}%`;

  const lvl = safeNumber(waifu?.level, 1);
  const xp = safeNumber(waifu?.experience, 0);
  const curTotal = totalExpForLevel(lvl);
  const nextTotal = totalExpForLevel(lvl + 1);
  const need = Math.max(1, nextTotal - curTotal);
  const into = Math.max(0, xp - curTotal);
  setText("profile-xp-text", `Ур. ${lvl} - ${into}/${need} EXP`);
  const xpFill = document.getElementById("profile-xp-fill");
  if (xpFill) xpFill.style.width = `${Math.round(clamp01(into / need) * 100)}%`;
}

function renderProfileIndicators(waifu, details = null) {
  const box = document.getElementById("profile-indicators-grid");
  if (!box || !waifu) return;
  const d = details || profileState.currentDetails || null;
  const indicators = getProfileIndicators(waifu, d);
  const rows = [
    ["HP максимальное", indicators.hpMax],
    ["Урон ближний", indicators.meleeRange],
    ["Урон дальний", indicators.rangedRange],
    ["Урон магический", indicators.magicRange],
    ["Шанс крит. атаки", indicators.critChance],
    ["Шанс уклонения", indicators.dodgeChance],
    ["Бонус к опыту", indicators.expBonus],
    ["Бонус к золоту", indicators.goldBonus],
    ["Торговля", indicators.merchant],
    ["Энергия", indicators.energy],
  ];
  box.innerHTML = rows
    .map(([label, value]) => `<div class="detail-row"><span class="muted">${label}</span><strong>${value}</strong></div>`)
    .join("");
}

function renderProfileStatistics() {
  const box = document.getElementById("profile-statistics-grid");
  if (!box) return;
  const rows = [
    "Пройдено подземелий",
    "Убито монстров",
    "Нанесено урона",
    "Получено урона",
    "Найдено предметов",
    "Заработано золота",
    "Потрачено золота",
  ];
  box.innerHTML = rows
    .map((label) => `<div class="detail-row"><span class="muted">${label}</span><strong>—</strong></div>`)
    .join("");
}

function syncProfileInfoTabs() {
  document.querySelectorAll(".profile-inner-tabs .tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.infoTab === profileState.infoTab);
  });
  document.querySelectorAll(".profile-info-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `profile-info-${profileState.infoTab}`);
  });
}

function switchProfileInfoTab(name) {
  profileState.infoTab = name === "statistics" ? "statistics" : "indicators";
  syncProfileInfoTabs();
}

function toggleProfileStatTooltip(statKey) {
  profileState.activeTooltipStat = profileState.activeTooltipStat === statKey ? null : statKey;
  const waifu = profileState.currentProfile?.main_waifu;
  if (waifu) renderStatsStrip("profile-stats-strip", waifu, profileState.currentDetails);
}

function toggleProfileStatAccordion(statKey) {
  profileState.activeAccordion = profileState.activeAccordion === statKey ? null : statKey;
  const waifu = profileState.currentProfile?.main_waifu;
  if (waifu) renderStatsBreakdown("profile-stats-breakdown", waifu, profileState.currentDetails);
}

function renderProfileSlotCard(slot, item) {
  const name = item ? escapeHtml(String(item?.display_name || item?.name || "Предмет")) : "Пусто";
  const slotTitle = escapeHtml(EQUIPMENT_SLOT_NAMES[slot] || `Слот ${slot}`);
  const rarity = item ? rarityClass(item?.rarity) : "rarity-common";
  const image = itemImageUrl(item);
  const bonusTotal = getProfileStatBonusTotal(item);
  const damage =
    item?.damage_min != null || item?.damage_max != null
      ? `${safeNumber(item?.damage_min, 0)}-${safeNumber(item?.damage_max, 0)}`
      : "—";
  const speed = item?.attack_speed != null ? String(item.attack_speed) : "—";

  return `
    <button type="button" class="profile-slot-card ${item ? rarity : "empty"}" onclick="WaifuApp.openProfileSlot(${slot})">
      <div class="profile-slot-media">
        ${image ? `<img src="${escapeHtml(image)}" alt="" />` : `<span class="profile-slot-fallback">${itemIconForSlotType(item?.slot_type || "")}</span>`}
      </div>
      <div class="profile-slot-info">
        <div class="profile-slot-name">${slotTitle}</div>
        <div class="profile-slot-title">${name}</div>
        <div class="profile-slot-line">${escapeHtml(item ? slotTypeLabel(item?.slot_type) : "Пустой слот")}</div>
        <div class="profile-slot-line">Ур. ${item?.level ?? "—"}${item ? ` · Бонус +${bonusTotal}` : ""}</div>
        ${
          item?.slot_type && String(item.slot_type).includes("weapon")
            ? `<div class="profile-slot-line">Урон ${damage} · Скорость ${speed}</div>`
            : `<div class="profile-slot-line">${item ? "Нажмите для карточки предмета" : "Нажмите, чтобы выбрать предмет"}</div>`
        }
      </div>
    </button>
  `;
}

function renderProfilePaperDoll(waifu) {
  return `
    <div class="profile-paperdoll">
      <div class="profile-paperdoll-body" aria-hidden="true">${escapeHtml(waifuPortraitEmoji(waifu) || "👤")}</div>
      <div class="profile-paperdoll-caption">
        <strong>${escapeHtml(String(waifu?.name || "Основная вайфу"))}</strong>
        <span class="muted tiny">${escapeHtml(className(waifu?.class ?? waifu?.class_))} · ${escapeHtml(raceName(waifu?.race))}</span>
      </div>
    </div>
  `;
}

function renderProfileEquipment() {
  const gear = document.getElementById("profile-gear");
  const badge = document.getElementById("profile-gear-mode-badge");
  const toggle = document.getElementById("profile-view-toggle");
  const waifu = profileState.currentProfile?.main_waifu;
  if (!gear || !waifu) return;

  const mode = profileState.viewMode;
  // Badge is a <span> inside the toggle button — update only it to preserve the SVG icon
  if (badge) badge.textContent = mode === "compact" ? "Расширенный режим" : "Компактный режим";

  gear.classList.remove("placeholder", "is-expanded");
  if (mode === "compact") {
    gear.innerHTML = `<div class="profile-equipment-grid">${[1, 2, 3, 4, 5, 6]
      .map((slot) => renderProfileSlotCard(slot, getProfileEquippedItem(slot)))
      .join("")}</div>`;
    return;
  }

  gear.classList.add("is-expanded");
  gear.innerHTML = `
    <div class="profile-gear-column">${PROFILE_SLOT_LAYOUT.left
      .map((slot) => renderProfileSlotCard(slot, getProfileEquippedItem(slot)))
      .join("")}</div>
    ${renderProfilePaperDoll(waifu)}
    <div class="profile-gear-column">${PROFILE_SLOT_LAYOUT.right
      .map((slot) => renderProfileSlotCard(slot, getProfileEquippedItem(slot)))
      .join("")}</div>
  `;
}

function renderProfileInventory() {
  const box = document.getElementById("profile-inventory");
  if (!box) return;

  const waifu = profileState.currentProfile?.main_waifu;
  const allItems = Array.isArray(profileState.inventory) ? profileState.inventory.slice() : [];
  const capacity = getProfileBagCapacity(waifu?.level);
  const maxAvailable = Math.min(allItems.length, capacity.cells);
  const visiblePool = allItems.slice(0, maxAvailable);
  const filtered = visiblePool
    .filter((item) => profileState.inventoryFilters[getProfileItemCategory(item)])
    .sort(compareProfileInventoryItems);
  const pageSize = getProfileBagPageSize();
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize) || 1);
  profileState.inventoryPage = Math.max(1, Math.min(profileState.inventoryPage, totalPages));
  const start = (profileState.inventoryPage - 1) * pageSize;
  const pageItems = filtered.slice(start, start + pageSize);

  box.classList.remove("placeholder");
  box.className = `profile-bag-grid mode-${profileState.viewMode}`;

  if (!filtered.length) {
    box.innerHTML = `<div class="placeholder" style="grid-column:1 / -1;">Нет предметов по выбранным фильтрам.</div>`;
  } else {
    const cells = [];
    pageItems.forEach((item) => {
      const rarity = rarityClass(item?.rarity);
      const name = escapeHtml(String(item?.display_name || item?.name || "Предмет"));
      const iconHtml = itemImageUrl(item) ? `<img src="${escapeHtml(itemImageUrl(item))}" alt="" />` : "📦";
      const upgrade = isProfileUpgradeItem(item);
      const locked = item?.can_equip === false;
      cells.push(`
        <button type="button" class="item-card ${rarity} ${locked ? "empty" : ""}" title="${name}" onclick="WaifuApp.openItemById(${Number(
          item?.id || 0
        )})">
          <div class="item-icon">${iconHtml}</div>
          ${upgrade ? `<div class="upgrade-arrow" title="Улучшение относительно экипировки">▲</div>` : ""}
          <div class="item-level">lvl ${item?.level ?? "?"}</div>
          <div class="item-name">${name}</div>
        </button>
      `);
    });
    for (let i = pageItems.length; i < pageSize; i += 1) {
      cells.push(`<div class="item-card empty" aria-hidden="true"><div class="item-icon">—</div></div>`);
    }
    box.innerHTML = cells.join("");
  }

  setText("profile-bag-capacity", `Ячейки: ${capacity.cells}`);
  setText(
    "profile-inventory-summary",
    `Доступно ${maxAvailable}/${allItems.length} предметов · страница ${profileState.inventoryPage}/${totalPages}`
  );
  setText("profile-page-status", `Страница ${profileState.inventoryPage}/${totalPages}`);

  const prevBtn = document.getElementById("profile-page-prev");
  const nextBtn = document.getElementById("profile-page-next");
  if (prevBtn) prevBtn.disabled = profileState.inventoryPage <= 1;
  if (nextBtn) nextBtn.disabled = profileState.inventoryPage >= totalPages;

  document.getElementById("profile-filter-weapon")?.classList.toggle("active", profileState.inventoryFilters.weapon);
  document.getElementById("profile-filter-armor")?.classList.toggle("active", profileState.inventoryFilters.armor);
  document.getElementById("profile-filter-accessory")?.classList.toggle("active", profileState.inventoryFilters.accessory);
  const sortSelect = document.getElementById("profile-sort-select");
  if (sortSelect) sortSelect.value = profileState.inventorySort;
  const dirBtn = document.getElementById("profile-sort-direction");
  if (dirBtn) dirBtn.textContent = profileState.inventorySortDir === "asc" ? "▲" : "▼";
}

function openProfileSlot(slot) {
  const item = getProfileEquippedItem(slot);
  if (item) {
    openItemModal(item);
    return;
  }
  openSlotModal(slot);
}

function openItemById(itemId) {
  const item = (profileState.inventory || []).find((candidate) => Number(candidate?.id) === Number(itemId));
  if (item) openItemModal(item);
}

function toggleProfileInventoryMode() {
  profileState.viewMode = profileState.viewMode === "compact" ? "expanded" : "compact";
  profileState.inventoryPage = 1;
  writeProfileInventoryMode(profileState.viewMode);
  renderProfileEquipment();
  renderProfileInventory();
}

function toggleProfileInventoryFilter(category) {
  if (!Object.prototype.hasOwnProperty.call(profileState.inventoryFilters, category)) return;
  profileState.inventoryFilters[category] = !profileState.inventoryFilters[category];
  profileState.inventoryPage = 1;
  renderProfileInventory();
}

function setProfileInventorySort(value) {
  profileState.inventorySort = ["level", "rarity", "equipability"].includes(value) ? value : "equipability";
  profileState.inventoryPage = 1;
  renderProfileInventory();
}

function toggleProfileInventorySortDir() {
  profileState.inventorySortDir = profileState.inventorySortDir === "asc" ? "desc" : "asc";
  renderProfileInventory();
}

function changeProfileInventoryPage(delta) {
  profileState.inventoryPage = Math.max(1, profileState.inventoryPage + safeNumber(delta, 0));
  renderProfileInventory();
}

async function populateProfile(profile) {
  const p = profile || (await loadProfile());
  const w = p?.main_waifu;
  if (!w) {
    window.location.href = "./waifu_generator.html";
    return;
  }

  profileState.currentProfile = p;
  profileState.currentDetails = p?.main_waifu_details || null;
  profileState.viewMode = readProfileInventoryMode();

  setText("profile-name", w.name || "—");
  setText("profile-level", w.level ?? "—");
  setText("profile-energy", w.energy != null && w.max_energy != null ? `${w.energy}/${w.max_energy}` : "—");

  const clsId = Number(w.class_ ?? w.class);
  const raceId = Number(w.race);
  const clsEl = document.getElementById("profile-class-icon");
  if (clsEl) {
    clsEl.textContent = classIcon(clsId);
    clsEl.title = className(clsId);
  }
  const raceEl = document.getElementById("profile-race-icon");
  if (raceEl) {
    raceEl.textContent = raceIcon(raceId);
    raceEl.title = raceName(raceId);
  }

  renderProfilePortrait(w);
  renderProfileHeroBars(w, profileState.currentDetails);
  renderStatsStrip("profile-stats-strip", w, profileState.currentDetails);
  renderStatsBreakdown("profile-stats-breakdown", w, profileState.currentDetails);
  renderProfileIndicators(w, profileState.currentDetails);
  renderProfileStatistics();
  switchProfileInfoTab(profileState.infoTab);

  const eq = await apiFetch(`/waifu/equipment`);
  const equipped = Array.isArray(eq?.equipped) ? eq.equipped : [];
  const inventory = Array.isArray(eq?.inventory) ? eq.inventory : [];
  profileState.inventory = inventory;
  profileState.equippedBySlot = {};
  equipped.forEach((it) => {
    if (it?.equipment_slot != null) profileState.equippedBySlot[Number(it.equipment_slot)] = it;
  });
  profileState.inventoryPage = 1;

  renderProfileEquipment();
  renderProfileInventory();

  try {
    const tab = new URLSearchParams(window.location.search).get("tab");
    if (tab) switchProfileTab(tab);
  } catch {
    // ignore
  }
}

async function openSlotModal(slot) {
  profileState.selectedSlot = slot;
  const modal = document.getElementById("slot-modal");
  const body = document.getElementById("slot-modal-body");
  if (!modal || !body) return;

  setText("slot-modal-title", `Подходящие предметы: ${EQUIPMENT_SLOT_NAMES[slot] || `Слот ${slot}`}`);
  setText("slot-modal-subtitle", "Список предметов из сумки, подходящих для данного слота.");
  body.innerHTML = `<div class="placeholder">Загрузка...</div>`;
  modal.style.display = "grid";

  const data = await apiFetch(`/waifu/equipment/available?slot=${slot}`);
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    body.innerHTML = `<div class="placeholder">Нет подходящих предметов для этого слота.</div>`;
    return;
  }

  body.innerHTML = items
    .map((item) => {
      const canEquip = item?.can_equip !== false;
      const errs = Array.isArray(item?.requirement_errors) ? item.requirement_errors : [];
      const name = escapeHtml(String(item?.display_name || item?.name || "Предмет"));
      const image = itemImageUrl(item);
      const upgrade = isProfileUpgradeItem(item);
      return `
        <div class="list-item ${rarityClass(item?.rarity)}" style="display:grid; gap:10px;">
          <div style="display:flex; gap:12px; align-items:center;">
            <div class="item-icon" style="width:54px; height:54px;">${image ? `<img src="${escapeHtml(image)}" alt="" />` : "📦"}</div>
            <div style="min-width:0; flex:1;">
              <strong>${name}</strong>
              <div class="muted tiny">Ур. ${item?.level ?? "—"} · ${escapeHtml(slotTypeLabel(item?.slot_type))}</div>
              ${upgrade ? `<div class="profile-modal-upgrade tiny">▲ Выше уровня текущей экипировки</div>` : ""}
              ${errs.length ? `<div class="muted tiny">${errs.map((err) => escapeHtml(String(err))).join("<br/>")}</div>` : ""}
            </div>
            <button class="primary" style="width:auto;" ${canEquip ? "" : "disabled"} onclick="WaifuApp.equipItemToProfileSlot(${Number(
              item?.id || 0
            )}, ${slot})">Экипировать</button>
          </div>
        </div>
      `;
    })
    .join("");
}

async function equipItemToProfileSlot(itemId, slot) {
  await apiFetch(`/waifu/equipment/equip?inventory_item_id=${itemId}&slot=${slot}`, { method: "POST" });
  closeSlotModal();
  closeItemModal();
  await bootstrapPage("profile", populateProfile);
}

function openProfileSlotReplacementFromModal() {
  const item = profileState.selectedItem;
  if (!item?.equipment_slot) return;
  closeItemModal();
  openSlotModal(Number(item.equipment_slot));
}

function estimateProfileSellPrice(item) {
  const charm = safeNumber(profileState.currentProfile?.main_waifu?.charm, 0);
  const baseValue = 100 * Math.max(1, safeNumber(item?.tier, 1)) * Math.max(1, safeNumber(item?.rarity, 1));
  const discountPct = Math.max(0, Math.min(50, charm - 10));
  const multiplier = 0.5 + (discountPct / 50) * 0.4;
  return Math.floor(baseValue * multiplier);
}

function openItemModal(item) {
  profileState.selectedItem = item;
  profileState.equipSlotChoice = null;
  const modal = document.getElementById("item-modal");
  const body = document.getElementById("item-modal-body");
  if (!modal || !body) return;

  const displayName = String(item?.display_name || "").trim() || composeItemDisplayName(item);
  const slotTypeRaw = item?.slot_type ? String(item.slot_type) : "";
  const slotType = slotTypeRaw ? slotTypeLabel(slotTypeRaw) : "—";
  const slotName =
    item?.equipment_slot != null
      ? EQUIPMENT_SLOT_NAMES[Number(item.equipment_slot)] || String(item.equipment_slot)
      : "Сумка";
  const errs = Array.isArray(item?.requirement_errors) ? item.requirement_errors : [];
  const isEquipped = item?.equipment_slot != null;
  const possibleSlots = !isEquipped && item?.slot_type ? SLOT_TYPE_TO_SLOTS[item.slot_type] || [] : [];
  const canEquip = !isEquipped && item?.can_equip !== false && possibleSlots.length > 0;

  setText("item-modal-name", displayName || "—");
  setText("item-modal-rarity", item?.rarity != null ? rarityLabel(item.rarity) : "—");
  setText("item-modal-level", item?.level != null ? `lvl ${item.level}` : "—");
  setText("item-modal-type", slotType);
  setText("item-modal-slot", slotName);

  const art = document.getElementById("item-modal-art");
  if (art) art.innerHTML = itemArtHtml(item);

  const content = document.getElementById("item-modal-content");
  if (content) {
    ["rarity-common", "rarity-uncommon", "rarity-rare", "rarity-epic", "rarity-legendary"].forEach((cls) => {
      content.classList.remove(cls);
    });
    content.classList.add(rarityClass(item?.rarity));
  }

  let slotPickerHtml = "";
  if (!isEquipped && item?.slot_type) {
    if (possibleSlots.length === 1) {
      profileState.equipSlotChoice = possibleSlots[0];
      slotPickerHtml = `<div class="detail-row"><span class="muted">Слот экипировки</span><strong>${EQUIPMENT_SLOT_NAMES[possibleSlots[0]]}</strong></div>`;
    } else if (possibleSlots.length > 1) {
      const emptySlot = possibleSlots.find((slot) => !getProfileEquippedItem(slot));
      profileState.equipSlotChoice = emptySlot ?? possibleSlots[0];
      slotPickerHtml = `
        <label class="form-field" style="display:block; margin-top:10px;">
          <div class="muted tiny">Куда надеть</div>
          <select id="item-modal-slot-select">
            ${possibleSlots
              .map((slot) => {
                const occupied = getProfileEquippedItem(slot);
                const text = occupied
                  ? `${EQUIPMENT_SLOT_NAMES[slot]} (занято: ${escapeHtml(String(occupied?.display_name || occupied?.name || "предмет"))})`
                  : `${EQUIPMENT_SLOT_NAMES[slot]} (свободно)`;
                return `<option value="${slot}" ${slot === profileState.equipSlotChoice ? "selected" : ""}>${text}</option>`;
              })
              .join("")}
          </select>
        </label>
      `;
    }
  }

  const bonusesHtml = renderItemBonusesHtml(item);
  const weaponStatsHtml = renderWeaponStatsHtml(item);
  const upgrade = !isEquipped && isProfileUpgradeItem(item);
  const sellConfirmHtml = !isEquipped && profileState.sellConfirm
    ? `
      <div class="profile-item-actions">
        <div class="detail-row"><span class="muted">Цена продажи</span><strong>🪙 ${estimateProfileSellPrice(item)}</strong></div>
        <button class="primary" onclick="WaifuApp.confirmSellSelectedItem()">Подтвердить продажу</button>
        <button class="secondary" onclick="WaifuApp.toggleItemSellConfirm()">Отмена</button>
      </div>
    `
    : "";

  body.innerHTML = `
    <div class="detail-row"><span class="muted">Редкость</span><strong>${escapeHtml(rarityLabel(item?.rarity))}</strong></div>
    <div class="detail-row"><span class="muted">Tier</span><strong>${item?.tier ?? "—"}</strong></div>
    ${upgrade ? `<div class="profile-modal-upgrade">▲ Предмет выше уровня текущей экипировки</div>` : ""}
    ${weaponStatsHtml}
    ${bonusesHtml}
    ${slotPickerHtml}
    ${errs.length ? `<div class="muted tiny">${errs.map((err) => escapeHtml(String(err))).join("<br/>")}</div>` : ""}
    ${sellConfirmHtml}
  `;

  const sellBtn = document.getElementById("item-modal-sell");
  const unequipBtn = document.getElementById("item-modal-unequip");
  const replaceBtn = document.getElementById("item-modal-replace");
  const equipBtn = document.getElementById("item-modal-equip");
  if (sellBtn) sellBtn.style.display = isEquipped ? "none" : "";
  if (unequipBtn) unequipBtn.style.display = isEquipped ? "" : "none";
  if (replaceBtn) replaceBtn.style.display = isEquipped ? "" : "none";
  if (equipBtn) {
    equipBtn.style.display = canEquip ? "" : "none";
    equipBtn.textContent = "Надеть";
  }

  const select = document.getElementById("item-modal-slot-select");
  if (select) {
    select.addEventListener("change", () => {
      profileState.equipSlotChoice = Number(select.value);
    });
  }

  modal.style.display = "grid";
}

function toggleItemSellConfirm() {
  profileState.sellConfirm = !profileState.sellConfirm;
  if (profileState.selectedItem) openItemModal(profileState.selectedItem);
}

async function confirmSellSelectedItem() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  await apiFetch(`/inventory/sell`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inventory_item_ids: [item.id] }),
  });
  closeItemModal();
  await bootstrapPage("profile", populateProfile);
}

async function unequipItemFromModal() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  await apiFetch(`/waifu/equipment/unequip?inventory_item_id=${item.id}`, { method: "POST" });
  closeItemModal();
  await bootstrapPage("profile", populateProfile);
}

async function equipItemFromModal() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  const slots = SLOT_TYPE_TO_SLOTS[item.slot_type] || [];
  if (!slots.length) return;

  const chosen = profileState.equipSlotChoice || slots[0];
  try {
    await apiFetch(`/waifu/equipment/equip?inventory_item_id=${item.id}&slot=${chosen}`, { method: "POST" });
  } catch (e) {
    const body = document.getElementById("item-modal-body");
    if (body) body.innerHTML += `<div class="muted" style="margin-top:10px;">Ошибка экипировки: ${escapeHtml(String(e?.message || e))}</div>`;
    return;
  }
  closeItemModal();
  await bootstrapPage("profile", populateProfile);
}

async function resetMainWaifu() {
  await apiFetch(`/profile/main-waifu`, { method: "DELETE" });
  window.location.href = "./waifu_generator.html";
}

function initWaifuGenerator() {
  const nameInput = document.getElementById("waifu-name-input");
  const classSel = document.getElementById("waifu-class-select");
  const raceSel = document.getElementById("waifu-race-select");
  const statsBox = document.getElementById("waifu-stats");
  const summary = document.getElementById("waifu-summary");
  const btn = document.getElementById("waifu-create-btn");

  if (!nameInput || !classSel || !raceSel || !statsBox || !btn) return;

  classSel.innerHTML = WAIFU_CLASSES.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  raceSel.innerHTML = WAIFU_RACES.map((r) => `<option value="${r.id}">${r.name}</option>`).join("");

  const recalc = () => {
    const name = nameInput.value.trim();
    const race = Number(raceSel.value);
    const cls = Number(classSel.value);
    const base = { strength: 10, agility: 10, intelligence: 10, endurance: 10, charm: 10, luck: 10 };
    const rb = WAIFU_RACE_BONUSES[race] || {};
    const cb = WAIFU_CLASS_BONUSES[cls] || {};
    const cur = { ...base };
    Object.entries(rb).forEach(([k, v]) => (cur[k] = (cur[k] || 0) + v));
    Object.entries(cb).forEach(([k, v]) => (cur[k] = (cur[k] || 0) + v));

    if (summary) summary.textContent = `${className(cls)} / ${raceName(race)}`;
    statsBox.innerHTML = [
      ["СИЛ", cur.strength],
      ["ЛОВ", cur.agility],
      ["ИНТ", cur.intelligence],
      ["ВЫН", cur.endurance],
      ["ОБА", cur.charm],
      ["УДЧ", cur.luck],
    ]
      .map(([k, v]) => `<div class="stat-card"><span class="muted">${k}</span><strong>${v}</strong></div>`)
      .join("");

    btn.disabled = !name;
  };

  nameInput.addEventListener("input", recalc);
  classSel.addEventListener("change", recalc);
  raceSel.addEventListener("change", recalc);
  recalc();
}

async function submitWaifuCreation() {
  const nameInput = document.getElementById("waifu-name-input");
  const classSel = document.getElementById("waifu-class-select");
  const raceSel = document.getElementById("waifu-race-select");
  const errBox = document.getElementById("waifu-create-error");
  const btn = document.getElementById("waifu-create-btn");
  if (!nameInput || !classSel || !raceSel) return;

  const payload = {
    name: nameInput.value.trim(),
    race: Number(raceSel.value),
    class: Number(classSel.value),
  };

  if (btn) btn.disabled = true;
  if (errBox) errBox.textContent = "";
  try {
    await apiFetch(`/profile/main-waifu`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    window.location.href = "./profile.html";
  } catch (e) {
    if (errBox) errBox.textContent = String(e?.message || e);
    if (btn) btn.disabled = false;
  }
}

async function loadSkills(act) {
  const data = await apiFetch(`/skills/available?act=${act}`);
  const list = document.getElementById("skills-list");
  if (!list) return data;
  list.innerHTML = "";
  data.skills.forEach((s) => {
    const li = document.createElement("div");
    li.className = "list-item";
    li.innerHTML = `<strong>${s.name}</strong> — tier ${s.tier}, тип ${s.skill_type}, энергия ${s.energy_cost || "-"}, КД ${s.cooldown || "-"}<br/>
      <span class="muted">${s.description || ""}</span>`;
    list.appendChild(li);
  });
  return data;
}

async function searchGuilds(query) {
  const qs = query ? `?query=${encodeURIComponent(query)}` : "";
  const data = await apiFetch(`/guilds/search${qs}`);
  const list = document.getElementById("guild-search-results");
  if (!list) return data;
  list.innerHTML = "";
  data.guilds.forEach((g) => {
    const li = document.createElement("div");
    li.className = "list-item";
    li.innerHTML = `<strong>[${g.tag}] ${g.name}</strong> — ур. ${g.level}, рекрутинг: ${g.is_recruiting ? "да" : "нет"}`;
    list.appendChild(li);
  });
  return data;
}

async function initPage(page) {
  applyTheme();
  if (tg) {
    tg.ready();
    tg.expand();
  }
  setActiveNav(page);
  connectSSE();

  // Reveal admin-only controls for the admin Telegram ID.
  if (isAdminUser()) {
    document.querySelectorAll(".admin-only").forEach((el) => {
      el.style.display = "";
    });
  }

  // Passive UI refresh: regen is time-based but applied on API calls.
  // Keep numbers fresh without forcing full-page reload.
  if (!window.__waifuProfileAutoRefresh) {
    window.__waifuProfileAutoRefresh = setInterval(async () => {
      try {
        const p = await loadProfile();
        const w = p?.main_waifu;
        if (!w) return;
        // If we're on profile screen, refresh visible stat widgets without refetching inventory/equipment.
        if (window.location.pathname.endsWith("/profile.html")) {
          profileState.currentProfile = { ...(profileState.currentProfile || {}), ...p };
          profileState.currentDetails = p?.main_waifu_details || profileState.currentDetails || null;
          renderProfilePortrait(w);
          renderProfileHeroBars(w, profileState.currentDetails);
          renderStatsStrip("profile-stats-strip", w, profileState.currentDetails);
          if (document.getElementById("profile-stats-breakdown")) {
            renderStatsBreakdown("profile-stats-breakdown", w, profileState.currentDetails);
          }
          renderProfileIndicators(w, profileState.currentDetails);
        }
      } catch {
        // ignore periodic refresh failures
      }
    }, 60_000);
  }
}

async function adminKillMonster() {
  const payload = await apiFetch(`/admin/dungeons/kill-monster`, { method: "POST" });
  if (payload?.dungeon_completed) openRewardModal(payload);
  await refreshSoloActive().catch(() => {});
}

async function adminCompleteDungeon() {
  const payload = await apiFetch(`/admin/dungeons/complete`, { method: "POST" });
  if (payload?.dungeon_completed) openRewardModal(payload);
  await refreshSoloActive().catch(() => {});
}

// Expose helpers globally for inline usage (merge, don't clobber handlers assigned earlier)
window.WaifuApp = Object.assign(window.WaifuApp || {}, {
  initPage,
  bootstrapPage,
  loadProfile,
  renderAtticDungeon,
  renderAtticExpeditions,
  refreshAtticChips,
  loadShop,
  loadTavern,
  switchTavernTab,
  hireFromTavern,
  openTavernWaifuModal,
  closeTavernWaifuModal,
  tavernWaifuModalAction,
  closeTavernSlotModal,
  adminRefreshTavern,
  loadDungeons,
  startDungeon,
  loadActiveDungeon,
  continueActiveDungeon,
  exitDungeon,
  openExitDungeonConfirm,
  closeExitDungeonConfirm,
  confirmExitDungeon,
  adminExitDungeon,
  loadBattle,
  continueBattle,
  exitBattle,
  switchShopTab,
  switchProfileTab,
  switchProfileInfoTab,
  showTab,
  loadExpeditionTab,
  closeExpeditionModal,
  startExpedition,
  populateProfile,
  toggleProfileStatTooltip,
  toggleProfileStatAccordion,
  toggleProfileInventoryMode,
  toggleProfileInventoryFilter,
  setProfileInventorySort,
  toggleProfileInventorySortDir,
  changeProfileInventoryPage,
  openProfileSlot,
  openItemById,
  closeSlotModal,
  closeItemModal,
  equipItemToProfileSlot,
  unequipItemFromModal,
  equipItemFromModal,
  openProfileSlotReplacementFromModal,
  toggleItemSellConfirm,
  confirmSellSelectedItem,
  resetMainWaifu,
  initWaifuGenerator,
  submitWaifuCreation,
  closeShopModal,
  confirmBuy,
  refreshShopDebug,
  adminAddGold,
  adminKillMonster,
  adminCompleteDungeon,
  sellSelected,
  gambleShop,
  loadSkills,
  searchGuilds,
  apiFetch,
  getInitData,
  spendStatPoint,
  populateDungeonsPage,
  refreshSoloActive,
  closeRewardModal,
  openInventoryFromReward,
  loadExpeditionTab,
  openExpeditionStartModal,
  closeExpeditionStartModal,
  submitExpeditionStart,
  claimExpedition,
  cancelExpedition,
  adminRefreshExpeditions,
});
