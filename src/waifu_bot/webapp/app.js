// Basic Telegram WebApp bootstrap + shared UI helpers + API/SSE wiring
// Если https://telegram.org/js/telegram-web-app.js не загрузился (сеть, блокировка), не оставляем Telegram.WebApp пустым — initPage вызывает tg.ready().
(function waifuTelegramWebAppStub() {
  if (typeof window === "undefined") return;
  window.Telegram = window.Telegram || {};
  if (window.Telegram.WebApp && typeof window.Telegram.WebApp.ready === "function") return;
  window.Telegram.WebApp = {
    ready() {},
    expand() {},
    initData: "",
    initDataUnsafe: {},
    colorScheme: "dark",
    showPopup(opts) {
      const m = opts && (opts.message || opts.title);
      if (m) alert(String(m));
    },
  };
})();
const tg = window.Telegram?.WebApp;

/**
 * Steam desktop client (Electron, desktop_client/) detection.
 *
 * The Electron preload script exposes `window.waifuDesktop` via contextBridge
 * (see desktop_client/preload.js). `?desktopClient=1` is a manual override for
 * testing the desktop branch in a plain browser (dev/stage only server-side,
 * see api/deps.py X-Steam-Ticket-Dev gating).
 *
 * Everything below is purely additive: when neither is present (the existing
 * Telegram WebApp / browser-with-devPlayerId flows), behavior is unchanged.
 */
function isDesktopClient() {
  try {
    if (window.waifuDesktop) return true;
    return new URLSearchParams(window.location.search).get("desktopClient") === "1";
  } catch {
    return false;
  }
}

function isMobileClient() {
  try {
    if (window.waifuMobile) return true;
    const q = new URLSearchParams(window.location.search);
    return q.get("mobileClient") === "1" || q.get("economy") === "activity";
  } catch {
    return false;
  }
}

function getClientEconomy() {
  if (isMobileClient() || isDesktopClient()) return "activity";
  try {
    const eco = new URLSearchParams(window.location.search).get("economy");
    if (eco === "activity") return "activity";
  } catch {
    /* ignore */
  }
  return "telegram";
}

/** Bonus channel for inventory resolve / remap (telegram | steam | mobile). */
function getClientChannel() {
  if (isMobileClient()) return "mobile";
  if (isDesktopClient()) return "steam";
  return "telegram";
}

function getMobileSessionTokenSync() {
  try {
    const fromMobile = window.waifuMobile?.getDesktopSessionToken?.();
    if (fromMobile) return String(fromMobile);
    if (typeof localStorage !== "undefined") {
      const fromLs = localStorage.getItem("waifuDesktopSession");
      if (fromLs) return String(fromLs);
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** Redirect Capacitor/mobile pages to login when desktop_session is missing. */
function requireMobileSessionOrRedirect() {
  if (!isMobileClient()) return true;
  try {
    const path = String(window.location.pathname || "");
    if (path.includes("/mobile/login.html")) return true;
  } catch {
    /* ignore */
  }
  if (getMobileSessionTokenSync()) return true;
  window.location.replace("/webapp/mobile/login.html?mobileClient=1");
  return false;
}

/** Desktop tab pages live under webapp/steam/ unless already on a steam layout. */
function steamRelativePage(page) {
  const inSteamDir =
    document.body?.classList?.contains("page-steam-shell") ||
    document.body?.classList?.contains("page-steam-waifu-gen");
  if (isDesktopClient() && !inSteamDir) return `./steam/${page}`;
  return `./${page}`;
}

/** Mobile dedicated pages under webapp/mobile/. */
function mobileRelativePage(page) {
  const inMobileDir =
    document.body?.classList?.contains("page-mobile-shell") ||
    document.body?.classList?.contains("page-mobile-login");
  if (isMobileClient() && !inMobileDir) {
    if (page === "activity" || page === "index" || page === "home") {
      return `/webapp/mobile/shell.html?mobileClient=1`;
    }
    if (page === "login") return `/webapp/mobile/login.html?mobileClient=1`;
    return `/webapp/mobile/shell.html?mobileClient=1`;
  }
  return `./${page}`;
}

const API_BASE = "/api";
/** Синхронно с waifu_bot.game.constants (EXP_BASE, MAX_LEVEL). */
const PLAYER_EXP_BASE = 16;
const PLAYER_MAX_LEVEL = 60;
const GAME_STATIC_BASE = "/static/game";

/** Synced with CACHE_VERSION in sw.js (bump via scripts/bump_webapp_version.sh). */
function resolveWebappShellVersion() {
  if (typeof window !== "undefined" && window.WAIFU_WEBAPP_VERSION) {
    return String(window.WAIFU_WEBAPP_VERSION);
  }
  if (typeof document !== "undefined") {
    try {
      for (const el of document.querySelectorAll('script[src], link[href]')) {
        const u = el.src || el.href || "";
        const m = u.match(/[?&]v=(waifu-webapp-v\d+)/);
        if (m) return m[1];
      }
    } catch (_) {
      /* ignore */
    }
  }
  return "waifu-webapp-v45";
}

const WAIFU_WEBAPP_VERSION = resolveWebappShellVersion();
if (typeof window !== "undefined") {
  window.WAIFU_WEBAPP_VERSION = WAIFU_WEBAPP_VERSION;
  window.monsterArtVersion = window.monsterArtVersion || {};
}

(function applyDesktopClientTheme() {
  if (typeof document === "undefined" || !isDesktopClient()) return;
  document.documentElement.classList.add("desktop-client");
  try {
    const mode = new URLSearchParams(window.location.search).get("desktopMode");
    document.documentElement.classList.add(mode === "overlay" ? "desktop-overlay" : "desktop-window");
  } catch {
    document.documentElement.classList.add("desktop-window");
  }
  try {
    if (!document.querySelector("link[data-desktop-theme]")) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `/webapp/desktop-theme.css?v=${WAIFU_WEBAPP_VERSION}`;
      link.setAttribute("data-desktop-theme", "1");
      document.head.appendChild(link);
    }
  } catch {
    /* ignore */
  }
})();

(function applyMobileClientTheme() {
  if (typeof document === "undefined" || !isMobileClient()) return;
  document.documentElement.classList.add("mobile-client");
  document.documentElement.classList.add("economy-activity");
  try {
    if (!document.querySelector("link[data-mobile-theme]")) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `/webapp/mobile-theme.css?v=${WAIFU_WEBAPP_VERSION}`;
      link.setAttribute("data-mobile-theme", "1");
      document.head.appendChild(link);
    }
  } catch {
    /* ignore */
  }
})();

// Mobile auth gate (after helpers below are defined — deferred microtask)
queueMicrotask(() => {
  try {
    if (typeof requireMobileSessionOrRedirect === "function") {
      requireMobileSessionOrRedirect();
    }
  } catch {
    /* ignore */
  }
});
const CARAVAN_STATIC_BASE = `${GAME_STATIC_BASE}/ui/caravan`;
const DUNGEONS_STATIC_BASE = `${GAME_STATIC_BASE}/dungeons`;
const SHOP_STATIC_BASE = `${GAME_STATIC_BASE}/ui/shop`;
const TAVERN_STATIC_BASE = `${GAME_STATIC_BASE}/ui/tavern`;
const NAV_STATIC_BASE = `${GAME_STATIC_BASE}/ui/nav`;
const EXPEDITION_BIOMES_BASE = `${GAME_STATIC_BASE}/expeditions/biomes`;
const EXPEDITION_ARCHETYPES_BASE = `${GAME_STATIC_BASE}/expeditions/archetypes`;
/** Cache-bust для свежесгенерированных артов архетипов (archetype_id -> v). */
const expeditionArchetypeArtVersion = {};
/** Имена файлов в `static/game/ui/tavern/audio/` (добавьте MP3 на сервер). */
const TAVERN_BGM_TRACKS = ["tavern-01.mp3", "tavern-02.mp3", "tavern-03.mp3"];

const ITEM_ART_GEN_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 3v3"/><path d="M12 18v3"/><path d="M3 12h3"/><path d="M18 12h3"/><path d="m5.6 5.6 2.1 2.1"/><path d="m16.3 16.3 2.1 2.1"/><path d="m5.6 18.4 2.1-2.1"/><path d="m16.3 7.7 2.1-2.1"/><circle cx="12" cy="12" r="3"/></svg>`;

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

function initNavIcons() {
  document.querySelectorAll(".nav.basement a[data-page]").forEach((link) => {
    const page = String(link.dataset.page || "").trim();
    if (!page) return;
    const title = String(link.getAttribute("title") || link.getAttribute("aria-label") || page).trim();
    if (title && !link.getAttribute("aria-label")) {
      link.setAttribute("aria-label", title);
    }
    let img = link.querySelector("img.nav-icon");
    if (!img) {
      img = document.createElement("img");
      img.className = "nav-icon";
      img.alt = "";
      img.decoding = "async";
      link.textContent = "";
      link.appendChild(img);
    }
    img.src = `${NAV_STATIC_BASE}/${page}.webp?v=${WAIFU_WEBAPP_VERSION}`;
  });
}

function getInitData() {
  const fromTelegram = tg?.initData || tg?.initDataUnsafe?.query_id ? tg.initData : null;
  const fromQuery = new URLSearchParams(window.location.search).get("initData");
  return fromTelegram || fromQuery || "";
}

/** Только для локальной отладки: при APP_ENV=dev сервер принимает заголовок X-Player-Id (см. api/deps.py). */
function getDevPlayerIdFromQuery() {
  try {
    const raw = new URLSearchParams(window.location.search).get("devPlayerId");
    if (raw == null || raw === "") return null;
    const n = parseInt(String(raw), 10);
    if (!Number.isFinite(n) || n <= 0) return null;
    return n;
  } catch {
    return null;
  }
}


/**
 * Desktop/mobile session token for X-Desktop-Session (and Steam ticket fallbacks).
 */
function getDesktopSessionTokenSync() {
  if (!isDesktopClient() && !isMobileClient()) return null;
  try {
    const fromMobile = window.waifuMobile?.getDesktopSessionToken?.();
    if (fromMobile) return String(fromMobile);
    const fromBridge = window.waifuDesktop?.getDesktopSessionToken?.();
    if (fromBridge) return String(fromBridge);
    if (typeof localStorage !== "undefined") {
      const fromLs = localStorage.getItem("waifuDesktopSession");
      if (fromLs) return String(fromLs);
    }
  } catch {
    /* ignore */
  }
  return null;
}

let _desktopSessionReadyPromise = null;

async function ensureDesktopSessionReady() {
  if (!isDesktopClient() && !isMobileClient()) return null;
  const sync = getDesktopSessionTokenSync();
  if (sync) return sync;
  if (!_desktopSessionReadyPromise) {
    _desktopSessionReadyPromise = (async () => {
      try {
        if (typeof window.waifuMobile?.whenDesktopSessionReady === "function") {
          const t = await window.waifuMobile.whenDesktopSessionReady();
          if (t) return String(t);
        }
        if (typeof window.waifuDesktop?.whenDesktopSessionReady === "function") {
          const t = await window.waifuDesktop.whenDesktopSessionReady();
          if (t) return String(t);
        }
        if (typeof window.waifuDesktop?.getDesktopSessionTokenAsync === "function") {
          const t = await window.waifuDesktop.getDesktopSessionTokenAsync();
          if (t) return String(t);
        }
      } catch {
        /* ignore */
      }
      return getDesktopSessionTokenSync();
    })().finally(() => {
      _desktopSessionReadyPromise = null;
    });
  }
  return _desktopSessionReadyPromise;
}

function getDesktopSteamAuthHeader() {
  if (!isDesktopClient() && !isMobileClient()) return null;
  try {
    const session = getDesktopSessionTokenSync();
    if (session) return { name: "X-Desktop-Session", value: String(session) };
    const real = window.waifuDesktop?.getSteamTicket?.();
    if (real) return { name: "X-Steam-Ticket", value: String(real) };
    const devStub = window.waifuDesktop?.steamTicketDev
      || new URLSearchParams(window.location.search).get("steamTicketDev");
    if (devStub) return { name: "X-Steam-Ticket-Dev", value: String(devStub) };
  } catch {
    /* ignore */
  }
  return null;
}

function authHeaders() {
  const headers = {};
  // Mobile/desktop: prefer desktop session so Capacitor never falls into TG initData 401.
  if (isMobileClient() || isDesktopClient()) {
    const steamAuth = getDesktopSteamAuthHeader();
    if (steamAuth) {
      headers[steamAuth.name] = steamAuth.value;
      return headers;
    }
  }
  const initData = getInitData();
  if (initData) {
    headers["X-Telegram-Init-Data"] = initData;
  } else {
    const devPid = getDevPlayerIdFromQuery();
    if (devPid != null) {
      headers["X-Player-Id"] = String(devPid);
    } else {
      const steamAuth = getDesktopSteamAuthHeader();
      if (steamAuth) headers[steamAuth.name] = steamAuth.value;
    }
  }
  return headers;
}

async function apiFetch(path, options = {}) {
  if (isMobileClient() || isDesktopClient()) {
    await ensureDesktopSessionReady();
  }
  if (isMobileClient() && !getMobileSessionTokenSync()) {
    const p = String(path || "");
    if (!p.startsWith("/auth/")) {
      requireMobileSessionOrRedirect();
      throw new Error("mobile_session_required");
    }
  }
  const opts = { ...options };
  opts.headers = { ...(options.headers || {}), ...authHeaders() };
  if (
    opts.body &&
    typeof opts.body === "string" &&
    !opts.headers["Content-Type"] &&
    !opts.headers["content-type"]
  ) {
    opts.headers["Content-Type"] = "application/json";
  }
  // Inventory: ask server for client-channel resolve (mobile/steam)
  let urlPath = path;
  if (
    typeof urlPath === "string" &&
    urlPath.startsWith("/inventory") &&
    !urlPath.includes("client=")
  ) {
    const ch = getClientChannel();
    urlPath += (urlPath.includes("?") ? "&" : "?") + `client=${encodeURIComponent(ch)}`;
  }
  const res = await fetch(`${API_BASE}${urlPath}`, opts);
  if (!res.ok) {
    const text = await res.text();
    if (res.status === 401 && isMobileClient()) {
      requireMobileSessionOrRedirect();
    }
    throw new Error(`HTTP ${res.status}: ${text || "failed"}`);
  }
  if (res.status === 204) return null;
  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (ct.includes("application/json")) return res.json();
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (_) {
    return text;
  }
}

function showToast(message, type = "success") {
  const title = type === "error" ? "Ошибка" : "Успех";
  if (window.Telegram?.WebApp?.showPopup) {
    window.Telegram.WebApp.showPopup({ title, message: String(message) });
  } else {
    const el = document.getElementById("expedition-error") || document.getElementById("dungeons-error");
    if (el) {
      el.textContent = message;
      el.style.display = "block";
      el.className = "banner " + (type === "error" ? "banner-danger" : "banner-success");
      setTimeout(() => { el.style.display = "none"; }, 4000);
    } else {
      alert(message);
    }
  }
}

/** Подтверждение действия: Telegram showConfirm в WebApp, иначе window.confirm. */
function confirmAction(message) {
  const tgConfirm = window.Telegram?.WebApp?.showConfirm;
  if (typeof tgConfirm === "function") {
    return new Promise((resolve) => {
      try {
        tgConfirm(String(message), (ok) => resolve(Boolean(ok)));
      } catch (_) {
        resolve(window.confirm(String(message)));
      }
    });
  }
  return Promise.resolve(window.confirm(String(message)));
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setHTML(id, value) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = value;
}

const SECONDARY_STAT_META = {
  crit_chance_pct: { icon: "💥", short: "Крит" },
  evade_pct: { icon: "💨", short: "Укл" },
  dmg_reduce_pct: { icon: "🧱", short: "Сниж. ур." },
  hp_max_pct: { icon: "❤️", short: "HP %" },
  exp_bonus_pct: { icon: "📚", short: "Опыт" },
  gold_bonus_pct: { icon: "🪙", short: "Золото" },
  magic_find_pct: { icon: "✨", short: "MF" },
  media_damage_text_percent: { icon: "✨", short: "Урон от текста" },
  media_damage_sticker_percent: { icon: "✨", short: "Урон от стикеров" },
  media_damage_photo_percent: { icon: "✨", short: "Урон от фото" },
  media_damage_gif_percent: { icon: "✨", short: "Урон от GIF" },
  media_damage_audio_percent: { icon: "✨", short: "Урон от аудио" },
  media_damage_voice_percent: { icon: "✨", short: "Урон от голосовых" },
  media_damage_video_percent: { icon: "✨", short: "Урон от видео" },
  media_damage_link_percent: { icon: "✨", short: "Урон от ссылок" },
};

/** Нормализация опечаток в ключах эффектов из БД/импорта для UI. */
function normalizeEffectKeyUi(s) {
  return String(s || "")
    .trim()
    .toLowerCase()
    .replace(/audioo/g, "audio")
    .replace(/magii/g, "magic");
}

/** Имена узлов пассивного дерева (совпадают с passive_skill_nodes.id); fallback до загрузки дерева. */
const PASSIVE_NODE_DISPLAY_NAMES_RU = {
  w_bash: "Удар",
  w_tough: "Закалка",
  w_cry: "Боевой дух",
  w_heavy: "Тяжёлый удар",
  w_iron: "Железная кожа",
  w_blood: "Кров. ярость",
  w_berserk: "Берсерк",
  w_fort: "Крепость",
  w_last: "Последний рубеж",
  w_wrath: "Гнев героя",
  w_imm: "Бессмертный",
  s_keen: "Острый глаз",
  s_nimble: "Проворство",
  s_media: "Чутьё",
  s_crit_m: "Мастер крита",
  s_shadow: "Шаг тени",
  s_exploit: "Уязвимость",
  s_nth: "Серия смерти",
  s_ghost: "Призрак",
  s_amp: "Усил. медиа",
  s_lethal: "Смерт. удар",
  s_phantom: "Фантом",
  m_arcane: "Аркана",
  m_wisdom: "Мудрость",
  m_trade: "Торговец",
  m_media_m: "Медиамаг",
  m_lore: "Знания",
  m_bargain: "Сделка",
  m_surge: "Маг. всплеск",
  m_cmd: "Командование",
  m_rune: "Рун. броня",
  m_trans: "Трансценд.",
  m_arch: "Архимаг",
};

const PASSIVE_BRANCH_LABELS_RU = {
  warrior: "воина",
  shadow: "тени",
  sage: "мудреца",
};

const MONSTER_FAMILY_LABELS_RU = {
  beast: "зверей",
  construct: "конструктов",
  demon: "демонов",
  dragon: "драконов",
  elemental: "элементалей",
  fae: "фей",
  humanoid: "гуманоидов",
  slime: "слизней",
  undead: "нежити",
};

const MONSTER_FAMILY_TYPE_LABELS_RU = {
  beast: "Зверь",
  construct: "Конструкт",
  demon: "Демон",
  dragon: "Дракон",
  elemental: "Элементаль",
  fae: "Фея",
  humanoid: "Гуманоид",
  slime: "Слизь",
  undead: "Нежить",
};

function formatMonsterTypeLabelRu(raw) {
  const s = String(raw || "").trim();
  if (!s || s === "—") return "";
  const low = s.toLowerCase();
  if (MONSTER_FAMILY_TYPE_LABELS_RU[low]) return MONSTER_FAMILY_TYPE_LABELS_RU[low];
  if (/[а-яё]/i.test(s)) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function setSoloExitBtnVisible(visible) {
  const btn = document.getElementById("solo-exit-btn");
  if (btn) btn.style.display = visible ? "" : "none";
}

function passiveNodeDisplayNameRu(nodeId) {
  const id = String(nodeId || "").trim();
  if (!id) return "";
  const live = typeof findPassiveNodeById === "function" ? findPassiveNodeById(id) : null;
  if (live && live.name) return String(live.name);
  return PASSIVE_NODE_DISPLAY_NAMES_RU[id] || id;
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
  melee_damage_flat: { icon: "⚔️", short: "Урон в ближнем бою" },
  ranged_damage_flat: { icon: "🏹", short: "Урон в дальнем бою" },
  magic_damage_flat: { icon: "🪄", short: "Урон магией" },
  damage_flat: { icon: "⚔️", short: "Доп. урон к оружию" },
  damage_percent: { icon: "⚔️", short: "Доп. урон к оружию %" },
  hp: { icon: "❤️", short: "HP" },
  defense: { icon: "🛡️", short: "Защита" },
  def: { icon: "🛡️", short: "Защита" },
};

// Описания перков экспедиций (id из expedition_data.PERKS). Кратко — что даёт в экспедиции.
const PERK_DESCS = {
  gas_mask: "Снижает штраф от вони и ядовитого воздуха",
  diver: "Снижает штраф в затопленных локациях",
  fireproof: "Снижает штраф в жарких локациях",
  frostproof: "Снижает штраф в ледяных локациях",
  navigator: "Снижает штраф в тумане и шторме",
  desert_walker: "Снижает штраф в пыли и зыбучих песках",
  gas_filter: "Снижает штраф от ядовитого воздуха",
  snow_warrior: "Снижает штраф в снежной буре",
  acid_proof: "Снижает штраф от кислотного дождя",
  wind_walker: "Снижает штраф в штормовых локациях",
  elf_slayer: "Бонус против злых эльфов",
  orc_hunter: "Бонус против орков-берсеркеров",
  priest: "Бонус против нежити",
  demon_slayer: "Бонус против демонов",
  dragonslayer: "Бонус против драконов",
  goblin_shaker: "Бонус против гоблинов",
  troll_slayer: "Бонус против троллей",
  vampire_hunter: "Бонус против вампиров",
  entomologist: "Бонус против гигантских насекомых",
  bat_hunter: "Бонус против летучих мышей",
  mushroom_expert: "Снижает штраф от ядовитых грибов",
  scout: "Снижает штраф от ловушек",
  archaeologist: "Снижает штраф от проклятых артефактов",
  swamp_walker: "Снижает штраф от зыбучих песков",
  spider_hunter: "Снижает штраф от паутины",
  chemist: "Снижает штраф от кислотных луж",
  magic_researcher: "Снижает штраф от магических аномалий",
  exorcist: "Снижает штраф от призрачных явлений",
  mountain_engineer: "Снижает штраф от обвалов",
  anti_magnet: "Снижает штраф от магнитных аномалий",
  curse_removal: "Снижает штраф от проклятий",
  anti_mage: "Снижает штраф от зачарований",
  spatial_mage: "Снижает штраф от искажений",
  light_protection: "Снижает штраф от ослепления",
  magic_resistance: "Снижает штраф от паралича",
  chronomancer: "Снижает штраф от замедления времени",
  accelerator: "Снижает штраф от ускорения времени",
  spatial_navigator: "Снижает штраф от искажения пространства",
  mana_shield: "Снижает штраф от магического истощения",
  lucky: "Снижает штраф от проклятия удачи",
  mental_shield: "Снижает штраф от ментальных атак",
  strong_spirit: "Снижает штраф от навязчивых страхов",
  mental_clarity: "Снижает штраф от галлюцинаций",
  sleepless: "Снижает штраф от магического сна",
  trusting: "Снижает штраф от паранойи",
  photographic_memory: "Снижает штраф от амнезии",
  calm: "Снижает штраф от мании преследования",
  optimist: "Снижает штраф от депрессии",
  anger_control: "Снижает штраф от агрессии",
  passionate: "Снижает штраф от апатии",
};

// Русские названия перков (синхрон с expedition_data.PERKS) — для таверны без payload perks в API.
const PERK_NAMES = {
  gas_mask: "Газовая маска",
  diver: "Водолаз",
  fireproof: "Огнестойкий",
  frostproof: "Морозостойкий",
  navigator: "Штурман",
  desert_walker: "Пустынник",
  gas_filter: "Газовый фильтр",
  snow_warrior: "Снежный воин",
  acid_proof: "Кислотостойкий",
  wind_walker: "Ветроход",
  elf_slayer: "Убийца эльфов",
  orc_hunter: "Охотник на орков",
  priest: "Священник",
  demon_slayer: "Демоноборец",
  dragonslayer: "Драконоборец",
  goblin_shaker: "Гоблинотряс",
  troll_slayer: "Троллеубийца",
  vampire_hunter: "Охотник на вампиров",
  entomologist: "Энтомолог",
  bat_hunter: "Охотник на летучих мышей",
  mushroom_expert: "Грибник-знаток",
  scout: "Разведчик",
  archaeologist: "Археолог",
  swamp_walker: "Болотный ходок",
  spider_hunter: "Охотник на пауков",
  chemist: "Химик",
  magic_researcher: "Маг-исследователь",
  exorcist: "Экзорцист",
  mountain_engineer: "Горный инженер",
  anti_magnet: "Анти-магнит",
  curse_removal: "Снятие проклятий",
  anti_mage: "Антимаг",
  spatial_mage: "Пространственный маг",
  light_protection: "Защита от света",
  magic_resistance: "Сопротивление магии",
  chronomancer: "Хрономант",
  accelerator: "Ускоритель",
  spatial_navigator: "Пространственный навигатор",
  mana_shield: "Мана-щит",
  lucky: "Удачливый",
  mental_shield: "Ментальный щит",
  strong_spirit: "Стойкий дух",
  mental_clarity: "Ясность разума",
  sleepless: "Бессонный",
  trusting: "Доверчивый",
  photographic_memory: "Фотографическая память",
  calm: "Спокойствие",
  optimist: "Оптимист",
  anger_control: "Контроль гнева",
  passionate: "Страстный",
};

// Иконки перков для экспедиций (id из expedition_data.PERKS)
const PERK_ICONS = {
  gas_mask: "🫓",
  diver: "🤿",
  fireproof: "🔥",
  frostproof: "❄️",
  navigator: "🧭",
  desert_walker: "🏜️",
  gas_filter: "💨",
  snow_warrior: "⛷️",
  acid_proof: "🧪",
  wind_walker: "💨",
  elf_slayer: "⚔️",
  orc_hunter: "🪓",
  priest: "✝️",
  demon_slayer: "😈",
  dragonslayer: "🐉",
  goblin_shaker: "👺",
  troll_slayer: "👹",
  vampire_hunter: "🧛",
  entomologist: "🐛",
  bat_hunter: "🦇",
  mushroom_expert: "🍄",
  scout: "🔍",
  archaeologist: "📜",
  swamp_walker: "🐸",
  spider_hunter: "🕷️",
  chemist: "⚗️",
  magic_researcher: "🔮",
  exorcist: "👻",
  mountain_engineer: "⛏️",
  anti_magnet: "🧲",
  curse_removal: "🛡️",
  anti_mage: "✨",
  spatial_mage: "🌀",
  light_protection: "🕶️",
  magic_resistance: "💫",
  chronomancer: "⏱️",
  accelerator: "⚡",
  spatial_navigator: "🗺️",
  mana_shield: "🔵",
  lucky: "🍀",
  mental_shield: "🧠",
  strong_spirit: "💪",
  mental_clarity: "👁️",
  sleepless: "🌙",
  trusting: "🤝",
  photographic_memory: "📷",
  calm: "😌",
  optimist: "😊",
  anger_control: "😤",
  passionate: "❤️",
};

/** Пояснение, как перк связан со сложностью экспедиций (слоты 1–5, сумма аффиксов). */
const PERK_EXPEDITION_COUNTER_HINT =
  "Перк помогает в экспедициях, если закрывает тип сложности слота (Монстры, Нежить…). Эффективность = min(100%, уровень_перка ÷ уровень_препятствия I–V). Прокачка перков — вкладка ⬆ LVL в таверне (очки за лвлап после экспедиции).";

function safeInt(x, fallback = 0) {
  const v = Number.parseInt(String(x), 10);
  return Number.isFinite(v) ? v : fallback;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function formatApiErrorDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        if (e && typeof e === "object") {
          const loc = Array.isArray(e.loc) ? e.loc.filter((x) => x !== "body").join(" → ") : "";
          const msg = e.msg != null ? String(e.msg) : JSON.stringify(e);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(e);
      })
      .join("; ");
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return String(detail);
}

function parseHttpErrorDetail(err) {
  const msg = String(err?.message || err || "");
  const idx = msg.indexOf(":");
  if (idx === -1) return { raw: msg, detail: msg };
  const tail = msg.slice(idx + 1).trim();
  try {
    const obj = JSON.parse(tail);
    const detail = obj?.detail != null ? formatApiErrorDetail(obj.detail) : tail;
    return { raw: msg, detail };
  } catch {
    return { raw: msg, detail: tail || msg };
  }
}

function isWebAppUnauthorizedError(err) {
  const msg = String(err?.message || "");
  if (!msg.includes("HTTP 401")) return false;
  const { detail } = parseHttpErrorDetail(err);
  const d = (detail || "").toLowerCase();
  return (
    d.includes("telegram") ||
    d.includes("init data") ||
    d.includes("hash missing") ||
    d.includes("invalid init") ||
    d.includes("expired")
  );
}

/** Сообщение при открытии WebApp вне Telegram или без валидного initData. */
function webAppAuthNoticeHtml() {
  const devBlock = `<details class="webapp-auth-details"><summary>Для разработчиков</summary>
    <p>При <code>APP_ENV=dev</code> на сервере можно открыть страницу с параметром <code>?devPlayerId=</code><em>id</em> (id игрока в БД) — тогда запросы пойдут с заголовком <code>X-Player-Id</code>. В production это отключено.</p>
  </details>`;
  return `<div class="webapp-auth-notice" role="alert">
    <h3 class="webapp-auth-notice-title">Нужен вход через Telegram</h3>
    <p>Откройте эту страницу из <strong>мини-приложения бота</strong> в Telegram. В обычном браузере не передаётся подпись <code>initData</code>, поэтому сервер отвечает 401.</p>
    <p class="muted">Если вы уже внутри Telegram, закройте мини-приложение полностью и откройте снова — иногда устаревает сессия.</p>
    ${devBlock}
  </div>`;
}

/** Сообщение при 502/503 или недоступном API (nginx upstream down). */
function serverUnavailableNoticeHtml() {
  return `<div class="webapp-auth-notice" role="alert">
    <h3 class="webapp-auth-notice-title">Сервер временно недоступен</h3>
    <p>Не удалось загрузить данные с сервера (ошибка 502 или сеть). Подождите немного и обновите страницу.</p>
    <p class="muted">Если ошибка не проходит, напишите администратору — возможно, упал backend за nginx.</p>
  </div>`;
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

function resolveImageUrl(url) {
  if (!url) return "";
  const u = String(url).trim();
  if (!u) return "";
  if (!u.startsWith("/api/")) return u;
  const params = new URLSearchParams();
  const initData = getInitData();
  if (initData) {
    params.set("initData", initData);
  } else {
    const devId = getDevPlayerIdFromQuery();
    if (devId) {
      params.set("devPlayerId", String(devId));
      const devToken = new URLSearchParams(window.location.search).get("devToken");
      if (devToken) params.set("devToken", devToken);
    }
  }
  const qs = params.toString();
  return qs ? `${u}${u.includes("?") ? "&" : "?"}${qs}` : u;
}

function hiredWaifuImageUrl(w, variant) {
  const u = w?.imageUrl ?? w?.image_url;
  const resolved = resolveImageUrl(u);
  // Portrait API supports ?variant=thumb|full (downscaled webp). Only append it
  // for that endpoint; static URLs ignore unknown queries but we keep them clean.
  if (!resolved || !variant || !resolved.includes("/portrait")) return resolved;
  return `${resolved}${resolved.includes("?") ? "&" : "?"}variant=${encodeURIComponent(variant)}`;
}

function waifuPortraitEmoji(w) {
  const race = raceIcon(w?.race);
  const cls = classIcon(w?.class ?? w?.class_ ?? w?.["class"]);
  return `${race}${cls}`;
}

function statMeta(stat) {
  const key = String(stat || "").trim();
  const low = normalizeEffectKeyUi(key);
  if (SECONDARY_STAT_META[low]) return SECONDARY_STAT_META[low];
  if (low.startsWith("passive_node_level_add:")) {
    const nid = key.slice(key.indexOf(":") + 1).trim();
    const nm = passiveNodeDisplayNameRu(nid);
    const ic =
      typeof PASSIVE_NODE_ICONS !== "undefined" && PASSIVE_NODE_ICONS[nid]
        ? PASSIVE_NODE_ICONS[nid]
        : "🌿";
    return { icon: ic, short: `Пассив: ${nm}` };
  }
  if (low.startsWith("passive_branch_level_add:")) {
    const br = key.slice(key.indexOf(":") + 1).trim().toLowerCase();
    const lbl = PASSIVE_BRANCH_LABELS_RU[br] || br;
    return { icon: "🌿", short: `Ветка: ${lbl}` };
  }
  if (low === "passive_all_nodes_level_add") {
    return { icon: "✨", short: "Все пассивы" };
  }
  if (low.startsWith("damage_vs_monster_type_flat:")) {
    const fam = key.slice(key.indexOf(":") + 1).trim().toLowerCase();
    const ru = MONSTER_FAMILY_LABELS_RU[fam] || fam;
    return { icon: "⚔️", short: `Урон vs ${ru}` };
  }
  if (low.startsWith("damage_vs_monster_type_percent:")) {
    const fam = key.slice(key.indexOf(":") + 1).trim().toLowerCase();
    const ru = MONSTER_FAMILY_LABELS_RU[fam] || fam;
    return { icon: "⚔️", short: `Урон % vs ${ru}` };
  }
  return STAT_META[low] || STAT_META[key] || { icon: "✨", short: key || "—" };
}

const PRIMARY_STAT_KEYS = new Set([
  "strength",
  "agility",
  "intelligence",
  "endurance",
  "charm",
  "luck",
]);

/** Подпись строки аффикса в характеристиках (не путать с affix.name для названия предмета). */
function resolveAffixCharacteristicLabel(affix) {
  const sk = String(affix?.stat || "").trim();
  const skl = sk.toLowerCase();
  const m = statMeta(sk);
  if (PRIMARY_STAT_KEYS.has(skl)) return m.short;
  const desc = String(affix?.description || "").trim();
  if (desc) return desc;
  if (m.short && m.short !== sk) return m.short;
  return sk || "—";
}

function formatBonusValue(stat, value) {
  const sk = String(stat || "").trim();
  // Вторичные аффиксы: целое значение в сотых долях процента (150 → +1.50%)
  if (sk.endsWith("_pct")) {
    const v = safeNumber(value, 0);
    const sign = v >= 0 ? "+" : "";
    return `${sign}${(v / 100).toFixed(2)}%`;
  }
  const v = safeNumber(value, 0);
  const isPercent =
    sk.endsWith("_percent") ||
    sk.includes("chance_percent") ||
    sk.endsWith("_pct");
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v}${isPercent ? "%" : ""}`;
}

/** Строка аффикса в модалке: проценты всегда с «+» (напр. +68%). */
function formatAffixCharacteristicValue(stat, rawValue, isPercentFlag) {
  const sk = String(stat || "").trim();
  const skl = sk.toLowerCase();
  if (sk.endsWith("_pct")) {
    return formatBonusValue(sk, rawValue);
  }
  const isPct =
    Boolean(isPercentFlag) ||
    skl.endsWith("_percent") ||
    sk.includes("chance_percent") ||
    sk.endsWith("_pct");
  if (isPct) {
    const n = safeNumber(rawValue, 0);
    const sign = n >= 0 ? "+" : "−";
    const abs = Math.abs(n);
    const body = Number.isInteger(abs) ? String(abs) : String(abs);
    return `${sign}${body}%`;
  }
  return formatBonusValue(sk, rawValue);
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
  endurance: "Даёт больше максимального HP и снижает входящий урон.",
  charm: "Улучшает торговлю и снижает стоимость найма и тренировок.",
  luck: "Повышает шанс критов, шанс добычи предметов и количество золота с монстров.",
};

function profileStatValue(waifu, statKey) {
  return safeNumber(waifu?.[statKey], 0);
}

function profileStatBase(waifu, statKey) {
  return safeNumber(waifu?.[`base_${statKey}`], 10);
}

/** Плоский бонус «Трансценд.» (main_stats_flat), входит в bonus_* вместе с экипировкой. */
function profileStatPassiveMainStatsFlat(waifu) {
  return safeNumber(waifu?.passive_main_stats_flat, 0);
}

function profileStatEquipmentBonus(waifu, statKey) {
  const combined = safeNumber(waifu?.[`bonus_${statKey}`], 0);
  const passive = profileStatPassiveMainStatsFlat(waifu);
  return Math.max(0, combined - passive);
}

function profileStatRaceBonus(waifu, statKey) {
  const fromApi = waifu?.race_flat_bonuses;
  if (fromApi != null && typeof fromApi === "object") {
    return safeNumber(fromApi[statKey], 0);
  }
  return safeNumber(WAIFU_RACE_BONUSES?.[Number(waifu?.race)]?.[statKey], 0);
}

function profileStatClassBonus(waifu, statKey) {
  const fromApi = waifu?.class_flat_bonuses;
  if (fromApi != null && typeof fromApi === "object") {
    return safeNumber(fromApi[statKey], 0);
  }
  return safeNumber(WAIFU_CLASS_BONUSES?.[Number(waifu?.class ?? waifu?.class_)]?.[statKey], 0);
}

function profileDamageRange(score) {
  const base = Math.max(0, safeNumber(score, 0));
  const min = Math.max(0, Math.floor(base * 0.9));
  const max = Math.max(min, Math.ceil(base * 1.1));
  return `${min}–${max}`;
}

function profileDamageRangeFromDetails(d, prefix, fallbackScore) {
  const minKey = `${prefix}_damage_min`;
  const maxKey = `${prefix}_damage_max`;
  const min = d?.[minKey];
  const max = d?.[maxKey];
  if (min != null && max != null) {
    return `${Math.max(0, safeInt(min, 0))}–${Math.max(0, safeInt(max, 0))}`;
  }
  return profileDamageRange(fallbackScore);
}

function profileFormatPercent(value, digits = 1) {
  const num = safeNumber(value, 0);
  const fixed = Number(num.toFixed(digits));
  return `${fixed}%`;
}

function getProfileIndicators(waifu, details = null) {
  const d = details || profileState?.currentDetails || null;
  const endurance = profileStatValue(waifu, "endurance");
  const strength = profileStatValue(waifu, "strength");
  const charm = profileStatValue(waifu, "charm");
  const luck = profileStatValue(waifu, "luck");
  const intelligence = profileStatValue(waifu, "intelligence");
  const agility = profileStatValue(waifu, "agility");

  const hpMax = safeNumber(d?.hp_max ?? waifu?.max_hp, 0);
  const melee = safeNumber(d?.melee_damage, 0);
  const ranged = safeNumber(d?.ranged_damage, 0);
  const magic = safeNumber(d?.magic_damage, 0);
  const crit = safeNumber(d?.crit_chance, 0);
  const dodge = safeNumber(d?.dodge_chance, 0);
  const fullEvade = safeNumber(d?.full_evade_chance, 0);
  // Use server-computed values when available, fallback to client formulas
  const expBonus = d ? safeNumber(d.exp_bonus, intelligence * 0.1) : intelligence * 0.1;
  const goldBonus = d ? safeNumber(d.gold_bonus, luck * 0.2) : luck * 0.2;
  const hireDiscount = d ? safeNumber(d.hire_discount, charm * 0.1) : charm * 0.1;
  const trainingDiscount = d ? safeNumber(d.training_discount, charm * 0.15) : charm * 0.15;
  const damageReduction = d ? safeNumber(d.damage_reduction, Math.min(35, endurance * 0.08)) : Math.min(35, endurance * 0.08);
  // HP regen per hour (in dungeon): HP_max × (1 − e^(−END/100)) %
  const hpRegenRatePct = hpMax > 0 ? hpMax * (1 - Math.exp(-endurance / 100)) : 0;
  const hpRegenOutPct = hpRegenRatePct * 5;
  const merchantDiscount = safeNumber(d?.merchant_discount, 0);
  // Торговля: покупка 100%/(1 + charm/100), продажа 50% + charm*0.1%
  const buyPct = merchantDiscount > 0
    ? Math.max(100, Math.round((1 - merchantDiscount / 100) * 200))
    : Math.round(200 - charm * 0.1 * 2);
  const sellPct = merchantDiscount > 0
    ? Math.min(99, Math.round((0.5 + merchantDiscount / 100 * 0.5) * 100))
    : Math.round(50 + charm * 0.1 * 0.5);

  return {
    hpMax,
    meleeRange: profileDamageRangeFromDetails(d, "melee", melee),
    rangedRange: profileDamageRangeFromDetails(d, "ranged", ranged),
    magicRange: profileDamageRangeFromDetails(d, "magic", magic),
    critChance: profileFormatPercent(crit, 2),
    dodgeChance: profileFormatPercent(dodge, 2),
    fullEvadeChance: profileFormatPercent(fullEvade, 2),
    expBonus: profileFormatPercent(expBonus, 1),
    goldBonus: profileFormatPercent(goldBonus, 1),
    damageReduction: profileFormatPercent(damageReduction, 1),
    hireDiscount: profileFormatPercent(hireDiscount, 1),
    trainingDiscount: profileFormatPercent(trainingDiscount, 1),
    merchant: `покупка ${buyPct}% · продажа ${sellPct}%`,
    hpRegen: `реген ${Math.round(hpRegenOutPct)}/час`,
    armor: safeNumber(d?.armor, 0),
    incomingReduction: profileFormatPercent(damageReduction, 1),
  };
}

function profileStatBonusLines(statKey, waifu, details = null) {
  const total = profileStatValue(waifu, statKey);
  switch (statKey) {
    case "strength":
      return [
        `+${(total * 0.5).toFixed(1)} к урону ближнего боя`,
        `+${total * 2} к HP`,
        `×${(1.5 + total * 0.005).toFixed(2)} множитель крит. урона`,
      ];
    case "agility":
      return [
        `+${(total * 0.5).toFixed(1)} к урону дальнего боя`,
        `+${profileFormatPercent(total * 0.1, 1)} к шансу уклонения (потолок 40%)`,
        `+${profileFormatPercent(total * 0.05, 2)} к шансу крит. атаки`,
      ];
    case "intelligence":
      return [
        `+${(total * 0.5).toFixed(1)} к урону магических атак`,
        `+${(total * 0.3).toFixed(1)} к урону активных навыков`,
        `+${profileFormatPercent(total * 0.1, 1)} к получаемому опыту`,
      ];
    case "endurance": {
      const maxHp = details?.hp_max ?? (waifu?.max_hp ?? 0);
      const regenInDungeon = maxHp > 0 ? (maxHp * (1 - Math.exp(-total / 100))).toFixed(0) : "—";
      const regenOut = maxHp > 0 ? (maxHp * (1 - Math.exp(-total / 100)) * 5).toFixed(0) : "—";
      return [
        `+${total * 5} к максимальному HP`,
        `-${profileFormatPercent(Math.min(35, total * 0.08), 1)} к получаемому урону (потолок 35%)`,
        `Реген HP: ~${regenInDungeon}/час в бою, ~${regenOut}/час вне боя`,
      ];
    }
    case "charm": {
      const deathPenalty = Math.max(0, 50 - total * 0.1);
      return [
        `Торговля: покупка ~${Math.max(100, Math.round(200 - total * 0.2))}%, продажа ~${Math.min(99, Math.round(50 + total * 0.05))}%`,
        `-${profileFormatPercent(total * 0.1, 1)} к стоимости найма вайфу`,
        `-${profileFormatPercent(total * 0.15, 1)} к стоимости тренировок`,
        `Штраф золота при смерти: ${deathPenalty.toFixed(1)}%`,
      ];
    }
    case "luck":
      return [
        `+${profileFormatPercent(total * 0.1, 1)} к шансу крит. атаки (основной источник)`,
        `+${profileFormatPercent(total * 0.05, 2)} к шансу выпадения предметов`,
        `+${profileFormatPercent(total * 0.2, 1)} к золоту с монстров`,
      ];
    default:
      return [];
  }
}

function profileStatSources(waifu, statKey) {
  const total = profileStatValue(waifu, statKey);
  const base = profileStatBase(waifu, statKey);
  const race = profileStatRaceBonus(waifu, statKey);
  const cls = profileStatClassBonus(waifu, statKey);
  const passive = profileStatPassiveMainStatsFlat(waifu);
  const equipment = profileStatEquipmentBonus(waifu, statKey);
  // «Навыки» = только пассивный плоский бонус; экипировка без дубля с Трансценд.
  const other = passive;
  return { base, race, classBonus: cls, equipment, other, total };
}

function renderStatsStrip(targetId, waifu) {
  const box = document.getElementById(targetId);
  if (!box || !waifu) return;
  const pts = safeNumber(waifu?.stat_points, 0);
  box.innerHTML = PROFILE_STAT_ORDER.map((statKey) => {
    const meta = statMeta(statKey);
    const label = PROFILE_STAT_LABELS[statKey] || meta.short;
    const plusBtn = pts > 0
      ? `<button class="stat-plus-btn stat-plus-inline" title="Потратить 1 ОХ на ${label}" onclick="event.stopPropagation(); WaifuApp.spendStatPoint('${statKey}')">+</button>`
      : "";
    return `
      <button class="profile-stat-row" type="button" onclick="WaifuApp.openProfileStatInfoModal('${statKey}')">
        <div class="profile-stat-row-main">
          <span class="profile-stat-row-left">
            <span class="profile-stat-icon" aria-hidden="true">${meta.icon}</span>
            <span>${label}</span>
          </span>
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <strong>${profileStatValue(waifu, statKey)}</strong>
            ${plusBtn}
          </span>
        </div>
      </button>
    `;
  }).join("");
}

function openProfileStatInfoModal(statKey) {
  const key = String(statKey || "").trim().toLowerCase();
  const modal = document.getElementById("profile-stat-info-modal");
  const titleEl = document.getElementById("profile-stat-info-title");
  const bodyEl = document.getElementById("profile-stat-info-body");
  if (!modal || !titleEl || !bodyEl) return;
  if (!PROFILE_STAT_ORDER.includes(key)) return;
  const meta = statMeta(key);
  const label = PROFILE_STAT_LABELS[key] || meta.short;
  titleEl.innerHTML = `<span class="profile-stat-info-title-icon" aria-hidden="true">${meta.icon}</span><span>${escapeHtml(label)}</span>`;
  bodyEl.textContent = PROFILE_STAT_TOOLTIPS[key] || "Описание характеристики появится позже.";
  modal.style.display = "grid";
  modal.setAttribute("aria-hidden", "false");
}

function closeProfileStatInfoModal() {
  const modal = document.getElementById("profile-stat-info-modal");
  if (modal) {
    modal.style.display = "none";
    modal.setAttribute("aria-hidden", "true");
  }
}

function renderStatBreakdownDetail(statKey, waifu, details) {
  const meta = statMeta(statKey);
  const label = PROFILE_STAT_LABELS[statKey] || meta.short;
  const sources = profileStatSources(waifu, statKey);
  const bonusLines = profileStatBonusLines(statKey, waifu, details);
  return `
    <div class="profile-stats-breakdown-detail-inner">
      <div class="profile-breakdown-detail-head">${meta.icon} ${escapeHtml(label)}</div>
      <div class="profile-accordion-section">
        <div class="profile-breakdown-detail-caption">Источники</div>
        <div class="profile-accordion-sources">
          <div class="profile-accordion-row"><span>База</span><strong>${sources.base}</strong></div>
          <div class="profile-accordion-row"><span>Раса</span><strong>${sources.race >= 0 ? `+${sources.race}` : sources.race}</strong></div>
          <div class="profile-accordion-row"><span>Класс</span><strong>${sources.classBonus >= 0 ? `+${sources.classBonus}` : sources.classBonus}</strong></div>
          <div class="profile-accordion-row"><span>Экипировка</span><strong>${sources.equipment >= 0 ? `+${sources.equipment}` : sources.equipment}</strong></div>
          <div class="profile-accordion-row"><span>Навыки</span><strong>${sources.other >= 0 ? `+${sources.other}` : sources.other}</strong></div>
          <div class="profile-accordion-row"><span>Итого</span><strong>${sources.total}</strong></div>
        </div>
      </div>
      <div class="profile-accordion-section">
        <div class="profile-breakdown-detail-caption">Бонусы от значения</div>
        <div class="profile-bonus-list">
          ${bonusLines.map((line) => `<div class="profile-bonus-item">${line}</div>`).join("")}
        </div>
      </div>
    </div>
  `;
}

function renderStatsBreakdown(targetId, waifu, details = null) {
  const box = document.getElementById(targetId);
  if (!box || !waifu) return;

  const pts = safeNumber(waifu?.stat_points, 0);
  const ptsEl = document.getElementById("profile-stat-points");
  if (ptsEl) ptsEl.textContent = `ОХ: ${pts}`;

  const activeKey = profileState?.activeAccordion;
  const tiles = PROFILE_STAT_ORDER.map((statKey) => {
    const meta = statMeta(statKey);
    const label = PROFILE_STAT_LABELS[statKey] || meta.short;
    const sources = profileStatSources(waifu, statKey);
    const isOpen = activeKey === statKey;
    const plusBtn = pts > 0
      ? `<button type="button" class="stat-plus-btn stat-plus-tile" title="Потратить 1 ОХ на ${escapeHtml(
          label
        )}" onclick="event.stopPropagation(); WaifuApp.spendStatPoint('${statKey}')">+</button>`
      : "";
    return `
      <div class="profile-stat-tile ${isOpen ? "active" : ""}" data-stat-key="${statKey}">
        <button type="button" class="profile-stat-tile-main" onclick="WaifuApp.toggleProfileStatAccordion('${statKey}')">
          <span class="profile-stat-tile-icon" aria-hidden="true">${meta.icon}</span>
          <span class="profile-stat-tile-mid">
            <span class="profile-stat-tile-label">${escapeHtml(label)}</span>
            <span class="profile-stat-tile-valrow">
              <strong class="profile-stat-tile-val">${sources.total}</strong>
              <span class="profile-stat-tile-chev" aria-hidden="true">${isOpen ? "▲" : "▼"}</span>
            </span>
          </span>
        </button>
        ${plusBtn}
      </div>
    `;
  }).join("");

  const detailHtml =
    activeKey && PROFILE_STAT_ORDER.includes(activeKey)
      ? `<div class="profile-stats-breakdown-detail">${renderStatBreakdownDetail(activeKey, waifu, details)}</div>`
      : "";

  box.innerHTML = `<div class="profile-stats-breakdown-grid">${tiles}</div>${detailHtml}`;
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
  return Math.floor(PLAYER_EXP_BASE * Math.pow(lvl, 2));
}

function totalExpForLevel(level) {
  const lvl = Number(level);
  if (!Number.isFinite(lvl) || lvl <= 1) return 0;
  let total = 0;
  for (let l = 2; l <= lvl; l += 1) total += expForLevel(l);
  return total;
}

// ── Attic (ОЧ) renderers ─────────────────────────────────────────────────────

/** Compact solo dungeon code for attic chip, e.g. 1-1, 2-5. */
function formatAtticSoloDungeonCode(active) {
  const act = Math.max(0, parseInt(active?.act, 10) || 0);
  const num = Math.max(0, parseInt(active?.dungeon_number, 10) || 0);
  if (act > 0 && num > 0) return `${act}-${num}`;
  return null;
}

/** Update the active-dungeon chip in the shared ОЧ header. Format: "код · curStage/total" + segmented bar. */
function renderAtticDungeon(active) {
  const chip = document.getElementById("attic-dungeon-chip");
  const label = document.getElementById("attic-dungeon-label");
  const progressWrap = document.getElementById("attic-dungeon-progress");
  if (!chip || !label) return;

  const renderSegments = (segs) => {
    if (!progressWrap) return;
    if (!segs.length) {
      progressWrap.hidden = true;
      progressWrap.innerHTML = "";
      return;
    }
    progressWrap.innerHTML = `<div class="attic-dungeon-segments">${segs.join("")}</div>`;
    progressWrap.hidden = false;
  };

  if (active?.abyss_active) {
    const hpPct = active.monster_max_hp > 0
      ? Math.round((active.monster_current_hp / active.monster_max_hp) * 100)
      : 0;
    label.textContent = `🕳️ Бездна · эт. ${Number(active.abyss_floor || 0)}`;
    chip.classList.remove("chip-ghost");
    chip.classList.add("chip-active");
    if (progressWrap) {
      const donePct = Math.max(0, Math.min(100, 100 - hpPct));
      renderSegments([
        `<div class="attic-dungeon-seg attic-dungeon-seg--done"><div class="attic-dungeon-seg-fill" style="width:${donePct}%"></div></div>`,
      ]);
      progressWrap.setAttribute("aria-label", `Бездна, этаж ${Number(active.abyss_floor || 0)}`);
    }
    return;
  }
  if (active?.active) {
    const code = formatAtticSoloDungeonCode(active) || active.dungeon_name || "Бой";
    const pl = Math.max(0, parseInt(active.plus_level, 10) || 0);
    const curStage = Math.max(
      1,
      Math.floor(Number(
        active?.monster_position ??
        active?.dungeon_stage ??
        active?.current_stage ??
        active?.stage ??
        1
      ) || 1),
    );
    const totalStages = Math.max(
      1,
      Math.floor(Number(
        active?.total_monsters ??
        active?.total_stages ??
        active?.total_rooms ??
        active?.rooms_total ??
        4
      ) || 4),
    );
    const hpFrac = active.monster_max_hp > 0
      ? 1 - clamp01(active.monster_current_hp / active.monster_max_hp)
      : 0;
    label.textContent = `${code}${pl > 0 ? ` (+${pl})` : ""} · ${curStage}/${totalStages}`;
    chip.title = active.dungeon_name ? String(active.dungeon_name) : "Подземелье";
    chip.classList.remove("chip-ghost");
    chip.classList.add("chip-active");

    if (progressWrap) {
      const segs = [];
      for (let i = 1; i <= totalStages; i++) {
        let fill = 0;
        if (i < curStage) fill = 1;
        else if (i === curStage) fill = hpFrac;
        const inner = fill > 0
          ? `<div class="attic-dungeon-seg-fill" style="width:${Math.round(fill * 100)}%"></div>`
          : "";
        segs.push(`<div class="attic-dungeon-seg${fill >= 1 ? " attic-dungeon-seg--done" : ""}">${inner}</div>`);
      }
      renderSegments(segs);
      progressWrap.setAttribute("aria-label", `Прогресс: ${curStage}/${totalStages}`);
    }
  } else {
    label.textContent = "Нет боя";
    chip.classList.add("chip-ghost");
    chip.classList.remove("chip-active");
    if (progressWrap) {
      progressWrap.hidden = true;
      progressWrap.innerHTML = "";
    }
  }
}

const ATTIC_LEVEL_RING_C = 2 * Math.PI * 16;

function bindAtticLevelCirclePerfectionNav(circle) {
  if (!circle || circle.dataset.perfectionNavBound === "1") return;
  circle.dataset.perfectionNavBound = "1";
  circle.addEventListener("click", () => {
    if (!circle.classList.contains("attic-level-circle--clickable")) return;
    window.location.href = "./training_hall.html?tab=perfection";
  });
  circle.addEventListener("keydown", (ev) => {
    if (!circle.classList.contains("attic-level-circle--clickable")) return;
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      window.location.href = "./training_hall.html?tab=perfection";
    }
  });
}

function renderAtticLevelCircle(level, xpPct, opts = {}) {
  const num = document.getElementById("badge-level");
  if (num && level != null) num.textContent = String(level);
  const ring = document.getElementById("attic-level-ring-fg");
  const circle = document.getElementById("attic-level-circle") || document.querySelector(".attic-level-circle");
  const usePerfection = Boolean(opts.perfection);
  const pendingCount = Number(opts.pendingCount || 0);
  if (circle) {
    circle.classList.toggle("attic-level-circle--perfection", usePerfection);
    circle.classList.toggle(
      "attic-level-circle--perfection-pending",
      usePerfection && pendingCount > 0
    );
    circle.classList.toggle("attic-level-circle--clickable", usePerfection);
    if (usePerfection) {
      circle.setAttribute("role", "link");
      circle.setAttribute("title", "Совершенствование");
      circle.setAttribute("tabindex", "0");
      bindAtticLevelCirclePerfectionNav(circle);
    } else {
      circle.removeAttribute("role");
      circle.removeAttribute("title");
      circle.removeAttribute("tabindex");
    }
  }
  let badge = document.getElementById("attic-perfection-pending");
  if (circle && pendingCount > 0) {
    if (!badge) {
      badge = document.createElement("span");
      badge.id = "attic-perfection-pending";
      badge.className = "attic-perfection-pending";
      badge.title = "Есть невыбранные бонусы совершенствования";
      circle.appendChild(badge);
    }
    badge.hidden = false;
    badge.textContent = String(pendingCount);
  } else if (badge) {
    badge.hidden = true;
  }
  if (!ring) return;
  const pct = Math.max(0, Math.min(100, Number(xpPct) || 0));
  ring.style.strokeDasharray = String(ATTIC_LEVEL_RING_C);
  ring.style.strokeDashoffset = String(ATTIC_LEVEL_RING_C * (1 - pct / 100));
}

function formatLevelWithPerfection(level, perfectionLevel) {
  const lvl = Number(level);
  const p = Number(perfectionLevel || 0);
  if (Number.isFinite(lvl) && lvl >= PLAYER_MAX_LEVEL && p > 0) return `${lvl} (${p})`;
  if (Number.isFinite(lvl)) return String(lvl);
  return "—";
}

function perfectionXpPct(profile) {
  const need = Number(profile?.perfection_xp_to_next || 0);
  const xp = Number(profile?.perfection_experience || 0);
  if (need <= 0) return 0;
  return Math.round(clamp01(xp / need) * 100);
}

function renderAtticExpeditions(actives, maxConcurrent) {
  const chip = document.getElementById("attic-exp-chip");
  const cellsWrap = document.getElementById("attic-exp-cells");
  if (!chip || !cellsWrap) return;
  const max = Math.max(1, Number(maxConcurrent) || 3);
  const list = Array.isArray(actives) ? actives : [];
  chip.hidden = false;
  const cells = [];
  for (let i = 0; i < max; i++) {
    const a = list[i] || null;
    if (!a) {
      cells.push('<div class="attic-exp-cell attic-exp-cell--empty" aria-label="Свободный слот"></div>');
      continue;
    }
    const title = escapeHtml(a.narrative_title || "Экспедиция");
    let cls = "attic-exp-cell--active";
    let label = "В процессе";
    if (a.outcome === "cancelled") {
      cls = "attic-exp-cell--cancelled";
      label = "Отменена";
    } else if (a.can_claim) {
      cls = "attic-exp-cell--done";
      label = "Готово";
    }
    cells.push(`<div class="attic-exp-cell ${cls}" title="${title}" aria-label="${label}"></div>`);
  }
  cellsWrap.innerHTML = cells.join("");
}

function hasAtticChrome() {
  return Boolean(document.getElementById("attic-dungeon-chip"));
}

function schedulePlayerMailBadgeRefresh() {
  const run = () => refreshAtticMailBadge().catch(() => {});
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(run, { timeout: 2000 });
  } else {
    setTimeout(run, 0);
  }
}

/** Fire-and-forget refresh of both dynamic ОЧ chips (dungeon + expeditions). */
const ACTIVE_DUNGEON_CACHE_MS = 5000;
const activeDungeonCache = {
  lite: { data: null, ts: 0, inFlight: null },
  full: { data: null, ts: 0, inFlight: null },
};
const activeExpeditionCache = { data: null, ts: 0, inFlight: null };

function invalidateActiveDungeonCache() {
  activeDungeonCache.lite = { data: null, ts: 0, inFlight: null };
  activeDungeonCache.full = { data: null, ts: 0, inFlight: null };
}

function invalidateActiveExpeditionCache() {
  activeExpeditionCache.data = null;
  activeExpeditionCache.ts = 0;
  activeExpeditionCache.inFlight = null;
}

function isDungeonsPage() {
  return typeof window !== "undefined" && window.location.pathname.endsWith("/dungeons.html");
}

function isGuildHallPage() {
  return typeof window !== "undefined" && window.location.pathname.endsWith("/guild_hall.html");
}

function isProfilePage() {
  return typeof window !== "undefined" && window.location.pathname.endsWith("/profile.html");
}

function scheduleDeferredAtticRefresh(profile) {
  const run = () => {
    refreshAtticChips();
    if (profile) renderAtticPlayerAvatar(profile);
    startAtticMailBadgePolling();
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(() => run(), { timeout: 2000 });
  } else {
    setTimeout(run, 0);
  }
}

async function fetchActiveDungeon(options = {}) {
  const includeLog = options.includeLog === true;
  const force = options.force === true;
  const slot = includeLog ? activeDungeonCache.full : activeDungeonCache.lite;
  const now = Date.now();
  if (!force && slot.data && now - slot.ts < ACTIVE_DUNGEON_CACHE_MS) return slot.data;
  if (slot.inFlight) return slot.inFlight;
  const qs = includeLog ? "?include_log=1" : "?include_log=0";
  slot.inFlight = apiFetch(`/dungeons/active${qs}`)
    .then((data) => {
      slot.data = data;
      slot.ts = Date.now();
      slot.inFlight = null;
      if (includeLog) {
        activeDungeonCache.lite.data = data;
        activeDungeonCache.lite.ts = slot.ts;
      }
      return data;
    })
    .catch((err) => {
      slot.inFlight = null;
      throw err;
    });
  return slot.inFlight;
}

async function fetchActiveExpeditions(options = {}) {
  const force = options.force === true;
  const now = Date.now();
  if (!force && activeExpeditionCache.data && now - activeExpeditionCache.ts < ACTIVE_DUNGEON_CACHE_MS) {
    return activeExpeditionCache.data;
  }
  if (activeExpeditionCache.inFlight) return activeExpeditionCache.inFlight;
  activeExpeditionCache.inFlight = apiFetch("/expeditions/active")
    .then((data) => {
      activeExpeditionCache.data = data;
      activeExpeditionCache.ts = Date.now();
      activeExpeditionCache.inFlight = null;
      return data;
    })
    .catch((err) => {
      activeExpeditionCache.inFlight = null;
      throw err;
    });
  return activeExpeditionCache.inFlight;
}

function refreshAtticChips(opts = {}) {
  if (!hasAtticChrome()) return;
  const skipDungeon = opts.skipDungeon === true || isDungeonsPage();
  if (!skipDungeon) {
    fetchActiveDungeon({ includeLog: false }).then(renderAtticDungeon).catch(() => {});
  }
  fetchActiveExpeditions()
    .then((res) => {
      const actives = Array.isArray(res?.active) ? res.active : [];
      const maxConcurrent = Number(res?.max_concurrent) || 3;
      renderAtticExpeditions(actives, maxConcurrent);
    })
    .catch(() => renderAtticExpeditions([], 3));
}

// ─────────────────────────────────────────────────────────────────────────────

function populateFromProfile(profile, opts = {}) {
  if (!profile) return;
  profileState.currentProfile = profile;

  // Shared ОЧ badges — populated on every page that has these IDs in its DOM
  if (profile.act != null) setText("badge-act", profile.act);
  if (profile.gold != null) setText("badge-gold", profile.gold);

  const w = profile.main_waifu;
  if (w) {
    const pLevel = Number(profile.perfection_level || 0);
    const pending = Number(profile.perfection_pending_count || 0);
    const usePerfection = Number(w.level) >= PLAYER_MAX_LEVEL && pLevel > 0;

    if (usePerfection) {
      setText("badge-level", pLevel);
    } else if (w.level != null) {
      setText("badge-level", w.level);
    }

    // Legacy IDs kept for back-compat (silently skipped when not in DOM)
    if (w.name) setText("waifu-name", w.name);
    if (w.name) setText("profile-name", w.name);
    if (w.level != null) {
      setText("profile-level", formatLevelWithPerfection(w.level, pLevel));
    }

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

    // XP progress — profile card + ОЧ level ring
    const fill = document.getElementById("profile-xp-fill");
    const xpBlock = document.querySelector(".profile-mtg-xp-block");
    if (usePerfection) {
      const need = Number(profile.perfection_xp_to_next || 0);
      const xp = Number(profile.perfection_experience || 0);
      const pct = perfectionXpPct(profile);
      setText(
        "profile-xp-text",
        `Совершенствование ${pLevel} · ${xp} / ${need} EXP`
      );
      if (fill) fill.style.width = `${pct}%`;
      if (xpBlock) xpBlock.classList.add("profile-mtg-xp-block--perfection");
      renderAtticLevelCircle(pLevel, pct, { perfection: true, pendingCount: pending });
    } else if (w.level != null && w.experience != null) {
      const lvl = Number(w.level);
      const xp = Number(w.experience);
      if (xpBlock) xpBlock.classList.remove("profile-mtg-xp-block--perfection");
      if (lvl >= PLAYER_MAX_LEVEL) {
        setText("profile-xp-text", `Ур. ${lvl} · макс.`);
        if (fill) fill.style.width = "100%";
        renderAtticLevelCircle(lvl, 100, { pendingCount: pending });
      } else {
        const nextTotal = totalExpForLevel(lvl + 1);
        const curTotal = totalExpForLevel(lvl);
        const span = Math.max(1, nextTotal - curTotal);
        const into = Math.max(0, xp - curTotal);
        const pct = Math.round(clamp01(into / span) * 100);
        setText("profile-xp-text", `Ур. ${lvl} · ${xp} / ${nextTotal} EXP`);
        if (fill) fill.style.width = `${pct}%`;
        renderAtticLevelCircle(lvl, pct, { pendingCount: pending });
      }
    } else if (w.level != null) {
      renderAtticLevelCircle(w.level, 0, { pendingCount: pending });
    }
  }

  // Async: update dynamic ОЧ chips on every page load/refresh
  if (!opts.skipAtticRefresh && hasAtticChrome()) {
    refreshAtticChips();
    renderAtticPlayerAvatar(profile);
    startAtticMailBadgePolling();
  }

  updateTrainingNavAttention(profile);
  ensureAtticPerfectionMenuItem(profile);

  if (document.getElementById("shop-gamble-cost")) updateShopGambleCost();
}

function updateTrainingNavAttention(profile) {
  const link = document.querySelector('.nav.basement a[data-page="training"]');
  if (!link) return;
  const skillPoints = Number(profile?.skill_points || 0);
  const pending = Number(profile?.perfection_pending_count || 0);
  const showDot = skillPoints > 0 || pending > 0;
  let dot = link.querySelector(".nav-attention-dot");
  if (showDot) {
    if (!dot) {
      dot = document.createElement("span");
      dot.className = "nav-attention-dot";
      dot.setAttribute("aria-hidden", "true");
      link.appendChild(dot);
    }
    dot.hidden = false;
  } else if (dot) {
    dot.hidden = true;
  }
  if (pending > 0) {
    link.setAttribute("href", "./training_hall.html?tab=perfection");
  } else {
    link.setAttribute("href", "./training_hall.html");
  }
}

function ensureAtticPerfectionMenuItem(profile) {
  const menu = document.getElementById("attic-menu");
  if (!menu) return;
  const level = Number(profile?.main_waifu?.level || 0);
  let item = document.getElementById("attic-menu-perfection");
  if (level < PLAYER_MAX_LEVEL) {
    if (item) item.hidden = true;
    return;
  }
  if (!item) {
    item = document.createElement("a");
    item.className = "attic-menu-item";
    item.id = "attic-menu-perfection";
    item.href = "./training_hall.html?tab=perfection";
    item.setAttribute("role", "menuitem");
    item.textContent = "✨ Совершенствование";
    const stats = Array.from(menu.querySelectorAll("a.attic-menu-item")).find((a) =>
      String(a.getAttribute("href") || "").includes("info=statistics")
    );
    const expedition = Array.from(menu.querySelectorAll("a.attic-menu-item")).find((a) =>
      String(a.getAttribute("href") || "").includes("tab=expedition")
    );
    if (stats && stats.nextSibling) {
      menu.insertBefore(item, stats.nextSibling);
    } else if (expedition) {
      menu.insertBefore(item, expedition);
    } else {
      menu.appendChild(item);
    }
  }
  item.hidden = false;
  item.href = "./training_hall.html?tab=perfection";
}

function getTelegramUser() {
  try {
    return tg?.initDataUnsafe?.user || null;
  } catch {
    return null;
  }
}

function playerDisplayInitials(profile) {
  const u = getTelegramUser();
  const name = (u?.first_name || profile?.main_waifu?.name || "И").trim();
  return name ? name.slice(0, 1).toUpperCase() : "?";
}

function applyPlayerAvatarUrl(avatarUrl, profile) {
  const initials = playerDisplayInitials(profile);
  const pairs = [
    ["attic-player-avatar-img", "attic-player-avatar-fallback"],
    ["player-hero-avatar-img", "player-hero-avatar-fallback"],
  ];
  pairs.forEach(([imgId, fbId]) => {
    const img = document.getElementById(imgId);
    const fb = document.getElementById(fbId);
    if (!img && !fb) return;
    if (avatarUrl && img) {
      img.src = avatarUrl;
      img.hidden = false;
      if (fb) fb.textContent = "";
    } else {
      if (img) {
        img.hidden = true;
        img.removeAttribute("src");
      }
      if (fb) fb.textContent = initials;
    }
  });
}

async function fetchPlayerAvatarUrl() {
  if (playerPageState.cachedAvatarUrl) return playerPageState.cachedAvatarUrl;
  try {
    const d = await apiFetch("/player/avatar");
    playerPageState.cachedAvatarUrl = d?.avatar_url || null;
    return playerPageState.cachedAvatarUrl;
  } catch {
    return null;
  }
}

async function applyPlayerAvatarToElements(profile) {
  const url =
    playerPageState.profileData?.avatar_url ||
    playerPageState.cachedAvatarUrl ||
    (await fetchPlayerAvatarUrl());
  applyPlayerAvatarUrl(url, profile);
}

function renderAtticPlayerAvatar(profile) {
  const btn = document.getElementById("attic-player-avatar");
  if (!btn) return;
  applyPlayerAvatarToElements(profile);
  if (!btn.__waifuBound) {
    btn.__waifuBound = true;
    btn.addEventListener("click", () => {
      window.location.href = "./player.html";
    });
  }
}

async function refreshAtticMailBadge() {
  const badge = document.getElementById("attic-player-mail-badge");
  const tabBadge = document.getElementById("player-tab-mail-badge");
  const overflowBadge = document.getElementById("player-overflow-mail-badge");
  const topbarOverflowBadge = document.getElementById("player-topbar-overflow-mail-badge");
  if (!badge && !tabBadge && !overflowBadge && !topbarOverflowBadge) return;
  try {
    const data = await apiFetch("/mail/badge");
    const show =
      Boolean(data?.show) ||
      safeInt(data?.unread, 0) > 0 ||
      safeInt(data?.pending_rewards, 0) > 0;
    if (badge) badge.hidden = !show;
    if (tabBadge) tabBadge.hidden = !show;
    if (overflowBadge) overflowBadge.hidden = !show;
    if (topbarOverflowBadge) topbarOverflowBadge.hidden = !show;
  } catch {
    if (badge) badge.hidden = true;
    if (tabBadge) tabBadge.hidden = true;
    if (overflowBadge) overflowBadge.hidden = true;
    if (topbarOverflowBadge) topbarOverflowBadge.hidden = true;
  }
}

function startAtticMailBadgePolling() {
  if (!document.getElementById("attic-player-avatar")) return;
  refreshAtticMailBadge().catch(() => {});
  if (window.__waifuMailBadgeInterval) return;
  window.__waifuMailBadgeInterval = setInterval(() => {
    refreshAtticMailBadge().catch(() => {});
  }, 60000);
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
/** Выбранная сложность (+N) отдельно для каждого подземелья (id → уровень). */
let selectedPlusLevelByDungeonId = {};

function getPlusLevelForDungeon(dungeonId) {
  const id = Number(dungeonId);
  if (!Number.isFinite(id)) return 0;
  const raw = Number(selectedPlusLevelByDungeonId[id] ?? 0);
  const st = dungeonPlusStatusById?.[id];
  const unlocked = Number(st?.unlocked_plus_level || 0);
  return Math.max(0, Math.min(raw, unlocked));
}

function setPlusLevelForDungeon(dungeonId, pl) {
  const id = Number(dungeonId);
  if (!Number.isFinite(id)) return;
  const st = dungeonPlusStatusById?.[id];
  const unlocked = Number(st?.unlocked_plus_level || 0);
  const v = Math.max(0, Math.min(Number(pl) || 0, unlocked));
  selectedPlusLevelByDungeonId[id] = v;
}

// Ensure global namespace exists before any assignments below (SSE handlers, plus selector, etc.)
window.WaifuApp = window.WaifuApp || {};
function connectSSE() {
  const initData = getInitData();
  const desktopSession = getDesktopSessionTokenSync();
  if (!initData && !desktopSession) return;
  if (sse) sse.close();
  const params = new URLSearchParams();
  if (initData) params.set("initData", initData);
  if (desktopSession) params.set("desktopSession", desktopSession);
  const url = `${API_BASE}/sse/stream?${params.toString()}`;
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
    if (typeof window.WaifuApp._scheduleSseRefetch === "function") {
      window.WaifuApp._scheduleSseRefetch();
    }
    setTimeout(connectSSE, 3000);
  };
}

let _sseRefetchTimer = null;
window.WaifuApp._scheduleSseRefetch = function scheduleSseRefetch() {
  if (_sseRefetchTimer) clearTimeout(_sseRefetchTimer);
  _sseRefetchTimer = setTimeout(() => {
    _sseRefetchTimer = null;
    if (typeof window.WaifuApp.refreshBattleState === "function") {
      window.WaifuApp.refreshBattleState();
    }
    if (typeof window.WaifuApp.loadProfile === "function") {
      window.WaifuApp.loadProfile();
    }
  }, 300);
};

const WAIFU_GEN_BASE = `${GAME_STATIC_BASE}/waifu-gen`;
const WAIFU_GEN_PLACEHOLDER = `${WAIFU_GEN_BASE}/placeholder.svg`;
const WAIFU_GEN_STAT_ORDER = ["strength", "agility", "intelligence", "endurance", "charm", "luck"];
const WAIFU_GEN_STAT_LABELS = {
  strength: "СИЛ",
  agility: "ЛОВ",
  intelligence: "ИНТ",
  endurance: "ВЫН",
  charm: "ОБА",
  luck: "УДЧ",
};

const WAIFU_RACES = [
  { id: 1, name: "Человек", icon: "🧑", slug: "human" },
  { id: 2, name: "Эльф", icon: "🧝", slug: "elf" },
  { id: 3, name: "Зверолюд", icon: "🐾", slug: "beastman" },
  { id: 4, name: "Ангел", icon: "😇", slug: "angel" },
  { id: 5, name: "Вампир", icon: "🦇", slug: "vampire" },
  { id: 6, name: "Демон", icon: "😈", slug: "demon" },
  { id: 7, name: "Фея", icon: "🧚", slug: "fey" },
];

const WAIFU_CLASSES = [
  { id: 1, name: "Рыцарь", icon: "🛡️", slug: "knight" },
  { id: 2, name: "Воин", icon: "⚔️", slug: "warrior" },
  { id: 3, name: "Лучник", icon: "🏹", slug: "archer" },
  { id: 4, name: "Маг", icon: "🔮", slug: "mage" },
  { id: 5, name: "Ассасин", icon: "🗡️", slug: "assassin" },
  { id: 6, name: "Хилер", icon: "💚", slug: "healer" },
  { id: 7, name: "Торговец", icon: "💰", slug: "merchant" },
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

/** Тексты пассивов расы — ориентировочные значения для экрана создания персонажа. */
const WAIFU_GEN_RACE_PASSIVES = {
  1: [
    "«Адаптивность» — каждые 10 уровней (10, 20, 30…) +1 свободное очко характеристики на выбор",
    "+5% к получаемому EXP с монстров",
    "+5% к золоту с монстров",
  ],
  2: [
    "«Лесное чутьё» — вклад ЛОВ в шанс крита удваивается (в формуле крита ЛОВ даёт ×2 к своему слагаемому)",
    "+3% к шансу крит. атаки (базовый расовый бонус)",
    "×2 к коэффициенту крита от ЛОВ",
    "−5% к максимальному HP",
  ],
  3: [
    "«Хищный инстинкт» — каждое N-е текстовое сообщение в подземелье: урон ×1,5; N = max(3, 10 − ⌊СИЛ/5⌋) (при СИЛ 10 → N=8, при 25 → 5, при СИЛ ≥ 35 → 3)",
    "+2 к урону ближнего боя (плоский бонус)",
    "+4% к шансу уклонения",
    "−5% к цене продажи предметов",
  ],
  4: [
    "«Благодать» — множитель формулы регенерации HP +50% (пассивная регенерация сильнее); дополнительно +2% к EXP от ИНТ",
    "+50% к скорости регенерации HP (множитель к формуле)",
    "+3% к получаемому EXP (дополнительно к бонусу ИНТ)",
    "−8% к урону крит. атак",
  ],
  5: [
    "«Жизнекрада» — часть урона текстовых атак восстанавливает HP; зависит от (СИЛ + ЛОВ)",
    "+5% к шансу крит. атаки",
    "−10% к навыку «Торговля»",
  ],
  6: [
    "«Инфернальный пакт» — вклад ИНТ к урону медиа-навыков удваивается",
    "+4% к урону активных навыков (медиа), базовый расовый бонус",
    "×2 к коэффициенту урона навыков от ИНТ",
    "−15% к навыку «Торговля»",
  ],
  7: [
    "«Торговая магия» — Торговля: двойной бонус от ОБА",
    "×2 к коэффициенту «Торговля» от ОБА",
    "+5% к цене продажи предметов",
    "−10% к урону ближнего боя",
  ],
};

/** Тексты пассивов класса — ориентировочные значения для экрана создания персонажа. */
const WAIFU_GEN_CLASS_PASSIVES = {
  1: [
    "«Железная воля» — получаемый урон снижен; при HP < 30% бонус удваивается (от ВЫН)",
    "−5% к получаемому урону (от ВЫН)",
    "+15 к максимальному HP",
    "−5% к урону дальнего боя",
  ],
  2: [
    "«Берсерк» — при HP < 50% урон текстовых атак выше (от СИЛ)",
    "+8% к урону ближнего боя при HP < 50%",
    "+3 к урону крит. атак (плоский бонус)",
    "−5% к урону магических навыков",
  ],
  3: [
    "«Меткий глаз» — шанс крита от текстовых атак выше (от ЛОВ); каждый 5-й крит — ×2 к крит-урону",
    "+6% к шансу крит. атаки (от ЛОВ)",
    "+5% к урону дальнего боя",
    "−5% к урону ближнего боя",
  ],
  4: [
    "«Аркана» — урон медиа-навыков выше (от ИНТ); бонус ИНТ к EXP усилен",
    "+6% к урону медиа-навыков (от ИНТ)",
    "+4% к получаемому EXP (дополнительно к стандартному бонусу ИНТ)",
    "−5% к урону ближнего боя",
  ],
  5: [
    "«Тень» — шанс уклонения выше (от ЛОВ); после уклонения следующая атака +30% урона",
    "+6% к шансу уклонения (от ЛОВ)",
    "+30% к урону следующей атаки после успешного уклонения",
    "−10 к максимальному HP (штраф)",
  ],
  6: [
    "«Регенерация» — периодическое исцеление в подземелье + усиленная пассивная регенерация",
    "+HP каждые несколько сообщений в подземелье (от ВЫН)",
    "+10% к скорости пассивной регенерации HP",
    "−5% к урону ближнего боя",
  ],
  7: [
    "«Чутьё» — больше золота с монстров (от УДЧ + ОБА); найм в Таверне дешевле",
    "+8% к золоту с монстров",
    "+5% к навыку «Торговля»",
    "−8% к стоимости найма вайфу в Таверне",
    "−5% к урону в бою",
  ],
};

/** Состояние мастера создания ОВ (шаг 2, варианты портрета). */
const waifuGeneratorState = {
  playerId: null,
  variants: [],
  selectedIdx: 0,
  /** Сколько превью уже сохранено на сервере (0–3). */
  generationsCount: 0,
  selectedRaceId: 1,
  selectedClassId: 1,
  cosmetics: {
    hair_color: "brown",
    eye_colors: ["amber"],
    hairstyle: "long_straight",
    eye_shape: "cute",
    outfit: "robes",
    accessories: [],
  },
};

const WAIFU_GEN_COSMETIC = {
  hair: [
    ["blonde", "Блонд"],
    ["black", "Чёрные"],
    ["brown", "Каштановые"],
    ["red", "Рыжие"],
    ["white", "Белые"],
    ["silver", "Серебристые"],
    ["blue", "Синие"],
    ["pink", "Розовые"],
    ["green", "Зелёные"],
  ],
  eyes: [
    ["red", "Красный"],
    ["burgundy", "Бордовый"],
    ["pink", "Розовый"],
    ["sky_blue", "Голубой"],
    ["blue", "Синий"],
    ["turquoise", "Бирюзовый"],
    ["aquamarine", "Аквамариновый"],
    ["green", "Зелёный"],
    ["emerald", "Изумрудный"],
    ["lime", "Лаймовый"],
    ["yellow", "Жёлтый"],
    ["amber", "Янтарный"],
    ["gold", "Золотой"],
    ["orange", "Оранжевый"],
    ["violet", "Фиолетовый"],
    ["gray", "Серый"],
  ],
  /** Ключи — для API/промпта; подписи — RU (англ. — отдельно при i18n). */
  hairstyle: [
    ["short_bob", "Короткое каре"],
    ["spiky_short", "Короткие колючие"],
    ["pixie", "Пикси"],
    ["shaggy", "Лохматые"],
    ["medium_straight", "Средние прямые"],
    ["medium_wavy", "Средние волнистые"],
    ["medium_straight_bangs", "Средние прямые с чёлкой"],
    ["medium_wavy_2", "Средние волнистые (вар. 2)"],
    ["messy_medium", "Средние растрёпанные"],
    ["side_pony", "Боковой хвост"],
    ["twin_tails", "Два хвоста"],
    ["long_pony", "Длинный хвост"],
    ["long_straight", "Длинные прямые"],
    ["long_curls", "Длинные кудри"],
    ["twin_tails_alt", "Два хвоста (вар. 2)"],
    ["side_braid", "Боковая коса"],
    ["space_buns", "Два пучка"],
    ["hime_cut", "Химэ-кат"],
  ],
};

const WAIFU_GEN_EYE_SHAPES = [
  ["bright", "Яркие"],
  ["tsundere", "Цундере"],
  ["cute", "Милые"],
  ["melancholy", "Меланхолия"],
  ["serious", "Серьёзные"],
  ["energetic", "Энергичные"],
  ["mystic", "Мистические"],
  ["gentle", "Нежные"],
  ["dormant_sleepy", "Сонные/дремлющие"],
  ["shocked", "Шок"],
  ["playful", "Игривые"],
  ["cold", "Холодные"],
  ["confused", "Растерянные"],
  ["determination", "Решимость"],
  ["yandere", "Яндере"],
  ["shyness", "Застенчивость"],
  ["confidence", "Уверенность"],
  ["tearful", "Со слезами"],
  ["joyful", "Радостные"],
  ["anger", "Злость"],
  ["sleepy", "Сонные"],
  ["annoyed", "Раздражённые"],
  ["pouty", "Надутые"],
  ["seductive", "Соблазнительные"],
];

const WAIFU_GEN_OUTFITS = [
  ["plate_armor", "Доспех"],
  ["leather_armor", "Кожа"],
  ["chainmail", "Кольчуга"],
  ["dress", "Платье"],
  ["robes", "Мантия"],
  ["casual", "Casual"],
  ["swimsuit", "Купальник"],
  ["bikini", "Бикини"],
  ["uniform", "Униформа"],
  ["kimono", "Кимоно"],
  ["cloak", "Плащ"],
];

const WAIFU_GEN_ACCS_MULTI = [
  ["none", "Нет"],
  ["necklace", "Ожерелье"],
  ["earrings", "Серьги"],
  ["makeup_light", "Макияж лёгкий"],
  ["makeup_bold", "Макияж яркий"],
  ["scars", "Шрамы"],
  ["freckles", "Веснушки"],
  ["glasses", "Очки"],
  ["eyepatch", "Повязка на глаз"],
  ["face_paint", "Раскраска"],
  ["choker", "Чокер"],
  ["gloves", "Перчатки"],
  ["hat", "Шляпа"],
  ["hood", "Капюшон"],
  ["circlet", "Диадема"],
  ["hair_ribbon", "Лента"],
];

function waifuGenGensUsed() {
  return Math.min(3, Math.max(0, Number(waifuGeneratorState.generationsCount) || 0));
}

function waifuGenSetGensUsed(n) {
  waifuGeneratorState.generationsCount = Math.min(3, Math.max(0, Number(n) || 0));
}

function waifuGenFillSelect(id, pairs) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = pairs
    .map(([v, l]) => `<option value="${String(v).replace(/"/g, "&quot;")}">${escapeHtml(l)}</option>`)
    .join("");
}

function waifuGenSyncHiddenSelects() {
  const rs = document.getElementById("waifu-race-select");
  const cs = document.getElementById("waifu-class-select");
  if (rs) rs.value = String(waifuGeneratorState.selectedRaceId);
  if (cs) cs.value = String(waifuGeneratorState.selectedClassId);
}

function waifuGenRaceAssetUrl(slug) {
  return `${WAIFU_GEN_BASE}/races/${slug}.webp`;
}

function waifuGenClassAssetUrl(slug) {
  return `${WAIFU_GEN_BASE}/classes/${slug}.webp`;
}

function waifuGenCosmeticAssetUrl(group, slug) {
  return `${WAIFU_GEN_BASE}/cosmetic/${group}/${slug}.webp`;
}

function waifuGenImgHtml(src, alt, className) {
  const cls = className || "waifu-gen-card-ico";
  const s = escapeHtml(src);
  const a = escapeHtml(alt || "");
  const ph = escapeHtml(WAIFU_GEN_PLACEHOLDER);
  return `<img class="${cls}" src="${s}" alt="${a}" loading="lazy" decoding="async" onerror="this.onerror=null;this.src='${ph}'" />`;
}

function waifuGenPassiveTitle(lines, fallback) {
  const first = (lines || [])[0] || "";
  const m = first.match(/«([^»]+)»/);
  return m ? m[1] : fallback;
}

function waifuGenRenderRadar(el, stats) {
  if (!el) return;
  const size = 240;
  const cx = size / 2;
  const cy = size / 2;
  const rOuter = 92;
  const scale = 20;
  const entries = WAIFU_GEN_STAT_ORDER.map((k) => [WAIFU_GEN_STAT_LABELS[k], Number(stats[k] ?? 0)]);
  const n = entries.length;

  function angle(i) {
    return -Math.PI / 2 + (i * Math.PI * 2) / n;
  }

  const rings = [0.25, 0.5, 0.75, 1].map((f) => {
    const r = f * rOuter;
    return entries
      .map((_, i) => {
        const a = angle(i);
        return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
      })
      .join(" ");
  });

  const axes = entries.map((_, i) => {
    const a = angle(i);
    return { x2: (cx + rOuter * Math.cos(a)).toFixed(1), y2: (cy + rOuter * Math.sin(a)).toFixed(1) };
  });

  const valuePoints = entries
    .map(([, v], i) => {
      const a = angle(i);
      const r = (Math.max(0, Math.min(scale, v)) / scale) * rOuter;
      return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
    })
    .join(" ");

  const vertices = entries.map(([, v], i) => {
    const a = angle(i);
    const r = (Math.max(0, Math.min(scale, v)) / scale) * rOuter;
    return { cx: (cx + r * Math.cos(a)).toFixed(1), cy: (cy + r * Math.sin(a)).toFixed(1) };
  });

  const rLabel = rOuter + 18;
  const labelTexts = entries
    .map(([label, v], i) => {
      const a = angle(i);
      const lx = (cx + rLabel * Math.cos(a)).toFixed(1);
      const ly = (cy + rLabel * Math.sin(a)).toFixed(1);
      return (
        `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="middle">` +
        `<tspan class="stat-value">${escapeHtml(String(v))}</tspan>` +
        `<tspan> ${escapeHtml(label)}</tspan>` +
        `</text>`
      );
    })
    .join("");

  el.innerHTML = `<svg viewBox="0 -22 240 272" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Радар характеристик">
    ${rings.map((pts) => `<polygon class="ring" points="${pts}" />`).join("")}
    ${axes.map((ax) => `<line class="axis" x1="${cx}" y1="${cy}" x2="${ax.x2}" y2="${ax.y2}" />`).join("")}
    <polygon class="area" points="${valuePoints}" />
    ${vertices.map((v) => `<circle class="vertex" cx="${v.cx}" cy="${v.cy}" r="2.5" />`).join("")}
    ${labelTexts}
  </svg>`;
}

function waifuGenSyncTriggerIco(kind, entry) {
  const img = document.getElementById(`waifu-trigger-${kind}-img`);
  const emoji = document.getElementById(`waifu-trigger-${kind}-emoji`);
  if (!entry) return;
  const src = kind === "race" ? waifuGenRaceAssetUrl(entry.slug) : waifuGenClassAssetUrl(entry.slug);
  if (img) {
    img.onerror = () => {
      img.hidden = true;
      if (emoji) emoji.textContent = entry.icon || "•";
    };
    img.onload = () => {
      img.hidden = false;
      if (emoji) emoji.textContent = "";
    };
    img.src = src;
    img.alt = entry.name;
  } else if (emoji) {
    emoji.textContent = entry.icon || "•";
  }
}

function waifuGenSyncTriggers() {
  const race = WAIFU_RACES.find((r) => r.id === waifuGeneratorState.selectedRaceId);
  const cls = WAIFU_CLASSES.find((c) => c.id === waifuGeneratorState.selectedClassId);
  const raceNameEl = document.getElementById("waifu-trigger-race-name");
  const classNameEl = document.getElementById("waifu-trigger-class-name");
  if (raceNameEl) raceNameEl.textContent = race?.name || "—";
  if (classNameEl) classNameEl.textContent = cls?.name || "—";
  waifuGenSyncTriggerIco("race", race);
  waifuGenSyncTriggerIco("class", cls);
}

function waifuGenRenderRaceClassGrid(containerId, entries, selectedId, kind) {
  const root = document.getElementById(containerId);
  if (!root) return;
  const cards = entries.map((e) => {
    const on = e.id === selectedId;
    const src = kind === "race" ? waifuGenRaceAssetUrl(e.slug) : waifuGenClassAssetUrl(e.slug);
    return `<button type="button" class="waifu-gen-card${on ? " waifu-gen-card--on" : ""}" data-id="${e.id}" aria-pressed="${on}" aria-label="${escapeHtml(e.name)}">
      <span class="waifu-gen-card-media">${waifuGenImgHtml(src, e.name)}</span>
      <span class="waifu-gen-card-caption">${escapeHtml(e.name)}</span>
    </button>`;
  });
  while (cards.length < 9) {
    cards.push(`<div class="waifu-gen-card waifu-gen-card--coming" aria-hidden="true"></div>`);
  }
  root.innerHTML = cards.join("");
  root.querySelectorAll(".waifu-gen-card:not(.waifu-gen-card--coming)").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-id"));
      if (kind === "race") waifuGeneratorState.selectedRaceId = id;
      else waifuGeneratorState.selectedClassId = id;
      waifuGenSyncHiddenSelects();
      waifuGenBuildRaceClassPickers();
      waifuGenSyncTriggers();
      if (typeof window.__waifuGenRecalc === "function") window.__waifuGenRecalc();
      waifuGenCloseModal(kind === "race" ? "waifu-modal-race" : "waifu-modal-class");
    });
  });
}

function waifuGenRenderAssetCardGrid(containerId, pairs, assetGroup, currentVal, mode, onPick) {
  const root = document.getElementById(containerId);
  if (!root) return;
  const curSet = mode === "multi" || mode === "multi2" ? new Set(currentVal || []) : null;
  root.innerHTML = pairs
    .map(([v, l]) => {
      const on =
        mode === "multi" || mode === "multi2"
          ? curSet && curSet.has(v)
          : String(currentVal) === String(v);
      const src = waifuGenCosmeticAssetUrl(assetGroup, v);
      return `<button type="button" class="waifu-gen-card${on ? " waifu-gen-card--on" : ""}" data-val="${String(v).replace(/"/g, "&quot;")}" aria-pressed="${on}" aria-label="${escapeHtml(l)}">
      <span class="waifu-gen-card-media">${waifuGenImgHtml(src, l)}</span>
      <span class="waifu-gen-card-caption">${escapeHtml(l)}</span>
    </button>`;
    })
    .join("");
  root.querySelectorAll(".waifu-gen-card").forEach((btn) => {
    btn.addEventListener("click", () => onPick(btn.getAttribute("data-val") || ""));
  });
}

function waifuGenOpenPassiveModal(kind) {
  const raceId = waifuGeneratorState.selectedRaceId;
  const clsId = waifuGeneratorState.selectedClassId;
  const lines =
    kind === "race" ? WAIFU_GEN_RACE_PASSIVES[raceId] || [] : WAIFU_GEN_CLASS_PASSIVES[clsId] || [];
  const fallback = kind === "race" ? "Расовый бонус" : "Классовый бонус";
  const title = waifuGenPassiveTitle(lines, fallback);
  const titleEl = document.getElementById("waifu-modal-passive-title");
  const body = document.getElementById("waifu-passive-modal-body");
  if (titleEl) titleEl.textContent = title;
  if (body) {
    const ul = lines.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
    body.innerHTML = `<ul>${ul || `<li class="muted tiny">—</li>`}</ul>`;
  }
  waifuGenOpenModal("waifu-modal-passive");
}

function waifuGenRenderPassiveList() {
  const root = document.getElementById("waifu-gen-passive-list");
  if (!root) return;
  const raceId = waifuGeneratorState.selectedRaceId;
  const clsId = waifuGeneratorState.selectedClassId;
  const race = WAIFU_RACES.find((r) => r.id === raceId);
  const cls = WAIFU_CLASSES.find((c) => c.id === clsId);
  const raceLines = WAIFU_GEN_RACE_PASSIVES[raceId] || [];
  const classLines = WAIFU_GEN_CLASS_PASSIVES[clsId] || [];
  const raceTitle = waifuGenPassiveTitle(raceLines, "Расовый бонус");
  const classTitle = waifuGenPassiveTitle(classLines, "Классовый бонус");

  const cardHtml = (kind, entry, title, tag) => {
    const src =
      kind === "race" ? waifuGenRaceAssetUrl(entry?.slug || "human") : waifuGenClassAssetUrl(entry?.slug || "knight");
    return `<button type="button" class="waifu-gen-passive-card" data-passive-kind="${kind}" aria-label="${escapeHtml(title)}">
      ${waifuGenImgHtml(src, title, "waifu-gen-passive-ico")}
      <span class="waifu-gen-passive-card-body">
        <span class="waifu-gen-passive-tag">${escapeHtml(tag)}</span>
        <span class="waifu-gen-passive-name">${escapeHtml(title)}</span>
      </span>
    </button>`;
  };

  root.innerHTML = cardHtml("race", race, raceTitle, "Раса") + cardHtml("class", cls, classTitle, "Класс");
  root.querySelectorAll(".waifu-gen-passive-card").forEach((btn) => {
    btn.addEventListener("click", () => waifuGenOpenPassiveModal(btn.getAttribute("data-passive-kind") || ""));
  });
}

function waifuGenBuildRaceClassPickers() {
  waifuGenRenderRaceClassGrid(
    "waifu-modal-race-grid",
    WAIFU_RACES,
    waifuGeneratorState.selectedRaceId,
    "race"
  );
  waifuGenRenderRaceClassGrid(
    "waifu-modal-class-grid",
    WAIFU_CLASSES,
    waifuGeneratorState.selectedClassId,
    "class"
  );
}

function waifuGenRefreshHairModal() {
  const c = waifuGeneratorState.cosmetics;
  waifuGenRenderAssetCardGrid("waifu-modal-hair-colors", WAIFU_GEN_COSMETIC.hair, "hair-colors", c.hair_color, "single", (v) => {
    waifuGeneratorState.cosmetics.hair_color = v;
    waifuGenRefreshHairModal();
  });
  waifuGenRenderAssetCardGrid("waifu-modal-hair-styles", WAIFU_GEN_COSMETIC.hairstyle, "hair-styles", c.hairstyle, "single", (v) => {
    waifuGeneratorState.cosmetics.hairstyle = v;
    waifuGenRefreshHairModal();
  });
}

function waifuGenRefreshEyesModal() {
  const c = waifuGeneratorState.cosmetics;
  let colors = Array.isArray(c.eye_colors) ? c.eye_colors.filter(Boolean) : [];
  if (colors.length === 0) colors = ["amber"];
  waifuGenRenderAssetCardGrid("waifu-modal-eye-colors", WAIFU_GEN_COSMETIC.eyes, "eye-colors", colors, "multi2", (v) => {
    let next = [...(Array.isArray(waifuGeneratorState.cosmetics.eye_colors) ? waifuGeneratorState.cosmetics.eye_colors : [])].filter(Boolean);
    if (next.length === 0) next = ["amber"];
    const i = next.indexOf(v);
    if (i >= 0) {
      if (next.length <= 1) return;
      next.splice(i, 1);
    } else if (next.length < 2) {
      next.push(v);
    } else {
      next = [next[1], v];
    }
    waifuGeneratorState.cosmetics.eye_colors = next;
    waifuGenRefreshEyesModal();
  });
  waifuGenRenderAssetCardGrid("waifu-modal-eye-shapes", WAIFU_GEN_EYE_SHAPES, "eye-shapes", c.eye_shape, "single", (v) => {
    waifuGeneratorState.cosmetics.eye_shape = v;
    waifuGenRefreshEyesModal();
  });
}

function waifuGenRefreshOutfitModal() {
  const c = waifuGeneratorState.cosmetics;
  waifuGenRenderAssetCardGrid("waifu-modal-outfits", WAIFU_GEN_OUTFITS, "outfits", c.outfit, "single", (v) => {
    waifuGeneratorState.cosmetics.outfit = v;
    waifuGenRefreshOutfitModal();
  });
}

function waifuGenRefreshAccModal() {
  const c = waifuGeneratorState.cosmetics;
  let acc = Array.isArray(c.accessories) ? [...c.accessories] : [];
  waifuGenRenderAssetCardGrid("waifu-modal-accs", WAIFU_GEN_ACCS_MULTI, "accessories", acc, "multi", (v) => {
    if (v === "none") {
      waifuGeneratorState.cosmetics.accessories = [];
    } else {
      let next = (waifuGeneratorState.cosmetics.accessories || []).filter((x) => x !== "none");
      if (next.includes(v)) next = next.filter((x) => x !== v);
      else if (next.length < 6) next.push(v);
      waifuGeneratorState.cosmetics.accessories = next;
    }
    waifuGenRefreshAccModal();
  });
}

function waifuGenOpenModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.hidden = false;
  el.removeAttribute("hidden");
  if (id === "waifu-modal-race" || id === "waifu-modal-class") waifuGenBuildRaceClassPickers();
  if (id === "waifu-modal-hair") waifuGenRefreshHairModal();
  if (id === "waifu-modal-eyes") waifuGenRefreshEyesModal();
  if (id === "waifu-modal-outfit") waifuGenRefreshOutfitModal();
  if (id === "waifu-modal-acc") waifuGenRefreshAccModal();
}

function waifuGenCloseModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.hidden = true;
  el.setAttribute("hidden", "");
}

function waifuGenBindModalsOnce() {
  if (window.__waifuGenModalsBound) return;
  window.__waifuGenModalsBound = true;
  const openRace = document.getElementById("waifu-open-race");
  if (openRace) openRace.addEventListener("click", () => waifuGenOpenModal("waifu-modal-race"));
  const openClass = document.getElementById("waifu-open-class");
  if (openClass) openClass.addEventListener("click", () => waifuGenOpenModal("waifu-modal-class"));
  ["waifu-open-hair", "waifu-open-eyes", "waifu-open-outfit", "waifu-open-acc"].forEach((bid, i) => {
    const ids = ["waifu-modal-hair", "waifu-modal-eyes", "waifu-modal-outfit", "waifu-modal-acc"];
    const b = document.getElementById(bid);
    if (b) b.addEventListener("click", () => waifuGenOpenModal(ids[i]));
  });
  document.querySelectorAll("[data-waifu-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => waifuGenCloseModal(btn.getAttribute("data-waifu-close-modal") || ""));
  });
  [
    "waifu-modal-race",
    "waifu-modal-class",
    "waifu-modal-hair",
    "waifu-modal-eyes",
    "waifu-modal-outfit",
    "waifu-modal-acc",
    "waifu-modal-passive",
  ].forEach((mid) => {
    const m = document.getElementById(mid);
    if (!m) return;
    m.addEventListener("click", (ev) => {
      if (ev.target === m) waifuGenCloseModal(mid);
    });
    const panel = m.querySelector(".waifu-gen-modal-panel");
    if (panel) {
      panel.addEventListener("click", (ev) => ev.stopPropagation());
    }
  });
}

function waifuGenPortraitRequestBody() {
  const c = waifuGeneratorState.cosmetics;
  const acc = (c.accessories || []).filter((x) => x && x !== "none").slice(0, 6);
  let eyeColors = Array.isArray(c.eye_colors) ? c.eye_colors.filter(Boolean) : [];
  if (eyeColors.length === 0) eyeColors = ["amber"];
  eyeColors = eyeColors
    .slice(0, 2)
    .map((x) => (x != null && typeof x === "object" ? String(x?.value ?? "") : String(x)))
    .filter(Boolean);
  if (eyeColors.length === 0) eyeColors = ["amber"];
  return {
    race: waifuGeneratorState.selectedRaceId,
    class: waifuGeneratorState.selectedClassId,
    hair_color: String(c.hair_color ?? "brown"),
    eye_colors: eyeColors,
    hairstyle: String(c.hairstyle ?? "long_straight"),
    eye_shape: String(c.eye_shape ?? "cute"),
    outfit: String(c.outfit ?? "robes"),
    accessories: acc.length ? acc : [],
  };
}

function waifuGenRefreshHint() {
  const hint = document.getElementById("waifu-gen-gen-hint");
  if (!hint) return;
  const used = waifuGenGensUsed();
  const left = Math.max(0, 3 - used);
  hint.textContent =
    left > 0 ? `Осталось вариантов генерации: ${left} из 3.` : "Лимит генераций исчерпан (3).";
}

function waifuGenRefreshGenerateButton() {
  const genBtn = document.getElementById("waifu-generate-btn");
  if (!genBtn) return;
  genBtn.disabled = waifuGenGensUsed() >= 3;
}

function setWaifuGenMagicLoading(on) {
  if (typeof document === "undefined" || !document.body) return;
  const modal = document.getElementById("waifu-gen-magic-modal");
  if (modal) modal.hidden = !on;
  document.body.classList.toggle("waifu-gen-magic-busy", Boolean(on));
}

function waifuGenApplyPortraitPreview(dataUrl) {
  const img = document.getElementById("waifu-portrait-preview");
  const ph = document.getElementById("waifu-portrait-placeholder");
  if (img) {
    img.src = dataUrl;
    img.hidden = false;
  }
  if (ph) ph.style.display = "none";
}

function waifuGenClearPortraitPreview() {
  const img = document.getElementById("waifu-portrait-preview");
  const ph = document.getElementById("waifu-portrait-placeholder");
  if (img) {
    img.removeAttribute("src");
    img.hidden = true;
  }
  if (ph) ph.style.display = "";
}

function waifuGenUpdatePortraitFrameCursor() {
  const frame = document.getElementById("waifu-portrait-frame");
  if (!frame) return;
  frame.classList.toggle("waifu-gen-portrait-frame--selectable", waifuGeneratorState.variants.length >= 2);
  frame.title =
    waifuGeneratorState.variants.length >= 2 ? "Нажмите, чтобы переключить вариант портрета" : "";
}

function waifuGenRenderVariants() {
  const root = document.getElementById("waifu-gen-variants");
  if (!root) return;
  const list = waifuGeneratorState.variants;
  if (!list.length) {
    root.innerHTML = "";
    waifuGenUpdatePortraitFrameCursor();
    return;
  }
  root.innerHTML = list
    .map(
      (v, i) =>
        `<button type="button" class="waifu-gen-variant${i === waifuGeneratorState.selectedIdx ? " waifu-gen-variant--selected" : ""}" data-idx="${i}" aria-label="Вариант ${i + 1}">
        <img src="${escapeHtml(v.dataUrl)}" alt="" />
      </button>`
    )
    .join("");
  root.querySelectorAll(".waifu-gen-variant").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-idx"));
      if (!Number.isFinite(idx)) return;
      waifuGeneratorState.selectedIdx = idx;
      waifuGenRenderVariants();
      const v = waifuGeneratorState.variants[idx];
      if (v?.dataUrl) waifuGenApplyPortraitPreview(v.dataUrl);
    });
  });
  waifuGenUpdatePortraitFrameCursor();
}

async function waifuGenLoadDraftsFromServer() {
  waifuGeneratorState.variants = [];
  waifuGeneratorState.selectedIdx = 0;
  waifuGeneratorState.generationsCount = 0;
  try {
    const data = await apiFetch(`/profile/main-waifu/portrait-drafts`);
    const items = Array.isArray(data?.items) ? data.items : [];
    waifuGenSetGensUsed(Number(data?.generations_count) || items.length);
    waifuGeneratorState.variants = items
      .slice()
      .sort((a, b) => (Number(a.slot_index) || 0) - (Number(b.slot_index) || 0))
      .map((it) => {
        const mime = it.mime || "image/webp";
        const b64 = it.image_base64;
        return {
          b64,
          dataUrl: `data:${mime};base64,${b64}`,
          slot_index: Number(it.slot_index),
        };
      });
    if (waifuGeneratorState.variants.length) {
      waifuGeneratorState.selectedIdx = waifuGeneratorState.variants.length - 1;
      waifuGenApplyPortraitPreview(waifuGeneratorState.variants[waifuGeneratorState.selectedIdx].dataUrl);
    } else {
      waifuGenClearPortraitPreview();
    }
    waifuGenRenderVariants();
  } catch {
    waifuGenClearPortraitPreview();
    waifuGenRenderVariants();
  }
  waifuGenRefreshHint();
  waifuGenRefreshGenerateButton();
}

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
  activeAccordion: null,
  infoTab: "indicators",
  slotSort: "level",
  slotSortDir: "desc",
  slotPickerItems: [],
  slotPickerEquipped: null,
  equipmentLoaded: false,
  equipmentLoading: false,
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

/** Слот экипировки по умолчанию (без UI). Для колец — null (выбор отдельным оверлеем). */
function defaultEquipSlotForItem(item) {
  const st = String(item?.slot_type || "").trim();
  if (st === "ring") return null;
  const slots = SLOT_TYPE_TO_SLOTS[st] || [];
  if (!slots.length) return null;
  if (slots.length === 1) return slots[0];
  const empty = slots.find((s) => !getProfileEquippedItem(s));
  if (empty != null) return empty;
  return slots[0];
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

const SELL_PAGE_SIZE = 12;

const shopState = {
  act: 1,
  size: 12,
  offers: [],
  selectedSlot: null,
  selectedOffer: null,
  sellSelected: new Set(),
  sellItems: [],
  sellPage: 0,
  /** Вкладка «Продать»: true — клик по ячейке только выбирает; false — открыть карточку предмета */
  sellSelectMode: false,
  sellFilters: { weapon: true, armor: true, accessory: true },
  sellSort: "equipability",
  sellSortDir: "desc",
  /** Активная вкладка магазина: buy | sell | gamble | smith */
  activeTab: "buy",
  gambleOffers: [],
  shopRefreshAt: null,
  gambleRefreshAt: null,
  /** Слот витрины (1–9), который ИИ выделил в реплике «купить» */
  merchantPickBuySlot: null,
  /** inventory_items.id предмета, который ИИ выделил в реплике «продать» */
  merchantPickSellId: null,
  /** Подсветка совета торговца — только после нажатия на торговца */
  merchantAdviceUnlocked: false,
  /** Кэш AI-реплик торговца (ключ: buy:slot / sell:id / gamble / smith) */
  merchantLineCache: {},
  /** inventory_items.id выбранный для заточки */
  smithSelectedId: null,
  /** кэш списка для модалки выбора (сортировка: экип первыми) */
  smithItems: [],
  /** страница сетки выбора (по 9 предметов) */
  smithPickPage: 0,
  /** sharpen | craft — подвкладка кузницы */
  smithSubTab: "sharpen",
};

const SMITH_PICK_PAGE_SIZE = 9;
const SMITH_SAFE_MAX = 7;

const SMITH_PICK_LOADING_HTML = `<div class="shop-smith-pick-loading" aria-busy="true" aria-label="Загрузка инвентаря">
  ${Array.from({ length: 9 }, () => '<div class="shop-smith-pick-loading-card"></div>').join("")}
</div>`;

function resolveShopOfferSlot(offer) {
  if (!offer) return null;
  const offers = shopState.offers || [];
  const idx = offers.indexOf(offer);
  const fallbackSlot = idx >= 0 ? idx + 1 : null;
  const s = Number(offer.slot ?? offer.offer_slot ?? offer.shop_slot ?? fallbackSlot);
  return Number.isFinite(s) ? s : null;
}

function applyShopMerchantHighlight() {
  document.querySelectorAll(".shop-item-card.shop-merchant-pick, .shop-sell-card.shop-merchant-pick").forEach((el) => {
    el.classList.remove("shop-merchant-pick");
  });
  if (!shopState.merchantAdviceUnlocked) return;
  const tab = shopState.activeTab || "buy";
  if (tab === "buy" && shopState.merchantPickBuySlot != null) {
    const slot = Number(shopState.merchantPickBuySlot);
    const el = document.querySelector(`#shop-buy-grid .shop-item-card[data-shop-slot="${slot}"]`);
    if (el && !el.classList.contains("empty")) el.classList.add("shop-merchant-pick");
  }
  if (tab === "sell" && shopState.merchantPickSellId != null) {
    const id = Number(shopState.merchantPickSellId);
    const el = document.querySelector(`#shop-sell-grid .shop-sell-card[data-id="${id}"]`);
    if (el && !el.classList.contains("empty")) el.classList.add("shop-merchant-pick");
  }
}

function revealMerchantAdvice() {
  shopState.merchantAdviceUnlocked = true;
  applyShopMerchantHighlight();
}

const ADMIN_USER_ID = 305174198;

function isAdminUser() {
  try {
    const u = tg?.initDataUnsafe?.user;
    return u && Number(u.id) === ADMIN_USER_ID;
  } catch {
    return false;
  }
}

const ADMIN_UI_STORAGE_KEY = "waifu_admin_ui_enabled";

function isAdminUiEnabled() {
  if (!isAdminUser()) return false;
  try {
    return localStorage.getItem(ADMIN_UI_STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

function setAdminUiEnabled(on) {
  try {
    localStorage.setItem(ADMIN_UI_STORAGE_KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
  syncAdminUiVisibility();
}

function syncAdminUiVisibility() {
  const show = isAdminUiEnabled();
  document.querySelectorAll(".admin-only").forEach((el) => {
    el.style.display = show ? "" : "none";
  });
}

const settingsState = {
  dmPrefs: null,
  notifySaveTimer: null,
  notifyModalReadyAt: 0,
  notifyBackHandler: null,
  soloAutoPrefs: null,
  soloAutoSaveTimer: null,
  soloAutoModalReadyAt: 0,
  soloAutoBackHandler: null,
  soloAutoLoadPromise: null,
};

function resetSettingsNotifyModalDom() {
  const modal = document.getElementById("settings-notify-modal");
  if (!modal) return;
  modal.classList.remove("settings-notify-modal--open");
  modal.style.display = "none";
}

function resetSettingsSoloAutoModalDom() {
  const modal = document.getElementById("settings-solo-auto-modal");
  if (!modal) return;
  modal.classList.remove("settings-notify-modal--open");
  modal.style.display = "none";
}

function syncSoloAutoSubpanelVisibility(enabled) {
  const sub = document.getElementById("settings-solo-auto-subpanel");
  if (sub) sub.hidden = !enabled;
}

function applySoloAutoPrefsToModal(prefs) {
  if (!prefs) return;
  const enabledInput = document.getElementById("settings-solo-auto-enabled");
  if (enabledInput) {
    enabledInput.checked = Boolean(prefs.enabled);
    syncSoloAutoSubpanelVisibility(enabledInput.checked);
  }
  const hp = document.getElementById("settings-solo-auto-hp");
  const hpValue = document.getElementById("settings-solo-auto-hp-value");
  if (hp && prefs.min_hp_percent != null) {
    hp.value = String(prefs.min_hp_percent);
    if (hpValue) hpValue.textContent = String(prefs.min_hp_percent);
  }
  document.querySelectorAll("#settings-solo-auto-modal [data-solo-auto-key]").forEach((input) => {
    const key = input.getAttribute("data-solo-auto-key");
    if (!key || key === "enabled" || key === "min_hp_percent") return;
    if (Object.prototype.hasOwnProperty.call(prefs, key)) {
      input.checked = Boolean(prefs[key]);
    }
  });
}

async function loadSoloDungeonAutoPrefs() {
  const data = await apiFetch("/player/solo-dungeon-auto-prefs");
  settingsState.soloAutoPrefs = data;
  return data;
}

function scheduleSaveSoloDungeonAutoPrefs() {
  if (settingsState.soloAutoSaveTimer) clearTimeout(settingsState.soloAutoSaveTimer);
  settingsState.soloAutoSaveTimer = setTimeout(() => {
    settingsState.soloAutoSaveTimer = null;
    saveSoloDungeonAutoPrefsFromModal();
  }, 400);
}

async function saveSoloDungeonAutoPrefsFromModal() {
  const patch = {};
  const enabledInput = document.getElementById("settings-solo-auto-enabled");
  if (enabledInput) patch.enabled = enabledInput.checked;
  const hp = document.getElementById("settings-solo-auto-hp");
  if (hp) patch.min_hp_percent = Number(hp.value);
  document.querySelectorAll("#settings-solo-auto-modal [data-solo-auto-key]").forEach((input) => {
    const key = input.getAttribute("data-solo-auto-key");
    if (!key || key === "enabled" || key === "min_hp_percent") return;
    patch[key] = input.checked;
  });
  try {
    const data = await apiFetch("/player/solo-dungeon-auto-prefs", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    settingsState.soloAutoPrefs = data;
    applySoloAutoPrefsToModal(data);
  } catch (e) {
    console.warn("saveSoloDungeonAutoPrefs failed:", e);
    showToast("Не удалось сохранить автовход", "error");
  }
}

async function ensureSoloDungeonAutoPrefsLoaded() {
  if (settingsState.soloAutoPrefs) return settingsState.soloAutoPrefs;
  if (settingsState.soloAutoLoadPromise) return settingsState.soloAutoLoadPromise;
  settingsState.soloAutoLoadPromise = loadSoloDungeonAutoPrefs()
    .then((prefs) => {
      settingsState.soloAutoPrefs = prefs;
      applySoloAutoPrefsToModal(prefs);
      return prefs;
    })
    .catch((e) => {
      console.warn("loadSoloDungeonAutoPrefs failed:", e);
      return null;
    })
    .finally(() => {
      settingsState.soloAutoLoadPromise = null;
    });
  return settingsState.soloAutoLoadPromise;
}

function openSettingsSoloAutoModal() {
  if (Date.now() < settingsState.soloAutoModalReadyAt) return;
  const modal = document.getElementById("settings-solo-auto-modal");
  if (!modal) return;
  void ensureSoloDungeonAutoPrefsLoaded().then((prefs) => {
    if (prefs) applySoloAutoPrefsToModal(prefs);
    modal.style.display = "";
    modal.classList.add("settings-notify-modal--open");
    if (tg?.BackButton) {
      if (!settingsState.soloAutoBackHandler) {
        settingsState.soloAutoBackHandler = () => closeSettingsSoloAutoModal();
      }
      tg.BackButton.onClick(settingsState.soloAutoBackHandler);
      tg.BackButton.show();
    }
  });
}

function closeSettingsSoloAutoModal() {
  const modal = document.getElementById("settings-solo-auto-modal");
  if (!modal) return;
  modal.classList.remove("settings-notify-modal--open");
  modal.style.display = "none";
  if (tg?.BackButton && settingsState.soloAutoBackHandler) {
    tg.BackButton.offClick(settingsState.soloAutoBackHandler);
    tg.BackButton.hide();
  }
}

async function loadDmNotificationPrefs() {
  const data = await apiFetch("/player/dm-notification-prefs");
  settingsState.dmPrefs = data;
  return data;
}

function applyDmPrefsToModal(prefs) {
  document.querySelectorAll("#settings-notify-modal [data-notify-key]").forEach((input) => {
    const key = input.getAttribute("data-notify-key");
    if (key && prefs && Object.prototype.hasOwnProperty.call(prefs, key)) {
      input.checked = Boolean(prefs[key]);
    }
  });
}

function scheduleSaveDmNotificationPrefs() {
  if (settingsState.notifySaveTimer) clearTimeout(settingsState.notifySaveTimer);
  settingsState.notifySaveTimer = setTimeout(() => {
    settingsState.notifySaveTimer = null;
    saveDmNotificationPrefsFromModal();
  }, 400);
}

async function saveDmNotificationPrefsFromModal() {
  const patch = {};
  document.querySelectorAll("#settings-notify-modal [data-notify-key]").forEach((input) => {
    const key = input.getAttribute("data-notify-key");
    if (key) patch[key] = input.checked;
  });
  try {
    const data = await apiFetch("/player/dm-notification-prefs", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    settingsState.dmPrefs = data;
  } catch (e) {
    console.warn("saveDmNotificationPrefs failed:", e);
    showToast("Не удалось сохранить уведомления", "error");
  }
}

async function ensureDmNotificationPrefsLoaded() {
  if (settingsState.dmPrefs) return settingsState.dmPrefs;
  if (settingsState.dmPrefsLoadPromise) return settingsState.dmPrefsLoadPromise;
  settingsState.dmPrefsLoadPromise = loadDmNotificationPrefs()
    .then((prefs) => {
      settingsState.dmPrefs = prefs;
      applyDmPrefsToModal(prefs);
      return prefs;
    })
    .catch((e) => {
      console.warn("loadDmNotificationPrefs failed:", e);
      return null;
    })
    .finally(() => {
      settingsState.dmPrefsLoadPromise = null;
    });
  return settingsState.dmPrefsLoadPromise;
}

function openSettingsNotifyModal() {
  if (Date.now() < settingsState.notifyModalReadyAt) return;
  const modal = document.getElementById("settings-notify-modal");
  if (!modal) return;
  void ensureDmNotificationPrefsLoaded().then((prefs) => {
    if (prefs) applyDmPrefsToModal(prefs);
    modal.style.display = "";
    modal.classList.add("settings-notify-modal--open");
    if (tg?.BackButton) {
      if (!settingsState.notifyBackHandler) {
        settingsState.notifyBackHandler = () => closeSettingsNotifyModal();
      }
      tg.BackButton.onClick(settingsState.notifyBackHandler);
      tg.BackButton.show();
    }
  });
}

function closeSettingsNotifyModal() {
  const modal = document.getElementById("settings-notify-modal");
  if (!modal) return;
  modal.classList.remove("settings-notify-modal--open");
  modal.style.display = "none";
  if (tg?.BackButton && settingsState.notifyBackHandler) {
    tg.BackButton.offClick(settingsState.notifyBackHandler);
    tg.BackButton.hide();
  }
}

function initSettingsPageBindings() {
  resetSettingsNotifyModalDom();
  closeSettingsNotifyModal();
  resetSettingsSoloAutoModalDom();
  closeSettingsSoloAutoModal();

  if (!window.__waifuSettingsPageshowBound) {
    window.__waifuSettingsPageshowBound = true;
    window.addEventListener("pageshow", () => {
      if (
        document.body.classList.contains("page-settings") ||
        document.body.classList.contains("page-player")
      ) {
        closeSettingsNotifyModal();
        closeSettingsSoloAutoModal();
      }
    });
  }

  if (!window.__waifuSettingsEscapeBound) {
    window.__waifuSettingsEscapeBound = true;
    window.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape") return;
      const notifyModal = document.getElementById("settings-notify-modal");
      if (notifyModal?.classList.contains("settings-notify-modal--open")) {
        ev.preventDefault();
        closeSettingsNotifyModal();
        return;
      }
      const soloModal = document.getElementById("settings-solo-auto-modal");
      if (soloModal?.classList.contains("settings-notify-modal--open")) {
        ev.preventDefault();
        closeSettingsSoloAutoModal();
      }
    });
  }

  syncAdminUiVisibility();
  const adminRow = document.getElementById("settings-admin-row");
  const adminToggle = document.getElementById("settings-admin-toggle");
  if (isAdminUser() && adminRow) {
    adminRow.style.display = "";
    if (adminToggle) {
      adminToggle.checked = isAdminUiEnabled();
      if (!adminToggle.__waifuBound) {
        adminToggle.__waifuBound = true;
        adminToggle.addEventListener("change", () => {
          setAdminUiEnabled(adminToggle.checked);
        });
      }
    }
  }

  const openBtn = document.getElementById("settings-open-notify");
  if (openBtn && !openBtn.__waifuBound) {
    openBtn.__waifuBound = true;
    openBtn.addEventListener("click", () => openSettingsNotifyModal());
  }

  const modal = document.getElementById("settings-notify-modal");
  if (modal && !modal.__waifuBound) {
    modal.__waifuBound = true;
    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) closeSettingsNotifyModal();
    });
    const panel = modal.querySelector(".settings-notify-panel");
    if (panel) {
      panel.addEventListener("click", (ev) => ev.stopPropagation());
    }
    document.getElementById("settings-notify-close")?.addEventListener("click", () => {
      closeSettingsNotifyModal();
    });
    document.getElementById("settings-notify-done")?.addEventListener("click", () => {
      closeSettingsNotifyModal();
    });
    document.querySelectorAll("#settings-notify-modal [data-notify-key]").forEach((input) => {
      input.addEventListener("change", scheduleSaveDmNotificationPrefs);
    });
  }

  const openSoloBtn = document.getElementById("settings-open-solo-auto");
  if (openSoloBtn && !openSoloBtn.__waifuBound) {
    openSoloBtn.__waifuBound = true;
    openSoloBtn.addEventListener("click", () => openSettingsSoloAutoModal());
  }

  const soloModal = document.getElementById("settings-solo-auto-modal");
  if (soloModal && !soloModal.__waifuBound) {
    soloModal.__waifuBound = true;
    soloModal.addEventListener("click", (ev) => {
      if (ev.target === soloModal) closeSettingsSoloAutoModal();
    });
    const soloPanel = soloModal.querySelector(".settings-notify-panel");
    if (soloPanel) {
      soloPanel.addEventListener("click", (ev) => ev.stopPropagation());
    }
    document.getElementById("settings-solo-auto-close")?.addEventListener("click", () => {
      closeSettingsSoloAutoModal();
    });
    document.getElementById("settings-solo-auto-done")?.addEventListener("click", () => {
      closeSettingsSoloAutoModal();
    });
    const enabledInput = document.getElementById("settings-solo-auto-enabled");
    if (enabledInput) {
      enabledInput.addEventListener("change", () => {
        syncSoloAutoSubpanelVisibility(enabledInput.checked);
        scheduleSaveSoloDungeonAutoPrefs();
      });
    }
    const hp = document.getElementById("settings-solo-auto-hp");
    if (hp) {
      hp.addEventListener("input", () => {
        const hpValue = document.getElementById("settings-solo-auto-hp-value");
        if (hpValue) hpValue.textContent = String(hp.value);
        scheduleSaveSoloDungeonAutoPrefs();
      });
    }
    document
      .querySelectorAll("#settings-solo-auto-modal [data-solo-auto-key='increase_plus_difficulty']")
      .forEach((input) => {
        input.addEventListener("change", scheduleSaveSoloDungeonAutoPrefs);
      });
  }

  settingsState.notifyModalReadyAt = Date.now() + 300;
  settingsState.soloAutoModalReadyAt = Date.now() + 300;
}

async function initSettingsPage() {
  initSettingsPageBindings();
  try {
    const prefs = await loadDmNotificationPrefs();
    applyDmPrefsToModal(prefs);
  } catch (e) {
    console.warn("loadDmNotificationPrefs failed:", e);
  }
}

// In-flight dedup for /profile. Many call sites refresh the profile right after
// a mutation, so we deliberately do NOT add a TTL cache (that would serve stale
// gold/state). Instead we only collapse *concurrent* duplicate requests — e.g.
// an SSE-triggered refetch firing while the page bootstrap is still loading —
// into a single blocking network call. Sequential (post-await) calls still hit
// the network and get fresh data.
const profileInFlight = { lite: null, full: null };

async function loadProfile(options = {}) {
  const lite = options.lite ?? !isProfilePage();
  const key = lite ? "lite" : "full";
  const populateOpts = { skipAtticRefresh: options.skipAtticRefresh === true };

  if (profileInFlight[key]) {
    const profile = await profileInFlight[key];
    populateFromProfile(profile, populateOpts);
    return profile;
  }

  const initData = getInitData();
  const params = new URLSearchParams();
  if (initData) params.set("initData", initData);
  if (lite) params.set("lite", "1");
  const qs = params.toString();
  const promise = apiFetch(`/profile${qs ? `?${qs}` : ""}`);
  profileInFlight[key] = promise;
  try {
    const profile = await promise;
    populateFromProfile(profile, populateOpts);
    return profile;
  } finally {
    if (profileInFlight[key] === promise) profileInFlight[key] = null;
  }
}

/** One-time bind: ОЧ chip clicks open dungeons.html with the right tab. */
function initAtticChipClicks() {
  if (window.__atticChipClicksBound) return;
  window.__atticChipClicksBound = true;
  const dungeonChip = document.getElementById("attic-dungeon-chip");
  if (dungeonChip) {
    dungeonChip.addEventListener("click", () => {
      window.location.href = "./dungeons.html?tab=solo";
    });
    dungeonChip.style.cursor = "pointer";
  }
  const expChip = document.getElementById("attic-exp-chip");
  if (expChip) {
    expChip.addEventListener("click", () => {
      window.location.href = "./dungeons.html?tab=expedition";
    });
    expChip.style.cursor = "pointer";
  }
  if (document.getElementById("attic-exp-cells")) {
    renderAtticExpeditions([], 3);
  }
}

function initAtticMenu() {
  if (window.__atticMenuBound) return;
  window.__atticMenuBound = true;
  const btn = document.getElementById("attic-menu-btn");
  const menu = document.getElementById("attic-menu");
  if (!btn || !menu) return;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = menu.hidden;
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  menu.addEventListener("click", (e) => e.stopPropagation());
  document.addEventListener("click", () => {
    if (!menu.hidden) {
      menu.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !menu.hidden) {
      menu.hidden = true;
      btn.setAttribute("aria-expanded", "false");
      btn.focus();
    }
  });
}

function registerWaifuServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  if (!window.__waifuSwControllerBound) {
    window.__waifuSwControllerBound = true;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (window.__waifuSwReloading) return;
      window.__waifuSwReloading = true;
      window.location.reload();
    });
  }
  const doUpdate = (reg) => {
    if (reg) reg.update().catch(() => {});
  };
  if (window.__waifuSwRegistered) {
    navigator.serviceWorker.getRegistration("/webapp/sw.js").then(doUpdate).catch(() => {});
    return;
  }
  window.__waifuSwRegistered = true;
  navigator.serviceWorker
    .register("/webapp/sw.js")
    .then((reg) => doUpdate(reg))
    .catch(() => {});
}

async function bootstrapPage(page, afterLoad) {
  await initPage(page);
  let profile = null;
  try {
    profile = await loadProfile({ lite: page !== "profile" });
  } catch (err) {
    if (isWebAppUnauthorizedError(err)) {
      console.warn("Профиль недоступен: откройте WebApp из Telegram или используйте ?devPlayerId= при APP_ENV=dev.");
      profile = { __authRequired: true };
    } else {
      console.error("Failed to load profile:", err);
    }
  }

  if (typeof afterLoad === "function") {
    try {
      await afterLoad(profile ?? (page === "index" ? null : { act: 1 }));
    } catch (err) {
      console.error("Failed to bootstrap page:", err);
    }
  }

  try {
    const forced = new URLSearchParams(window.location.search).get("tutorial");
    const hasWaifu = Boolean(
      profile?.main_waifu && (profile.main_waifu.id != null || profile.main_waifu.level != null),
    );
    if (hasWaifu || page !== "profile") {
      let opts;
      if (page === "dungeons") {
        const tabParam = new URLSearchParams(window.location.search).get("tab") || "solo";
        opts = { tab: tabParam };
      }
      window.WaifuApp?.Tutorial?.maybeRun(page, profile?.tutorial, forced, opts);
    }
  } catch (err) {
    console.warn("Tutorial bootstrap failed:", err);
  }

  if (page === "settings") {
    try {
      await initSettingsPage();
    } catch (err) {
      console.warn("initSettingsPage failed:", err);
    }
  }

  return profile;
}

async function bootstrapTrainingHall() {
  await initPage("training");
  let profile = null;
  const profilePromise = loadProfile({ lite: true, skipAtticRefresh: true })
    .then((p) => {
      profile = p;
      return p;
    })
    .catch((err) => {
      if (isWebAppUnauthorizedError(err)) {
        console.warn("Профиль недоступен: откройте WebApp из Telegram или используйте ?devPlayerId= при APP_ENV=dev.");
        profile = { __authRequired: true };
        return profile;
      }
      console.error("Failed to load profile:", err);
      return null;
    });
  await Promise.all([profilePromise, loadPassiveSkillTree()]);
  bindHiddenSkillsListenersOnce();
  bindPerfectionListenersOnce();
  try {
    const tabQ = new URLSearchParams(window.location.search).get("tab");
    if (tabQ === "perfection") {
      trainingHallTab = "perfection";
      applyTrainingHallTabUI();
      await loadPerfectionPanel();
    }
  } catch (_) {}
  scheduleDeferredAtticRefresh(profile);

  try {
    const forced = new URLSearchParams(window.location.search).get("tutorial");
    const hasWaifu = Boolean(
      profile?.main_waifu && (profile.main_waifu.id != null || profile.main_waifu.level != null),
    );
    if (hasWaifu) {
      window.WaifuApp?.Tutorial?.maybeRun("training", profile?.tutorial, forced);
    }
  } catch (err) {
    console.warn("Tutorial bootstrap failed:", err);
  }

  return profile;
}

let perfectionStateCache = null;
let perfectionListenersBound = false;

function bindPerfectionListenersOnce() {
  if (perfectionListenersBound) return;
  perfectionListenersBound = true;
  const closeBtn = document.getElementById("perfection-choose-close");
  if (closeBtn) closeBtn.addEventListener("click", closePerfectionChooseModal);
}

function closePerfectionChooseModal() {
  const modal = document.getElementById("perfection-choose-modal");
  if (modal) modal.style.display = "none";
}

function openPerfectionChooseModal(state) {
  // Single choose modal — never stack a second overlay.
  const existing = document.getElementById("perfection-choose-modal");
  if (!existing) return;
  const modal = existing;
  const body = document.getElementById("perfection-choose-body");
  const title = document.getElementById("perfection-choose-title");
  const pending = state?.pending;
  if (!body || !pending) return;
  const kind = pending.kind === "skill_point" ? "Очко навыка" : "Выбор бонуса";
  if (title) title.textContent = `${kind} · ур. ${pending.perfection_level}`;
  const opts = Array.isArray(pending.options) ? pending.options : [];
  body.innerHTML = `<div class="perfection-choose-grid">${opts
    .map((opt, idx) => {
      const label = escapeHtml(opt.label || (opt.kind === "permanent" ? "Навсегда" : "Сразу"));
      const name = escapeHtml(opt.title_ru || opt.bonus_id || "Бонус");
      const val = escapeHtml(opt.display_value || "");
      return `<button type="button" class="perfection-choose-card" data-perfection-opt="${idx}">
        <span class="perfection-choose-badge">${label}</span>
        <strong class="perfection-choose-name">${name}</strong>
        <span class="perfection-choose-value">${val}</span>
      </button>`;
    })
    .join("")}</div>`;
  body.querySelectorAll("[data-perfection-opt]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const idx = Number(btn.getAttribute("data-perfection-opt"));
      await choosePerfectionOption(pending.id, idx);
    });
  });
  modal.style.display = "flex";
}

async function loadPerfectionPanel() {
  const root = document.getElementById("perfection-root");
  if (!root) return;
  root.classList.add("placeholder");
  root.textContent = "Загрузка…";
  try {
    const state = await apiFetch("/perfection");
    perfectionStateCache = state;
    renderPerfectionPanel(state);
  } catch (err) {
    console.error(err);
    root.textContent = "Не удалось загрузить совершенствование.";
  }
}

function renderPerfectionPanel(state) {
  const root = document.getElementById("perfection-root");
  if (!root) return;
  root.classList.remove("placeholder");
  if (!state?.unlocked) {
    root.innerHTML = `<div class="perfection-locked muted">Откроется на 60 уровне основной вайфу.</div>`;
    return;
  }
  const lvl = Number(state.perfection_level || 0);
  const xp = Number(state.perfection_experience || 0);
  const need = Number(state.perfection_xp_to_next || 0);
  const pct = need > 0 ? Math.round(clamp01(xp / need) * 100) : 0;
  const pendingCount = Number(state.pending_count || 0);
  const summary = Array.isArray(state.bonuses_summary) ? state.bonuses_summary : [];
  const summaryHtml = summary.length
    ? `<ul class="perfection-bonus-list">${summary
        .map(
          (b) =>
            `<li><span>${escapeHtml(b.title_ru || b.bonus_id)}</span><strong>${escapeHtml(
              b.display_value || ""
            )}</strong><em class="perfection-bonus-tag">${escapeHtml(b.label || "Навсегда")}</em></li>`
        )
        .join("")}</ul>`
    : `<p class="muted tiny">Постоянных бонусов пока нет — выберите первый оффер.</p>`;
  root.innerHTML = `
    <div class="perfection-header">
      <div class="perfection-level-line">Совершенствование <strong>${lvl}</strong> · тир ${Number(state.tier || 1)}</div>
      <div class="perfection-xp-text">${xp} / ${need} EXP</div>
      <div class="perfection-xp-bar"><div class="perfection-xp-fill" style="width:${pct}%"></div></div>
    </div>
    <div class="perfection-actions">
      <button type="button" class="btn" id="perfection-open-choose" ${pendingCount > 0 ? "" : "disabled"}>
        Выбрать бонус${pendingCount > 1 ? ` (${pendingCount})` : ""}
      </button>
    </div>
    <h3 class="section-head">Текущие бонусы</h3>
    ${summaryHtml}
  `;
  const btn = document.getElementById("perfection-open-choose");
  if (btn && pendingCount > 0) {
    btn.addEventListener("click", () => openPerfectionChooseModal(state));
  }
  // Auto-open FIFO head when there are pending bonuses (single modal DOM).
  if (pendingCount > 0 && state.pending) {
    openPerfectionChooseModal(state);
  }
}

async function choosePerfectionOption(pendingId, optionIndex) {
  try {
    const state = await apiFetch("/perfection/choose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pending_id: pendingId,
        option_index: optionIndex,
      }),
    });
    closePerfectionChooseModal();
    perfectionStateCache = state;
    const applied = state?.applied;
    if (applied?.title_ru) {
      showToast(`${applied.title_ru} ${applied.display_value || ""}`, "success");
    }
    renderPerfectionPanel(state);
    const profile = await loadProfile({ lite: false });
    if (profile) {
      populateFromProfile(profile);
      if (isProfilePage()) await populateProfile(profile);
    }
    if (state?.pending_count > 0 && state.pending) {
      openPerfectionChooseModal(state);
    }
  } catch (err) {
    console.error(err);
    showToast(err?.message || "Не удалось выбрать бонус", "error");
  }
}

function consumeShopSmithIntent() {
  let openSmith = false;
  let smithItemId = null;
  try {
    const t = sessionStorage.getItem("waifu_shop_intent_tab");
    const raw = sessionStorage.getItem("waifu_shop_smith_item_id");
    sessionStorage.removeItem("waifu_shop_intent_tab");
    sessionStorage.removeItem("waifu_shop_smith_item_id");
    openSmith = t === "smith";
    if (raw != null) {
      const n = Number(raw);
      if (Number.isFinite(n) && n > 0) smithItemId = n;
    }
  } catch (e) {
    /* ignore */
  }
  return { openSmith, smithItemId };
}

async function applyShopSmithNavigationIntent(intent) {
  if (!intent?.openSmith) return;
  if (typeof window === "undefined" || !String(window.location.pathname || "").endsWith("/shop.html")) {
    return;
  }
  switchShopTab("smith");
  await loadSmithTab();
  const sid = intent.smithItemId;
  if (sid != null && shopState.smithItems.some((x) => x.id === sid)) {
    shopState.smithSelectedId = sid;
    updateSmithSelectionUI();
    await refreshSmithPreview();
  }
}

async function bootstrapShopPage() {
  await initPage("shop");
  let profile = null;
  const actHint = safeInt(profileState.currentProfile?.act ?? shopState.act, 1);
  const shopSmithNavIntent = consumeShopSmithIntent();
  const profilePromise = loadProfile({ lite: true, skipAtticRefresh: true })
    .then((p) => {
      profile = p;
      return p;
    })
    .catch((err) => {
      if (isWebAppUnauthorizedError(err)) {
        console.warn("Профиль недоступен: откройте WebApp из Telegram или используйте ?devPlayerId= при APP_ENV=dev.");
        profile = { __authRequired: true };
        return profile;
      }
      console.error("Failed to load profile:", err);
      return null;
    });

  await Promise.all([profilePromise, loadShop(actHint)]);

  const p = profile || profileState.currentProfile;
  const act = safeInt(p?.act ?? actHint, 1);
  applyShopHeroImages(act);
  updateShopProfileError(p);
  if (act !== actHint) {
    await loadShop(act);
  }
  if (shopSmithNavIntent.openSmith) {
    await applyShopSmithNavigationIntent(shopSmithNavIntent);
  } else {
    try {
      const shopTab = new URLSearchParams(window.location.search).get("tab");
      if (shopTab && ["buy", "sell", "gamble", "smith"].includes(shopTab)) {
        switchShopTab(shopTab);
      }
    } catch {
      // ignore
    }
  }
  ensureShopSellToolbar();
  updateShopGambleCost();
  scheduleDeferredAtticRefresh(profile);

  try {
    const forced = new URLSearchParams(window.location.search).get("tutorial");
    const hasWaifu = Boolean(
      p?.main_waifu && (p.main_waifu.id != null || p.main_waifu.level != null),
    );
    if (hasWaifu) {
      window.WaifuApp?.Tutorial?.maybeRun("shop", p?.tutorial, forced);
    }
  } catch (err) {
    console.warn("Tutorial bootstrap failed:", err);
  }

  return profile;
}

async function bootstrapTavernPage() {
  await initPage("tavern");
  let profile = null;
  const profilePromise = loadProfile({ lite: true, skipAtticRefresh: true })
    .then((p) => {
      profile = p;
      return p;
    })
    .catch((err) => {
      if (isWebAppUnauthorizedError(err)) {
        console.warn("Профиль недоступен: откройте WebApp из Telegram или используйте ?devPlayerId= при APP_ENV=dev.");
        profile = { __authRequired: true };
        return profile;
      }
      console.error("Failed to load profile:", err);
      return null;
    });
  const availablePromise = apiFetch("/tavern/available").catch((err) => {
    console.error("Failed to load tavern available:", err);
    return null;
  });
  const [, available] = await Promise.all([profilePromise, availablePromise]);
  const p = profile || profileState.currentProfile || { act: 1 };
  try {
    await window.WaifuApp?.loadTavernWithProfile?.(p, { preloadedAvailable: available });
  } catch (err) {
    console.error("Failed to bootstrap tavern:", err);
  }
  scheduleDeferredAtticRefresh(profile);

  try {
    const tavernTab = new URLSearchParams(window.location.search).get("tab");
    if (tavernTab && ["hire", "squad", "heal", "upgrade"].includes(tavernTab)) {
      window.WaifuApp?.switchTavernTab?.(tavernTab);
    }
  } catch {
    // ignore
  }

  try {
    const forced = new URLSearchParams(window.location.search).get("tutorial");
    const hasWaifu = Boolean(
      p?.main_waifu && (p.main_waifu.id != null || p.main_waifu.level != null),
    );
    if (hasWaifu) {
      window.WaifuApp?.Tutorial?.maybeRun("tavern", p?.tutorial, forced);
    }
  } catch (err) {
    console.warn("Tutorial bootstrap failed:", err);
  }

  return profile;
}

async function bootstrapPlayerPage() {
  await initPage("player");
  initSettingsPageBindings();

  const viewId = getPlayerViewIdFromQuery();
  let profile = null;
  const profilePromise = loadProfile({ lite: true, skipAtticRefresh: true })
    .then((p) => {
      profile = p;
      return p;
    })
    .catch((err) => {
      if (isWebAppUnauthorizedError(err)) {
        console.warn("Профиль недоступен: откройте WebApp из Telegram или используйте ?devPlayerId= при APP_ENV=dev.");
        profile = { __authRequired: true };
        return profile;
      }
      console.error("Failed to load profile:", err);
      return null;
    });

  const playerProfilePromise =
    viewId == null
      ? apiFetch("/player/profile").catch((err) => {
          console.error("Failed to load player profile:", err);
          return null;
        })
      : profilePromise.then((p) => {
          const selfId = p?.player_id != null ? Number(p.player_id) : null;
          const path =
            viewId != null && (selfId == null || viewId !== selfId)
              ? `/player/${encodeURIComponent(viewId)}/profile`
              : "/player/profile";
          return apiFetch(path).catch((err) => {
            console.error("Failed to load player profile:", err);
            return null;
          });
        });

  const [, preloadedPlayerProfile] = await Promise.all([profilePromise, playerProfilePromise]);
  const p = profile || profileState.currentProfile || {};

  try {
    await initPlayerPage(p, { preloadedPlayerProfile });
  } catch (err) {
    console.error("Failed to bootstrap player page:", err);
  }

  schedulePlayerMailBadgeRefresh();

  try {
    const forced = new URLSearchParams(window.location.search).get("tutorial");
    const hasWaifu = Boolean(
      p?.main_waifu && (p.main_waifu.id != null || p.main_waifu.level != null),
    );
    if (hasWaifu) {
      window.WaifuApp?.Tutorial?.maybeRun("player", p?.tutorial, forced);
    }
  } catch (err) {
    console.warn("Tutorial bootstrap failed:", err);
  }

  return profile;
}

function updateShopProfileError(profile) {
  const p = profile || profileState.currentProfile;
  const errBox = document.getElementById("shop-profile-error");
  if (!errBox) return;
  if (!p?.main_waifu) {
    errBox.textContent = "Сначала создайте вайфу.";
    errBox.style.display = "";
  } else {
    errBox.style.display = "none";
    errBox.textContent = "";
  }
}

async function shopPageBootstrap(profile, merchantMeta) {
  void merchantMeta;
  const p = profile || profileState.currentProfile || { act: 1 };
  const act = safeInt(p?.act ?? shopState.act, 1);
  shopState.act = act;
  shopState.activeTab = shopState.activeTab || "buy";
  updateShopProfileError(p);
  await loadShop(act);
  return p;
}

async function loadShop(act) {
  const data = await apiFetch(`/shop/inventory?act=${act}`);
  shopState.act = act;
  shopState.size = safeInt(data?.size, 12);
  shopState.offers = Array.isArray(data?.items) ? data.items : [];
  shopState.shopRefreshAt = data?.refresh_at || null;
  updateShopRefreshLabel("buy");

  if (typeof window !== "undefined") {
    syncAdminUiVisibility();
  }

  // New shop v1.3 layout
  const newGrid = document.getElementById("shop-buy-grid");
  if (newGrid) {
    newGrid.innerHTML = "";
    newGrid.classList.remove("placeholder");
    const offers = shopState.offers || [];
    const bySlot = new Map();
    offers.forEach((o, idx) => {
      const slot = Number(o.slot || o.offer_slot || o.shop_slot || idx + 1);
      if (Number.isFinite(slot)) bySlot.set(slot, { ...o, __slot: slot });
    });
    for (let s = 1; s <= shopState.size; s += 1) {
      const offer = bySlot.get(s) || null;
      const card = document.createElement("div");
      const isSold = Boolean(offer?.sold);
      const rarityClass = rarityClassFromValue(offer?.rarity);
      card.className = `shop-item-card item-card ${isSold || !offer ? "empty" : ""} ${rarityClass}`.trim();
      const levelStr = offer && !isSold ? `lvl ${offer.level ?? "?"}` : (isSold ? "Продано" : "—");
      const priceBottomStr = offer && !isSold && offer?.price != null
        ? `🪙 ${offer.price}`
        : (isSold ? "Продано" : "—");
      const iconHtml = offer ? itemArtHtml(offer, { lazy: true }) : "🎁";
      card.dataset.shopSlot = String(s);
      card.innerHTML = `
        <div class="item-icon">${iconHtml}</div>
        <div class="item-level">${levelStr}</div>
        <div class="item-price">${escapeHtml(String(priceBottomStr))}</div>
      `;
      card.onclick = () => {
        if (!offer || isSold) return;
        openShopOffer(s);
        newGrid.querySelectorAll(".shop-item-card").forEach((c) => c.classList.remove("selected"));
        card.classList.add("selected");
      };
      newGrid.appendChild(card);
    }

    const sellBtn = document.getElementById("shop-sell-submit");
    if (sellBtn) sellBtn.style.display = (shopState.activeTab || "buy") === "sell" ? "" : "none";
    if ((shopState.activeTab || "buy") === "smith") {
      loadSmithTab().catch(() => {});
    }
    ensureShopSellToolbar();
    return data;
  }

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
    const levelStr = offer && !isSold ? `lvl ${offer.level ?? "?"}` : (isSold ? "Продано" : "—");
    const priceBottomStr = offer && !isSold && offer?.price != null
      ? `🪙 ${offer.price}`
      : (isSold ? "Продано" : "—");
    const iconHtml = offer ? itemArtHtml(offer, { lazy: true }) : "🎁";
    card.dataset.shopSlot = String(slot);
    card.innerHTML = `
      <div class="item-icon">${iconHtml}</div>
      <div class="item-level">${levelStr}</div>
      <div class="item-price">${escapeHtml(String(priceBottomStr))}</div>
    `;
    card.title = offer ? `${offer?.display_name || offer?.name || "Предмет"} (слот ${slot})` : `Пусто (слот ${slot})`;
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

function rarityClassFromValue(r) {
  return r === 2
    ? "rarity-uncommon"
    : r === 3
      ? "rarity-rare"
      : r === 4
        ? "rarity-epic"
        : r === 5
          ? "rarity-legendary"
          : "rarity-common";
}

async function refreshMerchantLine() {
  return onShopHeroAdvice(shopState.activeTab || "buy");
}

let shopHeroDialogTimer = null;
const SHOP_HERO_DIALOG_MS = 5000;

function hideShopHeroDialogs() {
  clearTimeout(shopHeroDialogTimer);
  shopHeroDialogTimer = null;
  document.querySelectorAll("body.page-shop .shop-dialog.show").forEach((el) => {
    el.classList.remove("show");
  });
}

function updateShopHeroDialogText(tab, html) {
  const textEl = document.getElementById(`shop-dialog-text-${tab}`);
  if (textEl) textEl.innerHTML = html;
}

function showShopHeroDialog(tab, html) {
  const ctx = tab || shopState.activeTab || "buy";
  const dialog = document.getElementById(`shop-dialog-${ctx}`);
  const textEl = document.getElementById(`shop-dialog-text-${ctx}`);
  const fillEl = document.getElementById(`shop-dialog-timer-fill-${ctx}`);
  if (!dialog || !textEl) return;

  document.querySelectorAll("body.page-shop .shop-dialog.show").forEach((el) => {
    if (el !== dialog) el.classList.remove("show");
  });

  textEl.innerHTML = html;
  dialog.classList.add("show");

  if (fillEl) {
    fillEl.style.transition = "none";
    fillEl.style.width = "100%";
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        fillEl.style.transition = `width ${SHOP_HERO_DIALOG_MS}ms linear`;
        fillEl.style.width = "0%";
      });
    });
  }

  clearTimeout(shopHeroDialogTimer);
  shopHeroDialogTimer = setTimeout(() => {
    dialog.classList.remove("show");
    shopHeroDialogTimer = null;
  }, SHOP_HERO_DIALOG_MS);
}

function prepareMerchantAdvice(context) {
  const ctx = context || shopState.activeTab || "buy";
  shopState.merchantPickBuySlot = null;
  shopState.merchantPickSellId = null;

  if (ctx === "buy") {
    const available = (shopState.offers || []).filter((o) => !o?.sold);
    if (!available.length) {
      return {
        cacheKey: "buy:empty",
        fallback: "На сегодня товара нет, странник. Загляни позже.",
        apiBody: null,
      };
    }
    const chosen = available[Math.floor(Math.random() * available.length)];
    const slot = resolveShopOfferSlot(chosen);
    if (slot != null) shopState.merchantPickBuySlot = slot;
    const fallback = `Странник, присмотрись к <b>${escapeHtml(String(chosen?.display_name || chosen?.name || "товару"))}</b> — отличная вещь для твоего пути.`;
    return {
      cacheKey: `buy:${slot ?? chosen?.id ?? chosen?.name}`,
      fallback,
      apiBody: {
        context: "buy",
        name: chosen?.display_name || chosen?.name || "предмет",
        level: Number(chosen?.level || 1),
        rarity: rarityLabel(chosen?.rarity || 1),
        bonuses: typeof getItemBonusesText === "function" ? getItemBonusesText(chosen) : "",
      },
    };
  }

  if (ctx === "sell") {
    const items = shopState.sellItems || [];
    if (!items.length) {
      return {
        cacheKey: "sell:empty",
        fallback:
          "Развяжи ремни сумки — покажи, что продаёшь, странник. Золото у меня есть, а терпение — на вес.",
        apiBody: null,
      };
    }
    const chosen = items[Math.floor(Math.random() * items.length)];
    if (chosen?.id != null) shopState.merchantPickSellId = Number(chosen.id);
    const fallback = `Дай глянуть на <b>${escapeHtml(String(chosen?.display_name || chosen?.name || "эту штуку"))}</b>, странник — может, сойдёмся в цене.`;
    return {
      cacheKey: `sell:${chosen?.id ?? chosen?.name}`,
      fallback,
      apiBody: {
        context: "sell",
        name: chosen?.display_name || chosen?.name || "предмет",
        level: Number(chosen?.level || 1),
        rarity: rarityLabel(chosen?.rarity || 1),
        bonuses: typeof getItemBonusesText === "function" ? getItemBonusesText(chosen) : "",
      },
    };
  }

  if (ctx === "gamble") {
    return {
      cacheKey: "gamble",
      fallback:
        "Испытай удачу, странник! Мистическая гемба голодна по золоту — зато сыплет редкостями не хуже драконьего логова.",
      apiBody: {
        context: "gamble",
        name: "",
        level: 1,
        rarity: "",
        bonuses: "",
      },
    };
  }

  return {
    cacheKey: "smith",
    fallback:
      "Кузнец затачивает сталь до звона. До +7 — без риска; выше удача решает судьбу клинка. Камень защиты убережёт от поломки.",
    apiBody: {
      context: "smith",
      name: "заточка",
      level: 1,
      rarity: "",
      bonuses: "",
    },
  };
}

async function fetchMerchantLineAi(apiBody, fallback, cacheKey) {
  const cached = shopState.merchantLineCache[cacheKey];
  if (cached) return cached;
  try {
    const payload = await apiFetch("/shop/merchant-line", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(apiBody),
    });
    const text = String(payload?.text || "").trim();
    const out = text || fallback;
    if (!text && payload?.error && typeof console !== "undefined" && console.warn) {
      console.warn("[shop merchant-line]", payload.error);
    }
    shopState.merchantLineCache[cacheKey] = out;
    return out;
  } catch (e) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[shop merchant-line] запрос не удался:", e?.message || e);
    }
    return fallback;
  }
}

async function onShopHeroAdvice(tab) {
  const ctx = tab || shopState.activeTab || "buy";
  window.__shopMerchantTab = ctx;
  shopState.merchantAdviceUnlocked = false;

  const { cacheKey, fallback, apiBody } = prepareMerchantAdvice(ctx);
  window.__shopMerchantLine = shopState.merchantLineCache[cacheKey] || fallback;

  revealMerchantAdvice();
  showShopHeroDialog(ctx, window.__shopMerchantLine);

  if (!apiBody) return window.__shopMerchantLine;

  const cached = shopState.merchantLineCache[cacheKey];
  if (cached) return cached;

  const text = await fetchMerchantLineAi(apiBody, fallback, cacheKey);
  window.__shopMerchantLine = text;
  const dialog = document.getElementById(`shop-dialog-${ctx}`);
  if (dialog?.classList.contains("show")) {
    updateShopHeroDialogText(ctx, text);
  }
  applyShopMerchantHighlight();
  return text;
}

/**
 * Подготовка реплики торговца (без сетевого запроса; AI — только через onShopHeroAdvice).
 */
async function generateMerchantLine(context) {
  const ctx = context || shopState.activeTab || "buy";
  const { cacheKey, fallback } = prepareMerchantAdvice(ctx);
  window.__shopMerchantTab = ctx;
  window.__shopMerchantLine = shopState.merchantLineCache[cacheKey] || fallback;
  applyShopMerchantHighlight();
  return window.__shopMerchantLine;
}

/** Цена гембы как на бэкенде (game.constants + formulas.calculate_gamble_price). */
function calculateGamblePriceClient(level) {
  const GAMBLE_BASE_PRICE = 1000;
  const GAMBLE_PRICE_PER_LEVEL = 200;
  const GAMBLE_MAX_PRICE = 10000;
  const lv = Math.max(1, Number(level) || 1);
  return Math.min(GAMBLE_BASE_PRICE + lv * GAMBLE_PRICE_PER_LEVEL, GAMBLE_MAX_PRICE);
}

function updateShopGambleCost() {
  const el = document.getElementById("shop-gamble-cost");
  if (!el) return;
  const w = profileState.currentProfile?.main_waifu;
  const lvl = Number(w?.level) || 1;
  const price = calculateGamblePriceClient(lvl);
  el.textContent = `🪙 ${price.toLocaleString()} золота`;
}

const expeditionState = {
  active: [],
  roster: [],
  catalog: { reward_types: [], depth_tiers: [] },
};
const expeditionUiCache = { activeById: {}, _activeRaw: null };
const expeditionSend = {
  squadSlots: [null, null, null],
  rewardType: "gold",
  depthTier: 1,
};

function switchShopTab(name) {
  shopState.merchantAdviceUnlocked = false;
  shopState.activeTab = name;

  document.querySelectorAll(".shop-hero[data-tab-hero]").forEach((hero) => {
    const tab = hero.getAttribute("data-tab-hero");
    hero.classList.toggle("active", tab === name);
  });

  document.querySelectorAll(".tabs .tab, .shop-btab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".shop-tab-panel, .tab-panel").forEach((panel) => {
    if (panel.id?.startsWith("tab-")) {
      const active = panel.id === `tab-${name}`;
      panel.classList.toggle("active", active);
      panel.style.display = active ? "" : "none";
    }
  });

  if (window.location.pathname.endsWith("/shop.html")) {
    const sellBtn = document.getElementById("shop-sell-submit");
    if (sellBtn) sellBtn.style.display = name === "sell" ? "" : "none";
    if (name === "sell") {
      loadSellInventory().then(() => syncShopSellToolbarUI()).catch(console.error);
    } else if (name === "smith") {
      loadSmithTab().catch(console.error);
    } else if (name === "gamble") {
      loadGambleTab(shopState.act || 1).catch(console.error);
    }
  }
  hideShopHeroDialogs();
}

function sortSmithInventoryItems(items) {
  return [...(items || [])].sort((a, b) => {
    const ea = a.equipment_slot != null ? 1 : 0;
    const eb = b.equipment_slot != null ? 1 : 0;
    if (eb !== ea) return eb - ea;
    return (b.level || 0) - (a.level || 0);
  });
}

/** Какие строки превью заточки показывать в зависимости от типа предмета. */
function smithEnchantPreviewStatFlags(item) {
  const st = String(item?.slot_type || "").toLowerCase();
  const isWeapon = st.includes("weapon");
  const isAccessory = st.includes("ring") || st.includes("amulet");
  return {
    showDamage: isWeapon,
    showArmor: !isWeapon && !isAccessory,
    showSecondary: isAccessory || (!isWeapon && !isAccessory),
  };
}

function mainStatShortFromItem(item) {
  const a = String(item?.attack_type || "").toLowerCase();
  if (a === "melee") return "СИЛ";
  if (a === "ranged") return "ЛОВ";
  if (a === "magic") return "ИНТ";
  return null;
}

function buildItemModalMetaLine(item) {
  const tierStr = item?.tier != null ? `T${item.tier}` : "—";
  const lvlStr = item?.level != null ? `ур. ${item.level}` : "—";
  const st = String(item?.slot_type || "").toLowerCase();
  if (st.includes("weapon")) {
    const wt = item?.weapon_type ? weaponTypeLabel(item.weapon_type) : null;
    const typePart = wt ? `${wt} ${st.includes("2h") ? "(2H)" : "(1H)"}` : slotTypeLabel(item.slot_type);
    const ms = mainStatShortFromItem(item);
    return [typePart, ms, tierStr, lvlStr].filter(Boolean).join(" · ");
  }
  const typePart = slotTypeLabel(item.slot_type);
  const ms = mainStatShortFromItem(item);
  return [typePart, ms, tierStr, lvlStr].filter(Boolean).join(" · ");
}

function updateSmithMetaFromProfile(pr) {
  if (!pr) return;
  const stEl = document.getElementById("shop-smith-stones");
  const dEl = document.getElementById("shop-smith-dust-hint");
  if (stEl) stEl.textContent = String(pr.protection_stones ?? 0);
  if (dEl) dEl.textContent = String(pr.enchant_dust ?? 0);
}

function syncSmithEnchantBadge(level, visible) {
  const badge = document.getElementById("shop-smith-enchant-badge");
  if (!badge) return;
  const lv = Number(level) || 0;
  if (!visible || lv <= 0) {
    badge.hidden = true;
    return;
  }
  badge.textContent = `+${lv}`;
  badge.hidden = false;
}

function setSmithSharpenControlsDisabled(disabled) {
  const enchantBtn = document.getElementById("shop-smith-enchant-btn");
  const autoBtn = document.getElementById("shop-smith-auto-btn");
  const stoneCb = document.getElementById("shop-smith-use-stone");
  if (enchantBtn) enchantBtn.disabled = disabled;
  if (autoBtn) autoBtn.disabled = disabled;
  if (stoneCb) stoneCb.disabled = disabled;
}

function switchSmithSubTab(name) {
  const tab = name === "craft" ? "craft" : "sharpen";
  shopState.smithSubTab = tab;
  ["sharpen", "craft"].forEach((t) => {
    const btn = document.getElementById(`shop-smith-subtab-${t}`);
    if (btn) btn.classList.toggle("active", t === tab);
    const panel = document.getElementById(`shop-smith-panel-${t}`);
    if (panel) panel.style.display = t === tab ? "" : "none";
    const controls = document.getElementById(`shop-smith-controls-${t}`);
    if (controls) controls.style.display = t === tab ? "" : "none";
  });
  if (tab === "craft") {
    refreshSmithCraftPreview().catch(console.error);
  } else {
    refreshSmithPreview().catch(console.error);
  }
}

window.WaifuApp = window.WaifuApp || {};
window.WaifuApp.switchSmithSubTab = switchSmithSubTab;

function updateSmithSelectionUI() {
  const id = shopState.smithSelectedId;
  const items = shopState.smithItems || [];
  const it = id ? items.find((x) => x.id === id) : null;
  const wrap = document.getElementById("shop-smith-icon-wrap");
  const btn = document.getElementById("shop-smith-enchant-btn");
  if (wrap) {
    wrap.innerHTML = it ? itemArtHtml(it) : "⚒";
  }
  const lv = it ? Number(it.enchant_level ?? 0) : 0;
  syncSmithEnchantBadge(lv, Boolean(it) && lv > 0);
  if (btn && !it) btn.disabled = true;
  const autoBtn = document.getElementById("shop-smith-auto-btn");
  if (autoBtn && !it) autoBtn.disabled = true;
}

function syncSmithProtectionStoneCheckbox(targetLevel) {
  const stoneCheck = document.getElementById("shop-smith-stone-check-wrap");
  const stoneCb = document.getElementById("shop-smith-use-stone");
  if (!stoneCb) return;
  const t = Number(targetLevel);
  if (!Number.isFinite(t) || t < 8) {
    stoneCb.checked = false;
    if (stoneCheck) stoneCheck.hidden = true;
  } else if (stoneCheck) {
    stoneCheck.hidden = false;
  }
}

function renderSmithPickPage() {
  const grid = document.getElementById("shop-smith-pick-grid");
  const nav = document.getElementById("shop-smith-pick-nav");
  if (!grid) return;
  const items = shopState.smithItems || [];
  const n = items.length;
  if (!n) {
    grid.innerHTML = '<div class="muted tiny">Инвентарь пуст.</div>';
    if (nav) nav.innerHTML = "";
    return;
  }
  const pages = Math.max(1, Math.ceil(n / SMITH_PICK_PAGE_SIZE));
  if (shopState.smithPickPage > pages - 1) shopState.smithPickPage = pages - 1;
  const page = shopState.smithPickPage;
  const start = page * SMITH_PICK_PAGE_SIZE;
  const slice = items.slice(start, start + SMITH_PICK_PAGE_SIZE);
  grid.innerHTML = slice
    .map((it) => {
      const cls = rarityClassFromValue(it.rarity);
      const equipped = it.equipment_slot != null;
      const sel = shopState.smithSelectedId === it.id ? " shop-smith-pick-card--selected" : "";
      const lv = it.total_level != null ? safeNumber(it.total_level, 1) : safeNumber(it.level, 1);
      const label = composeItemDisplayName(it).replace(/<[^>]+>/g, "").trim();
      return `<button type="button" class="shop-smith-pick-card ${cls}${sel}" data-id="${it.id}" aria-label="${escapeHtml(label)}" onclick="WaifuApp.pickSmithItem(${it.id})">
        ${equipped ? '<span class="shop-smith-pick-equipped" title="Экипировано">⚔</span>' : ""}
        <div class="shop-smith-pick-art">${itemArtHtml(it)}${itemEnchantOverlayHtml(it, "bag")}</div>
        <span class="shop-smith-pick-lv">Ур. ${lv}</span>
      </button>`;
    })
    .join("");
  if (nav) {
    const prevDis = page <= 0 ? " disabled" : "";
    const nextDis = page >= pages - 1 ? " disabled" : "";
    nav.innerHTML = `<div class="shop-smith-pick-nav-inner">
      <button type="button" class="shop-smith-pick-nav-btn secondary"${prevDis} onclick="WaifuApp.smithPickPrev()">‹</button>
      <span class="shop-smith-pick-nav-label muted tiny">${page + 1} / ${pages}</span>
      <button type="button" class="shop-smith-pick-nav-btn secondary"${nextDis} onclick="WaifuApp.smithPickNext()">›</button>
    </div>`;
  }
}

function smithPickPrev() {
  if (shopState.smithPickPage > 0) {
    shopState.smithPickPage -= 1;
    renderSmithPickPage();
  }
}

function smithPickNext() {
  const items = shopState.smithItems || [];
  const pages = Math.max(1, Math.ceil(items.length / SMITH_PICK_PAGE_SIZE));
  if (shopState.smithPickPage < pages - 1) {
    shopState.smithPickPage += 1;
    renderSmithPickPage();
  }
}

async function openSmithPickModal() {
  const m = document.getElementById("shop-smith-pick-modal");
  const grid = document.getElementById("shop-smith-pick-grid");
  const nav = document.getElementById("shop-smith-pick-nav");
  if (m) m.style.display = "grid";

  const cached = Array.isArray(shopState.smithItems) && shopState.smithItems.length;
  if (cached) {
    shopState.smithPickPage = 0;
    renderSmithPickPage();
  } else if (grid) {
    grid.innerHTML = SMITH_PICK_LOADING_HTML;
    if (nav) nav.innerHTML = "";
  }

  try {
    const data = await apiFetch("/inventory?limit=100&offset=0");
    const items = Array.isArray(data?.items) ? data.items : [];
    shopState.smithItems = sortSmithInventoryItems(items);
    if (
      shopState.smithSelectedId != null &&
      !shopState.smithItems.some((x) => x.id === shopState.smithSelectedId)
    ) {
      shopState.smithSelectedId = null;
    }
    shopState.smithPickPage = 0;
    renderSmithPickPage();
  } catch (e) {
    console.error(e);
    if (grid) {
      grid.innerHTML = '<div class="muted tiny">Не удалось загрузить инвентарь.</div>';
    }
    if (nav) nav.innerHTML = "";
    showToast("Не удалось загрузить инвентарь", "error");
  }
}

function closeSmithPickModal() {
  const m = document.getElementById("shop-smith-pick-modal");
  if (m) m.style.display = "none";
}

function pickSmithItem(id) {
  shopState.smithSelectedId = Number(id);
  closeSmithPickModal();
  updateSmithSelectionUI();
  refreshSmithPreview().catch(console.error);
  refreshSmithCraftPreview().catch(console.error);
}

async function loadSmithTab() {
  const pr = await loadProfile().catch(() => null);
  updateSmithMetaFromProfile(pr);
  switchSmithSubTab(shopState.smithSubTab || "sharpen");

  const data = await apiFetch("/inventory?limit=100&offset=0");
  const items = Array.isArray(data?.items) ? data.items : [];
  shopState.smithItems = sortSmithInventoryItems(items);
  if (
    shopState.smithSelectedId != null &&
    !shopState.smithItems.some((x) => x.id === shopState.smithSelectedId)
  ) {
    shopState.smithSelectedId = null;
  }
  updateSmithSelectionUI();
  await refreshSmithPreview();
  await refreshSmithCraftPreview();
}

async function refreshSmithPreview() {
  const box = document.getElementById("shop-smith-preview");
  if (!box) return;
  const id = shopState.smithSelectedId ? Number(shopState.smithSelectedId) : 0;
  if (!id) {
    box.innerHTML = `<div class="muted tiny">Выберите предмет из инвентаря.</div>`;
    const btn = document.getElementById("shop-smith-enchant-btn");
    if (btn) btn.disabled = true;
    const autoBtn = document.getElementById("shop-smith-auto-btn");
    if (autoBtn) autoBtn.disabled = true;
    syncSmithEnchantBadge(0, false);
    syncSmithProtectionStoneCheckbox(0);
    return;
  }
  try {
    const prev = await apiFetch(`/inventory/${id}/enchant-preview`);
    if (prev?.error) {
      box.innerHTML = `<div class="muted tiny">Нет данных.</div>`;
      syncSmithProtectionStoneCheckbox(0);
      return;
    }
    const cur = Number(prev.current_level ?? 0);
    const tgt = Number(prev.target_level ?? cur + 1);
    const ch = prev.chance;
    const cost = prev.enchant_cost_gold ?? "—";
    const tp = prev.target_params || {};
    const item = shopState.smithItems?.find((x) => x.id === id) || {};
    const flags = smithEnchantPreviewStatFlags(item);

    const dm1 =
      tp.damage_min != null && tp.damage_max != null
        ? `${tp.damage_min}–${tp.damage_max}`
        : "—";
    const ar1 = tp.armor != null ? String(tp.armor) : "—";
    const sec1 = Number(tp.secondary ?? 0);
    const secStr = (x) => (x > 0 ? `+${(x * 100).toFixed(2)}%` : "—");
    const passiveType = String(prev.passive_secondary_type || "").trim();
    const fracType = String(prev.fraction_secondary_type || item?.secondary_fraction_type || "").trim();
    const fracEff = Number(
      prev.fraction_secondary_effective ?? item?.secondary_fraction_effective ?? prev.fraction_secondary_value ?? 0
    );

    const chanceLine =
      ch == null
        ? `<div class="muted tiny">✅ Гарантированный успех</div>`
        : `<div class="shop-smith-risk">⚠️ Шанс успеха: <strong>${Math.round(Number(ch) * 100)}%</strong></div>
           <div class="muted tiny">${escapeHtml(String(prev.on_fail_hint || ""))}</div>`;

    syncSmithProtectionStoneCheckbox(tgt);

    const statRows = [];
    if (flags.showDamage && dm1 !== "—") {
      statRows.push(
        `<div><span class="muted">Урон:</span> <strong>${escapeHtml(dm1)}</strong></div>`
      );
    }
    if (flags.showArmor && ar1 !== "—") {
      statRows.push(`<div><span class="muted">Броня:</span> <strong>${escapeHtml(ar1)}</strong></div>`);
    }
    if (flags.showSecondary && sec1 > 0) {
      const fracLabel = fracType ? secondaryBonusTitleRu(fracType) : "Вторичка (заточка)";
      statRows.push(
        `<div><span class="muted">${escapeHtml(fracLabel)}:</span> <strong>${escapeHtml(secStr(sec1))}</strong></div>`
      );
    }
    if (passiveType) {
      const pv = Number(prev.passive_secondary_value ?? item?.secondary_bonus_value ?? 0);
      if (pv > 0) {
        statRows.push(
          `<div><span class="muted">Пассив:</span> <strong>${escapeHtml(formatSecondaryBonusValueDisplay(passiveType, pv))}</strong> <span class="muted tiny">(не растёт от заточки)</span></div>`
        );
      }
    }
    if (prev.awaken_on_success) {
      statRows.push(
        `<div class="muted tiny" style="margin-top:6px;">При +1: случайная вторичка (крит / уклонение / …)</div>`
      );
    }

    let noGainHint = "";
    if (!statRows.length) {
      const st = String(item?.slot_type || "").toLowerCase();
      const secType = String(item?.secondary_bonus_type || passiveType || "").trim().toLowerCase();
      if (secType.startsWith("passive_")) {
        noGainHint =
          '<div class="muted tiny" style="margin-top:8px;">Заточка не усиливает бонус к пассивному навыку — при +1 может пробудиться fraction-вторичка.</div>';
      } else if (st.includes("ring") || st.includes("amulet")) {
        noGainHint =
          '<div class="muted tiny" style="margin-top:8px;">Нет fraction-вторички для роста от заточки. При +1 возможно пробуждение или используйте «Зачарование» за пыль.</div>';
      } else {
        noGainHint =
          '<div class="muted tiny" style="margin-top:8px;">Заточка усилит урон или броню; fraction-вторичку можно добавить во вкладке «Зачарование».</div>';
      }
    } else if (fracType && fracEff <= 0 && flags.showSecondary) {
      noGainHint =
        '<div class="muted tiny" style="margin-top:8px;">Fraction-вторичка появится при успешной заточке +1 или через «Зачарование».</div>';
    }

    box.innerHTML = `
      <div><span class="muted">Уровень:</span> <strong>+${cur}</strong> → <strong>+${tgt}</strong></div>
      <div style="margin-top:6px;"><span class="muted">Стоимость:</span> <strong>🪙 ${escapeHtml(String(cost))}</strong></div>
      ${chanceLine}
      ${
        statRows.length
          ? `<div style="margin-top:8px;font-size:12px;">${statRows.join("")}</div>`
          : noGainHint
      }`;
    syncSmithEnchantBadge(cur, cur > 0);
    const broken = Boolean(item.is_broken);
    const btn = document.getElementById("shop-smith-enchant-btn");
    if (btn) btn.disabled = cur >= 10 || broken;
    const autoBtn = document.getElementById("shop-smith-auto-btn");
    if (autoBtn) autoBtn.disabled = cur >= SMITH_SAFE_MAX || Boolean(prev.is_risky) || broken;
  } catch (e) {
    console.error(e);
    box.innerHTML = `<div class="muted tiny">Ошибка превью.</div>`;
    syncSmithProtectionStoneCheckbox(0);
  }
}

async function smithTryEnchant() {
  const id = shopState.smithSelectedId ? Number(shopState.smithSelectedId) : 0;
  if (!id) return;
  const useStone = Boolean(document.getElementById("shop-smith-use-stone")?.checked);
  setSmithSharpenControlsDisabled(true);
  try {
    const res = await apiFetch(`/inventory/${id}/enchant`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ use_protection_stone: useStone }),
    });
    if (res?.error) {
      showToast(String(res.error));
      return;
    }
    if (res?.success) {
      window.WaifuApp?.Tutorial?.notify?.("shop:enchanted", { inventory_item_id: id, new_level: res?.new_level });
    }
    const ok = res?.success;
    const nl = res?.new_level;
    const br = res?.broken;
    const removed = Boolean(res?.removed);
    if (removed) {
      showToast("Предмет уничтожен при заточке", "error");
      shopState.smithSelectedId = null;
      shopState.smithItems = (shopState.smithItems || []).filter((x) => x.id !== id);
      const pr = await loadProfile().catch(() => null);
      updateSmithMetaFromProfile(pr);
      updateSmithSelectionUI();
      return;
    }
    if (br) {
      showToast("Предмет сломан…", "error");
    } else if (!ok) {
      showToast(`Неудача. Новый уровень: +${nl}`, "error");
    }
    if (res?.stone_used) {
      const stoneCb = document.getElementById("shop-smith-use-stone");
      if (stoneCb) stoneCb.checked = false;
    }
    if (res?.awaken?.secondary_fraction_type) {
      const aw = res.awaken;
      showToast(
        `Пробуждение: ${secondaryBonusTitleRu(aw.secondary_fraction_type)} +${(Number(aw.secondary_fraction_value || 0) * 100).toFixed(2)}%`,
        "success"
      );
    }
    const pr = await loadProfile().catch(() => null);
    updateSmithMetaFromProfile(pr);
    const it = shopState.smithItems?.find((x) => x.id === id);
    if (it && nl != null) {
      it.enchant_level = nl;
      if (br) it.is_broken = true;
    }
    syncSmithEnchantBadge(nl, nl != null && Number(nl) > 0);
    updateSmithSelectionUI();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const d = String(detail || "");
    if (d.includes("stone_not_needed")) {
      const stoneCb = document.getElementById("shop-smith-use-stone");
      if (stoneCb) stoneCb.checked = false;
    }
    showToast(detail || e?.message || "Ошибка заточки", "error");
  } finally {
    const stoneCb = document.getElementById("shop-smith-use-stone");
    if (stoneCb) stoneCb.disabled = false;
    await refreshSmithPreview().catch(() => {});
  }
}

async function smithAutoSafeEnchant() {
  const id = shopState.smithSelectedId ? Number(shopState.smithSelectedId) : 0;
  if (!id) return;
  const item = shopState.smithItems?.find((x) => x.id === id);
  if (item?.is_broken) {
    showToast("Предмет сломан", "error");
    return;
  }
  setSmithSharpenControlsDisabled(true);
  try {
    for (let step = 0; step < SMITH_SAFE_MAX; step += 1) {
      const prev = await apiFetch(`/inventory/${id}/enchant-preview`);
      if (prev?.error) {
        showToast(String(prev.error), "error");
        break;
      }
      const cur = Number(prev.current_level ?? 0);
      const tgt = Number(prev.target_level ?? cur + 1);
      if (prev.is_risky || tgt >= 8) break;
      if (cur >= SMITH_SAFE_MAX) break;

      const res = await apiFetch(`/inventory/${id}/enchant`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ use_protection_stone: false }),
      });
      if (res?.error) {
        showToast(String(res.error), "error");
        break;
      }
      if (res?.removed) {
        showToast("Предмет уничтожен при заточке", "error");
        shopState.smithSelectedId = null;
        shopState.smithItems = (shopState.smithItems || []).filter((x) => x.id !== id);
        break;
      }
      const nl = res?.new_level;
      const it = shopState.smithItems?.find((x) => x.id === id);
      if (it && nl != null) {
        it.enchant_level = nl;
        if (res?.broken) it.is_broken = true;
      }
      syncSmithEnchantBadge(nl, nl != null && Number(nl) > 0);
      if (res?.broken) {
        showToast("Предмет сломан…", "error");
        break;
      }
      if (!res?.success) {
        showToast(`Неудача. Новый уровень: +${nl}`, "error");
        break;
      }
      if (res?.awaken?.secondary_fraction_type) {
        const aw = res.awaken;
        showToast(
          `Пробуждение: ${secondaryBonusTitleRu(aw.secondary_fraction_type)} +${(Number(aw.secondary_fraction_value || 0) * 100).toFixed(2)}%`,
          "success"
        );
      }
      if (Number(nl) >= SMITH_SAFE_MAX) break;
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || e?.message || "Ошибка автозаточки", "error");
  } finally {
    const stoneCb = document.getElementById("shop-smith-use-stone");
    if (stoneCb) stoneCb.disabled = false;
    const pr = await loadProfile().catch(() => null);
    updateSmithMetaFromProfile(pr);
    updateSmithSelectionUI();
    await refreshSmithPreview().catch(() => {});
  }
}

async function refreshSmithCraftPreview() {
  const box = document.getElementById("shop-smith-craft-preview");
  if (!box) return;
  const id = shopState.smithSelectedId ? Number(shopState.smithSelectedId) : 0;
  const addBtn = document.getElementById("shop-smith-craft-add");
  const rerollBtn = document.getElementById("shop-smith-craft-reroll");
  const upBtn = document.getElementById("shop-smith-craft-upgrade");
  if (!id) {
    box.innerHTML = `<div class="muted tiny">Выберите предмет из инвентаря.</div>`;
    if (addBtn) addBtn.disabled = true;
    if (rerollBtn) rerollBtn.disabled = true;
    if (upBtn) upBtn.disabled = true;
    return;
  }
  try {
    const prev = await apiFetch(`/inventory/${id}/craft-enchant-preview`);
    const ft = String(prev?.secondary_fraction_type || "").trim();
    const fv = Number(prev?.secondary_fraction_value ?? 0);
    const cap = Number(prev?.fraction_cap ?? 0);
    const costs = prev?.costs || {};
    const fracLine =
      ft && fv > 0
        ? `<div><span class="muted">Вторичка:</span> <strong>${escapeHtml(secondaryBonusTitleRu(ft))} ${escapeHtml(formatSecondaryBonusValueDisplay(ft, fv))}</strong></div>`
        : `<div class="muted tiny">Вторичного бонуса пока нет.</div>`;
    box.innerHTML = `
      ${fracLine}
      ${cap > 0 ? `<div class="muted tiny">Максимум для tier: ${(cap * 100).toFixed(2)}%</div>` : ""}`;
    if (addBtn) {
      addBtn.disabled = costs.add == null;
      addBtn.title = "Случайная вторичка, если её ещё нет";
      addBtn.innerHTML =
        costs.add != null
          ? `Выдать бонус<span class="shop-smith-craft-btn-cost">✨ ${costs.add}</span>`
          : "Выдать бонус";
    }
    if (rerollBtn) {
      rerollBtn.disabled = costs.reroll == null;
      rerollBtn.title = "Другой тип и сила вторички";
      rerollBtn.innerHTML =
        costs.reroll != null
          ? `Сменить бонус<span class="shop-smith-craft-btn-cost">✨ ${costs.reroll}</span>`
          : "Сменить бонус";
    }
    if (upBtn) {
      upBtn.disabled = costs.upgrade == null;
      upBtn.title = "+шаг к текущей вторичке";
      upBtn.innerHTML =
        costs.upgrade != null
          ? `Усилить бонус<span class="shop-smith-craft-btn-cost">✨ ${costs.upgrade}</span>`
          : "Усилить бонус";
    }
  } catch (e) {
    console.error(e);
    box.innerHTML = `<div class="muted tiny">Ошибка превью зачарования.</div>`;
  }
}

async function smithTryCraftEnchant(operation) {
  const id = shopState.smithSelectedId ? Number(shopState.smithSelectedId) : 0;
  if (!id) return;
  try {
    const res = await apiFetch(`/inventory/${id}/craft-enchant`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation, target: "fraction" }),
    });
    if (res?.error) {
      showToast(String(res.error), "error");
      return;
    }
    showToast("Зачарование выполнено", "success");
    window.WaifuApp?.Tutorial?.notify?.("shop:crafted", { inventory_item_id: id, operation });
    const it = shopState.smithItems?.find((x) => x.id === id);
    if (it) {
      it.secondary_fraction_type = res.secondary_fraction_type;
      it.secondary_fraction_value = res.secondary_fraction_value;
      it.enchant_sec_step = res.enchant_sec_step;
    }
    await loadProfile().catch(() => null);
    await refreshSmithCraftPreview();
    if (shopState.smithSubTab !== "craft") {
      await refreshSmithPreview().catch(() => {});
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || e?.message || "Ошибка зачарования", "error");
  }
}

async function buyProtectionStoneShop() {
  try {
    const res = await apiFetch("/shop/buy-protection-stone", { method: "POST" });
    if (!res?.success) {
      showToast("Не удалось купить камень", "error");
      return;
    }
    showToast(`Камень защиты +1 · осталось 🪙 ${res.gold_remaining}`);
    await loadProfile().catch(() => {});
    await loadSmithTab().catch(console.error);
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Недостаточно золота", "error");
  }
}

function switchProfileTab(name) {
  document.querySelectorAll(".profile-tabs .tab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll("main .tab-panel").forEach((panel) => {
    if (panel.id?.startsWith("tab-")) panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
  if (name === "inventory") {
    ensureProfileEquipmentLoaded().catch(() => {});
  }
}

function closeShopModal() {
  const m = document.getElementById("shop-modal");
  if (m) {
    m.classList.remove("shop-modal--open");
    m.style.display = "none";
  }
  shopState.selectedSlot = null;
  shopState.selectedOffer = null;
  const grid = document.getElementById("shop-items") || document.getElementById("shop-buy-grid");
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

  const contentEl = document.getElementById("shop-offer-modal-content");
  const nameEl = document.getElementById("shop-offer-modal-name");
  const subEl = document.getElementById("shop-offer-modal-subline");
  const rpill = document.getElementById("shop-offer-modal-rpill");
  const upHint = document.getElementById("shop-offer-modal-upgrade-hint");
  const art = document.getElementById("shop-offer-modal-art");
  const body = document.getElementById("shop-offer-modal-body");
  const buyBtn = document.getElementById("shop-modal-buy");

  if (!offer) {
    if (nameEl) nameEl.textContent = `Слот ${slot}`;
    if (subEl) subEl.textContent = "";
    if (rpill) {
      rpill.textContent = "—";
      rpill.className = "item-modal-v2-rpill";
    }
    if (upHint) {
      upHint.style.display = "none";
      upHint.textContent = "";
      upHint.setAttribute("aria-hidden", "true");
    }
    if (art) art.innerHTML = "—";
    if (body) body.innerHTML = `<div class="muted tiny" style="padding:8px 0;">Пустой слот.</div>`;
    const reqSec = document.getElementById("shop-offer-modal-req-section");
    const reqFoot = document.getElementById("shop-offer-modal-requirements");
    if (reqFoot) reqFoot.innerHTML = "";
    if (reqSec) reqSec.style.display = "none";
    const descEl = document.getElementById("shop-offer-modal-desc");
    if (descEl) {
      descEl.style.display = "none";
      descEl.innerHTML = "";
    }
    if (buyBtn) {
      buyBtn.disabled = true;
      buyBtn.textContent = "—";
    }
    if (contentEl) {
      ["rarity-common", "rarity-uncommon", "rarity-rare", "rarity-epic", "rarity-legendary"].forEach((c) => contentEl.classList.remove(c));
      contentEl.classList.add("rarity-common");
    }
    m.classList.add("shop-modal--open");
    m.style.display = "grid";
    return;
  }

  const nm = String(offer?.display_name || offer?.name || "").trim() || `Слот ${slot}`;
  if (nameEl) {
    nameEl.innerHTML = composeItemTitlePlain(offer) || escapeHtml(nm);
    const en = safeNumber(offer?.enchant_level, 0);
    const br = Boolean(offer?.is_broken);
    nameEl.classList.toggle("item-modal-v2-title--enchant-high", en > 7 && !br);
  }
  if (subEl) subEl.textContent = buildItemModalMetaLine(offer);
  if (rpill) {
    rpill.textContent = rarityLabel(offer?.rarity);
    rpill.className = `item-modal-v2-rpill ${rarityPillModifierClass(offer?.rarity)}`.trim();
  }
  if (upHint) {
    upHint.style.display = "none";
    upHint.textContent = "";
    upHint.setAttribute("aria-hidden", "true");
  }
  if (art) art.innerHTML = itemArtHtml(offer, { adminGen: true });

  if (contentEl) {
    ["rarity-common", "rarity-uncommon", "rarity-rare", "rarity-epic", "rarity-legendary"].forEach((c) => contentEl.classList.remove(c));
    contentEl.classList.add(offer?.rarity != null ? rarityClass(offer.rarity) : "rarity-common");
  }

  const combinedBonusesHtml = renderCombinedBonusesHtml(offer);
  const weaponStatsHtml = renderWeaponStatsHtml(offer);
  let charHtml = renderItemModalV2CharacteristicsHtml(offer);
  if (!charHtml) {
    const statsInner = [weaponStatsHtml, combinedBonusesHtml].filter(Boolean).join("");
    charHtml = statsInner
      ? `<div class="item-mtg-stats-merged">${statsInner}</div>`
      : `<div class="muted tiny" style="padding:6px 0;">Нет характеристик для отображения.</div>`;
  }

  if (body) {
    if (offer?.sold) {
      body.innerHTML = `<div class="muted tiny" style="padding:8px 0;">Этот предмет уже продан.</div>`;
    } else {
      body.innerHTML = charHtml;
    }
  }

  const mw = profileState.currentProfile?.main_waifu || null;
  const reqFoot = document.getElementById("shop-offer-modal-requirements");
  const reqSec = document.getElementById("shop-offer-modal-req-section");
  const pillsHtml = buildItemModalRequirementsPillsHtml(offer, mw);
  if (reqFoot) reqFoot.innerHTML = pillsHtml;
  if (reqSec) reqSec.style.display = pillsHtml && !offer?.sold ? "" : "none";

  const descEl = document.getElementById("shop-offer-modal-desc");
  const descText = String(offer?.description || "").trim();
  if (descEl) {
    if (descText && !offer?.sold) {
      descEl.style.display = "";
      descEl.textContent = `"${descText}"`;
    } else {
      descEl.style.display = "none";
      descEl.innerHTML = "";
    }
  }

  if (buyBtn) {
    buyBtn.disabled = Boolean(offer?.sold) || offer?.price == null;
    if (offer?.sold) {
      buyBtn.textContent = "Продано";
    } else if (offer?.price != null) {
      buyBtn.textContent = `Купить ${offer.price} 🪙`;
    } else {
      buyBtn.textContent = "Купить";
    }
  }

  m.classList.add("shop-modal--open");
  m.style.display = "grid";
}

async function confirmBuy() {
  if (!shopState.selectedSlot) return;
  const act = shopState.act || 1;
  let buyRes = null;
  try {
    buyRes = await apiFetch(`/shop/buy?act=${act}&slot=${shopState.selectedSlot}`, { method: "POST" });
  } catch (e) {
    const body = document.getElementById("shop-offer-modal-body");
    if (body) body.innerHTML = `<div class="muted tiny" style="padding:8px 0;">Ошибка покупки: ${escapeHtml(String(e?.message || e))}</div>`;
    return;
  }
  await loadProfile().catch(console.error);
  await loadShop(act).catch(console.error);
  closeShopModal();
  window.WaifuApp?.Tutorial?.notify?.("shop:bought", {
    inventory_item_id: buyRes?.inventory_item_id ?? null,
    slot: shopState.selectedSlot,
  });
}

async function refreshShopDebug() {
  const act = shopState.act || 1;
  try {
    await apiFetch(`/shop/refresh?act=${act}`, { method: "GET" });
    await loadShop(act);
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const msg = detail || e?.message || "Ошибка обновления";
    showToast(
      msg.includes("sql_programming_error")
        ? "Ошибка БД (схема): выполните alembic upgrade на сервере."
        : msg.includes("database_unavailable")
          ? "База данных недоступна или обрыв соединения."
          : msg,
      "error"
    );
    console.warn("refreshShopDebug:", e);
  }
}

async function adminAddGold() {
  try {
    await apiFetch(`/admin/add-gold?amount=10000`, { method: "POST" });
    await loadProfile().catch(console.error);
  } catch (e) {
    console.warn("adminAddGold failed:", e);
  }
}

let shopSellToolbarBound = false;

function getSellFilteredSortedItems() {
  const items = shopState.sellItems || [];
  return items
    .filter((item) => shopState.sellFilters[getProfileItemCategory(item)])
    .sort(compareSellItems);
}

function compareSellItems(a, b) {
  const sortKey = shopState.sellSort || "equipability";
  const dir = shopState.sellSortDir === "asc" ? 1 : -1;
  const rarityA = safeNumber(a?.rarity, 1);
  const rarityB = safeNumber(b?.rarity, 1);
  const levelA = safeNumber(a?.level, 0);
  const levelB = safeNumber(b?.level, 0);
  const equipA = a?.can_equip === false ? 0 : 1;
  const equipB = b?.can_equip === false ? 0 : 1;
  let result = 0;
  if (sortKey === "level") result = levelA - levelB || rarityA - rarityB;
  if (sortKey === "rarity") result = rarityA - rarityB || levelA - levelB;
  if (sortKey === "price") {
    result = estimateProfileSellPrice(a) - estimateProfileSellPrice(b) || levelA - levelB;
  }
  if (sortKey === "equipability") result = equipA - equipB || levelA - levelB || rarityA - rarityB;
  if (result === 0) {
    const nameA = String(a?.display_name || a?.name || "").toLowerCase();
    const nameB = String(b?.display_name || b?.name || "").toLowerCase();
    result = nameA.localeCompare(nameB, "ru");
  }
  return result * dir;
}

function ensureShopSellToolbar() {
  if (shopSellToolbarBound || typeof document === "undefined") return;
  const cb = document.getElementById("shop-sell-select-mode");
  if (!cb) return;
  shopSellToolbarBound = true;
  cb.addEventListener("change", (e) => {
    shopState.sellSelectMode = Boolean(e.target?.checked);
  });
}

function syncShopSellToolbarUI() {
  const cb = document.getElementById("shop-sell-select-mode");
  if (cb) cb.checked = Boolean(shopState.sellSelectMode);
  document.getElementById("shop-sell-filter-weapon")?.classList.toggle("active", shopState.sellFilters.weapon);
  document.getElementById("shop-sell-filter-armor")?.classList.toggle("active", shopState.sellFilters.armor);
  document.getElementById("shop-sell-filter-accessory")?.classList.toggle("active", shopState.sellFilters.accessory);
  const sortSelect = document.getElementById("shop-sell-sort-select");
  if (sortSelect) sortSelect.value = shopState.sellSort || "equipability";
  const dirBtn = document.getElementById("shop-sell-sort-dir");
  if (dirBtn) dirBtn.textContent = shopState.sellSortDir === "asc" ? "▲" : "▼";
}

function toggleShopSellFilter(category) {
  if (!Object.prototype.hasOwnProperty.call(shopState.sellFilters, category)) return;
  shopState.sellFilters[category] = !shopState.sellFilters[category];
  shopState.sellPage = 0;
  renderSellPage();
  renderSellPagination();
  syncShopSellToolbarUI();
}

function setShopSellSort(value) {
  shopState.sellSort = ["level", "rarity", "equipability", "price"].includes(value) ? value : "equipability";
  shopState.sellPage = 0;
  renderSellPage();
  renderSellPagination();
  syncShopSellToolbarUI();
}

function toggleShopSellSortDir() {
  shopState.sellSortDir = shopState.sellSortDir === "asc" ? "desc" : "asc";
  shopState.sellPage = 0;
  renderSellPage();
  renderSellPagination();
  syncShopSellToolbarUI();
}

async function loadSellInventory() {
  const box = document.getElementById("shop-sell-grid") || document.getElementById("sell-inventory");
  if (!box) return;

  const data = await apiFetch(`/inventory?equipped=false&limit=100&offset=0`);
  const items = Array.isArray(data?.items) ? data.items : [];
  shopState.sellItems = items;
  shopState.sellPage = 0;
  shopState.sellSelected = new Set();

  ensureShopSellToolbar();
  renderSellPage();
  renderSellPagination();
  updateSellResultHint();
  syncShopSellToolbarUI();
}

function renderSellPage() {
  const box = document.getElementById("shop-sell-grid");
  if (!box) return;

  const filtered = getSellFilteredSortedItems();
  const totalPages = Math.max(1, Math.ceil(filtered.length / SELL_PAGE_SIZE) || 1);
  const page = Math.max(0, Math.min(shopState.sellPage, totalPages - 1));
  shopState.sellPage = page;
  const start = page * SELL_PAGE_SIZE;
  const pageItems = filtered.slice(start, start + SELL_PAGE_SIZE);

  box.classList.remove("placeholder");
  box.innerHTML = "";

  if (!filtered.length) {
    box.innerHTML = `<div class="placeholder muted tiny" style="grid-column:1/-1;text-align:center;padding:24px 0;">Нет предметов по выбранным фильтрам.</div>`;
    applyShopMerchantHighlight();
    return;
  }

  for (let i = 0; i < SELL_PAGE_SIZE; i += 1) {
    const it = pageItems[i];
    const card = document.createElement("div");
    if (it) {
      card.className = "shop-sell-card item-card " + (rarityClassFromValue(it.rarity) || "");
      card.dataset.id = String(it.id);
      if (shopState.sellSelected.has(it.id)) card.classList.add("selected");
      const nm = String(it?.display_name || "").trim() || String(it?.name || "Предмет");
      const iconHtml = itemArtHtml(it);
      const priceBottomStr = it?.sell_price != null
        ? `🪙 ${Number(it.sell_price).toLocaleString()}`
        : "—";
      card.innerHTML = `
        <div class="item-icon">${iconHtml}</div>
        <div class="item-level">lvl ${it.level ?? "?"}</div>
        <div class="item-price">${escapeHtml(String(priceBottomStr))}</div>
      `;
      card.title = `${nm} (id ${it.id})`;
      card.onclick = () => {
        if (shopState.sellSelectMode) {
          if (shopState.sellSelected.has(it.id)) {
            shopState.sellSelected.delete(it.id);
            card.classList.remove("selected");
          } else {
            shopState.sellSelected.add(it.id);
            card.classList.add("selected");
          }
          updateSellResultHint();
        } else {
          openItemModal(it);
        }
      };
    } else {
      card.className = "shop-sell-card item-card empty";
      card.innerHTML = `<div class="item-icon">—</div><div class="item-level">—</div><div class="item-price">—</div>`;
      card.onclick = () => {};
    }
    box.appendChild(card);
  }
  applyShopMerchantHighlight();
}

function renderSellPagination() {
  const wrap = document.getElementById("shop-sell-pagination");
  if (!wrap) return;

  const filtered = getSellFilteredSortedItems();
  if (!filtered.length) {
    wrap.innerHTML = "";
    wrap.style.display = "none";
    return;
  }
  const totalPages = Math.max(1, Math.ceil(filtered.length / SELL_PAGE_SIZE));
  const page = shopState.sellPage;

  if (totalPages <= 1) {
    wrap.innerHTML = "";
    wrap.style.display = "none";
    return;
  }

  wrap.style.display = "flex";
  wrap.innerHTML = `
    <button type="button" class="shop-pagination-btn" ${page <= 0 ? "disabled" : ""} data-page="prev" aria-label="Назад">‹</button>
    <span class="shop-pagination-info">Стр. ${page + 1} из ${totalPages}</span>
    <button type="button" class="shop-pagination-btn" ${page >= totalPages - 1 ? "disabled" : ""} data-page="next" aria-label="Вперёд">›</button>
  `;

  wrap.querySelectorAll(".shop-pagination-btn").forEach((btn) => {
    if (btn.disabled) return;
    btn.addEventListener("click", () => {
      const dir = btn.dataset.page;
      if (dir === "prev" && shopState.sellPage > 0) {
        shopState.sellPage -= 1;
        renderSellPage();
        renderSellPagination();
      } else if (dir === "next" && shopState.sellPage < totalPages - 1) {
        shopState.sellPage += 1;
        renderSellPage();
        renderSellPagination();
      }
    });
  });
}

function updateSellResultHint() {
  const hint = document.getElementById("sell-result");
  if (hint) hint.textContent = `Выбрано: ${(shopState.sellSelected || new Set()).size}`;
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
  updateSellResultHint();
}

function openShopGambleResultModal(item, pricePaid, goldRemaining) {
  const m = document.getElementById("shop-gamble-result-modal");
  if (!m || !item) return;

  const nm = String(item.display_name || item.name || "Предмет").trim() || "Предмет";
  setText("shop-gamble-result-name", nm);
  setText("shop-gamble-result-rarity", item.rarity != null ? rarityLabel(item.rarity) : "—");
  setText("shop-gamble-result-level", item.level != null ? `lvl ${item.level}` : "—");

  const art = document.getElementById("shop-gamble-result-art");
  if (art) art.innerHTML = itemArtHtml(item, { adminGen: true });

  const body = document.getElementById("shop-gamble-result-body");
  if (body) {
    const parts = [];
    if (item?.tier != null) parts.push(`<div><span class="muted">Tier</span> <strong>${item.tier}</strong></div>`);
    parts.push(renderWeaponStatsHtml(item));
    parts.push(renderCombinedBonusesHtml(item));
    body.innerHTML = parts.filter(Boolean).join("") || `<div class="muted">Нет деталей предмета.</div>`;
  }

  setText("shop-gamble-result-paid", pricePaid != null ? String(pricePaid) : "—");
  setText("shop-gamble-result-gold", goldRemaining != null ? String(goldRemaining) : "—");

  const contentEl = document.getElementById("shop-gamble-result-content");
  if (contentEl) {
    ["rarity-common", "rarity-uncommon", "rarity-rare", "rarity-epic", "rarity-legendary"].forEach((c) =>
      contentEl.classList.remove(c)
    );
    contentEl.classList.add(item?.rarity != null ? rarityClass(item.rarity) : "rarity-common");
  }

  m.classList.add("shop-modal--open");
  m.style.display = "grid";
}

function closeShopGambleResultModal() {
  const m = document.getElementById("shop-gamble-result-modal");
  if (m) {
    m.classList.remove("shop-modal--open");
    m.style.display = "none";
  }
}

async function loadGambleTab(act) {
  const data = await apiFetch(`/shop/gamble/offers?act=${act}`);
  shopState.gambleOffers = Array.isArray(data?.offers) ? data.offers : [];
  shopState.gambleRefreshAt = data?.refresh_at || null;
  updateShopRefreshLabel("gamble");
  renderGambleGrid();
}

function updateShopRefreshLabel(tab) {
  const id = tab === "gamble" ? "shop-gamble-refresh-label" : "shop-buy-refresh-label";
  const el = document.getElementById(id);
  if (!el) return;
  const refreshAt = tab === "gamble" ? shopState.gambleRefreshAt : shopState.shopRefreshAt;
  if (!refreshAt) {
    el.textContent = "Обновляется в 00:00 МСК";
    return;
  }
  const end = new Date(refreshAt).getTime();
  const fmt = () => {
    const sec = Math.max(0, Math.floor((end - Date.now()) / 1000));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    el.textContent = `Обновляется в 00:00 МСК — осталось ${h}ч ${m}м`;
  };
  fmt();
  if (!window.__shopRefreshLabelTimer) {
    window.__shopRefreshLabelTimer = setInterval(() => {
      updateShopRefreshLabel("buy");
      updateShopRefreshLabel("gamble");
    }, 60_000);
  }
}

function renderGambleGrid() {
  const grid = document.getElementById("shop-gamble-grid");
  if (!grid) return;
  grid.innerHTML = "";
  for (let s = 1; s <= 12; s += 1) {
    const offer = (shopState.gambleOffers || []).find((o) => Number(o.slot) === s);
    const card = document.createElement("div");
    const purchased = Boolean(offer?.purchased);
    card.className = `shop-gamble-card shop-item-card item-card${purchased ? " purchased empty" : ""}`.trim();
    const typeLabel = offer?.slot_type ? slotTypeLabel(offer.slot_type) : "Предмет";
    const iconHtml = offer && !purchased ? itemArtEmoji(offer) : "❓";
    card.innerHTML = `
      <div class="item-icon">${iconHtml}</div>
      <div class="item-name">${escapeHtml(typeLabel)}</div>
      <div class="item-price">${purchased ? "Куплено" : `🪙 ${offer?.price ?? "—"}`}</div>
    `;
    if (offer && !purchased) {
      card.onclick = () => openGambleConfirm(s, offer.price, offer);
    }
    grid.appendChild(card);
  }
}

async function openGambleConfirm(slot, price, offer) {
  const typeLabel = offer?.slot_type ? slotTypeLabel(offer.slot_type) : "предмет";
  if (
    !confirm(
      `Купить ${typeLabel} за ${price} 🪙?\nХарактеристики скрыты — узнаешь только после покупки.`
    )
  ) {
    return;
  }
  try {
    const res = await apiFetch(`/shop/gamble/buy?act=${shopState.act}&slot=${slot}`, { method: "POST" });
    if (res?.error === "insufficient_gold" || String(res?.detail || "").includes("insufficient_gold")) {
      showToast("Недостаточно золота.", "error");
      return;
    }
    if (res?.success && res?.item) {
      openShopGambleResultModal(res.item, res.price_paid, res.gold_remaining);
      await loadProfile().catch(() => {});
      await loadGambleTab(shopState.act);
    } else if (res?.success) {
      showToast("Предмет добавлен в инвентарь.", "success");
      await loadGambleTab(shopState.act);
    } else {
      showToast(res?.error || "Не удалось купить", "error");
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || String(e?.message || e), "error");
  }
}

function showShopGambleResultModal(item, pricePaid, goldRemaining) {
  openShopGambleResultModal(item, pricePaid, goldRemaining);
}

async function gambleShop() {
  const act = shopState.act || 1;
  const btn = document.getElementById("shop-gamble-btn");
  if (btn) btn.disabled = true;
  try {
    const res = await apiFetch(`/shop/gamble?act=${act}`, { method: "POST" });
    if (res?.error === "insufficient_gold") {
      const req = res?.required != null ? String(res.required) : "?";
      const have = res?.have != null ? String(res.have) : "?";
      showToast(`Недостаточно золота. Нужно ${req}, у вас ${have}.`, "error");
      return;
    }
    if (res?.error === "not_found") {
      showToast("Сначала создайте вайфу.", "error");
      return;
    }
    if (res?.error) {
      showToast(String(res.error), "error");
      return;
    }
    let item = res?.item;
    const iid = res?.inventory_item_id;
    if (res?.success && !item && iid != null) {
      try {
        item = await apiFetch(`/inventory/${encodeURIComponent(String(iid))}`);
      } catch (_) {
        /* ниже — тост если совсем нет данных */
      }
    }
    if (res?.success && item) {
      openShopGambleResultModal(item, res.price_paid, res.gold_remaining);
    } else if (res?.success) {
      showToast("Предмет добавлен в инвентарь. Откройте профиль / магазин «Продать», чтобы увидеть его.", "success");
    } else {
      showToast("Не удалось получить предмет. Попробуйте ещё раз.", "error");
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || String(e?.message || e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
  await loadProfile().catch(console.error);
  await loadShop(act).catch(console.error);
  updateShopGambleCost();
}

function closeSlotModal() {
  const m = document.getElementById("slot-modal");
  if (m) m.style.display = "none";
  profileState.selectedSlot = null;
  profileState.slotPickerItems = [];
  profileState.slotPickerEquipped = null;
  const sortWrap = document.getElementById("slot-sort-wrap");
  if (sortWrap) sortWrap.style.display = "none";
}

function closeItemSellConfirmOverlay() {
  const ov = document.getElementById("item-modal-sell-overlay");
  if (!ov) return;
  ov.style.display = "none";
  ov.setAttribute("aria-hidden", "true");
}

function closeItemDismantleConfirmOverlay() {
  const ov = document.getElementById("item-modal-dismantle-overlay");
  if (!ov) return;
  ov.style.display = "none";
  ov.setAttribute("aria-hidden", "true");
}

async function openItemDismantleConfirmOverlay() {
  const item = profileState.selectedItem;
  if (!item?.id || item.equipment_slot != null) return;
  const ov = document.getElementById("item-modal-dismantle-overlay");
  if (!ov) return;
  const nmEl = document.getElementById("item-modal-dismantle-item-name");
  if (nmEl) nmEl.innerHTML = composeItemTitlePlain(item) || escapeHtml(String(item?.name || "—"));
  const dEl = document.getElementById("item-modal-dismantle-dust");
  if (dEl) dEl.textContent = "…";
  ov.style.display = "flex";
  ov.setAttribute("aria-hidden", "false");
  try {
    const data = await apiFetch(`/inventory/${item.id}/dismantle-preview`);
    if (dEl) dEl.textContent = String(data?.dust_preview ?? "—");
  } catch (e) {
    if (dEl) dEl.textContent = "—";
  }
}

function formatItemSellPriceGold(item) {
  if (item?.sell_price != null) {
    const n = Number(item.sell_price);
    if (Number.isFinite(n)) return n.toLocaleString();
  }
  return String(estimateProfileSellPrice(item));
}

async function openItemSellConfirmOverlay() {
  let item = profileState.selectedItem;
  if (!item?.id || item.equipment_slot != null) return;
  const ov = document.getElementById("item-modal-sell-overlay");
  if (!ov) return;
  const nmEl = document.getElementById("item-modal-sell-item-name");
  if (nmEl) nmEl.innerHTML = composeItemTitlePlain(item) || escapeHtml(String(item?.name || "—"));
  const gEl = document.getElementById("item-modal-sell-gold");
  if (item.sell_price == null && item.id) {
    try {
      const data = await apiFetch(`/inventory/${item.id}`);
      if (data?.sell_price != null) {
        item = { ...item, sell_price: data.sell_price };
        profileState.selectedItem = item;
      }
    } catch (_) {
      /* keep estimate fallback */
    }
  }
  if (gEl) gEl.textContent = formatItemSellPriceGold(item);
  ov.style.display = "flex";
  ov.setAttribute("aria-hidden", "false");
}

function closeItemEquipRingOverlay() {
  const ov = document.getElementById("item-modal-equip-ring-overlay");
  if (!ov) return;
  ov.style.display = "none";
  ov.setAttribute("aria-hidden", "true");
}

function openItemEquipRingOverlay() {
  const item = profileState.selectedItem;
  if (!item?.id || item.slot_type !== "ring") return;
  const ov = document.getElementById("item-modal-equip-ring-overlay");
  if (!ov) return;
  const hint = document.getElementById("item-modal-equip-ring-hint");
  if (hint) hint.textContent = composeItemTitlePlain(item) || escapeHtml(String(item?.name || "—"));
  const ringLabel = (slotNum) => {
    const occ = getProfileEquippedItem(slotNum);
    const base = EQUIPMENT_SLOT_NAMES[slotNum] || `Слот ${slotNum}`;
    if (!occ) return `${base} (свободно)`;
    const on = escapeHtml(String(occ.display_name || occ.name || "предмет").trim());
    return `${base} (занято: ${on})`;
  };
  const b4 = document.getElementById("item-modal-equip-ring-btn-4");
  const b5 = document.getElementById("item-modal-equip-ring-btn-5");
  if (b4) b4.textContent = ringLabel(4);
  if (b5) b5.textContent = ringLabel(5);
  ov.style.display = "flex";
  ov.setAttribute("aria-hidden", "false");
}

function closeItemModal() {
  const m = document.getElementById("item-modal");
  if (m) {
    m.classList.remove("item-modal-v2--open");
    m.style.removeProperty("--attic-bar-height");
    m.style.display = "none";
  }
  closeItemSellConfirmOverlay();
  closeItemDismantleConfirmOverlay();
  closeItemEquipRingOverlay();
  profileState.selectedItem = null;
  const reqEl = document.getElementById("item-modal-requirements");
  if (reqEl) reqEl.innerHTML = "";
  const reqSec = document.getElementById("item-modal-req-section");
  if (reqSec) reqSec.style.display = "none";
  const ench = document.getElementById("item-modal-ench");
  if (ench) ench.innerHTML = "";
  const desc = document.getElementById("item-modal-desc");
  if (desc) {
    desc.innerHTML = "";
    desc.style.display = "none";
  }
  const sub = document.getElementById("item-modal-subline");
  if (sub) sub.textContent = "";
  const rp = document.getElementById("item-modal-rpill");
  if (rp) {
    rp.textContent = "—";
    rp.className = "item-modal-v2-rpill";
  }
  const upHint = document.getElementById("item-modal-upgrade-hint");
  if (upHint) {
    upHint.style.display = "none";
    upHint.textContent = "";
    upHint.removeAttribute("title");
    upHint.removeAttribute("aria-label");
    upHint.setAttribute("aria-hidden", "true");
  }
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
    const sk = String(a.stat || "").trim();
    const m = statMeta(sk);
    const cls = bonusClass(a.value);
    const lbl = resolveAffixCharacteristicLabel(a);
    const v = formatAffixCharacteristicValue(sk, a.value, a?.is_percent);
    lines.push(
      `<div><span aria-hidden="true">${m.icon}</span> <span class="muted">${escapeHtml(lbl)}</span> <strong><span class="${cls}">${escapeHtml(v)}</span></strong></div>`
    );
  });

  if (!lines.length) return "";
  return `<div class="affixes">${lines.join("")}</div>`;
}

function renderLegendaryBonusesHtml(item) {
  if (!item) return "";
  const rows = Array.isArray(item.legendary_bonuses) ? item.legendary_bonuses : [];
  if (!rows.length) return "";
  const lines = rows.map((b) => {
    const name = escapeHtml(String(b.name || b.bonus_key || "Уникальный бонус"));
    const desc = escapeHtml(String(b.description || b.description_tpl || "").trim());
    const descHtml = desc ? `<div class="legendary-unique-bonus-desc muted tiny">${desc}</div>` : "";
    return `<div class="legendary-unique-bonus-row"><span class="legendary-unique-bonus-star" aria-hidden="true">★</span> <strong>${name}</strong>${descHtml}</div>`;
  });
  return `<div class="legendary-unique-bonuses">${lines.join("")}</div>`;
}

/** Вторичный бонус + стат/аффиксы — компактный блок карты предмета */
function renderCombinedBonusesHtml(item) {
  const secondary = renderSecondaryBonusHtml(item);
  const legendary = renderLegendaryBonusesHtml(item);
  const bonuses = renderItemBonusesHtml(item);
  const parts = [secondary, legendary, bonuses].filter(Boolean);
  if (!parts.length) return "";
  return `<div class="item-mtg-cluster">${parts.join("")}</div>`;
}

function itemArtEmoji(item) {
  const st = String(item?.slot_type || "");
  const wt = String(item?.weapon_type || "");
  if (st.includes("ring")) return "💍";
  if (st.includes("amulet")) return "📿";
  if (st.includes("costume")) return "🧥";
  if (st.includes("offhand")) return wt.includes("orb") ? "🔮" : "🛡️";
  if (st.includes("weapon")) {
    if (wt.includes("orb")) return "🔮";
    if (wt.includes("bow")) return "🏹";
    if (wt.includes("staff") || wt.includes("wand")) return "🪄";
    if (wt.includes("dagger")) return "🗡️";
    if (wt.includes("axe")) return "🪓";
    if (wt.includes("hammer") || wt.includes("mace")) return "🔨";
    return "⚔️";
  }
  return "📦";
}

function encodeArtKeyPath(artKey) {
  return String(artKey || "")
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
}

function itemArtTierNormalized(item) {
  const tierRaw = item?.tier != null ? Number(item.tier) : 1;
  return Number.isFinite(tierRaw) ? Math.min(10, Math.max(1, Math.floor(tierRaw))) : 1;
}

function itemArtDisplayLabel(item) {
  return String(item?.display_name || item?.name || item?.base_name || "").trim().slice(0, 200);
}

/** Admin: pixel-art generate control markup (shared by img wrap and spawn placeholders). */
function itemArtGenerateBtnHtml(item) {
  const artKey = String(item?.art_key || "").trim();
  if (!artKey) return "";
  const tier = itemArtTierNormalized(item);
  const wtype = String(item?.weapon_type || "").trim();
  const stype = String(item?.slot_type || "").trim();
  const dname = itemArtDisplayLabel(item);
  const wAttr = wtype ? ` data-weapon-type="${escapeHtml(wtype)}"` : "";
  const sAttr = stype ? ` data-slot-type="${escapeHtml(stype)}"` : "";
  const dAttr = dname ? ` data-display-label="${escapeHtml(dname)}"` : "";
  return `<span class="item-art-generate-btn" role="button" tabindex="0" data-art-key="${escapeHtml(artKey)}" data-art-tier="${tier}"${sAttr}${wAttr}${dAttr} title="Сгенерировать pixel art (admin)" aria-label="Сгенерировать иконку предмета">${ITEM_ART_GEN_SVG}</span>`;
}

/** Admin: wrap <img> for items under /static/game/items/ with pixel-art generate control. */
function wrapItemImageWithAdminGen(item, imgHtml) {
  if (!isAdminUiEnabled() || !item || !imgHtml || !String(imgHtml).includes("<img")) return imgHtml;
  const artKey = String(item.art_key || "").trim();
  if (!artKey) return imgHtml;
  const m = String(imgHtml).match(/src="([^"]*)"/);
  const src = m ? m[1] : "";
  const itemsPath = `${GAME_STATIC_BASE}/items/`;
  if (!src || !src.includes(itemsPath)) return imgHtml;
  const btn = itemArtGenerateBtnHtml(item);
  if (!btn) return imgHtml;
  return `<span class="item-art-admin-wrap">${imgHtml}${btn}</span>`;
}

function setItemArtGenBusy(on) {
  if (typeof document === "undefined" || !document.body) return;
  document.body.classList.toggle("item-art-gen-busy", Boolean(on));
}

function itemArtGenerateErrorMessage(err) {
  const { detail } = parseHttpErrorDetail(err);
  return detail || "";
}

async function handleItemArtGenerateClick(el) {
  if (!isAdminUser() || !el) return;
  el.classList.add("is-loading");
  el.setAttribute("aria-busy", "true");
  setItemArtGenBusy(true);
  try {
    const artKey = el.getAttribute("data-art-key");
    const tier = el.getAttribute("data-art-tier");
    const wtype = el.getAttribute("data-weapon-type");
    const dlabel = el.getAttribute("data-display-label");
    let qs = `art_key=${encodeURIComponent(artKey)}&tier=${encodeURIComponent(tier)}`;
    if (wtype) qs += `&weapon_type=${encodeURIComponent(wtype)}`;
    if (dlabel) qs += `&display_label=${encodeURIComponent(dlabel)}`;
    const payload = await apiFetch(`/admin/item-art/generate?${qs}`, { method: "POST" });
    const wrap = el.closest(".item-art-admin-wrap");
    const img = wrap && wrap.querySelector("img");
    const newUrl = String(payload?.image_url || "").trim();
    if (img) {
      const base = newUrl || img.src.split("?")[0];
      try {
        const u = new URL(base, window.location.origin);
        u.searchParams.set("v", String(Date.now()));
        img.src = u.pathname + (u.search || "") + (u.hash || "");
      } catch {
        img.src = `${base.split("?")[0]}?v=${Date.now()}`;
      }
      img.onerror = null;
    } else if (wrap && artKey) {
      const cardArt = wrap.closest(".lib-card-art");
      const inSpawnGrid = cardArt && cardArt.closest("#admin-spawn-items-grid");
      if (inSpawnGrid && cardArt) {
        adminSpawnArtFailCache.delete(artKey);
        cardArt.classList.remove("silhouette");
        const tierNum = Math.min(10, Math.max(1, parseInt(tier, 10) || 1));
        const base = newUrl || `${GAME_STATIC_BASE}/items/webp/${encodeArtKeyPath(artKey)}/t${tierNum}.webp`;
        let src;
        try {
          const u = new URL(base, window.location.origin);
          u.searchParams.set("v", String(Date.now()));
          src = u.pathname + (u.search || "") + (u.hash || "");
        } catch {
          src = `${base.split("?")[0]}?v=${Date.now()}`;
        }
        const urls = [];
        for (let t = tierNum; t >= 1; t -= 1) {
          urls.push(`${GAME_STATIC_BASE}/items/webp/${encodeArtKeyPath(artKey)}/t${t}.webp`);
        }
        const slotType = escapeHtml(el.getAttribute("data-slot-type") || "");
        const weaponType = escapeHtml(el.getAttribute("data-weapon-type") || "");
        const imgHtml = `<img src="${src}" alt="" data-art-key="${escapeHtml(artKey)}" data-art-tier="${tierNum}" data-slot-type="${slotType}" data-weapon-type="${weaponType}" data-fallback-urls="${escapeHtml(JSON.stringify(urls))}" data-fallback-index="0" onerror="WaifuApp.adminSpawnOnArtError(this)" />`;
        wrap.classList.remove("item-art-admin-wrap--placeholder");
        wrap.innerHTML = `${imgHtml}${el.outerHTML}`;
      }
    }
    if (artKey) adminSpawnArtFailCache.delete(artKey);
    showToast("Иконка сохранена");
  } catch (e) {
    const msg = itemArtGenerateErrorMessage(e);
    showToast(msg || "Ошибка генерации", "error");
  } finally {
    el.classList.remove("is-loading");
    el.removeAttribute("aria-busy");
    setItemArtGenBusy(false);
  }
}

function initItemArtGenerateDelegated() {
  if (window.__waifuItemArtGenBound) return;
  window.__waifuItemArtGenBound = true;
  const onActivate = (e) => {
    const el = e.target.closest(".item-art-generate-btn");
    if (!el || !document.body.contains(el)) return;
    e.preventDefault();
    e.stopPropagation();
    handleItemArtGenerateClick(el);
  };
  document.addEventListener("click", onActivate, true);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest(".item-art-generate-btn");
    if (!el || !document.body.contains(el)) return;
    e.preventDefault();
    e.stopPropagation();
    handleItemArtGenerateClick(el);
  }, true);
}

function itemImageUrl(item) {
  // Prefer server-provided absolute/relative URL (DB-driven mapping).
  const direct = String(item?.image_url || "").trim();
  if (direct) return direct;

  const tier = itemArtTierNormalized(item);

  // Tiered .webp by art_key (e.g. armor/kozhanaya_bronya)
  const artKey = String(item?.art_key || "").trim();
  if (artKey) {
    return `${GAME_STATIC_BASE}/items/webp/${encodeArtKeyPath(artKey)}/t${tier}.webp`;
  }

  // Legacy svg placeholders by image_key
  const key = String(item?.image_key || "").trim();
  if (!key) return "";
  return `${GAME_STATIC_BASE}/items/svg/${encodeURIComponent(key)}.svg`;
}

function itemArtHtml(item, options = {}) {
  if (!item) return `${itemArtEmoji(item)}`;
  const adminGen = Boolean(options.adminGen);
  const lazyLoad = Boolean(options.lazy);
  const maybeWrap = (img) => (adminGen ? wrapItemImageWithAdminGen(item, img) : img);
  const tier = itemArtTierNormalized(item);
  const artKey = String(item?.art_key || "").trim();
  const svgKey = String(item?.image_key || "").trim();
  const direct = String(item?.image_url || "").trim();

  const webpUrl = direct
    ? direct
    : artKey
      ? `${GAME_STATIC_BASE}/items/webp/${encodeArtKeyPath(artKey)}/t${tier}.webp`
      : "";
  const svgUrl = svgKey ? `${GAME_STATIC_BASE}/items/svg/${encodeURIComponent(svgKey)}.svg` : "";

  if (webpUrl) {
    const onErr = svgUrl
      ? `this.onerror=null;this.src='${svgUrl}';`
      : `this.onerror=null;this.remove();`;
    const lazyAttrs = lazyLoad ? ' loading="lazy" decoding="async"' : "";
    const img = `<img src="${webpUrl}" alt=""${lazyAttrs} onerror="${onErr}" />`;
    return maybeWrap(img);
  }

  const url = itemImageUrl(item);
  if (url) {
    const lazyAttrs = lazyLoad ? ' loading="lazy" decoding="async"' : "";
    return maybeWrap(`<img src="${url}" alt=""${lazyAttrs} />`);
  }
  return `${itemArtEmoji(item)}`;
}

/** Магазин отдаёт name/display_name уже с префиксом и суффиксом; повторная сборка даёт дубли. */
function itemNameAlreadyIncludesAffixRollup(item) {
  const nm = String(item?.name || "").trim();
  const dn = String(item?.display_name || "").trim();
  if (!nm || nm !== dn) return false;
  const aff = Array.isArray(item?.affixes) ? item.affixes : [];
  return aff.some((a) => {
    const k = String(a?.kind || "");
    return k === "affix" || k === "suffix";
  });
}

function collectAffixNameParts(aff) {
  const list = Array.isArray(aff) ? aff : [];
  const prefixes = list
    .filter((a) => String(a?.kind || "") === "affix")
    .map((a) => String(a?.name || "").trim())
    .filter(Boolean);
  const suffixes = list
    .filter((a) => String(a?.kind || "") === "suffix")
    .map((a) => String(a?.name || "").trim())
    .filter(Boolean);
  return { prefixes, suffixes };
}

function composeItemNameCore(item) {
  const displayName = String(item?.display_name || "").trim();
  if (displayName) return displayName;
  if (itemNameAlreadyIncludesAffixRollup(item)) {
    return String(item.name || "Предмет").trim() || "Предмет";
  }
  const base = String(item?.name || "Предмет").trim() || "Предмет";
  const { prefixes, suffixes } = collectAffixNameParts(item?.affixes);
  const parts = [...prefixes, base, ...suffixes].filter(Boolean);
  return parts.join(" ").trim() || base;
}

function composeItemDisplayName(item) {
  const en = safeNumber(item?.enchant_level, 0);
  const enHtml =
    en > 0 && !item?.is_broken ? ` <span class="enchant-badge">+${en}</span>` : "";
  const brk = item?.is_broken ? ` <span class="broken-badge">💔 Сломан</span>` : "";
  const core = composeItemNameCore(item);
  return `${escapeHtml(core)}${enHtml}${brk}`.trim();
}

/** Название для шапки модалки v2: префикс/база/суффикс без +заточки (она в блоке «Заточка»). */
function composeItemTitlePlain(item) {
  const brk = item?.is_broken ? " 💔" : "";
  const core = composeItemNameCore(item);
  return `${escapeHtml(core)}${brk}`.trim();
}

const ITEM_MODAL_ENCHANT_PIP_MAX = 10;

const _ITEM_MODAL_V2_ICO = [
  ["⚔️", "item-modal-v2-ico-re"],
  ["💙", "item-modal-v2-ico-te"],
  ["💜", "item-modal-v2-ico-pu"],
  ["✨", "item-modal-v2-ico-go"],
  ["💚", "item-modal-v2-ico-gr"],
];

function itemModalV2NextIcon() {
  const i = itemModalV2NextIcon._i;
  itemModalV2NextIcon._i = i + 1;
  return _ITEM_MODAL_V2_ICO[i % _ITEM_MODAL_V2_ICO.length];
}
itemModalV2NextIcon._i = 0;

function itemModalV2StatRow(name, valHtml, valCls, secHtml, compact = false) {
  const sec = secHtml ? `<div class="item-modal-v2-ssec">${secHtml}</div>` : "";
  const vc = valCls ? ` ${valCls}` : "";
  if (compact) {
    return `<div class="item-modal-v2-srow item-modal-v2-srow--compact">
    <div class="item-modal-v2-srow-l">
      <div><div class="item-modal-v2-sname">${escapeHtml(name)}</div>${sec}</div>
    </div>
    <span class="item-modal-v2-sval${vc}">${valHtml}</span>
  </div>`;
  }
  const [emoji, icl] = itemModalV2NextIcon();
  return `<div class="item-modal-v2-srow">
    <div class="item-modal-v2-srow-l">
      <div class="item-modal-v2-sico ${icl}" aria-hidden="true">${emoji}</div>
      <div><div class="item-modal-v2-sname">${escapeHtml(name)}</div>${sec}</div>
    </div>
    <span class="item-modal-v2-sval${vc}">${valHtml}</span>
  </div>`;
}

function rarityPillModifierClass(r) {
  const v = Number(r);
  if (v === 5) return "item-modal-v2-rpill--legendary";
  if (v === 4) return "item-modal-v2-rpill--epic";
  if (v === 3) return "item-modal-v2-rpill--rare";
  if (v === 2) return "item-modal-v2-rpill--uncommon";
  return "";
}

function itemEnchantOverlayHtml(item, context = "bag") {
  const ctx = ["bag", "slot", "modal"].includes(context) ? context : "bag";
  const br = Boolean(item?.is_broken);
  const en = safeNumber(item?.enchant_level, 0);
  if (br) {
    return `<span class="item-enchant-overlay item-enchant-overlay--${ctx} item-enchant-overlay--broken" title="Сломан">—</span>`;
  }
  if (en <= 0) return "";
  return `<span class="item-enchant-overlay item-enchant-overlay--${ctx}">+${en}</span>`;
}

function buildItemModalEnchantRowHtml(item) {
  const en = safeNumber(item?.enchant_level, 0);
  const mx = ITEM_MODAL_ENCHANT_PIP_MAX;
  const pips = Array.from({ length: mx }, (_, i) => {
    const f = i < en;
    const mxf = f && en >= mx;
    const cls = mxf ? " item-modal-v2-pip--mx" : f ? " item-modal-v2-pip--f" : "";
    return `<div class="item-modal-v2-pip${cls}" aria-hidden="true"></div>`;
  }).join("");
  return `<div class="item-modal-v2-pips">${pips}</div>`;
}

function itemModalV2Subpanel(modifierClass, innerHtml) {
  if (!innerHtml) return "";
  const mod = String(modifierClass || "").trim();
  return `<div class="item-modal-v2-subpanel${mod ? ` ${mod}` : ""}">${innerHtml}</div>`;
}

function renderItemModalV2LegendaryBlockHtml(bonuses) {
  const rows = Array.isArray(bonuses) ? bonuses : [];
  if (!rows.length) return "";
  const entries = rows
    .map((b) => {
      const name = String(b.name || b.bonus_key || "Уникальный бонус");
      const desc = String(b.description || b.description_tpl || "").trim();
      const descHtml = desc
        ? `<div class="item-modal-v2-leg-desc">${escapeHtml(desc)}</div>`
        : "";
      return `<div class="item-modal-v2-leg-entry">
        <div class="item-modal-v2-leg-name"><span class="item-modal-v2-leg-star" aria-hidden="true">★</span> ${escapeHtml(name)}</div>
        ${descHtml}
      </div>`;
    })
    .join("");
  return entries;
}

function renderItemModalV2CharacteristicsHtml(item) {
  if (!item) return "";
  itemModalV2NextIcon._i = 0;
  const baseRows = [];
  const otherRows = [];

  const armorEff =
    item?.armor_effective != null
      ? safeNumber(item.armor_effective, safeNumber(item?.armor_base, 0))
      : safeNumber(item?.armor_base, 0);
  const dmgMinE = item?.damage_min_effective != null ? Number(item.damage_min_effective) : Number(item?.damage_min ?? NaN);
  const dmgMaxE = item?.damage_max_effective != null ? Number(item.damage_max_effective) : Number(item?.damage_max ?? NaN);
  const speed = item?.attack_speed != null ? Number(item.attack_speed) : null;
  const st = String(item?.slot_type || "").toLowerCase();
  const isWeapon = st.includes("weapon");
  const isAccessory = st.includes("ring") || st.includes("amulet");

  if (!isWeapon && !isAccessory && armorEff > 0) {
    baseRows.push(
      itemModalV2StatRow("Броня", escapeHtml(String(armorEff)), "item-modal-v2-sv-te", null)
    );
  }
  if (isWeapon && Number.isFinite(dmgMinE) && Number.isFinite(dmgMaxE)) {
    baseRows.push(
      itemModalV2StatRow("Урон", escapeHtml(`${dmgMinE}–${dmgMaxE}`), "item-modal-v2-sv-re", null)
    );
  }
  if (isWeapon && speed != null) {
    baseRows.push(
      itemModalV2StatRow("Скорость атаки", escapeHtml(String(speed)), "item-modal-v2-sv-go", null)
    );
  }

  if (item.base_stat && item.base_stat_value != null) {
    const m = statMeta(item.base_stat);
    const v = formatBonusValue(item.base_stat, item.base_stat_value);
    const cls =
      String(item.base_stat).includes("strength") || String(item.base_stat).includes("damage")
        ? "item-modal-v2-sv-re"
        : "item-modal-v2-sv-pu";
    otherRows.push(itemModalV2StatRow(m.short, escapeHtml(v), cls, null, true));
  }

  const t = String(item?.secondary_bonus_type || "").trim();
  const v0 = Number(item?.secondary_bonus_value ?? 0);
  const vEff =
    item?.secondary_bonus_effective != null ? Number(item.secondary_bonus_effective) : v0;
  if (t && Number.isFinite(vEff) && vEff > 0) {
    const label = secondaryBonusTitleRu(t);
    const valDisp = formatSecondaryBonusValueDisplay(t, vEff);
    otherRows.push(
      itemModalV2StatRow(
        label,
        escapeHtml(valDisp),
        "item-modal-v2-sv-go",
        secondaryBonusModalSubtitle(t),
        true
      )
    );
  }

  const ft = String(item?.secondary_fraction_type || "").trim();
  const fvEff =
    item?.secondary_fraction_effective != null
      ? Number(item.secondary_fraction_effective)
      : Number(item?.secondary_fraction_value ?? 0);
  if (ft && Number.isFinite(fvEff) && fvEff > 0) {
    otherRows.push(
      itemModalV2StatRow(
        secondaryBonusTitleRu(ft),
        escapeHtml(formatSecondaryBonusValueDisplay(ft, fvEff)),
        "item-modal-v2-sv-go",
        "Fraction-вторичка (растёт от заточки)",
        true
      )
    );
  }

  const aff = Array.isArray(item.affixes) ? item.affixes : [];
  aff.forEach((a) => {
    const sk = String(a.stat || "").trim();
    const skl = sk.toLowerCase();
    const label = resolveAffixCharacteristicLabel(a);
    let v = formatAffixCharacteristicValue(sk, a.value, a?.is_percent);
    if (
      skl.startsWith("passive_node_level_add:") ||
      skl.startsWith("passive_branch_level_add:") ||
      skl === "passive_all_nodes_level_add"
    ) {
      v = `${v} ур.`;
    }
    otherRows.push(itemModalV2StatRow(label, escapeHtml(v), "item-modal-v2-sv-pu", null, true));
  });

  const leg = Array.isArray(item.legendary_bonuses) ? item.legendary_bonuses : [];
  const basePanel = itemModalV2Subpanel("item-modal-v2-subpanel--base", baseRows.join(""));
  const legendaryPanel = itemModalV2Subpanel(
    "item-modal-v2-subpanel--legendary",
    renderItemModalV2LegendaryBlockHtml(leg)
  );
  const otherHtml = otherRows.length
    ? `<div class="item-modal-v2-other-stats">${otherRows.join("")}</div>`
    : "";

  return [basePanel, legendaryPanel, otherHtml].filter(Boolean).join("");
}

function goShopSmithEnchant(inventoryItemId) {
  const id = Number(inventoryItemId);
  if (!Number.isFinite(id) || id <= 0) return;
  const onShop =
    typeof window !== "undefined" && String(window.location.pathname || "").endsWith("/shop.html");
  if (onShop) {
    closeItemModal();
    void (async () => {
      switchShopTab("smith");
      await loadSmithTab();
      if (shopState.smithItems.some((x) => x.id === id)) {
        shopState.smithSelectedId = id;
        updateSmithSelectionUI();
        await refreshSmithPreview();
      } else {
        showToast("Предмет не найден в инвентаре", "error");
      }
    })();
    return;
  }
  try {
    sessionStorage.setItem("waifu_shop_intent_tab", "smith");
    sessionStorage.setItem("waifu_shop_smith_item_id", String(id));
  } catch (e) {
    /* ignore */
  }
  window.location.href = "./shop.html";
}

function goShopSmithEnchantFromModal() {
  const it = profileState.selectedItem;
  if (!it?.id) return;
  goShopSmithEnchant(it.id);
}

function renderWeaponStatsHtml(item) {
  const armorEff =
    item?.armor_effective != null
      ? safeNumber(item.armor_effective, safeNumber(item?.armor_base, 0))
      : safeNumber(item?.armor_base, 0);

  const dmgMin = item?.damage_min != null ? Number(item.damage_min) : null;
  const dmgMax = item?.damage_max != null ? Number(item.damage_max) : null;
  const dmgMinE = item?.damage_min_effective != null ? Number(item.damage_min_effective) : dmgMin;
  const dmgMaxE = item?.damage_max_effective != null ? Number(item.damage_max_effective) : dmgMax;
  const dmg =
    dmgMinE != null && dmgMaxE != null
      ? `${dmgMinE}–${dmgMaxE}`
      : dmgMinE != null
        ? `${dmgMinE}+`
        : dmgMaxE != null
          ? `0–${dmgMaxE}`
          : null;

  const speed = item?.attack_speed != null ? Number(item.attack_speed) : null;

  const st = String(item?.slot_type || "").toLowerCase();
  const isWeapon = st.includes("weapon");
  const isAccessory = st.includes("ring") || st.includes("amulet");
  const hasArmor = !isWeapon && !isAccessory && armorEff > 0;
  const hasDmg = isWeapon && dmg != null;

  const rows = [];
  if (hasArmor) {
    rows.push(
      `<div class="item-mtg-field"><span class="muted">Броня</span><strong>${escapeHtml(String(armorEff))}</strong></div>`
    );
  }
  if (hasDmg) rows.push(`<div class="item-mtg-field"><span class="muted">Урон</span><strong>${dmg}</strong></div>`);
  if (isWeapon && speed != null) {
    rows.push(`<div class="item-mtg-field"><span class="muted">Скорость атаки</span><strong>${speed}</strong></div>`);
  }

  if (rows.length === 0) return "";
  return `<div class="item-mtg-cluster">${rows.join("")}</div>`;
}

const SECONDARY_LABELS = {
  crit_chance_pct: "Шанс крита",
  evade_pct: "Уклонение",
  dmg_reduce_pct: "Снижение урона",
  hp_max_pct: "Бонус HP",
  exp_bonus_pct: "Бонус к опыту",
  gold_bonus_pct: "Бонус к золоту",
  magic_find_pct: "Поиск магических предметов",
  media_damage_text_percent: "Урон от текста",
  media_damage_sticker_percent: "Урон от стикеров",
  media_damage_photo_percent: "Урон от фото",
  media_damage_gif_percent: "Урон от GIF",
  media_damage_audio_percent: "Урон от аудио",
  media_damage_voice_percent: "Урон от голосовых",
  media_damage_video_percent: "Урон от видео",
  media_damage_link_percent: "Урон от ссылок",
};

function secondaryBonusUsesFractionDisplay(t) {
  const k = normalizeEffectKeyUi(t);
  if (!k || k.includes(":")) return false;
  return Object.prototype.hasOwnProperty.call(SECONDARY_LABELS, k);
}

function formatSecondaryBonusValueDisplay(t, vEff) {
  const typ = String(t || "").trim();
  const low = normalizeEffectKeyUi(typ);
  if (secondaryBonusUsesFractionDisplay(typ)) {
    return `+${(safeNumber(vEff, 0) * 100).toFixed(1)}%`;
  }
  if (
    low.startsWith("passive_node_level_add:") ||
    low.startsWith("passive_branch_level_add:") ||
    low === "passive_all_nodes_level_add"
  ) {
    const n = Math.round(safeNumber(vEff, 0));
    const sign = n >= 0 ? "+" : "";
    return `${sign}${n} ур.`;
  }
  if (low.startsWith("damage_vs_monster_type_percent:")) {
    const n = safeNumber(vEff, 0);
    const sign = n >= 0 ? "+" : "";
    return `${sign}${n.toFixed(1)}%`;
  }
  if (low.startsWith("damage_vs_monster_type_flat:")) {
    const n = safeNumber(vEff, 0);
    const sign = n >= 0 ? "+" : "";
    return `${sign}${Math.round(n)}`;
  }
  const v = safeNumber(vEff, 0);
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v}`;
}

function secondaryBonusTitleRu(t) {
  const typ = String(t || "").trim();
  const low = normalizeEffectKeyUi(typ);
  if (low.startsWith("passive_node_level_add:")) {
    const nid = typ.slice(typ.indexOf(":") + 1).trim();
    const nm = passiveNodeDisplayNameRu(nid);
    return `Пассив «${nm}»`;
  }
  if (low.startsWith("passive_branch_level_add:")) {
    const br = typ.slice(typ.indexOf(":") + 1).trim().toLowerCase();
    const lbl = PASSIVE_BRANCH_LABELS_RU[br] || br;
    return `Пассивы ветки (${lbl})`;
  }
  if (low === "passive_all_nodes_level_add") {
    return "Все пассивные навыки";
  }
  if (low.startsWith("damage_vs_monster_type_flat:")) {
    const fam = typ.slice(typ.indexOf(":") + 1).trim().toLowerCase();
    const ru = MONSTER_FAMILY_LABELS_RU[fam] || fam;
    return `Урон по ${ru}`;
  }
  if (low.startsWith("damage_vs_monster_type_percent:")) {
    const fam = typ.slice(typ.indexOf(":") + 1).trim().toLowerCase();
    const ru = MONSTER_FAMILY_LABELS_RU[fam] || fam;
    return `Урон % по ${ru}`;
  }
  return SECONDARY_LABELS[low] || typ;
}

function secondaryBonusModalSubtitle(t) {
  const low = String(t || "").toLowerCase();
  if (low.startsWith("passive_node_level_add:")) {
    return "К уровню узла на дереве пассивов (для части навыков эффект ограничен капом таблицы)";
  }
  if (low.startsWith("passive_branch_level_add:") || low === "passive_all_nodes_level_add") {
    return "Легендарный тип бонуса";
  }
  if (secondaryBonusUsesFractionDisplay(t)) return "Вторичный бонус";
  return "Доп. свойство";
}

function renderSecondaryBonusHtml(item) {
  const t = String(item?.secondary_bonus_type || "").trim();
  const v0 = Number(item?.secondary_bonus_value ?? 0);
  const v =
    item?.secondary_bonus_effective != null ? Number(item.secondary_bonus_effective) : v0;
  if (!t || !Number.isFinite(v) || v <= 0) return "";
  const label = secondaryBonusTitleRu(t);
  const inner = formatSecondaryBonusValueDisplay(t, v);
  return `<div class="item-mtg-field"><span class="muted">${escapeHtml(label)}</span><strong>${escapeHtml(inner)}</strong></div>`;
}

/** Краткое текстовое описание бонусов предмета для промпта ИИ торговца */
function getItemBonusesText(item) {
  if (!item) return "";
  const parts = [];
  if (item.base_stat && item.base_stat_value != null) {
    const m = statMeta(item.base_stat);
    const v = formatBonusValue(item.base_stat, item.base_stat_value);
    parts.push(`${m.short} ${v}`);
  }
  const aff = Array.isArray(item.affixes) ? item.affixes : [];
  aff.forEach((a) => {
    const sk = String(a.stat || "").trim();
    const lbl = resolveAffixCharacteristicLabel(a);
    const v = formatAffixCharacteristicValue(sk, a.value, a?.is_percent);
    parts.push(`${lbl} ${v}`);
  });
  const armor = safeNumber(item?.armor_base, 0);
  if (armor > 0) parts.push(`броня ${armor}`);
  if (item?.damage_min != null || item?.damage_max != null) {
    const dmin = item.damage_min != null ? Number(item.damage_min) : 0;
    const dmax = item.damage_max != null ? Number(item.damage_max) : dmin;
    parts.push(`урон ${dmin}–${dmax}`);
  }
  const st = String(item?.secondary_bonus_type || "").trim();
  const sv = Number(item?.secondary_bonus_value ?? 0);
  if (st && Number.isFinite(sv) && sv > 0) {
    const label = secondaryBonusTitleRu(st);
    const val = formatSecondaryBonusValueDisplay(st, sv);
    parts.push(`${label} ${val}`);
  }
  return parts.join(", ");
}

function renderProfilePortrait(waifu, profile = null) {
  setText("profile-portrait-name", waifu?.name || "—");
  const metaEl = document.getElementById("profile-mtg-meta");
  if (metaEl) {
    const p = profile || profileState.currentProfile;
    const lvlLabel = formatLevelWithPerfection(
      waifu?.level,
      p?.perfection_level
    );
    metaEl.textContent = `Ур. ${lvlLabel} · ${raceName(waifu?.race)} · ${className(waifu?.class ?? waifu?.class_)}`;
  }

  const portraitUrl = resolveImageUrl(
    String(
      waifu?.portrait_url || waifu?.image_url || waifu?.sprite_url || waifu?.avatar_url || ""
    ).trim()
  );
  const bg = document.getElementById("profile-mtg-bg");
  const fallback = document.getElementById("profile-mtg-fallback");
  if (bg) {
    if (portraitUrl) {
      bg.style.backgroundImage = `url(${JSON.stringify(portraitUrl)})`;
      bg.classList.remove("profile-mtg-bg--empty");
    } else {
      bg.style.backgroundImage = "none";
      bg.classList.add("profile-mtg-bg--empty");
    }
  }
  if (fallback) {
    fallback.textContent = portraitUrl ? "" : waifuPortraitEmoji(waifu) || "👤";
  }

  const legacyPortrait = document.getElementById("profile-portrait-media");
  if (legacyPortrait) {
    legacyPortrait.innerHTML = portraitUrl
      ? `<img src="${escapeHtml(portraitUrl)}" alt="${escapeHtml(String(waifu?.name || "Портрет"))}" />`
      : escapeHtml(waifuPortraitEmoji(waifu) || "👤");
  }
}

function renderProfileHeroBars(waifu, details = null, profile = null) {
  const d = details || profileState.currentDetails || null;
  const p = profile || profileState.currentProfile || null;
  const hpCur = safeNumber(d?.hp_current ?? waifu?.current_hp, 0);
  const hpMax = Math.max(1, safeNumber(d?.hp_max ?? waifu?.max_hp, 1));
  setText("profile-hp-text", `${hpCur}/${hpMax}`);
  const hpFill = document.getElementById("profile-hp-fill");
  if (hpFill) hpFill.style.width = `${Math.round(clamp01(hpCur / hpMax) * 100)}%`;

  const lvl = safeNumber(waifu?.level, 1);
  const xp = safeNumber(waifu?.experience, 0);
  const xpFill = document.getElementById("profile-xp-fill");
  const xpBlock = document.querySelector(".profile-mtg-xp-block");
  const pLevel = safeNumber(p?.perfection_level, 0);
  if (lvl >= PLAYER_MAX_LEVEL && pLevel > 0) {
    const need = safeNumber(p?.perfection_xp_to_next, 0);
    const pxp = safeNumber(p?.perfection_experience, 0);
    const pct = need > 0 ? Math.round(clamp01(pxp / need) * 100) : 0;
    setText("profile-xp-text", `Совершенствование ${pLevel} · ${pxp} / ${need} EXP`);
    if (xpFill) xpFill.style.width = `${pct}%`;
    if (xpBlock) xpBlock.classList.add("profile-mtg-xp-block--perfection");
  } else if (lvl >= PLAYER_MAX_LEVEL) {
    setText("profile-xp-text", `Ур. ${lvl} · макс.`);
    if (xpFill) xpFill.style.width = "100%";
    if (xpBlock) xpBlock.classList.remove("profile-mtg-xp-block--perfection");
  } else {
    const curTotal = totalExpForLevel(lvl);
    const nextTotal = totalExpForLevel(lvl + 1);
    const xpPct = curTotal > 0 && nextTotal > curTotal
      ? Math.round(clamp01((xp - curTotal) / (nextTotal - curTotal)) * 100)
      : Math.round(clamp01(xp / nextTotal) * 100);
    setText("profile-xp-text", `Ур. ${lvl} · ${xp} / ${nextTotal} EXP`);
    if (xpFill) xpFill.style.width = `${Math.max(0, xpPct)}%`;
    if (xpBlock) xpBlock.classList.remove("profile-mtg-xp-block--perfection");
  }
}

function renderProfilePerfectionSummary(profile) {
  const wrap = document.getElementById("profile-perfection-summary");
  const list = document.getElementById("profile-perfection-bonus-list");
  if (!wrap || !list) return;
  const summary = Array.isArray(profile?.perfection_bonuses_summary)
    ? profile.perfection_bonuses_summary
    : [];
  const pLevel = Number(profile?.perfection_level || 0);
  if (!pLevel || !summary.length) {
    wrap.hidden = true;
    list.innerHTML = "";
    return;
  }
  wrap.hidden = false;
  list.innerHTML = summary
    .map(
      (b) =>
        `<li><span>${escapeHtml(b.title_ru || b.bonus_id)}</span><strong>${escapeHtml(
          b.display_value || ""
        )}</strong><em class="perfection-bonus-tag">${escapeHtml(b.label || "Навсегда")}</em></li>`
    )
    .join("");
}

function renderProfileIndicators(waifu, details = null) {
  const box = document.getElementById("profile-indicators-grid");
  if (!box || !waifu) return;
  const d = details || profileState.currentDetails || null;
  const indicators = getProfileIndicators(waifu, d);
  const charm = profileStatValue(waifu, "charm");
  const merchantDiscount = safeNumber(d?.merchant_discount, 0);
  const buyPct = merchantDiscount > 0
    ? Math.max(100, Math.round((1 - merchantDiscount / 100) * 200))
    : Math.round(200 - charm * 0.1 * 2);
  const sellPct = merchantDiscount > 0
    ? Math.min(99, Math.round((0.5 + merchantDiscount / 100 * 0.5) * 100))
    : Math.round(50 + charm * 0.1 * 0.5);

  const rows = [
    ["HP макс.", indicators.hpMax],
    ["Броня", indicators.armor],
    ["Сниж. ур. (ВЫН)", indicators.damageReduction],
    ["Урон ближний", indicators.meleeRange],
    ["Урон дальний", indicators.rangedRange],
    ["Урон магич.", indicators.magicRange],
    ["Крит", indicators.critChance],
    [
      "Уклонение",
      indicators.dodgeChance,
      "Шанс не получить урон от ответного удара монстра. Складывается: ЛОВ × 0,1% + вторички на предметах + пассивы (например Проворство). Потолок 40%.",
    ],
    [
      "Полное уклонение",
      indicators.fullEvadeChance,
      "Отдельный бросок после обычного уклонения: при успехе урон = 0. Даётся пассивами вроде «Шаг тени». Не суммируется со строкой «Уклонение».",
    ],
    ["Бонус EXP", indicators.expBonus],
    ["Бонус золота", indicators.goldBonus],
    ["Скидка найма", indicators.hireDiscount],
    ["Скидка трен.", indicators.trainingDiscount],
    ["Реген HP", indicators.hpRegen],
  ];

  const cells = rows
    .map((row) => {
      const label = row[0];
      const value = row[1];
      const tip = row[2] || "";
      const tipAttr = tip ? ` title="${escapeHtml(tip)}"` : "";
      return `<div class="profile-detail-cell"${tipAttr}><span class="profile-detail-label">${escapeHtml(label)}</span><strong class="profile-detail-value">${escapeHtml(
        String(value)
      )}</strong></div>`;
    })
    .join("");

  const merchantCell = `<div class="profile-detail-cell profile-detail-cell--merchant">
    <span class="profile-detail-label">Торговля</span>
    <div class="profile-detail-value-stack">
      <span class="profile-detail-value">покупка ${buyPct}%</span>
      <span class="profile-detail-value">продажа ${sellPct}%</span>
    </div>
  </div>`;

  box.innerHTML = `${cells}${merchantCell}`;
}

async function renderProfileStatistics() {
  const box = document.getElementById("profile-statistics-grid");
  if (!box) return;
  box.innerHTML = `<div class="profile-detail-cell profile-detail-cell--full"><span class="profile-detail-label">Загрузка…</span></div>`;
  try {
    const stats = await apiFetch("/waifu/statistics");
    const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("ru-RU"));
    const rows = [
      ["Подземелий", fmt(stats.dungeons_completed)],
      ["Монстров", fmt(stats.monsters_killed)],
      ["Урона нанесено", fmt(stats.damage_dealt)],
      ["Урона (HP)", fmt(stats.hp_lost)],
      ["Золота", fmt(stats.gold_earned)],
      ["Опыта", fmt(stats.exp_earned)],
    ];
    box.innerHTML = rows
      .map(
        ([label, value]) =>
          `<div class="profile-detail-cell"><span class="profile-detail-label">${escapeHtml(label)}</span><strong class="profile-detail-value">${escapeHtml(
            String(value)
          )}</strong></div>`
      )
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="profile-detail-cell profile-detail-cell--full"><span class="profile-detail-label">Ошибка загрузки</span></div>`;
  }
  renderProfileAbyssStats().catch(() => {});
}

async function renderProfileAbyssStats() {
  const section = document.getElementById("profile-abyss-section");
  const box = document.getElementById("profile-abyss-stats");
  if (!section || !box) return;
  try {
    const st = await apiFetch("/abyss/status");
    const record = Number(st.max_floor_reached || 0);
    if (record <= 0 && !st.session_active) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("ru-RU"));
    const rows = [
      ["Рекорд (этаж)", fmt(record)],
      ["Чекпоинт", fmt(st.current_checkpoint)],
      ["Осколки", fmt(st.abyss_shards)],
      ["Чекпоинтов сегодня", `${fmt(st.checkpoints_today)} / ${fmt(st.daily_limit)}`],
    ];
    if (st.session_active) {
      rows.unshift(["Сейчас на этаже", fmt(st.current_floor)]);
    }
    box.innerHTML = rows
      .map(
        ([label, value]) =>
          `<div class="profile-detail-cell"><span class="profile-detail-label">${escapeHtml(label)}</span><strong class="profile-detail-value">${escapeHtml(String(value))}</strong></div>`
      )
      .join("");
  } catch (e) {
    section.hidden = true;
  }
}

function syncProfileInfoTabs() {
  document.querySelectorAll(".profile-inner-tabs .tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.infoTab === profileState.infoTab);
  });
  document.querySelectorAll(".profile-info-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `profile-info-${profileState.infoTab}`);
  });
}

function profileFormatFlatBonusBlock(title, bonusMap) {
  const lines = [];
  for (const statKey of PROFILE_STAT_ORDER) {
    const v = safeNumber(bonusMap?.[statKey], 0);
    if (v !== 0) {
      const meta = statMeta(statKey);
      const label = PROFILE_STAT_LABELS[statKey] || meta.short;
      lines.push(`${label}: ${v >= 0 ? "+" : ""}${v}`);
    }
  }
  const inner =
    lines.length > 0
      ? lines.map((l) => `<div class="profile-bonus-item">${escapeHtml(l)}</div>`).join("")
      : `<div class="muted tiny">Без бонусов к характеристикам</div>`;
  return `<div class="profile-raceclass-block"><div class="profile-breakdown-detail-caption">${escapeHtml(
    title
  )}</div>${inner}</div>`;
}

function renderProfileRaceClassPanel() {
  const root = document.getElementById("profile-raceclass-content");
  if (!root) return;
  const waifu = profileState.currentProfile?.main_waifu;
  if (!waifu) {
    root.innerHTML = "";
    return;
  }
  const raceId = Number(waifu.race);
  const clsId = Number(waifu.class ?? waifu.class_);
  const raceMap =
    waifu.race_flat_bonuses != null && typeof waifu.race_flat_bonuses === "object"
      ? waifu.race_flat_bonuses
      : WAIFU_RACE_BONUSES[raceId] || {};
  const classMap =
    waifu.class_flat_bonuses != null && typeof waifu.class_flat_bonuses === "object"
      ? waifu.class_flat_bonuses
      : WAIFU_CLASS_BONUSES[clsId] || {};

  const raceLines = (WAIFU_GEN_RACE_PASSIVES[raceId] || [])
    .map((t) => `<li>${escapeHtml(t)}</li>`)
    .join("");
  const classLines = (WAIFU_GEN_CLASS_PASSIVES[clsId] || [])
    .map((t) => `<li>${escapeHtml(t)}</li>`)
    .join("");

  root.innerHTML =
    `<div class="profile-raceclass-flat">` +
    `${profileFormatFlatBonusBlock(`Раса: ${raceName(raceId)}`, raceMap)}` +
    `${profileFormatFlatBonusBlock(`Класс: ${className(clsId)}`, classMap)}` +
    `</div>` +
    `<div class="profile-breakdown-detail-caption" style="margin-top:12px">Особенности (ТЗ)</div>` +
    `<div class="profile-raceclass-passive">` +
    `<div class="waifu-gen-passive-sub">Раса</div><ul>${raceLines || `<li class="muted tiny">—</li>`}</ul>` +
    `<div class="waifu-gen-passive-sub">Класс</div><ul>${classLines || `<li class="muted tiny">—</li>`}</ul>` +
    `</div>`;
}

function switchProfileInfoTab(name) {
  if (name === "statistics") profileState.infoTab = "statistics";
  else if (name === "raceclass") profileState.infoTab = "raceclass";
  else profileState.infoTab = "indicators";
  syncProfileInfoTabs();
  if (profileState.infoTab === "statistics") renderProfileStatistics().catch(() => {});
  else if (profileState.infoTab === "raceclass") renderProfileRaceClassPanel();
}

function toggleProfileStatAccordion(statKey) {
  profileState.activeAccordion = profileState.activeAccordion === statKey ? null : statKey;
  const waifu = profileState.currentProfile?.main_waifu;
  if (waifu) renderStatsBreakdown("profile-stats-breakdown", waifu, profileState.currentDetails);
}

function renderProfileSlotCard(slot, item) {
  const rarity = item ? rarityClass(item?.rarity) : "rarity-common";
  const lvl = item?.level ?? "—";
  const slotName = EQUIPMENT_SLOT_NAMES[slot] || `Слот ${slot}`;
  const titleText = item
    ? String(item?.display_name || item?.name || "Предмет")
    : `Пусто · ${slotName}`;
  const mediaHtml = item
    ? itemArtHtml(item)
    : `<span class="profile-slot-fallback">${itemIconForSlotType("")}</span>`;

  const enchantOverlay = item ? itemEnchantOverlayHtml(item, "slot") : "";
  return `
    <button type="button" class="profile-slot-card profile-slot-card--mini ${item ? rarity : "empty"}" title="${escapeHtml(titleText)}" aria-label="${escapeHtml(slotName)}" onclick="WaifuApp.openProfileSlot(${slot})">
      <div class="profile-slot-media">
        ${mediaHtml}
        ${enchantOverlay}
        ${item ? `<div class="profile-slot-mini-level profile-slot-mini-level--overlay">Ур. ${lvl}</div>` : ""}
      </div>
    </button>
  `;
}

let paperdollMenuOutsideBound = false;

function closePaperdollMenuOnOutside(ev) {
  const menu = document.getElementById("profile-paperdoll-menu");
  if (!menu || menu.style.display === "none") return;
  if (ev.target.closest?.(".profile-paperdoll-menu-btn") || ev.target.closest?.(".profile-paperdoll-menu")) {
    return;
  }
  menu.style.display = "none";
}

function togglePaperdollMenu(ev) {
  if (ev) ev.stopPropagation();
  const menu = document.getElementById("profile-paperdoll-menu");
  if (!menu) return;
  const willOpen = menu.style.display === "none" || !menu.style.display;
  menu.style.display = willOpen ? "block" : "none";
  if (willOpen && !paperdollMenuOutsideBound) {
    paperdollMenuOutsideBound = true;
    document.addEventListener("click", closePaperdollMenuOnOutside, true);
  }
}

function paperdollGenerationsRemaining(waifu) {
  const n = waifu?.paperdoll_generations_remaining;
  if (n != null && !Number.isNaN(Number(n))) return Number(n);
  const paperdollUrl = String(waifu?.paperdoll_url || "").trim();
  return paperdollUrl ? 0 : 1;
}

function renderProfilePaperDoll(waifu) {
  const paperdollUrl = resolveImageUrl(String(waifu?.paperdoll_url || "").trim());
  const portraitUrl = resolveImageUrl(
    String(
      waifu?.portrait_url || waifu?.image_url || waifu?.sprite_url || waifu?.avatar_url || ""
    ).trim()
  );
  const hasPortrait = Boolean(portraitUrl);
  const admin = isAdminUser();
  const gensLeft = paperdollGenerationsRemaining(waifu);
  const remaining = admin ? "безлимит" : String(gensLeft);
  const canGenerate = hasPortrait && (admin || gensLeft > 0);
  const name = escapeHtml(String(waifu?.name || "Основная вайфу"));
  const meta = `${escapeHtml(className(waifu?.class ?? waifu?.class_))} · ${escapeHtml(raceName(waifu?.race))}`;

  let bodyInner = "";
  let bodyClass = "profile-paperdoll-body profile-paperdoll-body--stage";
  if (paperdollUrl) {
    bodyInner = `<img class="profile-paperdoll-img" src="${escapeHtml(paperdollUrl)}" alt="${name}" />`;
  } else {
    bodyInner = escapeHtml(waifuPortraitEmoji(waifu) || "👤");
  }

  const menuBtn = `<button type="button" class="profile-paperdoll-menu-btn" data-tutorial="profile-paperdoll-menu" title="Действия с образом" aria-label="Меню образа" onclick="event.stopPropagation();WaifuApp.togglePaperdollMenu(event)">⋯</button>`;
  const menuBlock = `
    <div id="profile-paperdoll-menu" class="profile-paperdoll-menu" style="display:none" role="menu">
      <button type="button" class="profile-paperdoll-menu-item" data-tutorial="profile-paperdoll-generate" role="menuitem"${canGenerate ? "" : " disabled"}
        onclick="event.stopPropagation();WaifuApp.generateMainWaifuPaperdoll()">
        <span class="profile-paperdoll-menu-title">Сгенерировать изображение</span>
        <span class="profile-paperdoll-menu-meta">Осталось генераций: ${escapeHtml(remaining)}</span>
      </button>
    </div>`;

  return `
    <div class="profile-paperdoll">
      <div class="${bodyClass}">${bodyInner}${menuBtn}${menuBlock}</div>
      <div class="profile-paperdoll-caption">
        <strong>${name}</strong>
        <span class="muted tiny">${meta}</span>
      </div>
    </div>
  `;
}

async function generateMainWaifuPaperdoll() {
  const waifu = profileState.currentProfile?.main_waifu;
  if (!waifu) {
    showToast("Нет основной вайфу", "error");
    return;
  }
  const portraitUrl = String(
    waifu?.portrait_url || waifu?.image_url || waifu?.sprite_url || waifu?.avatar_url || ""
  ).trim();
  if (!portraitUrl) {
    showToast("Сначала нужен портрет вайфу", "error");
    return;
  }
  const admin = isAdminUser();
  if (!admin && paperdollGenerationsRemaining(waifu) <= 0) {
    showToast("Генерация образа уже использована", "error");
    return;
  }
  const menu = document.getElementById("profile-paperdoll-menu");
  if (menu) menu.style.display = "none";
  setItemArtGenBusy(true);
  try {
    const path = admin
      ? "/profile/main-waifu/paperdoll/regenerate"
      : "/profile/main-waifu/paperdoll";
    const payload = await apiFetch(path, { method: "POST" });
    const url = String(payload?.paperdoll_url || "").trim();
    if (url && profileState.currentProfile?.main_waifu) {
      const mw = profileState.currentProfile.main_waifu;
      mw.paperdoll_url = url;
      if (!admin) {
        mw.paperdoll_generations_remaining = Math.max(0, paperdollGenerationsRemaining(mw) - 1);
      }
    }
    renderProfileEquipment();
    showToast("Образ с экипировкой сохранён");
    try {
      if (window.WaifuApp?.Tutorial?.notify) {
        window.WaifuApp.Tutorial.notify("paperdoll:generated", { paperdoll_url: url || "" });
      }
    } catch (e) {
      /* ignore */
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const msg =
      detail === "portrait_required_for_paperdoll"
        ? "Сначала нужен портрет вайфу"
        : detail === "paperdoll_already_generated"
          ? "Генерация образа уже использована"
          : detail === "paperdoll_generation_failed"
            ? "Не удалось сгенерировать образ"
            : detail || "Ошибка генерации";
    showToast(msg, "error");
  } finally {
    setItemArtGenBusy(false);
  }
}

async function adminGenerateMainWaifuPaperdoll() {
  return generateMainWaifuPaperdoll();
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
      const iconHtml = itemArtHtml(item);
      const upgrade = isProfileUpgradeItem(item);
      const locked = item?.can_equip === false;
      const enchantOverlay = itemEnchantOverlayHtml(item, "bag");
      cells.push(`
        <button type="button" class="item-card profile-inv-item ${rarity} ${locked ? "empty" : ""}" title="${name}" onclick="WaifuApp.openItemById(${Number(
          item?.id || 0
        )})">
          <div class="item-icon">${iconHtml}${enchantOverlay}</div>
          ${upgrade ? `<div class="upgrade-arrow" title="Улучшение относительно экипировки">▲</div>` : ""}
          <div class="item-level">Ур. ${item?.level ?? "?"}</div>
        </button>
      `);
    });
    for (let i = pageItems.length; i < pageSize; i += 1) {
      cells.push(
        `<div class="item-card profile-inv-item profile-inv-placeholder empty" aria-hidden="true"><div class="item-icon">—</div></div>`
      );
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

function renderChatRewardsStatus(data) {
  const bag = document.getElementById("chat-reward-bag-btn");
  if (!bag || !data) {
    if (bag) bag.hidden = true;
    return;
  }

  const claimable = Boolean(data.claimable);
  bag.hidden = !claimable;
  if (!claimable) return;

  const chests = Number(data.wallet?.pending_chests || 0);
  bag.classList.toggle("chat-reward-bag-btn--chest", chests > 0);
  bag.classList.toggle("chat-reward-bag-btn--gold", chests <= 0);
  bag.title = "Награды за чат · авто-начисление в 00:00 МСК · нажмите, чтобы забрать досрочно";

  if (!bag.dataset.bound) {
    bag.dataset.bound = "1";
    bag.addEventListener("click", (e) => {
      e.stopPropagation();
      claimChatRewards().catch(console.error);
    });
  }
}

async function loadChatRewardsStatus() {
  try {
    const data = await apiFetch("/chat-rewards/status");
    renderChatRewardsStatus(data);
    return data;
  } catch (err) {
    console.warn("chat rewards status failed", err);
    return null;
  }
}

function closeChatRewardClaimModal() {
  const m = document.getElementById("chat-reward-claim-modal");
  if (m) m.hidden = true;
}

function showChatRewardClaimModal(payload) {
  const m = document.getElementById("chat-reward-claim-modal");
  const body = document.getElementById("chat-reward-claim-body");
  const dialog = document.getElementById("chat-reward-claim-dialog");
  const sub = document.getElementById("chat-reward-claim-sub");
  if (!m || !body) return;

  const chests = Number(payload?.chests || 0);
  if (dialog) {
    dialog.classList.toggle("chat-reward-claim-dialog--chest", chests > 0);
  }
  if (sub) {
    sub.hidden = chests > 0;
  }

  const lines = [];
  if (payload.gold > 0) lines.push(`🪙 Золото: +${payload.gold}`);
  if (payload.exp > 0) lines.push(`✨ Опыт ОВ: +${payload.exp}`);
  if (chests > 0) lines.push(`📦 Сундуков: ${chests}`);
  if (payload.level_up) {
    lines.push(`⭐ Уровень: ${payload.level_before} → ${payload.level_after}`);
  }
  const items = Array.isArray(payload.items) ? payload.items : [];
  items.forEach((it) => {
    if (it?.name) lines.push(`🎁 ${it.name}`);
  });
  if (!lines.length) lines.push("Нечего забирать.");
  body.innerHTML = lines.map((l) => `<p class="chat-reward-claim-line">${l}</p>`).join("");
  m.hidden = false;
}

async function claimChatRewards() {
  const bag = document.getElementById("chat-reward-bag-btn");
  if (bag?.classList.contains("chat-reward-bag-btn--claiming")) return;
  if (bag) bag.classList.add("chat-reward-bag-btn--claiming");
  try {
    const payload = await apiFetch("/chat-rewards/claim", { method: "POST" });
    showChatRewardClaimModal(payload);
    await loadChatRewardsStatus();
    const profile = await loadProfile().catch(() => null);
    if (profile) await populateProfile(profile);
  } catch (err) {
    console.error("claim chat rewards failed", err);
    alert("Не удалось забрать награды. Попробуйте позже.");
  } finally {
    if (bag) bag.classList.remove("chat-reward-bag-btn--claiming");
    await loadChatRewardsStatus();
  }
}

async function ensureProfileEquipmentLoaded() {
  if (profileState.equipmentLoaded || profileState.equipmentLoading) return;
  profileState.equipmentLoading = true;
  try {
    const eq = await apiFetch(`/waifu/equipment`);
    const equipped = Array.isArray(eq?.equipped) ? eq.equipped : [];
    const inventory = Array.isArray(eq?.inventory) ? eq.inventory : [];
    profileState.inventory = inventory;
    profileState.equippedBySlot = {};
    equipped.forEach((it) => {
      if (it?.equipment_slot != null) profileState.equippedBySlot[Number(it.equipment_slot)] = it;
    });
    profileState.inventoryPage = 1;
    profileState.equipmentLoaded = true;
    renderProfileEquipment();
    renderProfileInventory();
  } finally {
    profileState.equipmentLoading = false;
  }
}

async function reloadProfileEquipment() {
  profileState.equipmentLoaded = false;
  await ensureProfileEquipmentLoaded();
}

async function populateProfile(profile) {
  let p = profile;
  if (!isProfilePage()) {
    if (!p) p = await loadProfile({ lite: true });
  } else if (!p) {
    p = await loadProfile({ lite: false });
  }
  const w = p?.main_waifu;
  const mainEl = document.querySelector("main.profile-layout");
  const missEl = document.getElementById("profile-missing-waifu");
  const hasMw = Boolean(w && (w.id != null || w.level != null));

  if (!hasMw) {
    mainEl?.classList.add("profile-layout--no-mw");
    if (missEl) missEl.hidden = false;
    return;
  }

  mainEl?.classList.remove("profile-layout--no-mw");
  if (missEl) missEl.hidden = true;

  profileState.currentProfile = p;
  profileState.currentDetails = p?.main_waifu_details || null;
  profileState.viewMode = readProfileInventoryMode();

  setText("profile-name", w.name || "—");
  setText("profile-level", formatLevelWithPerfection(w.level, p?.perfection_level));

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

  renderProfilePortrait(w, p);
  renderProfileHeroBars(w, profileState.currentDetails, p);
  renderStatsStrip("profile-stats-strip", w);
  renderStatsBreakdown("profile-stats-breakdown", w, profileState.currentDetails);
  renderProfileIndicators(w, profileState.currentDetails);
  renderProfilePerfectionSummary(p);
  switchProfileInfoTab(profileState.infoTab);

  const invTabActive = document.getElementById("tab-inventory")?.classList.contains("active");
  if (invTabActive) {
    await ensureProfileEquipmentLoaded();
  } else {
    const gear = document.getElementById("profile-gear");
    const inv = document.getElementById("profile-inventory");
    if (gear && !profileState.equipmentLoaded) {
      gear.classList.add("placeholder");
      gear.textContent = "Откройте вкладку «Инвентарь», чтобы загрузить экипировку.";
    }
    if (inv && !profileState.equipmentLoaded) {
      inv.classList.add("placeholder");
      inv.textContent = "—";
    }
  }

  const scheduleChatRewards = () => {
    loadChatRewardsStatus().catch(() => null);
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(scheduleChatRewards, { timeout: 2500 });
  } else {
    setTimeout(scheduleChatRewards, 0);
  }

  try {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    const info = params.get("info");
    if (tab) switchProfileTab(tab);
    if (info) {
      if (tab !== "info") switchProfileTab("info");
      switchProfileInfoTab(info);
    }
  } catch {
    // ignore
  }
}

const SLOT_MAIN_STAT_KEYS = new Set([
  "strength",
  "agility",
  "intelligence",
  "endurance",
  "charm",
  "luck",
]);

function mainStatSum(item) {
  if (!item) return 0;
  let sum = 0;
  const bs = String(item.base_stat || "").trim().toLowerCase();
  if (SLOT_MAIN_STAT_KEYS.has(bs)) sum += safeNumber(item.base_stat_value, 0);
  (item.affixes || []).forEach((a) => {
    const sk = String(a?.stat || "").trim().toLowerCase();
    if (SLOT_MAIN_STAT_KEYS.has(sk)) sum += safeNumber(a?.value, 0);
  });
  return sum;
}

function averageWeaponDamageForCompare(item) {
  if (!item) return null;
  const a =
    item.damage_min_effective != null
      ? Number(item.damage_min_effective)
      : item.damage_min != null
        ? Number(item.damage_min)
        : null;
  const b =
    item.damage_max_effective != null
      ? Number(item.damage_max_effective)
      : item.damage_max != null
        ? Number(item.damage_max)
        : null;
  if (a == null && b == null) return null;
  if (a != null && b != null) return (a + b) / 2;
  return a ?? b;
}

function slotCompareChip(label, delta, opts = {}) {
  const isFloat = Boolean(opts.isFloat);
  const isPercent = Boolean(opts.isPercent);
  if (!Number.isFinite(delta) || delta === 0) return "";
  const up = delta > 0;
  const cls = up ? "slot-compare-chip slot-compare-chip--up" : "slot-compare-chip slot-compare-chip--down";
  const abs = Math.abs(delta);
  let numStr;
  if (isPercent) numStr = `${abs.toFixed(1)}%`;
  else if (isFloat) numStr = abs >= 10 ? abs.toFixed(0) : abs.toFixed(1);
  else numStr = String(Math.round(abs));
  const arrow = up ? "▲" : "▼";
  const sign = up ? "+" : "−";
  return `<span class="${cls}">${arrow}${sign}${numStr} ${escapeHtml(label)}</span>`;
}

function buildSlotReplaceCompareHtml(candidate, equipped) {
  if (!candidate) return "";
  if (!equipped) {
    return `<span class="slot-replace-compare muted tiny">Слот пуст — предмет будет надет впервые.</span>`;
  }

  const chips = [];
  const bc = candidate.base_stat ? String(candidate.base_stat) : "";
  const be = equipped.base_stat ? String(equipped.base_stat) : "";
  const vc = safeNumber(candidate.base_stat_value, 0);
  const ve = safeNumber(equipped.base_stat_value, 0);
  if (bc && be && bc === be) {
    const d = vc - ve;
    if (d !== 0) chips.push(slotCompareChip(statMeta(bc).short, d));
  } else if ((bc || be) && bc !== be) {
    if (be && ve !== 0) {
      chips.push(
        `<span class="slot-compare-chip slot-compare-chip--down">▼${escapeHtml(formatBonusValue(be, ve))} ${escapeHtml(statMeta(be).short)}</span>`
      );
    }
    if (bc && vc !== 0) {
      chips.push(
        `<span class="slot-compare-chip slot-compare-chip--up">▲${escapeHtml(formatBonusValue(bc, vc))} ${escapeHtml(statMeta(bc).short)}</span>`
      );
    }
  }

  const avgC = averageWeaponDamageForCompare(candidate);
  const avgE = averageWeaponDamageForCompare(equipped);
  if (avgC != null && avgE != null) {
    const d = avgC - avgE;
    if (Math.abs(d) >= 0.05) chips.push(slotCompareChip("Урон", d, { isFloat: true }));
  }

  const spC = candidate.attack_speed != null ? Number(candidate.attack_speed) : null;
  const spE = equipped.attack_speed != null ? Number(equipped.attack_speed) : null;
  if (spC != null && spE != null) {
    const d = spC - spE;
    if (Math.abs(d) >= 0.01) chips.push(slotCompareChip("Скор. атк.", d, { isFloat: true }));
  }

  const arC = safeNumber(candidate.armor_effective ?? candidate.armor_base, 0);
  const arE = safeNumber(equipped.armor_effective ?? equipped.armor_base, 0);
  if (arC > 0 || arE > 0) {
    const d = arC - arE;
    if (d !== 0) chips.push(slotCompareChip("Броня", d));
  }

  const stC = String(candidate.secondary_bonus_type || "").trim();
  const stE = String(equipped.secondary_bonus_type || "").trim();
  const svC = Number(candidate.secondary_bonus_effective ?? candidate.secondary_bonus_value ?? 0);
  const svE = Number(equipped.secondary_bonus_effective ?? equipped.secondary_bonus_value ?? 0);
  if (stC && stE && stC === stE) {
    const d = (svC - svE) * 100;
    if (Math.abs(d) >= 0.05) chips.push(slotCompareChip(SECONDARY_LABELS[stC] || stC, d, { isPercent: true }));
  }

  if (!chips.length) {
    return `<span class="slot-replace-compare muted tiny">По основным параметрам без заметных отличий</span>`;
  }
  return `<span class="slot-replace-compare">${chips.join(" ")}</span>`;
}

function renderSlotPickerList() {
  const body = document.getElementById("slot-modal-body");
  const slot = profileState.selectedSlot;
  if (!body || slot == null) return;

  const items = Array.isArray(profileState.slotPickerItems) ? profileState.slotPickerItems.slice() : [];
  const equipped = profileState.slotPickerEquipped;

  if (!items.length) {
    body.innerHTML = `<div class="placeholder">Нет подходящих предметов для этого слота.</div>`;
    return;
  }

  const dir = profileState.slotSortDir === "asc" ? 1 : -1;
  const sortKey = profileState.slotSort;
  items.sort((a, b) => {
    let va = 0;
    let vb = 0;
    if (sortKey === "level") {
      va = safeNumber(a?.level, 0);
      vb = safeNumber(b?.level, 0);
    } else if (sortKey === "damage") {
      va = averageWeaponDamageForCompare(a) ?? 0;
      vb = averageWeaponDamageForCompare(b) ?? 0;
      if (equipped) {
        const base = averageWeaponDamageForCompare(equipped) ?? 0;
        va -= base;
        vb -= base;
      }
    } else if (sortKey === "stats") {
      va = mainStatSum(a);
      vb = mainStatSum(b);
      if (equipped) {
        const base = mainStatSum(equipped);
        va -= base;
        vb -= base;
      }
    }
    if (va !== vb) return (va - vb) * dir;
    return String(a?.display_name || a?.name || "").localeCompare(
      String(b?.display_name || b?.name || ""),
      "ru"
    );
  });

  const sortSelect = document.getElementById("slot-sort-select");
  if (sortSelect) sortSelect.value = profileState.slotSort;
  const dirBtn = document.getElementById("slot-sort-direction");
  if (dirBtn) dirBtn.textContent = profileState.slotSortDir === "asc" ? "▲" : "▼";

  body.innerHTML = `<div class="slot-replace-list">${items
    .map((item) => {
      const canEquip = item?.can_equip !== false;
      const errs = Array.isArray(item?.requirement_errors) ? item.requirement_errors : [];
      const name = escapeHtml(String(item?.display_name || item?.name || "Предмет"));
      const rc = rarityClass(item?.rarity);
      const iid = Number(item?.id || 0);
      const compareHtml = buildSlotReplaceCompareHtml(item, equipped);
      const art = itemArtHtml(item);
      const meta = `Ур. ${item?.level ?? "—"} · ${escapeHtml(slotTypeLabel(item?.slot_type))} · T${item?.tier ?? "—"}`;
      const disabledAttr = canEquip ? "" : " disabled";
      const rowCls = `slot-replace-row ${rc}${canEquip ? "" : " slot-replace-row--disabled"}`;
      return `
        <button type="button" class="${rowCls}"${disabledAttr} onclick="WaifuApp.equipItemToProfileSlot(${iid}, ${Number(slot)})">
          <span class="slot-replace-portrait" aria-hidden="true">${art}</span>
          <span class="slot-replace-main">
            <span class="slot-replace-name">${name}</span>
            <span class="slot-replace-meta muted tiny">${meta}</span>
            ${compareHtml}
            ${errs.length ? `<span class="slot-replace-err muted tiny">${errs.map((err) => escapeHtml(String(err))).join("<br/>")}</span>` : ""}
          </span>
        </button>
      `;
    })
    .join("")}</div>`;
}

function setSlotSort(value) {
  profileState.slotSort = ["level", "damage", "stats"].includes(value) ? value : "level";
  renderSlotPickerList();
}

function toggleSlotSortDir() {
  profileState.slotSortDir = profileState.slotSortDir === "asc" ? "desc" : "asc";
  renderSlotPickerList();
}

async function openSlotModal(slot) {
  profileState.selectedSlot = slot;
  const modal = document.getElementById("slot-modal");
  const body = document.getElementById("slot-modal-body");
  if (!modal || !body) return;

  setText("slot-modal-title", `Замена: ${EQUIPMENT_SLOT_NAMES[slot] || `Слот ${slot}`}`);
  setText("slot-modal-subtitle", "Нажмите на предмет, чтобы экипировать его в этот слот.");
  body.innerHTML = `<div class="placeholder">Загрузка...</div>`;
  modal.style.display = "grid";
  const sortWrap = document.getElementById("slot-sort-wrap");
  if (sortWrap) sortWrap.style.display = "";

  const data = await apiFetch(`/waifu/equipment/available?slot=${slot}`);
  const items = Array.isArray(data?.items) ? data.items : [];
  profileState.slotPickerItems = items;
  profileState.slotPickerEquipped = getProfileEquippedItem(slot);

  if (!items.length) {
    body.innerHTML = `<div class="placeholder">Нет подходящих предметов для этого слота.</div>`;
    return;
  }

  renderSlotPickerList();
}

async function equipItemToProfileSlot(itemId, slot) {
  await apiFetch(`/waifu/equipment/equip?inventory_item_id=${itemId}&slot=${slot}`, { method: "POST" });
  closeSlotModal();
  closeItemModal();
  profileState.equipmentLoaded = false;
  await bootstrapPage("profile", populateProfile);
  switchProfileTab("inventory");
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

/** Требования v2: пилюли «Ур.» / «ВЫН» и т.д.; fail — красная рамка. */
function requirementPillOk(item, waifu, key, fallbackHave, need) {
  const rs = item?.requirements_status;
  if (rs && rs[key] && typeof rs[key] === "object" && rs[key].ok != null) {
    return Boolean(rs[key].ok);
  }
  const hasWaifu = Boolean(waifu && (waifu.level != null || waifu.id != null));
  return !hasWaifu || safeNumber(fallbackHave, 0) >= safeNumber(need, 0);
}

function buildItemModalRequirementsPillsHtml(item, waifu) {
  const req = item?.requirements && typeof item.requirements === "object" ? item.requirements : {};
  const w = waifu || {};
  const hasWaifu = Boolean(w && (w.level != null || w.id != null));
  const entries = [];

  const pushPill = (lbl, val, ok) => {
    entries.push({ lbl, val, ok });
  };

  if (Boolean(item?.is_broken)) {
    pushPill("Сост.", "Сломан", false);
  }

  const lvlNeed = safeNumber(req.level, 0);
  if (lvlNeed > 0) {
    const have = safeNumber(w.level, 0);
    const ok = requirementPillOk(item, w, "level", have, lvlNeed);
    pushPill("Ур.", String(lvlNeed), ok);
  }

  const statBits = [
    ["strength", "СИЛ", "strength"],
    ["agility", "ЛОВ", "agility"],
    ["intelligence", "ИНТ", "intelligence"],
    ["endurance", "ВЫН", "endurance"],
    ["charm", "ОБА", "charm"],
    ["luck", "УДЧ", "luck"],
  ];
  statBits.forEach(([rk, abbrev, wk]) => {
    const need = safeNumber(req[rk], 0);
    if (need <= 0) return;
    const have = profileStatValue(w, wk);
    const ok = requirementPillOk(item, w, rk, have, need);
    pushPill(abbrev, String(need), ok);
  });

  if (req.waifu_race != null && req.waifu_race !== "") {
    const need = Number(req.waifu_race);
    const have = w.race != null ? Number(w.race) : NaN;
    const ok = requirementPillOk(item, w, "waifu_race", have, need);
    pushPill("Раса", raceName(need), ok);
  }
  if (req.waifu_class != null && req.waifu_class !== "") {
    const need = Number(req.waifu_class);
    const wc = w.class != null ? w.class : w.class_;
    const have = wc != null ? Number(wc) : NaN;
    const ok = requirementPillOk(item, w, "waifu_class", have, need);
    pushPill("Класс", className(need), ok);
  }

  if (!entries.length) return "";

  return entries
    .map(
      (e) =>
        `<div class="item-modal-v2-rpil${e.ok ? "" : " item-modal-v2-rpil--fail"}"><span class="item-modal-v2-rpil-lbl">${escapeHtml(
          e.lbl
        )}</span><span class="item-modal-v2-rpil-val">${escapeHtml(e.val)}</span></div>`
    )
    .join("");
}

function openItemModal(item) {
  profileState.selectedItem = item;
  profileState.equipSlotChoice = null;
  closeItemSellConfirmOverlay();
  closeItemEquipRingOverlay();
  const modal = document.getElementById("item-modal");
  const body = document.getElementById("item-modal-body");
  if (!modal || !body) return;

  const isEquipped = item?.equipment_slot != null;
  const possibleSlots = !isEquipped && item?.slot_type ? SLOT_TYPE_TO_SLOTS[item.slot_type] || [] : [];
  const canEquip = !isEquipped && item?.can_equip !== false && possibleSlots.length > 0;
  const hasInvId = item?.id != null;
  const canSmith = Boolean(hasInvId && !item?.is_broken);

  const nameEl = document.getElementById("item-modal-name");
  if (nameEl) {
    nameEl.innerHTML = composeItemTitlePlain(item) || "—";
    const en = safeNumber(item?.enchant_level, 0);
    const br = Boolean(item?.is_broken);
    nameEl.classList.toggle("item-modal-v2-title--enchant-high", en > 7 && !br);
  }

  const subEl = document.getElementById("item-modal-subline");
  if (subEl) {
    subEl.textContent = buildItemModalMetaLine(item);
  }

  const rpill = document.getElementById("item-modal-rpill");
  if (rpill) {
    rpill.textContent = rarityLabel(item?.rarity);
    rpill.className = `item-modal-v2-rpill ${rarityPillModifierClass(item?.rarity)}`.trim();
  }

  const art = document.getElementById("item-modal-art");
  if (art) art.innerHTML = itemArtHtml(item, { adminGen: true });
  const artFrame = document.getElementById("item-modal-art-frame");
  if (artFrame) {
    artFrame.querySelectorAll(".item-enchant-overlay").forEach((el) => el.remove());
    const overlayHtml = itemEnchantOverlayHtml(item, "modal");
    if (overlayHtml) artFrame.insertAdjacentHTML("beforeend", overlayHtml);
  }

  const enchRow = document.getElementById("item-modal-ench");
  if (enchRow) enchRow.innerHTML = buildItemModalEnchantRowHtml(item);

  const content = document.getElementById("item-modal-content");
  if (content) {
    ["rarity-common", "rarity-uncommon", "rarity-rare", "rarity-epic", "rarity-legendary"].forEach((cls) => {
      content.classList.remove(cls);
    });
    content.classList.add(rarityClass(item?.rarity));
  }

  const combinedBonusesHtml = renderCombinedBonusesHtml(item);
  const weaponStatsHtml = renderWeaponStatsHtml(item);
  const upgrade = !isEquipped && isProfileUpgradeItem(item);
  const upHintEl = document.getElementById("item-modal-upgrade-hint");
  if (upHintEl) {
    if (upgrade) {
      upHintEl.textContent = "▲";
      upHintEl.style.display = "inline-flex";
      upHintEl.setAttribute("title", "Предмет выше уровня текущей экипировки");
      upHintEl.setAttribute("aria-label", "Предмет выше уровня текущей экипировки");
      upHintEl.removeAttribute("aria-hidden");
    } else {
      upHintEl.textContent = "";
      upHintEl.style.display = "none";
      upHintEl.removeAttribute("title");
      upHintEl.removeAttribute("aria-label");
      upHintEl.setAttribute("aria-hidden", "true");
    }
  }
  let charHtml = renderItemModalV2CharacteristicsHtml(item);
  if (!charHtml) {
    const statsInner = [weaponStatsHtml, combinedBonusesHtml].filter(Boolean).join("");
    charHtml = statsInner
      ? `<div class="item-mtg-stats-merged">${statsInner}</div>`
      : `<div class="muted tiny" style="padding:6px 0;">Нет характеристик для отображения.</div>`;
  }

  body.innerHTML = charHtml;

  const descEl = document.getElementById("item-modal-desc");
  const descText = String(item?.description || "").trim();
  if (descEl) {
    if (descText) {
      descEl.style.display = "";
      descEl.textContent = `"${descText}"`;
    } else {
      descEl.style.display = "none";
      descEl.innerHTML = "";
    }
  }

  const reqFoot = document.getElementById("item-modal-requirements");
  const reqSec = document.getElementById("item-modal-req-section");
  const pillsHtml = buildItemModalRequirementsPillsHtml(item, profileState.currentProfile?.main_waifu || null);
  if (reqFoot) reqFoot.innerHTML = pillsHtml;
  if (reqSec) reqSec.style.display = pillsHtml ? "" : "none";

  const sellBtn = document.getElementById("item-modal-sell");
  const dismantleBtn = document.getElementById("item-modal-dismantle");
  const enchBtn = document.getElementById("item-modal-enchant");
  const unequipBtn = document.getElementById("item-modal-unequip");
  const replaceBtn = document.getElementById("item-modal-replace");
  const equipBtn = document.getElementById("item-modal-equip");
  const actionsRow = document.getElementById("item-modal-actions-row");

  if (sellBtn) sellBtn.style.display = isEquipped ? "none" : "";
  if (dismantleBtn) dismantleBtn.style.display = isEquipped ? "none" : "";
  if (unequipBtn) unequipBtn.style.display = isEquipped ? "" : "none";
  if (replaceBtn) replaceBtn.style.display = isEquipped ? "" : "none";
  if (equipBtn) {
    equipBtn.style.display = canEquip ? "" : "none";
    equipBtn.textContent = "Надеть";
  }
  if (enchBtn) {
    const showEnch = canSmith;
    enchBtn.style.display = showEnch ? "" : "none";
    enchBtn.disabled = false;
  }

  let visibleFooter = 0;
  if (sellBtn && sellBtn.style.display !== "none") visibleFooter += 1;
  if (dismantleBtn && dismantleBtn.style.display !== "none") visibleFooter += 1;
  if (enchBtn && enchBtn.style.display !== "none") visibleFooter += 1;
  if (unequipBtn && unequipBtn.style.display !== "none") visibleFooter += 1;
  if (replaceBtn && replaceBtn.style.display !== "none") visibleFooter += 1;
  if (equipBtn && equipBtn.style.display !== "none") visibleFooter += 1;
  if (actionsRow) {
    actionsRow.setAttribute("data-cols", String(Math.max(1, Math.min(visibleFooter, 4))));
  }

  const atticEl = document.querySelector("header.attic, .attic");
  const atticH = atticEl ? Math.ceil(atticEl.getBoundingClientRect().height) : 58;
  modal.style.setProperty("--attic-bar-height", `${atticH}px`);

  modal.classList.add("item-modal-v2--open");
  modal.style.display = "grid";
}

async function refreshAfterInventoryModalAction() {
  const path = typeof window !== "undefined" ? window.location.pathname || "" : "";
  if (/dungeons\.html$/.test(path)) {
    const p = await loadProfile();
    await populateDungeonsPage(p);
    return;
  }
  if (/shop\.html$/.test(path)) {
    const p = await loadProfile();
    const act = shopState.act || p?.act || 1;
    await loadShop(act).catch(console.error);
    if (shopState.activeTab === "sell") {
      await loadSellInventory().catch(console.error);
    }
    return;
  }
  profileState.equipmentLoaded = false;
  await bootstrapPage("profile", populateProfile);
}

async function confirmDismantleSelectedItem() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  try {
    await apiFetch(`/inventory/${item.id}/dismantle`, { method: "POST" });
    showToast("Предмет распылён", "success");
    closeItemDismantleConfirmOverlay();
    closeItemModal();
    await loadProfile().catch(() => null);
    if (typeof loadSellInventory === "function" && shopState.activeTab === "sell") {
      await loadSellInventory().catch(() => {});
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || e?.message || "Не удалось распылить", "error");
  }
}

async function confirmSellSelectedItem() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  const soldId = item.id;
  closeItemSellConfirmOverlay();
  await apiFetch(`/inventory/sell`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inventory_item_ids: [item.id] }),
  });
  closeItemModal();
  await refreshAfterInventoryModalAction();
  window.WaifuApp?.Tutorial?.notify?.("shop:sold", { inventory_item_id: soldId });
}

async function unequipItemFromModal() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  await apiFetch(`/waifu/equipment/unequip?inventory_item_id=${item.id}`, { method: "POST" });
  closeItemModal();
  await refreshAfterInventoryModalAction();
}

async function equipItemFromModal() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  const slots = SLOT_TYPE_TO_SLOTS[item.slot_type] || [];
  if (!slots.length) return;

  if (item.slot_type === "ring") {
    openItemEquipRingOverlay();
    return;
  }
  const chosen = defaultEquipSlotForItem(item) ?? slots[0];
  try {
    await apiFetch(`/waifu/equipment/equip?inventory_item_id=${item.id}&slot=${chosen}`, { method: "POST" });
  } catch (e) {
    const body = document.getElementById("item-modal-body");
    if (body) body.innerHTML += `<div class="muted" style="margin-top:10px;">Ошибка экипировки: ${escapeHtml(String(e?.message || e))}</div>`;
    return;
  }
  closeItemModal();
  await refreshAfterInventoryModalAction();
  window.WaifuApp?.Tutorial?.notify?.("equip:done", { inventory_item_id: item.id, slot: chosen });
}

async function confirmEquipToRingSlot(slot) {
  const item = profileState.selectedItem;
  if (!item?.id || item.slot_type !== "ring") return;
  const s = Number(slot);
  if (s !== 4 && s !== 5) return;
  try {
    await apiFetch(`/waifu/equipment/equip?inventory_item_id=${item.id}&slot=${s}`, { method: "POST" });
  } catch (e) {
    const body = document.getElementById("item-modal-body");
    if (body) body.innerHTML += `<div class="muted" style="margin-top:10px;">Ошибка экипировки: ${escapeHtml(String(e?.message || e))}</div>`;
    closeItemEquipRingOverlay();
    return;
  }
  window.WaifuApp?.Tutorial?.notify?.("equip:done", { inventory_item_id: item.id, slot: s });
  closeItemEquipRingOverlay();
  closeItemModal();
  await refreshAfterInventoryModalAction();
}

async function resetMainWaifu() {
  if (
    !confirm(
      "Полный сброс прогресса: золото, акт, инвентарь, найм, данжи, экспедиции, пассивы, гильдия и ОВ. Продолжить?"
    )
  ) {
    return;
  }
  await apiFetch(`/admin/player/reset-new-game`, { method: "POST" });
  window.location.href = "./waifu_generator.html";
}

/** Стартовый экран index.html: «Новая игра» / «Продолжить» по наличию ОВ. */
function initTitleScreen(profile) {
  const btn = document.getElementById("title-primary-btn");
  const authEl = document.getElementById("title-screen-auth");
  const modal = document.getElementById("title-info-modal");
  const infoBtn = document.getElementById("title-info-btn");
  const infoClose = document.getElementById("title-info-close");

  if (infoBtn && modal) {
    infoBtn.addEventListener("click", () => {
      modal.hidden = false;
    });
  }
  if (infoClose && modal) {
    infoClose.addEventListener("click", () => {
      modal.hidden = true;
    });
  }
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.hidden = true;
    });
  }

  if (!btn) return;

  if (!profile) {
    if (authEl) {
      authEl.style.display = "block";
      authEl.innerHTML = serverUnavailableNoticeHtml();
    }
    btn.textContent = "Повторить";
    btn.disabled = false;
    btn.onclick = () => window.location.reload();
    return;
  }

  if (profile.__authRequired) {
    if (authEl) {
      authEl.style.display = "block";
      authEl.innerHTML = webAppAuthNoticeHtml();
    }
    btn.textContent = "Вход недоступен";
    btn.disabled = true;
    btn.onclick = null;
    return;
  }

  if (authEl) authEl.style.display = "none";

  const w = profile?.main_waifu;
  if (w && (w.id != null || w.level != null)) {
    btn.textContent = "Продолжить";
    btn.disabled = false;
    btn.onclick = () => {
      window.location.href = "./profile.html";
    };
    return;
  }

  btn.textContent = "Новая игра";
  btn.disabled = false;
  btn.onclick = () => {
    window.location.href = "./waifu_generator.html";
  };
}

async function adminLevelUpWaifu() {
  try {
    const data = await apiFetch("/admin/waifu/levelup", { method: "POST" });
    await loadProfile();
    showToast(`Уровень повышен до ${data.new_level}`);
  } catch (e) {
    showToast("Ошибка: " + (e?.message || e), "error");
  }
}

async function refreshProfileAfterAdminWaifuEdit() {
  closeProfileStatInfoModal();
  const p = await loadProfile().catch(() => null);
  if (p && window.location.pathname.endsWith("/profile.html")) {
    await populateProfile(p).catch(() => {});
  }
  return p;
}

async function adminAddMainWaifuStat(stat, ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  closeProfileStatInfoModal();
  const allowed = ["strength", "agility", "intelligence", "endurance", "charm", "luck"];
  if (!allowed.includes(stat)) return;
  try {
    await apiFetch(`/admin/waifu/add-stat?stat=${encodeURIComponent(stat)}&amount=100`, { method: "POST" });
    await refreshProfileAfterAdminWaifuEdit();
  } catch (e) {
    console.warn("adminAddMainWaifuStat failed:", e);
  }
}

async function adminAddStatPoints(ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  closeProfileStatInfoModal();
  try {
    await apiFetch("/admin/waifu/add-stat-points?amount=100", { method: "POST" });
    await refreshProfileAfterAdminWaifuEdit();
  } catch (e) {
    console.warn("adminAddStatPoints failed:", e);
  }
}

async function adminResetMainWaifuStatSpend() {
  if (!confirm("Сбросить потраченные ОХ? Статы вернутся к базе расы/класса.")) return;
  try {
    const data = await apiFetch("/admin/waifu/reset-stat-spend", { method: "POST" });
    await loadProfile();
    showToast(`Возвращено ${data.refunded} ОХ`);
  } catch (e) {
    showToast("Ошибка: " + (e?.message || e), "error");
  }
}

async function adminClearAllItems() {
  if (!confirm("Удалить ВСЕ предметы? (экипировка + инвентарь)")) return;
  try {
    await apiFetch("/admin/items/clear", { method: "POST" });
    await loadProfile();
    showToast("Все предметы удалены");
  } catch (e) {
    showToast("Ошибка: " + (e?.message || e), "error");
  }
}

const adminSpawnState = {
  catalog: null,
  filters: { search: "", tier: "all", itemKind: "all", slot: "all", baseGrade: "all" },
  affixFilters: { search: "", kind: "all", category: "all" },
  selectedTemplateId: null,
  rarity: 2,
  selectedAffixKeys: new Set(),
};

const adminSpawnArtFailCache = new Set();

function adminSpawnAffixKey(entry) {
  return `${entry.catalog_kind}:${entry.catalog_id}`;
}

/** Admin spawn grid: emoji placeholder with optional generate button. */
function adminSpawnArtPlaceholderHtml(fakeItem) {
  const emoji = `<span class="lib-art-emoji">${itemArtEmoji(fakeItem)}</span>`;
  const artKey = String(fakeItem?.art_key || "").trim();
  if (!isAdminUiEnabled() || !artKey) return emoji;
  const btn = itemArtGenerateBtnHtml(fakeItem);
  if (!btn) return emoji;
  return `<span class="item-art-admin-wrap item-art-admin-wrap--placeholder">${emoji}${btn}</span>`;
}

function adminSpawnOnArtError(img) {
  if (!img) return;
  const artKey = String(img.dataset?.artKey || "").trim();
  let urls = [];
  try {
    urls = JSON.parse(img.dataset?.fallbackUrls || "[]");
  } catch {
    urls = [];
  }
  let index = parseInt(img.dataset?.fallbackIndex || "0", 10) + 1;
  if (index < urls.length) {
    img.dataset.fallbackIndex = String(index);
    img.src = urls[index];
    return;
  }
  if (artKey) adminSpawnArtFailCache.add(artKey);
  const wrap = img.closest(".lib-card-art");
  if (wrap) {
    wrap.classList.add("silhouette");
    const card = wrap.closest(".lib-card");
    const cardName = card?.querySelector(".lib-card-name")?.textContent?.trim() || "";
    const fakeItem = {
      art_key: artKey,
      tier: parseInt(img.dataset?.artTier || "1", 10) || 1,
      slot_type: img.dataset?.slotType || "",
      weapon_type: img.dataset?.weaponType || "",
      name: cardName,
      display_name: cardName,
    };
    wrap.innerHTML = adminSpawnArtPlaceholderHtml(fakeItem);
  }
}

function adminSpawnResolveArtKey(entry) {
  if (adminSpawnResolveIsLegendary()) {
    const legKey = String(entry?.legendary_art_key || "").trim();
    if (legKey) return legKey;
    const base = String(entry?.art_key || "").trim();
    if (base) return `legendary/${base}`;
  }
  return String(entry?.art_key || "").trim();
}

function adminSpawnCardArtHtml(entry) {
  const artKey = adminSpawnResolveArtKey(entry);
  const itemName = adminSpawnDisplayName(entry) || String(entry?.name || "").trim();
  const fakeItem = {
    art_key: artKey,
    tier: entry?.tier,
    slot_type: entry?.slot_type,
    weapon_type: entry?.subtype,
    name: itemName,
    display_name: itemName,
  };
  if (!artKey) {
    return `<div class="lib-card-art silhouette"><span class="lib-art-emoji">${itemArtEmoji(fakeItem)}</span></div>`;
  }
  if (adminSpawnArtFailCache.has(artKey)) {
    return `<div class="lib-card-art silhouette">${adminSpawnArtPlaceholderHtml(fakeItem)}</div>`;
  }
  const startTier = Math.min(10, Math.max(1, Number(entry?.tier) || 1));
  const urls = [];
  for (let t = startTier; t >= 1; t -= 1) {
    urls.push(`${GAME_STATIC_BASE}/items/webp/${encodeArtKeyPath(artKey)}/t${t}.webp`);
  }
  const slotType = escapeHtml(String(entry?.slot_type || ""));
  const weaponType = escapeHtml(String(entry?.subtype || ""));
  const imgHtml = `<img src="${urls[0]}" alt="" data-art-key="${escapeHtml(artKey)}" data-art-tier="${startTier}" data-slot-type="${slotType}" data-weapon-type="${weaponType}" data-fallback-urls="${escapeHtml(JSON.stringify(urls))}" data-fallback-index="0" onerror="WaifuApp.adminSpawnOnArtError(this)" />`;
  const inner = isAdminUiEnabled() ? wrapItemImageWithAdminGen(fakeItem, imgHtml) : imgHtml;
  return `<div class="lib-card-art">${inner}</div>`;
}

function adminSpawnUpdateAffixBtn() {
  const btn = document.getElementById("admin-spawn-affix-open-btn");
  if (btn) btn.textContent = `Аффиксы (${adminSpawnState.selectedAffixKeys.size})`;
}

function adminSpawnSetFabEnabled(on) {
  const fab = document.getElementById("admin-spawn-submit-fab");
  if (fab) fab.disabled = !on;
}

function adminSpawnResolveBaseGrade(tpl) {
  const f = adminSpawnState.filters.baseGrade;
  if (f !== "all") return Math.max(0, Math.min(2, parseInt(f, 10) || 0));
  return Number(tpl?.base_grade) || 0;
}

function adminSpawnResolveIsLegendary() {
  return adminSpawnState.filters.itemKind === "legendary";
}

function adminSpawnResolveSubmitRarity() {
  if (adminSpawnResolveIsLegendary()) return 5;
  return Math.max(1, Math.min(4, Number(adminSpawnState.rarity) || 2));
}

function adminSpawnDisplayName(it) {
  if (!it) return "?";
  if (adminSpawnState.filters.itemKind === "legendary") {
    return String(it.legendary_name_ru || it.name || "?").trim() || "?";
  }
  return String(it.name || "?").trim() || "?";
}

function adminSpawnDisplaySubtitle(it) {
  if (!it || adminSpawnState.filters.itemKind !== "legendary") return "";
  const canon = String(it.name || "").trim();
  const leg = String(it.legendary_name_ru || "").trim();
  if (!canon || !leg || canon === leg) return "";
  return canon;
}

function adminSpawnSyncRarityControl() {
  const rarity = document.getElementById("admin-spawn-rarity");
  if (!rarity) return;
  const leg = adminSpawnResolveIsLegendary();
  rarity.disabled = leg;
  rarity.title = leg ? "Редкость фиксирована для легендарных предметов" : "";
}

function adminSpawnBindFilterHandlers() {
  const search = document.getElementById("admin-spawn-search");
  const tier = document.getElementById("admin-spawn-tier");
  const itemKind = document.getElementById("admin-spawn-item-kind");
  const slot = document.getElementById("admin-spawn-slot");
  const baseGrade = document.getElementById("admin-spawn-base-grade-filter");
  const rarity = document.getElementById("admin-spawn-rarity");
  if (search && !search.dataset.bound) {
    search.dataset.bound = "1";
    search.addEventListener("input", () => {
      adminSpawnState.filters.search = search.value.trim().toLowerCase();
      adminSpawnRenderGrid();
    });
  }
  if (tier && !tier.dataset.bound) {
    tier.dataset.bound = "1";
    tier.addEventListener("change", () => {
      adminSpawnState.filters.tier = tier.value;
      adminSpawnRenderGrid();
      adminSpawnRenderConfig();
    });
  }
  if (itemKind && !itemKind.dataset.bound) {
    itemKind.dataset.bound = "1";
    itemKind.addEventListener("change", () => {
      adminSpawnState.filters.itemKind = itemKind.value;
      adminSpawnSyncRarityControl();
      adminSpawnRenderGrid();
      adminSpawnRenderConfig();
    });
  }
  if (slot && !slot.dataset.bound) {
    slot.dataset.bound = "1";
    slot.addEventListener("change", () => {
      adminSpawnState.filters.slot = slot.value;
      adminSpawnRenderGrid();
    });
  }
  if (baseGrade && !baseGrade.dataset.bound) {
    baseGrade.dataset.bound = "1";
    baseGrade.addEventListener("change", () => {
      adminSpawnState.filters.baseGrade = baseGrade.value;
      adminSpawnRenderGrid();
    });
  }
  if (rarity && !rarity.dataset.bound) {
    rarity.dataset.bound = "1";
    rarity.addEventListener("change", () => {
      adminSpawnState.rarity = Math.max(1, Math.min(4, parseInt(rarity.value, 10) || 2));
      adminSpawnRenderConfig();
    });
  }
}

function adminSpawnBindAffixFilterHandlers() {
  const affSearch = document.getElementById("admin-spawn-affix-search");
  const affKind = document.getElementById("admin-spawn-affix-kind");
  const affCategory = document.getElementById("admin-spawn-affix-category");
  if (affSearch && !affSearch.dataset.bound) {
    affSearch.dataset.bound = "1";
    affSearch.addEventListener("input", () => {
      adminSpawnState.affixFilters.search = affSearch.value.trim().toLowerCase();
      adminSpawnRenderAffixList();
    });
  }
  if (affKind && !affKind.dataset.bound) {
    affKind.dataset.bound = "1";
    affKind.addEventListener("change", () => {
      adminSpawnState.affixFilters.kind = affKind.value;
      adminSpawnRenderAffixList();
    });
  }
  if (affCategory && !affCategory.dataset.bound) {
    affCategory.dataset.bound = "1";
    affCategory.addEventListener("change", () => {
      adminSpawnState.affixFilters.category = affCategory.value;
      adminSpawnRenderAffixList();
    });
  }
}

function adminSpawnRenderGrid() {
  const grid = document.getElementById("admin-spawn-items-grid");
  const cat = adminSpawnState.catalog;
  if (!grid || !cat) return;
  const f = adminSpawnState.filters;
  let items = cat.items || [];
  if (f.search) {
    items = items.filter((it) => String(it.name || "").toLowerCase().includes(f.search));
  }
  if (f.tier !== "all") {
    const t = Number(f.tier);
    items = items.filter((it) => Number(it.tier) === t);
  }
  if (f.itemKind === "legendary") {
    items = items.filter((it) => Boolean(it.has_curated_legendary) && Boolean(it.legendary_name_ru));
  }
  if (f.baseGrade !== "all") {
    const bg = Number(f.baseGrade);
    items = items.filter((it) => Number(it.base_grade) === bg);
  }
  if (f.slot !== "all") {
    items = items.filter((it) => String(it.slot_type || "") === f.slot);
  }
  const selId = adminSpawnState.selectedTemplateId;
  grid.innerHTML = items
    .map((it) => {
      const tid = Number(it.base_template_id);
      const tierCls = libraryTierClass(Math.max(1, Number(it.tier) || 1));
      const selected = tid === selId ? " selected admin-spawn-card" : " admin-spawn-card";
      const displayName = adminSpawnDisplayName(it);
      const subtitle = adminSpawnDisplaySubtitle(it);
      const legBadge =
        f.itemKind !== "legendary" && it.has_curated_legendary
          ? `<span class="admin-spawn-leg-badge">★</span>`
          : "";
      const subtitleHtml = subtitle
        ? `<div class="lib-card-sub muted tiny">${escapeHtml(subtitle)}</div>`
        : "";
      return `
        <div class="lib-card ${tierCls}${selected}" role="button" tabindex="0" data-template-id="${tid}"
          onclick="WaifuApp.adminSpawnSelectTemplate(${tid})">
          ${adminSpawnCardArtHtml(it)}
          <div class="lib-card-meta">
            <div class="lib-card-name">${escapeHtml(displayName)}</div>
            ${subtitleHtml}
            <div class="lib-card-tier">T${Number(it.tier) || "?"}${legBadge}</div>
          </div>
        </div>`;
    })
    .join("");
}

function adminSpawnFindTemplate(tid) {
  const items = adminSpawnState.catalog?.items || [];
  return items.find((it) => Number(it.base_template_id) === Number(tid)) || null;
}

function adminSpawnRenderConfig() {
  const box = document.getElementById("admin-spawn-config");
  const tid = adminSpawnState.selectedTemplateId;
  if (!box) return;
  if (!tid) {
    box.textContent = "Выберите шаблон.";
    adminSpawnSetFabEnabled(false);
    return;
  }
  const tpl = adminSpawnFindTemplate(tid);
  if (!tpl) {
    box.textContent = "Шаблон не найден.";
    adminSpawnSetFabEnabled(false);
    return;
  }
  adminSpawnSetFabEnabled(true);
  const displayName = adminSpawnDisplayName(tpl);
  const subtitle = adminSpawnDisplaySubtitle(tpl);
  const spawnLeg = adminSpawnResolveIsLegendary();
  const rar = adminSpawnResolveSubmitRarity();
  const rarLabels = ["", "обычная", "необычная", "редкая", "эпическая", "легендарная"];
  const subLine = subtitle ? ` <span class="muted">(${escapeHtml(subtitle)})</span>` : "";
  box.innerHTML = `<strong>${escapeHtml(displayName)}</strong>${subLine} · T${Number(tpl.tier) || "?"} · редкость: ${escapeHtml(rarLabels[rar] || String(rar))}${spawnLeg ? " · легендарный" : ""} · ilvl по аффиксам · аффиксов: ${adminSpawnState.selectedAffixKeys.size}`;
}

function adminSpawnRenderAffixList() {
  const list = document.getElementById("admin-spawn-affix-list");
  const cat = adminSpawnState.catalog;
  if (!list || !cat) return;
  const f = adminSpawnState.affixFilters;
  let rows = cat.affixes || [];
  if (f.search) {
    const q = f.search;
    rows = rows.filter(
      (a) =>
        String(a.name_ru || a.name || "")
          .toLowerCase()
          .includes(q) ||
        String(a.description_ru || "")
          .toLowerCase()
          .includes(q)
    );
  }
  if (f.kind !== "all") {
    if (f.kind === "prefix") {
      rows = rows.filter((a) => String(a.kind || "") === "prefix" || String(a.kind || "") === "affix");
    } else if (f.kind === "suffix") {
      rows = rows.filter((a) => String(a.kind || "") === "suffix");
    }
  }
  rows = rows.filter((a) => String(a.catalog_kind || "") !== "legacy_affix");
  if (f.category !== "all") {
    rows = rows.filter((a) => String(a.bonus_category || "other") === f.category);
  }
  if (!rows.length) {
    list.innerHTML = '<p class="muted tiny">Ничего не найдено.</p>';
    return;
  }
  list.innerHTML = rows
    .map((a) => {
      const key = adminSpawnAffixKey(a);
      const on = adminSpawnState.selectedAffixKeys.has(key);
      const kindLabel =
        String(a.kind || "") === "suffix"
          ? "Суффикс"
          : String(a.kind || "") === "prefix"
            ? "Префикс"
            : "Аффикс";
      const catLabel = a.bonus_category_label || "";
      const subParts = [kindLabel, catLabel, a.range_label ? String(a.range_label) : ""].filter(Boolean);
      const subLine = subParts.length ? escapeHtml(subParts.join(" · ")) : "";
      const descLine = a.description_ru
        ? `<span class="muted tiny admin-spawn-affix-desc">${escapeHtml(a.description_ru)}</span>`
        : "";
      return `
        <label class="admin-spawn-affix-row${on ? " selected" : ""}">
          <input type="checkbox" data-affix-key="${key}"${on ? " checked" : ""}
            onchange="WaifuApp.adminSpawnToggleAffixFromEl(this)" />
          <span class="admin-spawn-affix-meta">
            <span class="admin-spawn-affix-name">${escapeHtml(a.name_ru || a.name || "?")}</span>
            <span class="muted tiny">${subLine}</span>
            ${descLine}
          </span>
        </label>`;
    })
    .join("");
}

function adminSpawnSelectTemplate(templateId) {
  const tid = Number(templateId);
  const tpl = adminSpawnFindTemplate(tid);
  adminSpawnState.selectedTemplateId = tpl ? tid : null;
  adminSpawnRenderGrid();
  adminSpawnRenderConfig();
  adminSpawnRenderAffixList();
}

function adminSpawnToggleAffix(key, checked) {
  if (!key) return;
  if (checked) adminSpawnState.selectedAffixKeys.add(key);
  else adminSpawnState.selectedAffixKeys.delete(key);
  adminSpawnUpdateAffixBtn();
  adminSpawnRenderConfig();
}

function adminSpawnToggleAffixFromEl(el) {
  if (!el) return;
  adminSpawnToggleAffix(el.getAttribute("data-affix-key"), el.checked);
  const row = el.closest(".admin-spawn-affix-row");
  if (row) row.classList.toggle("selected", Boolean(el.checked));
}

async function adminOpenSpawnItemModal() {
  if (!isAdminUser() || !isAdminUiEnabled()) {
    showToast("Нужен админ-режим", "error");
    return;
  }
  const modal = document.getElementById("admin-spawn-item-modal");
  if (!modal) return;
  try {
    if (!adminSpawnState.catalog) {
      adminSpawnState.catalog = await apiFetch("/admin/spawn-item/catalog");
    }
  } catch (e) {
    showToast("Каталог: " + (e?.message || e), "error");
    return;
  }
  adminSpawnBindFilterHandlers();
  const tierSel = document.getElementById("admin-spawn-tier");
  const kindSel = document.getElementById("admin-spawn-item-kind");
  const raritySel = document.getElementById("admin-spawn-rarity");
  if (tierSel) tierSel.value = adminSpawnState.filters.tier;
  if (kindSel) kindSel.value = adminSpawnState.filters.itemKind;
  if (raritySel) raritySel.value = String(adminSpawnState.rarity);
  adminSpawnSyncRarityControl();
  adminSpawnUpdateAffixBtn();
  adminSpawnRenderGrid();
  adminSpawnRenderConfig();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
}

function adminOpenSpawnAffixModal() {
  const modal = document.getElementById("admin-spawn-affix-modal");
  if (!modal) return;
  if (!adminSpawnState.catalog) {
    showToast("Сначала откройте генератор предметов", "error");
    return;
  }
  adminSpawnBindAffixFilterHandlers();
  const affSearch = document.getElementById("admin-spawn-affix-search");
  const affKind = document.getElementById("admin-spawn-affix-kind");
  const affCategory = document.getElementById("admin-spawn-affix-category");
  if (affSearch) affSearch.value = adminSpawnState.affixFilters.search;
  if (affKind) affKind.value = adminSpawnState.affixFilters.kind;
  if (affCategory) affCategory.value = adminSpawnState.affixFilters.category;
  adminSpawnRenderAffixList();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
}

function adminCloseSpawnAffixModal() {
  const modal = document.getElementById("admin-spawn-affix-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function adminCloseSpawnItemModal() {
  const modal = document.getElementById("admin-spawn-item-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

async function adminSpawnSubmit() {
  const tid = adminSpawnState.selectedTemplateId;
  if (!tid) {
    showToast("Выберите шаблон", "error");
    return;
  }
  const affixes = [];
  for (const key of adminSpawnState.selectedAffixKeys) {
    const [kind, idStr] = String(key).split(":");
    const cid = parseInt(idStr, 10);
    if (!kind || !Number.isFinite(cid)) continue;
    affixes.push({ catalog_kind: kind, catalog_id: cid });
  }
  const tpl = adminSpawnFindTemplate(tid);
  if (!tpl) {
    showToast("Шаблон не найден", "error");
    return;
  }
  const fab = document.getElementById("admin-spawn-submit-fab");
  if (fab) fab.disabled = true;
  const isLegendary = adminSpawnResolveIsLegendary();
  const rarity = adminSpawnResolveSubmitRarity();
  if (isLegendary && !tpl.legendary_name_ru) {
    showToast("У шаблона нет легендарного имени", "error");
    if (fab) fab.disabled = false;
    return;
  }
  try {
    const payload = await apiFetch("/admin/inventory/spawn-item", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_template_id: tid,
        rarity,
        is_legendary: isLegendary,
        base_grade: adminSpawnResolveBaseGrade(tpl),
        affixes,
      }),
    });
    adminCloseSpawnItemModal();
    await reloadProfileEquipment();
    await loadProfile();
    let toastMsg = `Добавлено: ${payload.name || "предмет"} (${payload.affix_count || 0} афф.)`;
    const affReq = Number(payload.affixes_requested ?? 0);
    const affApp = Number(payload.affixes_applied ?? 0);
    if (affReq > 0 && affApp < affReq) {
      toastMsg += ` · применено ${affApp} из ${affReq}`;
    }
    showToast(toastMsg);
  } catch (e) {
    showToast("Ошибка: " + (e?.message || e), "error");
  } finally {
    adminSpawnSetFabEnabled(Boolean(adminSpawnState.selectedTemplateId));
  }
}

async function initWaifuGenerator(profile) {
  const mw = profile?.main_waifu;
  if (mw && (mw.id != null || mw.level != null)) {
    window.location.href = "./profile.html";
    return;
  }

  waifuGeneratorState.playerId = profile?.player_id != null ? profile.player_id : null;
  waifuGeneratorState.variants = [];
  waifuGeneratorState.selectedIdx = 0;
  waifuGeneratorState.generationsCount = 0;

  const nameInput = document.getElementById("waifu-name-input");
  const classSel = document.getElementById("waifu-class-select");
  const raceSel = document.getElementById("waifu-race-select");
  const statsBox = document.getElementById("waifu-stats");
  const nextBtn = document.getElementById("waifu-next-btn");

  if (!nameInput || !classSel || !raceSel || !statsBox || !nextBtn) return;

  classSel.innerHTML = WAIFU_CLASSES.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  raceSel.innerHTML = WAIFU_RACES.map((r) => `<option value="${r.id}">${r.name}</option>`).join("");

  const raceIds = new Set(WAIFU_RACES.map((r) => r.id));
  const classIds = new Set(WAIFU_CLASSES.map((c) => c.id));
  if (!raceIds.has(waifuGeneratorState.selectedRaceId)) waifuGeneratorState.selectedRaceId = WAIFU_RACES[0].id;
  if (!classIds.has(waifuGeneratorState.selectedClassId)) waifuGeneratorState.selectedClassId = WAIFU_CLASSES[0].id;
  waifuGenSyncHiddenSelects();
  waifuGenBuildRaceClassPickers();
  waifuGenBindModalsOnce();

  const recalc = () => {
    const name = nameInput.value.trim();
    const race = waifuGeneratorState.selectedRaceId;
    const cls = waifuGeneratorState.selectedClassId;
    const base = { strength: 10, agility: 10, intelligence: 10, endurance: 10, charm: 10, luck: 10 };
    const rb = WAIFU_RACE_BONUSES[race] || {};
    const cb = WAIFU_CLASS_BONUSES[cls] || {};
    const cur = { ...base };
    Object.entries(rb).forEach(([k, v]) => (cur[k] = (cur[k] || 0) + v));
    Object.entries(cb).forEach(([k, v]) => (cur[k] = (cur[k] || 0) + v));

    waifuGenRenderRadar(statsBox, cur);
    waifuGenSyncTriggers();
    waifuGenRenderPassiveList();

    nextBtn.disabled = !name;
  };

  window.__waifuGenRecalc = recalc;
  nameInput.addEventListener("input", recalc);
  recalc();

  const frame = document.getElementById("waifu-portrait-frame");
  if (frame && !frame.dataset.waifuCycleBound) {
    frame.dataset.waifuCycleBound = "1";
    frame.addEventListener("click", () => {
      if (waifuGeneratorState.variants.length < 2) return;
      const n = waifuGeneratorState.variants.length;
      waifuGeneratorState.selectedIdx = (waifuGeneratorState.selectedIdx + 1) % n;
      waifuGenRenderVariants();
      const v = waifuGeneratorState.variants[waifuGeneratorState.selectedIdx];
      if (v?.dataUrl) waifuGenApplyPortraitPreview(v.dataUrl);
    });
  }

  await waifuGenLoadDraftsFromServer();
}

function waifuGenTogglePanelHidden(el, hidden) {
  if (!el) return;
  el.hidden = hidden;
  if (hidden) el.setAttribute("hidden", "");
  else el.removeAttribute("hidden");
}

function waifuGenGoStep2() {
  const nameInput = document.getElementById("waifu-name-input");
  const err1 = document.getElementById("waifu-step1-error");
  const name = nameInput?.value?.trim() || "";
  if (!name) {
    if (err1) err1.textContent = "Введите имя.";
    return;
  }
  if (err1) err1.textContent = "";

  const s1 = document.getElementById("waifu-step-1");
  const s2 = document.getElementById("waifu-step-2");
  const st1 = document.getElementById("waifu-gen-sticky-step1");
  const st2 = document.getElementById("waifu-gen-sticky-step2");

  waifuGenTogglePanelHidden(s1, true);
  waifuGenTogglePanelHidden(s2, false);
  waifuGenTogglePanelHidden(st1, true);
  waifuGenTogglePanelHidden(st2, false);

  waifuGenRefreshHint();
  waifuGenRefreshGenerateButton();

  try {
    const tutorial = window.profileState?.currentProfile?.tutorial || null;
    window.WaifuApp?.Tutorial?.maybeRun?.("waifu_generator", tutorial, "waifu_gen_step2");
  } catch (e) {
    console.warn("waifu_gen_step2 tutorial failed:", e);
  }
}

function waifuGenGoStep1() {
  const s1 = document.getElementById("waifu-step-1");
  const s2 = document.getElementById("waifu-step-2");
  const st1 = document.getElementById("waifu-gen-sticky-step1");
  const st2 = document.getElementById("waifu-gen-sticky-step2");
  const errP = document.getElementById("waifu-gen-portrait-err");
  waifuGenTogglePanelHidden(s1, false);
  waifuGenTogglePanelHidden(s2, true);
  waifuGenTogglePanelHidden(st1, false);
  waifuGenTogglePanelHidden(st2, true);
  if (errP) errP.textContent = "";
}

async function waifuGenPreviewPortrait() {
  const errP = document.getElementById("waifu-gen-portrait-err");
  const genBtn = document.getElementById("waifu-generate-btn");
  const createBtn = document.getElementById("waifu-create-btn");
  if (waifuGenGensUsed() >= 3) {
    if (errP) errP.textContent = "Достигнут лимит трёх генераций.";
    return;
  }

  if (errP) errP.textContent = "";
  if (genBtn) genBtn.disabled = true;
  if (createBtn) createBtn.disabled = true;
  setWaifuGenMagicLoading(true);

  const body = waifuGenPortraitRequestBody();

  try {
    const data = await apiFetch(`/profile/main-waifu/preview-portrait`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const b64 = data?.image_base64;
    const mime = data?.mime || "image/webp";
    if (!b64) throw new Error("Пустой ответ изображения");

    const slotIdx = Number(data?.slot_index);
    const gens = Number(data?.generations_count);
    if (Number.isFinite(gens) && gens > 0) waifuGenSetGensUsed(gens);
    else waifuGenSetGensUsed(waifuGenGensUsed() + 1);

    const dataUrl = `data:${mime};base64,${b64}`;
    waifuGeneratorState.variants.push({
      b64,
      dataUrl,
      slot_index: Number.isFinite(slotIdx) ? slotIdx : waifuGeneratorState.variants.length,
    });
    waifuGeneratorState.selectedIdx = waifuGeneratorState.variants.length - 1;
    waifuGenApplyPortraitPreview(dataUrl);
    waifuGenRenderVariants();
    waifuGenRefreshHint();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const lim = (detail || "").includes("portrait_preview_limit");
    if (errP) {
      errP.textContent = lim
        ? "Лимит трёх генераций. Обновите страницу или создайте персонажа с уже выбранным портретом."
        : detail || String(e?.message || e);
    }
    if (lim) waifuGenSetGensUsed(3);
    waifuGenRefreshHint();
  } finally {
    setWaifuGenMagicLoading(false);
    waifuGenRefreshGenerateButton();
    if (createBtn) createBtn.disabled = false;
  }
}

async function submitWaifuCreation() {
  const nameInput = document.getElementById("waifu-name-input");
  const errBox = document.getElementById("waifu-create-error");
  const btn = document.getElementById("waifu-create-btn");
  if (!nameInput) return;

  const payload = {
    name: nameInput.value.trim(),
    race: waifuGeneratorState.selectedRaceId,
    class: waifuGeneratorState.selectedClassId,
  };
  const sel = waifuGeneratorState.variants[waifuGeneratorState.selectedIdx];
  if (sel && Number.isFinite(Number(sel.slot_index)) && sel.slot_index >= 0 && sel.slot_index <= 2) {
    payload.selected_slot = Number(sel.slot_index);
  } else if (sel?.b64) {
    payload.portrait_base64 = sel.b64;
  }

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

// ---- Guild hall ----

const guildHallState = {
  tab: "main",
  activitySubTab: "raid",
  me: null,
  profileGold: 0,
  bankItems: [],
  bankPage: 1,
  bankPageSize: 12,
  bankFilters: { weapon: true, armor: true, accessory: true },
  bankSort: "level",
  bankSortDir: "desc",
  bankGoldMode: "deposit",
  selectedBankItem: null,
  depositInventory: [],
  depositPage: 1,
  depositPageSize: 12,
  depositPreviewItem: null,
  memberPreviewData: null,
  mailCompose: { recipientId: null, inventoryItemId: null, itemLabel: "" },
  mailState: { inbox: [], selectedId: null, unreadCount: 0 },
  skillsBranch: "combat",
  raidParticipantIds: [],
  raidChatId: null,
  raidChatTitle: null,
  raidEligibleMembers: null,
  raidAvailableChats: [],
  warTargets: null,
  questsData: null,
  questsTab: "milestones",
  questsLoading: false,
  heroMenuListener: false,
  membersModalGuardUntil: 0,
  historyLoaded: false,
};

const GUILD_MEMBERS_MODAL_GUARD_MS = 400;
const GUILD_ME_CACHE_MS = 8000;
const guildMeCache = { data: null, ts: 0, inFlight: null };

function invalidateGuildMeCache() {
  guildMeCache.data = null;
  guildMeCache.ts = 0;
  guildHallState.historyLoaded = false;
}

async function fetchGuildMe(opts = {}) {
  const force = opts.force === true;
  const now = Date.now();
  if (!force && guildMeCache.data && now - guildMeCache.ts < GUILD_ME_CACHE_MS) {
    return guildMeCache.data;
  }
  if (guildMeCache.inFlight) return guildMeCache.inFlight;
  guildMeCache.inFlight = apiFetch("/guilds/me")
    .then((data) => {
      guildMeCache.data = data;
      guildMeCache.ts = Date.now();
      guildMeCache.inFlight = null;
      return data;
    })
    .catch((err) => {
      guildMeCache.inFlight = null;
      throw err;
    });
  return guildMeCache.inFlight;
}

async function loadGuildHistoryTab() {
  if (guildHallState.historyLoaded && Array.isArray(guildHallState.me?.history)) {
    return guildHallState.me.history;
  }
  const data = await apiFetch("/guilds/me/history");
  const history = Array.isArray(data?.history) ? data.history : [];
  if (guildHallState.me) guildHallState.me.history = history;
  guildHallState.historyLoaded = true;
  return history;
}

function isGuildLeader(d) {
  if (!d) return false;
  if (d.is_leader) return true;
  const viewerId = Number(d.viewer_player_id);
  if (!viewerId) return false;
  const members = Array.isArray(d.members) ? d.members : [];
  return members.some((m) => Number(m.player_id) === viewerId && m.is_leader);
}

function canEditGuildMedia(d) {
  return isGuildLeader(d);
}

function guildApiErrorToUser(detail, fallback) {
  const err =
    typeof detail === "object" && detail != null
      ? detail.error || detail.reason
      : String(detail || "");
  const map = {
    insufficient_gold: "Недостаточно золота.",
    already_in_guild: "Вы уже в гильдии.",
    name_taken: "Название гильдии занято.",
    tag_taken: "Тег гильдии занят.",
    waifu_level_too_low: "Нужна основная вайфу минимум 1 уровня.",
    guild_not_found: "Гильдия не найдена.",
    requirements_not_met: "Не выполнены требования вступления.",
    guild_full: "В гильдии нет свободных мест.",
    leader_only: "Только глава гильдии.",
    forbidden: "Недостаточно прав.",
    leader_cannot_leave: "Глава не может покинуть гильдию — передайте лидерство или распустите гильдию.",
    not_in_guild: "Вы не в гильдии.",
    locked: "Навык заблокирован уровнем гильдии.",
    tier_locked: "Навык заблокирован тиром гильдии.",
    max_level: "Навык уже максимального уровня.",
    no_skill_points: "Недостаточно очков прокачки (ОПГ).",
    cannot_kick_leader: "Нельзя исключить главу гильдии.",
    cannot_kick_self: "Нельзя исключить самого себя.",
    invalid_role: "Недопустимое звание.",
    target_not_found: "Участник не найден.",
    raid_already_active: "Рейд уже идёт.",
    no_active_raid: "Нет активного рейда.",
    not_in_raid: "Вы не участник этого рейда.",
    need_participants: "Нужно минимум 2 участника.",
    need_guild_chat: "Выберите групповой чат для рейда.",
    invalid_raid_chat: "Этот чат недоступен для рейда.",
    not_in_raid_chat: "Участник не состоит в выбранном чате.",
    wars_locked: "Войны доступны с 10 уровня гильдии.",
    already_at_war: "У гильдии уже активная война.",
    bad_target: "Нельзя объявить войну этой гильдии.",
    level_range: "Уровень цели вне диапазона ±3.",
  };
  return map[err] || fallback || String(err || "Ошибка");
}

function mailApiErrorToUser(detail, fallback) {
  const err = typeof detail === "string" ? detail : String(detail?.error || detail || "");
  const map = {
    cannot_mail_self: "Нельзя отправить письмо самому себе.",
    not_same_guild: "Нет доступа к профилю этого игрока.",
    empty_mail: "Укажите текст, золото или предмет.",
    body_too_long: "Слишком длинное сообщение.",
    gold_too_much: "Слишком много золота в одном письме.",
    insufficient_gold: "Недостаточно золота.",
    item_not_found: "Предмет не найден.",
    item_equipped: "Снимите предмет перед отправкой.",
    recipient_inbox_full: "Входящие получателя переполнены.",
    daily_send_limit: "Достигнут дневной лимит отправки писем.",
    sender_not_found: "Отправитель не найден.",
    recipient_not_found: "Получатель не найден.",
  };
  return map[err] || guildApiErrorToUser(detail, fallback);
}

function setGuildPageLoading(on) {
  if (typeof document === "undefined" || !document.body?.classList?.contains("page-guild")) return;
  const v = Boolean(on);
  document.body.classList.toggle("guild-loading", v);
  const modal = document.getElementById("guild-page-loading-modal");
  if (modal) modal.setAttribute("aria-busy", v ? "true" : "false");
}

function updateGuildHallChrome(inGuild) {
  const tabs = document.querySelector(".guild-tabs-row");
  const hero = document.getElementById("guild-hero-banner");
  const createSec = document.getElementById("guild-create-section");
  if (tabs) tabs.style.display = inGuild ? "" : "none";
  if (hero) {
    hero.hidden = !inGuild;
    hero.setAttribute("aria-hidden", inGuild ? "false" : "true");
  }
  if (createSec) createSec.style.display = inGuild ? "none" : "";
}

function formatGuildPower(n) {
  const v = safeInt(n, 0);
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(v);
}

function formatGuildRelativeTime(iso) {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return "только что";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} мин. назад`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} ч. назад`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} дн. назад`;
  return new Date(t).toLocaleDateString("ru-RU");
}

function renderGuildHero(d) {
  const hero = document.getElementById("guild-hero-banner");
  if (!hero || !d?.in_guild) return;
  const tagEl = document.getElementById("guild-hero-tag");
  const nameEl = document.getElementById("guild-hero-name");
  const levelEl = document.getElementById("guild-hero-level");
  const xpFill = document.getElementById("guild-hero-xp-fill");
  const xpLabel = document.getElementById("guild-hero-xp-label");
  const emblemEl = document.getElementById("guild-hero-emblem");
  const emblemInner = document.getElementById("guild-hero-emblem-inner");
  const heroBg = document.getElementById("guild-hero-bg");
  const bannerImg = document.getElementById("guild-hero-banner-img");
  const svgFallback = document.getElementById("guild-hero-svg-fallback");
  const iconInp = document.getElementById("guild-icon-file-input");
  const bannerInp = document.getElementById("guild-banner-file-input");
  const bar = formatGuildGxpBar(d);
  const canEdit = isGuildLeader(d);
  if (tagEl) tagEl.textContent = `[${d.guild_tag || ""}]`;
  if (nameEl) nameEl.textContent = d.guild_name || "—";
  if (levelEl) levelEl.textContent = `Ур. гильдии ${d.guild_level ?? "—"}`;
  if (xpFill) xpFill.style.width = `${bar.pct}%`;
  if (xpLabel) xpLabel.textContent = bar.label;
  const bannerUrl = d.guild_banner_url || "";
  if (bannerImg) {
    if (bannerUrl) {
      bannerImg.src = bannerUrl;
      bannerImg.hidden = false;
      if (svgFallback) svgFallback.style.display = "none";
    } else {
      bannerImg.removeAttribute("src");
      bannerImg.hidden = true;
      if (svgFallback) svgFallback.style.display = "";
    }
  }
  const iconUrl = d.guild_icon_url || "";
  if (emblemInner) {
    if (iconUrl) {
      emblemInner.innerHTML = `<img src="${escapeHtml(iconUrl)}" alt="" />`;
    } else {
      emblemInner.textContent = "🏛️";
    }
  }
  hero.onclick = null;
  hero.classList.remove("guild-hero-banner--editable");
  if (heroBg) {
    heroBg.onclick = null;
    heroBg.style.cursor = "";
  }
  const menuIcon = document.getElementById("guild-hero-menu-icon");
  const menuBanner = document.getElementById("guild-hero-menu-banner");
  const menuDivider = document.getElementById("guild-hero-menu-divider");
  const menuLeave = document.getElementById("guild-hero-menu-leave");
  if (menuIcon) menuIcon.hidden = !canEdit;
  if (menuBanner) menuBanner.hidden = !canEdit;
  if (menuDivider) menuDivider.hidden = !canEdit;
  if (menuLeave) menuLeave.hidden = canEdit;
  closeGuildHeroMenu();
  if (iconInp) iconInp.onchange = () => uploadGuildIcon(iconInp);
  if (bannerInp) bannerInp.onchange = () => uploadGuildBanner(bannerInp);
  if (!guildHallState.heroMenuListener) {
    guildHallState.heroMenuListener = true;
    document.addEventListener("click", (ev) => {
      if (!ev.target.closest("#guild-hero-menu") && !ev.target.closest("#guild-hero-menu-btn")) {
        closeGuildHeroMenu();
      }
      if (!ev.target.closest(".guild-member-actions")) {
        closeGuildMemberActionMenus();
      }
    });
  }
}

function renderGuildStatsGrid(d) {
  const members = Array.isArray(d?.members) ? d.members : [];
  const onlineN = members.filter((m) => m.online).length;
  const slots = d?.member_slots ?? "—";
  const power =
    d?.guild_power != null && d.guild_power !== ""
      ? formatGuildPower(d.guild_power)
      : "—";
  const rating =
    d?.guild_rating != null && d.guild_rating > 0 ? `#${d.guild_rating}` : "—";
  return `
    <div class="guild-section-label">Статистика</div>
    <div class="guild-stats-grid">
      <button type="button" id="guild-stat-members-btn" class="guild-stat-card guild-stat-card--btn">
        <div class="guild-stat-label">Участники</div>
        <div class="guild-stat-val">${members.length} <span class="guild-stat-sub">/ ${slots}</span></div>
      </button>
      <div class="guild-stat-card">
        <div class="guild-stat-label">Онлайн</div>
        <div class="guild-stat-val guild-stat-val--green"><span class="guild-dot-online" aria-hidden="true"></span>${onlineN}</div>
      </div>
      <div class="guild-stat-card">
        <div class="guild-stat-label">Мощь</div>
        <div class="guild-stat-val guild-stat-val--gold" id="guild-stat-power">${escapeHtml(String(power))}</div>
      </div>
      <div class="guild-stat-card">
        <div class="guild-stat-label">Рейтинг</div>
        <div class="guild-stat-val" id="guild-stat-rating">${escapeHtml(String(rating))}</div>
      </div>
    </div>`;
}

function armGuildMembersModalGuard() {
  guildHallState.membersModalGuardUntil = Date.now() + GUILD_MEMBERS_MODAL_GUARD_MS;
  const grid = document.querySelector(".guild-stats-grid");
  if (!grid) return;
  grid.classList.add("guild-stats-grid--arming");
  window.setTimeout(() => grid.classList.remove("guild-stats-grid--arming"), GUILD_MEMBERS_MODAL_GUARD_MS);
}

function bindGuildMembersStatCard() {
  const root = document.getElementById("guild-tab-content");
  if (!root || root.dataset.membersBtnBound === "1") return;
  root.dataset.membersBtnBound = "1";
  root.addEventListener("click", (ev) => {
    const btn = ev.target.closest("#guild-stat-members-btn");
    if (!btn) return;
    if (Date.now() < (guildHallState.membersModalGuardUntil || 0)) {
      ev.preventDefault();
      ev.stopPropagation();
      return;
    }
    openGuildMembersModal();
  });
}

function bindGuildMembersModalChrome() {
  if (window.__guildMembersModalBound) return;
  window.__guildMembersModalBound = true;

  const modal = document.getElementById("guild-members-modal");
  const closeBtn = document.getElementById("guild-members-modal-close");
  const panel = modal?.querySelector(".guild-members-modal-panel");

  const onCloseClick = (ev) => {
    ev.preventDefault();
    closeGuildMembersModal();
  };
  closeBtn?.addEventListener("click", onCloseClick);
  closeBtn?.addEventListener("touchend", onCloseClick);

  modal?.addEventListener("click", (ev) => {
    if (ev.target === modal) closeGuildMembersModal();
  });
  panel?.addEventListener("click", (ev) => {
    ev.stopPropagation();
  });

  window.addEventListener("pageshow", () => {
    if (document.body.classList.contains("page-guild")) {
      closeGuildMembersModal();
    }
  });
}

function openGuildMembersModal() {
  const d = guildHallState.me;
  if (!d?.in_guild) return;
  const body = document.getElementById("guild-members-modal-body");
  const modal = document.getElementById("guild-members-modal");
  if (body) body.innerHTML = renderGuildMembersHtml(d.members, d);
  if (modal) {
    modal.classList.add("guild-members-modal--open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }
}

function closeGuildMembersModal() {
  const modal = document.getElementById("guild-members-modal");
  closeGuildMemberActionMenus();
  if (modal) {
    modal.classList.remove("guild-members-modal--open");
    modal.setAttribute("aria-hidden", "true");
  }
  if (document.body.classList.contains("page-guild")) {
    document.body.style.overflow = "";
  }
}

function refreshGuildMembersModal() {
  const modal = document.getElementById("guild-members-modal");
  if (!modal?.classList.contains("guild-members-modal--open")) return;
  const d = guildHallState.me;
  const body = document.getElementById("guild-members-modal-body");
  if (body && d?.members) {
    body.innerHTML = renderGuildMembersHtml(d.members, d);
  }
}

function toggleGuildMemberActionMenu(ev, playerId) {
  ev?.stopPropagation?.();
  const menu = document.getElementById(`guild-member-menu-${playerId}`);
  if (!menu) return;
  const willOpen = menu.hidden;
  closeGuildMemberActionMenus();
  if (willOpen) {
    menu.hidden = false;
  }
}

function closeGuildMemberActionMenus() {
  document.querySelectorAll(".guild-member-actions-menu").forEach((menu) => {
    menu.hidden = true;
  });
}

function toggleGuildHeroMenu(ev) {
  ev?.stopPropagation?.();
  const menu = document.getElementById("guild-hero-menu");
  const btn = document.getElementById("guild-hero-menu-btn");
  if (!menu) return;
  const willOpen = menu.hidden;
  closeGuildHeroMenu();
  if (willOpen) {
    menu.hidden = false;
    if (btn) btn.setAttribute("aria-expanded", "true");
  }
}

function closeGuildHeroMenu() {
  const menu = document.getElementById("guild-hero-menu");
  const btn = document.getElementById("guild-hero-menu-btn");
  if (menu) menu.hidden = true;
  if (btn) btn.setAttribute("aria-expanded", "false");
}

function renderGuildActivityFeed(d) {
  const feed = Array.isArray(d?.activity_feed) ? d.activity_feed.slice(0, 3) : [];
  const inner = !feed.length
    ? `<p class="muted tiny guild-activity-empty">Пока нет событий.</p>`
    : `<div class="guild-activity-list">${feed
        .map((ev) => {
          const avatar = ev.actor_avatar || "📋";
          const text = ev.text || "";
          const time = formatGuildRelativeTime(ev.created_at);
          return `<div class="guild-act-item">
        <div class="guild-act-avatar" aria-hidden="true">${escapeHtml(String(avatar))}</div>
        <div class="guild-act-body">
          <div class="guild-act-text">${escapeHtml(text)}</div>
          ${time ? `<div class="guild-act-time">${escapeHtml(time)}</div>` : ""}
        </div>
      </div>`;
        })
        .join("")}</div>`;
  return `<div class="guild-activity-panel">
    <div class="guild-section-label">Активность</div>
    ${inner}
  </div>`;
}

function renderGuildHistoryPane(d) {
  const history = Array.isArray(d?.history) ? d.history : [];
  if (!history.length) {
    return `<p class="muted tiny" style="padding:12px 0;text-align:center">История пуста.</p>`;
  }
  const items = history
    .map((ev) => {
      const avatar = ev.actor_avatar || "📜";
      const text = ev.text || "";
      const time = formatGuildRelativeTime(ev.created_at);
      return `<div class="guild-act-item">
        <div class="guild-act-avatar" aria-hidden="true">${escapeHtml(String(avatar))}</div>
        <div class="guild-act-body">
          <div class="guild-act-text">${escapeHtml(text)}</div>
          ${time ? `<div class="guild-act-time">${escapeHtml(time)}</div>` : ""}
        </div>
      </div>`;
    })
    .join("");
  return `<div class="guild-history-list">${items}</div>`;
}

function switchGuildTab(name) {
  guildHallState.tab = name;
  document.querySelectorAll("[data-guild-tab-btn]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.guildTabBtn === name);
  });
  if (name === "battles" && !guildHallState.activitySubTab) {
    guildHallState.activitySubTab = "raid";
  }
  void renderGuildTabContent();
}

function switchGuildActivityTab(sub) {
  guildHallState.activitySubTab = sub;
  if (sub === "quests") {
    void loadGuildQuests().then(() => renderGuildTabContent());
    return;
  }
  void renderGuildTabContent();
}

function formatGuildGxpBar(d) {
  const gxp = safeInt(d?.gxp, 0);
  const next = d?.gxp_next_level;
  if (next == null || next <= 0) {
    return { pct: 100, label: `${gxp} GXP · макс. уровень` };
  }
  const prev = Math.max(0, gxp);
  const pct = Math.min(100, Math.max(0, Math.round((prev / next) * 100)));
  return { pct, label: `${gxp} / ${next} GXP` };
}

function guildMemberLabel(m) {
  const un = (m.telegram_username || "").trim();
  if (un) return `@${un}`;
  return escapeHtml(m.display_name || `Игрок ${m.player_id}`);
}

function guildMemberPlainName(m) {
  const un = (m.telegram_username || "").trim();
  if (un) return `@${un}`;
  return m.display_name || `Игрок ${m.player_id}`;
}

function guildMemberRankLabel(m) {
  if (m.rank) return m.rank;
  if (m.is_leader) return "Глава";
  if (m.is_officer) return "Офицер";
  return "Участник";
}

function guildMemberAvatarHtml(m) {
  const url = resolveImageUrl((m.portrait_url || "").trim());
  if (url && m.has_portrait !== false) {
    return `<img class="guild-member-avatar" src="${escapeHtml(url)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'guild-member-avatar guild-member-avatar--fallback',textContent:'🧙',ariaHidden:'true'}))" />`;
  }
  return `<div class="guild-member-avatar guild-member-avatar--fallback" aria-hidden="true">🧙</div>`;
}

function guildMemberActionMenuHtml(m, d) {
  const viewerId = Number(d?.viewer_player_id);
  const targetId = Number(m.player_id);
  if (!isGuildLeader(d) || !viewerId || targetId === viewerId || m.is_leader) {
    return `<span class="guild-member-actions-spacer" aria-hidden="true"></span>`;
  }
  const items = [];
  if (m.is_officer) {
    items.push(
      `<button type="button" class="guild-member-actions-menu-item" onclick="WaifuApp.guildSetMemberRank(${targetId}, 'member')">Снять с офицера</button>`
    );
  } else {
    items.push(
      `<button type="button" class="guild-member-actions-menu-item" onclick="WaifuApp.guildSetMemberRank(${targetId}, 'officer')">Назначить офицером</button>`
    );
  }
  items.push(
    `<button type="button" class="guild-member-actions-menu-item guild-member-actions-menu-item--danger" onclick="WaifuApp.guildKickMember(${targetId})">Исключить</button>`
  );
  items.push(
    `<button type="button" class="guild-member-actions-menu-item" onclick="WaifuApp.guildSetMemberRank(${targetId}, 'leader')">Передать лидерство</button>`
  );
  return `<div class="guild-member-actions">
    <button type="button" class="guild-member-actions-btn" aria-label="Действия" aria-haspopup="true" onclick="WaifuApp.toggleGuildMemberActionMenu(event, ${targetId})">⋯</button>
    <div id="guild-member-menu-${targetId}" class="guild-member-actions-menu" hidden>${items.join("")}</div>
  </div>`;
}

function renderGuildMembersHtml(members, viewerContext) {
  if (!Array.isArray(members) || !members.length) {
    return `<p class="muted tiny">Нет участников.</p>`;
  }
  const sorted = [...members].sort((a, b) => {
    const ao = a.online ? 1 : 0;
    const bo = b.online ? 1 : 0;
    if (bo !== ao) return bo - ao;
    const al = a.is_leader ? 2 : a.is_officer ? 1 : 0;
    const bl = b.is_leader ? 2 : b.is_officer ? 1 : 0;
    if (bl !== al) return bl - al;
    return String(a.display_name || "").localeCompare(String(b.display_name || ""), "ru");
  });
  const rows = sorted
    .map((m) => {
      const dotCls = m.online ? "guild-member-dot--online" : "guild-member-dot--offline";
      const pwr =
        m.member_power != null && m.member_power !== ""
          ? formatGuildPower(m.member_power)
          : "—";
      const lvl =
        m.waifu_level != null
          ? formatLevelWithPerfection(m.waifu_level, m.perfection_level)
          : "";
      const lvlHtml = lvl
        ? ` <span class="guild-member-level muted tiny">Ур. ${escapeHtml(lvl)}</span>`
        : "";
      return `<div class="guild-members-table-row">
      <span class="gmc gmc--dot"><span class="guild-member-dot ${dotCls}" aria-hidden="true" title="${m.online ? "Онлайн" : "Оффлайн"}"></span></span>
      <span class="gmc gmc--avatar">${guildMemberAvatarHtml(m)}</span>
      <span class="gmc gmc--name"><button type="button" class="guild-member-name-btn" onclick="WaifuApp.openPlayerProfile(${Number(m.player_id)})">${guildMemberLabel(m)}</button>${lvlHtml}</span>
      <span class="gmc gmc--rank"><span class="guild-member-rank">${escapeHtml(guildMemberRankLabel(m))}</span></span>
      <span class="gmc gmc--power"><span class="guild-member-power">${escapeHtml(String(pwr))}</span></span>
      <span class="gmc gmc--actions">${guildMemberActionMenuHtml(m, viewerContext)}</span>
    </div>`;
    })
    .join("");
  return `<div class="guild-members-table">
    <div class="guild-members-table-head">
      <span class="gmc gmc--dot" aria-hidden="true"></span>
      <span class="gmc gmc--avatar" aria-hidden="true"></span>
      <span class="gmc gmc--name">Игрок</span>
      <span class="gmc gmc--rank">Звание</span>
      <span class="gmc gmc--power">Мощь</span>
      <span class="gmc gmc--actions" aria-hidden="true"></span>
    </div>
    <div class="guild-members-table-body">${rows}</div>
  </div>`;
}

async function guildKickMember(targetId) {
  closeGuildMemberActionMenus();
  const d = guildHallState.me;
  const member = (d?.members || []).find((m) => Number(m.player_id) === Number(targetId));
  const name = member ? guildMemberPlainName(member) : `игрока ${targetId}`;
  if (!confirm(`Исключить ${name} из гильдии?`)) return;
  try {
    const res = await apiFetch(`/guilds/members/${targetId}/kick`, { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось исключить"), "error");
      return;
    }
    showToast("Участник исключён", "success");
    await refreshGuildHall({ force: true });
    refreshGuildMembersModal();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function guildSetMemberRank(targetId, role) {
  closeGuildMemberActionMenus();
  if (role === "leader") {
    const d = guildHallState.me;
    const member = (d?.members || []).find((m) => Number(m.player_id) === Number(targetId));
    const name = member ? guildMemberPlainName(member) : `игроку ${targetId}`;
    if (!confirm(`Передать лидерство ${name}? Вы станете обычным участником.`)) return;
  }
  try {
    const res = await apiFetch(`/guilds/members/${targetId}/rank`, {
      method: "POST",
      body: JSON.stringify({ role }),
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось изменить звание"), "error");
      return;
    }
    const toastMsg =
      role === "leader"
        ? "Лидерство передано"
        : role === "officer"
          ? "Участник назначен офицером"
          : "Офицер снят";
    showToast(toastMsg, "success");
    await refreshGuildHall({ force: true });
    refreshGuildMembersModal();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function getGuildRaidChatId(d) {
  const fromGuild = d?.raid?.telegram_chat_id ?? d?.telegram_chat_id;
  if (fromGuild != null && Number(fromGuild) !== 0) return Number(fromGuild);
  const chat = tg?.initDataUnsafe?.chat;
  if (chat?.id) return Number(chat.id);
  return null;
}

function guildRaidMusterStatusLabel(st) {
  const map = {
    pending: "ожидает",
    accepted: "принял",
    declined: "отказался",
    timeout: "таймаут (3 ч)",
  };
  return map[String(st || "").toLowerCase()] || st || "—";
}

function closeGuildRaidChatModal() {
  const modal = document.getElementById("guild-raid-chat-modal");
  if (!modal) return;
  modal.classList.remove("guild-raid-participants-modal--open");
  modal.setAttribute("aria-hidden", "true");
}

async function openGuildRaidChatModal() {
  const d = guildHallState.me;
  if (!isGuildLeader(d)) {
    showToast("Только глава гильдии может выбрать чат", "error");
    return;
  }
  const body = document.getElementById("guild-raid-chat-modal-body");
  const modal = document.getElementById("guild-raid-chat-modal");
  if (!body || !modal) return;
  body.innerHTML = `<p class="muted tiny">Загрузка чатов…</p>`;
  modal.classList.add("guild-raid-participants-modal--open");
  modal.setAttribute("aria-hidden", "false");
  try {
    const data = await apiFetch("/guilds/raid/available-chats");
    const chats = Array.isArray(data?.chats) ? data.chats : [];
    guildHallState.raidAvailableChats = chats;
    if (!chats.length) {
      const hint = data?.hint || "Нет доступных чатов. Напишите сообщение в группе с ботом.";
      body.innerHTML = `<p class="muted tiny">${escapeHtml(hint)}</p>`;
      return;
    }
    body.innerHTML = chats
      .map((c, idx) => {
        const cid = Number(c.chat_id);
        const rawTitle = String(c.title || `Чат ${cid}`);
        const title = escapeHtml(rawTitle);
        const current = c.is_current ? ' <span class="muted tiny">(текущий)</span>' : "";
        return `<button type="button" class="guild-raid-chat-row" data-chat-index="${idx}">
          <span class="guild-raid-chat-row-title">${title}${current}</span>
          <span class="muted tiny">${cid}</span>
        </button>`;
      })
      .join("");
    body.querySelectorAll(".guild-raid-chat-row").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.chatIndex);
        const c = (guildHallState.raidAvailableChats || [])[idx];
        if (!c) return;
        selectGuildRaidChat(Number(c.chat_id), c.title || "");
      });
    });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    body.innerHTML = `<p class="muted tiny">${escapeHtml(guildApiErrorToUser(detail, "Не удалось загрузить чаты"))}</p>`;
  }
}

async function selectGuildRaidChat(chatId, title) {
  guildHallState.raidChatId = Number(chatId);
  guildHallState.raidChatTitle = String(title || "").trim() || `Чат ${chatId}`;
  guildHallState.raidParticipantIds = [];
  guildHallState.raidEligibleMembers = null;
  closeGuildRaidChatModal();
  await openGuildRaidParticipantModal();
}

async function openGuildRaidParticipantModal() {
  const d = guildHallState.me;
  const chatId = guildHallState.raidChatId;
  if (!chatId) {
    showToast("Сначала выберите чат", "error");
    return;
  }
  const maxSlots = safeInt(d?.raid?.raid_party_slots, 10) || 10;
  const body = document.getElementById("guild-raid-participants-modal-body");
  const modal = document.getElementById("guild-raid-participants-modal");
  const chatLabel = document.getElementById("guild-raid-participants-chat-label");
  if (!body || !modal) return;
  const chatTitle = guildHallState.raidChatTitle || `Чат ${chatId}`;
  if (chatLabel) {
    chatLabel.textContent = `Чат: ${chatTitle}. Минимум 2 участника из этого чата. Окно подтверждения — 3 часа.`;
  }
  body.innerHTML = `<p class="muted tiny">Загрузка участников…</p>`;
  modal.classList.add("guild-raid-participants-modal--open");
  modal.setAttribute("aria-hidden", "false");
  let members = guildHallState.raidEligibleMembers;
  try {
    if (!Array.isArray(members)) {
      const data = await apiFetch(`/guilds/raid/chat-members?chat_id=${encodeURIComponent(chatId)}`);
      members = Array.isArray(data?.members) ? data.members : [];
      guildHallState.raidEligibleMembers = members;
      if (data?.chat_title) guildHallState.raidChatTitle = data.chat_title;
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    body.innerHTML = `<p class="muted tiny">${escapeHtml(guildApiErrorToUser(detail, "Не удалось загрузить участников"))}</p>`;
    return;
  }
  if (!members.length) {
    body.innerHTML = `<p class="muted tiny">В этом чате нет членов гильдии, которых бот видел. Участники должны написать хотя бы одно сообщение в чате.</p>`;
    return;
  }
  const eligibleIds = new Set(members.map((m) => Number(m.player_id)));
  if (!guildHallState.raidParticipantIds.length) {
    const viewerId = safeInt(d?.viewer_player_id, 0);
    if (viewerId && eligibleIds.has(viewerId)) guildHallState.raidParticipantIds = [viewerId];
  } else {
    guildHallState.raidParticipantIds = guildHallState.raidParticipantIds.filter((pid) =>
      eligibleIds.has(Number(pid))
    );
  }
  body.innerHTML = members
    .map((m) => {
      const pid = Number(m.player_id);
      const checked = guildHallState.raidParticipantIds.includes(pid);
      const label = guildMemberLabel(m);
      const online = m.online ? " 🟢" : "";
      return `<label class="guild-raid-participant-row">
        <input type="checkbox" ${checked ? "checked" : ""} onchange="WaifuApp.toggleGuildRaidParticipant(${pid}, this.checked)" />
        ${guildMemberAvatarHtml(m)}
        <span>${label}${online}</span>
      </label>`;
    })
    .join("");
  body.innerHTML += `<p class="muted tiny" style="margin-top:8px">Выбрано: <span id="guild-raid-picked-count">${guildHallState.raidParticipantIds.length}</span> / ${maxSlots}</p>`;
}

function closeGuildRaidParticipantModal() {
  const modal = document.getElementById("guild-raid-participants-modal");
  if (!modal) return;
  modal.classList.remove("guild-raid-participants-modal--open");
  modal.setAttribute("aria-hidden", "true");
}

function updateGuildRaidPickedCount() {
  const el = document.getElementById("guild-raid-picked-count");
  const d = guildHallState.me;
  const maxSlots = safeInt(d?.raid?.raid_party_slots, 10) || 10;
  if (el) el.textContent = String(Math.min(guildHallState.raidParticipantIds.length, maxSlots));
}

async function loadGuildBankItems() {
  const data = await apiFetch("/guilds/bank/items");
  guildHallState.bankItems = Array.isArray(data?.items) ? data.items : [];
  return guildHallState.bankItems;
}

function fillItemOfferModal(item, prefix) {
  const offer = item;
  const el = (suffix) => document.getElementById(`${prefix}-${suffix}`);
  const contentEl = el("content");
  const nameEl = el("name");
  const subEl = el("subline");
  const rpill = el("rpill");
  const art = el("art");
  const body = el("body");
  const upHint = el("upgrade-hint");
  if (!offer) return;
  const nm = String(offer?.display_name || offer?.name || "Предмет").trim();
  if (nameEl) nameEl.innerHTML = composeItemTitlePlain(offer) || escapeHtml(nm);
  if (subEl) subEl.textContent = buildItemModalMetaLine(offer);
  if (rpill) {
    rpill.textContent = rarityLabel(offer?.rarity);
    rpill.className = `item-modal-v2-rpill ${rarityPillModifierClass(offer?.rarity)}`.trim();
  }
  if (upHint) {
    upHint.style.display = "none";
    upHint.setAttribute("aria-hidden", "true");
  }
  if (art) art.innerHTML = itemArtHtml(offer);
  if (contentEl) {
    ["rarity-common", "rarity-uncommon", "rarity-rare", "rarity-epic", "rarity-legendary"].forEach((c) =>
      contentEl.classList.remove(c)
    );
    contentEl.classList.add(offer?.rarity != null ? rarityClass(offer.rarity) : "rarity-common");
  }
  const charHtml =
    renderItemModalV2CharacteristicsHtml(offer) ||
    `<div class="muted tiny" style="padding:6px 0;">Нет характеристик.</div>`;
  if (body) body.innerHTML = charHtml;
  const reqSec = el("req-section");
  const reqFoot = el("requirements");
  const mw = profileState.currentProfile?.main_waifu || null;
  const pillsHtml = buildItemModalRequirementsPillsHtml(offer, mw);
  if (reqFoot) reqFoot.innerHTML = pillsHtml;
  if (reqSec) reqSec.style.display = pillsHtml ? "" : "none";
  const descEl = el("desc");
  const descText = String(offer?.description || "").trim();
  if (descEl) {
    if (descText) {
      descEl.style.display = "";
      descEl.textContent = `"${descText}"`;
    } else {
      descEl.style.display = "none";
      descEl.innerHTML = "";
    }
  }
}

function fillGuildBankOfferModal(item) {
  fillItemOfferModal(item, "guild-bank-offer-modal");
}

function openGuildBankItemModal(bankItemId) {
  const it = guildHallState.bankItems.find((x) => Number(x.bank_item_id) === Number(bankItemId));
  if (!it) return;
  guildHallState.selectedBankItem = it;
  fillGuildBankOfferModal(it);
  const m = document.getElementById("guild-bank-item-modal");
  if (m) {
    m.classList.add("shop-modal--open");
    m.style.display = "grid";
  }
}

function closeGuildBankItemModal() {
  guildHallState.selectedBankItem = null;
  const m = document.getElementById("guild-bank-item-modal");
  if (m) {
    m.classList.remove("shop-modal--open");
    m.style.display = "none";
  }
}

async function confirmGuildBankTake() {
  const it = guildHallState.selectedBankItem;
  if (!it?.bank_item_id) return;
  try {
    const res = await apiFetch(`/guilds/withdraw/item?bank_item_id=${encodeURIComponent(it.bank_item_id)}`, {
      method: "POST",
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось взять предмет"), "error");
      return;
    }
    showToast("Предмет взят из банка");
    closeGuildBankItemModal();
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function openGuildBankGoldModal(mode) {
  const m = mode === "withdraw" ? "withdraw" : "deposit";
  guildHallState.bankGoldMode = m;
  const d = guildHallState.me;
  const bal = document.getElementById("guild-bank-gold-modal-balance");
  const pl = document.getElementById("guild-bank-gold-modal-player");
  const title = document.getElementById("guild-bank-gold-modal-title");
  const confirm = document.getElementById("guild-bank-gold-confirm");
  const inp = document.getElementById("guild-bank-gold-amount");
  if (bal) bal.textContent = formatGuildBankGold(d?.bank_gold ?? 0);
  if (pl) pl.textContent = formatGuildBankGold(guildHallState.profileGold ?? 0);
  if (title) title.textContent = m === "withdraw" ? "Снять золото" : "Внести золото";
  if (confirm) confirm.textContent = m === "withdraw" ? "Снять" : "Внести";
  if (inp) inp.value = "1";
  const modal = document.getElementById("guild-bank-gold-modal");
  if (modal) {
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
  }
}

function closeGuildBankGoldModal() {
  const m = document.getElementById("guild-bank-gold-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
}

async function confirmGuildBankGold() {
  if (guildHallState.bankGoldMode === "withdraw") {
    await confirmGuildBankGoldTake();
  } else {
    await confirmGuildBankGoldDeposit();
  }
}

async function confirmGuildBankGoldDeposit() {
  const inp = document.getElementById("guild-bank-gold-amount");
  const amount = safeInt(inp?.value, 0);
  if (amount < 1) {
    showToast("Укажите сумму", "error");
    return;
  }
  try {
    const res = await apiFetch(`/guilds/deposit/gold?amount=${encodeURIComponent(amount)}`, { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Ошибка вложения"), "error");
      return;
    }
    closeGuildBankGoldModal();
    await loadProfile().catch(() => {});
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function confirmGuildBankGoldTake() {
  const inp = document.getElementById("guild-bank-gold-amount");
  const amount = safeInt(inp?.value, 0);
  if (amount < 1) {
    showToast("Укажите сумму", "error");
    return;
  }
  try {
    const res = await apiFetch(`/guilds/withdraw/gold?amount=${encodeURIComponent(amount)}`, { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Ошибка снятия"), "error");
      return;
    }
    showToast("Золото снято из банка");
    closeGuildBankGoldModal();
    await loadProfile().catch(() => {});
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function renderGuildBankDepositCell(it) {
  const rCls = rarityClassFromValue(it?.rarity);
  const lvl = safeInt(it?.level, 0);
  const lvlLabel = lvl > 0 ? `ур. ${lvl}` : "ур. ?";
  return `<button type="button" class="guild-bank-deposit-cell ${rCls}" onclick="WaifuApp.openGuildBankDepositItemPreview(${Number(it.id)})" aria-label="${escapeHtml(composeItemDisplayName(it))}">
    <span class="item-level">${lvlLabel}</span>
    <span class="guild-bank-deposit-cell-art">${itemArtHtml(it)}</span>
  </button>`;
}

function renderGuildBankDepositPicker() {
  const grid = document.getElementById("guild-bank-deposit-grid");
  const pager = document.getElementById("guild-bank-deposit-pagination");
  const emptyNote = document.getElementById("guild-bank-deposit-empty-note");
  if (!grid || !pager) return;
  const items = guildHallState.depositInventory;
  const pageSize = guildHallState.depositPageSize;
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(Math.max(1, guildHallState.depositPage), totalPages);
  if (page !== guildHallState.depositPage) guildHallState.depositPage = page;
  const start = (page - 1) * pageSize;
  const slice = items.slice(start, start + pageSize);
  const cells = [];
  for (let i = 0; i < pageSize; i += 1) {
    if (i < slice.length) {
      cells.push(renderGuildBankDepositCell(slice[i]));
    } else {
      cells.push(`<div class="guild-bank-deposit-cell guild-bank-deposit-cell--empty" aria-hidden="true"></div>`);
    }
  }
  grid.innerHTML = cells.join("");
  if (emptyNote) {
    if (!items.length) {
      emptyNote.textContent = "Нет предметов для вложения (только неэкипированные).";
      emptyNote.style.display = "";
    } else {
      emptyNote.textContent = "";
      emptyNote.style.display = "none";
    }
  }
  if (totalPages > 1) {
    pager.innerHTML = `<button type="button" class="guild-bank-pag-btn" ${page <= 1 ? "disabled" : ""} onclick="WaifuApp.guildBankDepositPrevPage()">← Назад</button>
      <span class="guild-bank-pag-info">Стр. ${page}</span>
      <button type="button" class="guild-bank-pag-btn" ${page >= totalPages ? "disabled" : ""} onclick="WaifuApp.guildBankDepositNextPage()">Вперёд →</button>`;
    pager.style.display = "";
  } else {
    pager.innerHTML = "";
    pager.style.display = "none";
  }
}

function syncGuildBankDepositModalBodyScrollLock() {
  const picker = document.getElementById("guild-bank-deposit-modal");
  const preview = document.getElementById("guild-bank-deposit-item-modal");
  const pickerOpen = Boolean(picker && picker.style.display !== "none");
  const previewOpen = Boolean(preview && preview.classList.contains("shop-modal--open"));
  document.body.style.overflow = pickerOpen || previewOpen ? "hidden" : "";
}

async function openGuildBankDepositModal() {
  try {
    const eq = await apiFetch("/waifu/equipment");
    const inv = (Array.isArray(eq?.inventory) ? eq.inventory : []).filter((i) => i?.id && !i?.equipment_slot);
    guildHallState.depositInventory = inv;
    guildHallState.depositPage = 1;
    guildHallState.depositPreviewItem = null;
    renderGuildBankDepositPicker();
    const m = document.getElementById("guild-bank-deposit-modal");
    if (m) {
      m.style.display = "flex";
      m.setAttribute("aria-hidden", "false");
    }
    syncGuildBankDepositModalBodyScrollLock();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить инвентарь", "error");
  }
}

function guildBankDepositPrevPage() {
  guildHallState.depositPage = Math.max(1, guildHallState.depositPage - 1);
  renderGuildBankDepositPicker();
}

function guildBankDepositNextPage() {
  const pageSize = guildHallState.depositPageSize;
  const totalPages = Math.max(1, Math.ceil(guildHallState.depositInventory.length / pageSize));
  guildHallState.depositPage = Math.min(guildHallState.depositPage + 1, totalPages);
  renderGuildBankDepositPicker();
}

function openGuildBankDepositItemPreview(inventoryItemId) {
  const it = guildHallState.depositInventory.find((x) => Number(x.id) === Number(inventoryItemId));
  if (!it) return;
  guildHallState.depositPreviewItem = it;
  fillItemOfferModal(it, "guild-bank-deposit-offer-modal");
  const m = document.getElementById("guild-bank-deposit-item-modal");
  if (m) {
    m.classList.add("shop-modal--open");
    m.style.display = "grid";
    m.setAttribute("aria-hidden", "false");
  }
  syncGuildBankDepositModalBodyScrollLock();
}

function closeGuildBankDepositItemPreview() {
  guildHallState.depositPreviewItem = null;
  const m = document.getElementById("guild-bank-deposit-item-modal");
  if (m) {
    m.classList.remove("shop-modal--open");
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
  syncGuildBankDepositModalBodyScrollLock();
}

async function confirmGuildBankDepositItem() {
  const it = guildHallState.depositPreviewItem;
  const iid = Number(it?.id);
  if (!iid) return;
  try {
    const res = await apiFetch(`/guilds/deposit/item?inventory_item_id=${encodeURIComponent(iid)}`, {
      method: "POST",
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось вложить"), "error");
      return;
    }
    closeGuildBankDepositItemPreview();
    closeGuildBankDepositModal();
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function closeGuildBankDepositModal() {
  closeGuildBankDepositItemPreview();
  const m = document.getElementById("guild-bank-deposit-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
  syncGuildBankDepositModalBodyScrollLock();
}

function closeGuildSkillModal() {
  const m = document.getElementById("guild-skill-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
}

function guildSkillUpgradeCost(sk) {
  const cur = safeInt(sk?.current_level, 0);
  if (sk?.upgrade_cost != null && cur < 3) return safeInt(sk.upgrade_cost, 1);
  return cur === 0 ? safeInt(sk?.cost_sp, 1) : safeInt(sk?.cost_per_upgrade, 1);
}

function guildSkillCanUpgradeClientFallback(sk, d) {
  const cur = safeInt(sk?.current_level, 0);
  const guildLevel = safeInt(d?.guild_level, 1);
  const tierUnlock = safeInt(d?.skill_tier_unlock, 1);
  const glReq = safeInt(sk?.guild_level_req, 1);
  const tier = safeInt(sk?.tier, 1);
  const avail = safeInt(d?.skill_points_available, 0);
  const cost = guildSkillUpgradeCost(sk);
  return (
    isGuildLeader(d) &&
    cur < 3 &&
    guildLevel >= glReq &&
    tier <= tierUnlock &&
    avail >= cost
  );
}

function guildSkillCanUpgrade(sk, d) {
  if (typeof sk?.can_upgrade === "boolean") return sk.can_upgrade;
  return guildSkillCanUpgradeClientFallback(sk, d);
}

function guildSkillBlockReasonRu(sk, d, reason) {
  const cost = guildSkillUpgradeCost(sk);
  const glReq = safeInt(sk?.guild_level_req, 1);
  const tier = safeInt(sk?.tier, 1);
  switch (String(reason || "").trim()) {
    case "leader_only":
      return "Только глава гильдии";
    case "locked":
      return `Нужен ${glReq} ур. гильдии`;
    case "tier_locked":
      return `Откроется с тиром навыков ${tier}`;
    case "no_skill_points":
      return `Недостаточно ОПГ (нужно ${cost})`;
    case "max_level":
      return "Максимальный уровень";
    default:
      if (!isGuildLeader(d)) return "Только глава гильдии";
      return guildApiErrorToUser(reason, "Нельзя улучшить");
  }
}

function openGuildSkillModal(skillId) {
  const d = guildHallState.me;
  const sk = (d?.definitions || []).find((x) => Number(x.id) === Number(skillId));
  if (!sk) return;
  const title = document.getElementById("guild-skill-modal-title");
  const body = document.getElementById("guild-skill-modal-body");
  const footer = document.getElementById("guild-skill-modal-footer");
  if (title) title.textContent = sk.name || "Навык";
  const cur = safeInt(sk.current_level, 0);
  const eff = Array.isArray(sk.effect_per_level) ? sk.effect_per_level : [];
  const effCur = cur > 0 && eff[cur - 1] != null ? eff[cur - 1] : "—";
  const effNext = cur < 3 && eff[cur] != null ? eff[cur] : null;
  const cost = guildSkillUpgradeCost(sk);
  const avail = safeInt(d?.skill_points_available, 0);
  const canUp = guildSkillCanUpgrade(sk, d);
  const blockReason = sk.upgrade_block_reason || (canUp ? null : "no_skill_points");
  if (body) {
    body.innerHTML = `
      <div class="detail-row"><span>Тир</span><strong>${sk.tier ?? "—"}</strong></div>
      <div class="detail-row"><span>Уровень</span><strong>${cur} / 3</strong></div>
      <div class="detail-row"><span>Треб. ур. гильдии</span><strong>${sk.guild_level_req ?? "—"}</strong></div>
      <div class="detail-row"><span>Эффект сейчас</span><strong>${escapeHtml(String(effCur))}</strong></div>
      ${effNext != null ? `<div class="detail-row"><span>След. уровень</span><strong>${escapeHtml(String(effNext))}</strong></div>` : ""}
      <div class="detail-row"><span>Стоимость ОПГ</span><strong>${cost}</strong></div>
      <div class="detail-row"><span>ОПГ доступно</span><strong>${avail}</strong></div>`;
  }
  if (footer) {
    footer.innerHTML = canUp
      ? `<button type="button" class="btn primary" onclick="WaifuApp.guildSkillUpgrade(${Number(sk.id)})">+1 ОПГ (${cost})</button>`
      : `<span class="muted tiny">${escapeHtml(guildSkillBlockReasonRu(sk, d, blockReason))}</span>`;
  }
  const m = document.getElementById("guild-skill-modal");
  if (m) {
    m.style.display = "flex";
    m.setAttribute("aria-hidden", "false");
  }
}

async function guildSkillUpgrade(skillId) {
  try {
    const res = await apiFetch(`/guilds/skill/upgrade?skill_definition_id=${encodeURIComponent(skillId)}`, {
      method: "POST",
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Ошибка прокачки"), "error");
      return;
    }
    showToast("Навык улучшен");
    closeGuildSkillModal();
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function guildSkillReset() {
  if (!confirm("Сбросить все навыки гильдии? Стоимость зависит от уровня гильдии.")) return;
  try {
    const res = await apiFetch("/guilds/skill/reset", { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Ошибка сброса"), "error");
      return;
    }
    showToast("Навыки сброшены");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function formatGuildContrib(n) {
  const v = safeInt(n, 0);
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(v);
}

function guildMemberPreviewHeroUrl(data) {
  const mw = data?.main_waifu;
  if (!mw) return "";
  return mw.paperdoll_url || mw.portrait_url || "";
}

function renderGuildMemberPreviewBody() {
  const data = guildHallState.memberPreviewData;
  if (!data) return;

  const mw = data.main_waifu;
  const charNameEl = document.getElementById("guild-member-preview-char-name");
  const heroImg = document.getElementById("guild-member-preview-hero-img");
  const statusDot = document.getElementById("guild-member-preview-status-dot");
  const statusLabel = document.getElementById("guild-member-preview-status-label");
  const rankEl = document.getElementById("guild-member-preview-rank");
  const levelEl = document.getElementById("guild-member-preview-level");
  const powerEl = document.getElementById("guild-member-preview-power");
  const contribEl = document.getElementById("guild-member-preview-contrib");
  const contribBar = document.getElementById("guild-member-preview-contrib-bar");
  const heroesRow = document.getElementById("guild-member-preview-heroes-row");

  const charName = (mw?.name || data.first_name || "Участник").trim();
  if (charNameEl) charNameEl.textContent = charName.toUpperCase();

  const heroUrl = guildMemberPreviewHeroUrl(data);
  if (heroImg) {
    if (heroUrl) {
      heroImg.src = heroUrl;
      heroImg.hidden = false;
    } else {
      heroImg.removeAttribute("src");
      heroImg.hidden = true;
    }
  }

  const online = Boolean(data.online);
  if (statusDot) statusDot.classList.toggle("online", online);
  if (statusLabel) statusLabel.textContent = online ? "В сети" : "Офлайн";
  if (rankEl) rankEl.textContent = data.rank || "Участник";

  const viewerId = Number(guildHallState.me?.viewer_player_id);
  const mailBtn = document.getElementById("guild-member-preview-mail");
  if (mailBtn) {
    const isSelf =
      Boolean(data.is_self) ||
      (viewerId > 0 && viewerId === Number(data.player_id)) ||
      Number(profileState.currentProfile?.player_id) === Number(data.player_id);
    mailBtn.hidden = isSelf;
    mailBtn.style.display = isSelf ? "none" : "";
  }

  if (levelEl) {
    const lvl = mw?.level;
    const pLvl = mw?.perfection_level ?? data?.perfection_level;
    levelEl.textContent =
      lvl != null && lvl !== ""
        ? `Ур. ${formatLevelWithPerfection(lvl, pLvl)}`
        : "—";
  }
  if (powerEl) {
    const mp = data.member_power != null ? Number(data.member_power) : 0;
    powerEl.innerHTML =
      mp > 0
        ? `${escapeHtml(formatGuildPower(mp))} <em>(GvG)</em>`
        : `<span class="gold">—</span> <em>(GvG)</em>`;
  }

  const contrib = safeInt(data.contribution_week, 0);
  const contribCap = safeInt(data.contribution_week_cap, 200_000);
  const contribPct = contribCap > 0 ? Math.min(100, (contrib / contribCap) * 100) : 0;
  if (contribEl) {
    contribEl.innerHTML = `${escapeHtml(formatGuildContrib(contrib))} <em>/ ${escapeHtml(formatGuildContrib(contribCap))}</em>`;
  }
  if (contribBar) contribBar.style.width = `${contribPct}%`;

  if (heroesRow) {
    const hired = Array.isArray(data.hired_waifus) ? data.hired_waifus : [];
    if (!hired.length) {
      heroesRow.innerHTML = `<div class="guild-member-preview-heroes-empty">Нет наёмниц</div>`;
    } else {
      heroesRow.innerHTML = hired
        .map((hw) => {
          const portrait = hw.portrait_url ? String(hw.portrait_url) : "";
          const imgInner = portrait
            ? `<img src="${escapeHtml(portrait)}" alt="" />`
            : "🧝";
          return `<div class="guild-member-preview-hero-thumb">
            <div class="guild-member-preview-hero-thumb-img">${imgInner}</div>
            <div class="guild-member-preview-hero-level">Ур. ${Number(hw.level || 1)}</div>
          </div>`;
        })
        .join("");
    }
  }
}

function closeGuildMemberPreviewModal() {
  const m = document.getElementById("guild-member-preview-modal");
  if (!m) return;
  m.classList.remove("visible");
  const onEnd = () => {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
    guildHallState.memberPreviewData = null;
  };
  m.addEventListener("transitionend", onEnd, { once: true });
  setTimeout(onEnd, 300);
}

async function openGuildMemberPreviewModal(playerId) {
  try {
    const data = await apiFetch(`/guilds/members/${encodeURIComponent(playerId)}/preview`);
    guildHallState.memberPreviewData = data;
    renderGuildMemberPreviewBody();
    const m = document.getElementById("guild-member-preview-modal");
    if (m) {
      m.style.display = "flex";
      m.setAttribute("aria-hidden", "false");
      requestAnimationFrame(() => m.classList.add("visible"));
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить профиль", "error");
  }
}

function openGuildMemberMailCompose() {
  const data = guildHallState.memberPreviewData;
  if (!data?.player_id) return;
  const isSelf =
    Boolean(data.is_self) ||
    Number(guildHallState.me?.viewer_player_id) === Number(data.player_id) ||
    Number(profileState.currentProfile?.player_id) === Number(data.player_id);
  if (isSelf) {
    showToast("Нельзя отправить письмо самому себе.", "error");
    return;
  }
  openPlayerMailComposeModal(Number(data.player_id), data);
}

function mailRecipientLabel(data) {
  const un = (data?.telegram_username || "").trim();
  if (un) return `@${un}`;
  return (data?.first_name || data?.main_waifu?.name || `Игрок ${data?.player_id || ""}`).trim();
}

async function openPlayerMailComposeModal(recipientId, previewData = null) {
  const rid = Number(recipientId);
  if (!Number.isFinite(rid) || rid <= 0) return;
  guildHallState.mailCompose = { recipientId: rid, inventoryItemId: null, itemLabel: "" };
  let label = previewData ? mailRecipientLabel(previewData) : `Игрок ${rid}`;
  if (!previewData) {
    try {
      const p = await apiFetch(`/guilds/members/${encodeURIComponent(rid)}/preview`);
      label = mailRecipientLabel(p);
    } catch {
      /* keep fallback */
    }
  }
  const recEl = document.getElementById("player-mail-compose-recipient");
  const bodyEl = document.getElementById("player-mail-compose-body");
  const goldEl = document.getElementById("player-mail-compose-gold");
  const pickEl = document.getElementById("player-mail-compose-item-pick");
  const listEl = document.getElementById("player-mail-compose-item-list");
  if (recEl) recEl.textContent = label;
  if (bodyEl) bodyEl.value = "";
  if (goldEl) goldEl.value = "0";
  if (pickEl) pickEl.textContent = "Не выбран";
  if (listEl) listEl.style.display = "none";
  const m = document.getElementById("player-mail-compose-modal");
  if (m) {
    m.style.display = "flex";
    m.setAttribute("aria-hidden", "false");
  }
}

function closePlayerMailComposeModal() {
  const m = document.getElementById("player-mail-compose-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
  guildHallState.mailCompose = { recipientId: null, inventoryItemId: null, itemLabel: "" };
}

function getActiveMailComposeContext() {
  const tabPane = document.getElementById("player-mail-compose-pane");
  if (
    document.body.classList.contains("page-player") &&
    tabPane &&
    !tabPane.hidden &&
    playerPageState.activeSection === "mail"
  ) {
    return {
      state: playerPageState.mailCompose,
      bodyId: "player-mail-tab-body",
      goldId: "player-mail-tab-gold",
      pickId: "player-mail-tab-item-pick",
      onSuccess: () => {
        resetPlayerMailComposeForm();
        setPlayerMailTab("inbox");
        refreshMailInbox().catch(() => {});
      },
    };
  }
  return {
    state: guildHallState.mailCompose,
    bodyId: "player-mail-compose-body",
    goldId: "player-mail-compose-gold",
    pickId: "player-mail-compose-item-pick",
    listId: "player-mail-compose-item-list",
    onSuccess: () => {
      refreshAtticMailBadge().catch(() => {});
      closePlayerMailComposeModal();
    },
  };
}

function renderPlayerMailItemCell(it) {
  const rCls = rarityClassFromValue(it?.rarity);
  const lvl = safeInt(it?.level, 0);
  const lvlLabel = lvl > 0 ? `ур. ${lvl}` : "ур. ?";
  return `<button type="button" class="guild-bank-deposit-cell ${rCls}" onclick="WaifuApp.selectPlayerMailItem(${Number(it.id)})" aria-label="${escapeHtml(composeItemDisplayName(it))}">
    <span class="item-level">${lvlLabel}</span>
    <span class="guild-bank-deposit-cell-art">${itemArtHtml(it)}</span>
  </button>`;
}

function renderPlayerMailItemPicker() {
  const grid = document.getElementById("player-mail-item-grid");
  const pager = document.getElementById("player-mail-item-pagination");
  const emptyNote = document.getElementById("player-mail-item-empty-note");
  if (!grid || !pager) return;
  const items = playerPageState.mailItemInventory;
  const pageSize = playerPageState.mailItemPageSize;
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(Math.max(1, playerPageState.mailItemPage), totalPages);
  if (page !== playerPageState.mailItemPage) playerPageState.mailItemPage = page;
  const start = (page - 1) * pageSize;
  const slice = items.slice(start, start + pageSize);
  const cells = [];
  for (let i = 0; i < pageSize; i += 1) {
    if (i < slice.length) {
      cells.push(renderPlayerMailItemCell(slice[i]));
    } else {
      cells.push(`<div class="guild-bank-deposit-cell guild-bank-deposit-cell--empty" aria-hidden="true"></div>`);
    }
  }
  grid.innerHTML = cells.join("");
  if (emptyNote) {
    if (!items.length) {
      emptyNote.textContent = "Нет предметов для отправки (только неэкипированные).";
      emptyNote.hidden = false;
    } else {
      emptyNote.textContent = "";
      emptyNote.hidden = true;
    }
  }
  if (totalPages > 1) {
    pager.innerHTML = `<button type="button" class="guild-bank-pag-btn" ${page <= 1 ? "disabled" : ""} onclick="WaifuApp.playerMailItemPrevPage()">← Назад</button>
      <span class="guild-bank-pag-info">Стр. ${page}</span>
      <button type="button" class="guild-bank-pag-btn" ${page >= totalPages ? "disabled" : ""} onclick="WaifuApp.playerMailItemNextPage()">Вперёд →</button>`;
    pager.hidden = false;
  } else {
    pager.innerHTML = "";
    pager.hidden = true;
  }
}

async function openPlayerMailItemModal() {
  try {
    const eq = await apiFetch("/waifu/equipment");
    const inv = (Array.isArray(eq?.inventory) ? eq.inventory : []).filter((i) => i?.id && !i?.equipment_slot);
    playerPageState.mailItemInventory = inv;
    playerPageState.mailItemPage = 1;
    renderPlayerMailItemPicker();
    const m = document.getElementById("player-mail-item-modal");
    if (m) {
      m.style.display = "flex";
      m.setAttribute("aria-hidden", "false");
    }
    document.body.style.overflow = "hidden";
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить инвентарь", "error");
  }
}

function closePlayerMailItemModal() {
  const m = document.getElementById("player-mail-item-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
  document.body.style.overflow = "";
}

function playerMailItemPrevPage() {
  playerPageState.mailItemPage = Math.max(1, playerPageState.mailItemPage - 1);
  renderPlayerMailItemPicker();
}

function playerMailItemNextPage() {
  const pageSize = playerPageState.mailItemPageSize;
  const totalPages = Math.max(1, Math.ceil(playerPageState.mailItemInventory.length / pageSize));
  playerPageState.mailItemPage = Math.min(playerPageState.mailItemPage + 1, totalPages);
  renderPlayerMailItemPicker();
}

async function openPlayerMailItemPicker() {
  const tabPane = document.getElementById("player-mail-compose-pane");
  if (
    document.body.classList.contains("page-player") &&
    tabPane &&
    !tabPane.hidden &&
    playerPageState.activeSection === "mail"
  ) {
    return openPlayerMailItemModal();
  }
  const ctx = getActiveMailComposeContext();
  const listEl = document.getElementById(ctx.listId);
  if (!listEl) return;
  try {
    const eq = await apiFetch("/waifu/equipment");
    const inv = (Array.isArray(eq?.inventory) ? eq.inventory : []).filter((i) => i?.id);
    if (!inv.length) {
      listEl.innerHTML = `<p class="muted tiny">Нет предметов (только неэкипированные).</p>`;
    } else {
      listEl.innerHTML = inv
        .map((it) => {
          const iid = Number(it.id);
          const sel = ctx.state.inventoryItemId === iid ? " selected" : "";
          return `<div class="player-mail-compose-item-row${sel}" data-id="${iid}" onclick="WaifuApp.selectPlayerMailItem(${iid})">
            <span>${itemArtHtml(it)}</span>
            <span>${escapeHtml(composeItemDisplayName(it))}</span>
          </div>`;
        })
        .join("");
    }
    listEl.hidden = false;
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить инвентарь", "error");
  }
}

function renderMailComposeItemPick(item) {
  const pickEl = document.getElementById("player-mail-tab-item-pick");
  if (!pickEl) return;
  if (!item) {
    pickEl.innerHTML = `<span class="player-mail-item-pick-empty">Не выбран</span>`;
    return;
  }
  pickEl.innerHTML = `<span class="player-mail-item-pick-art">${itemArtHtml(item)}</span><span class="player-mail-item-pick-name">${composeItemDisplayName(item)}</span>`;
}

function selectPlayerMailItem(id) {
  const ctx = getActiveMailComposeContext();
  const iid = Number(id);
  ctx.state.inventoryItemId = iid;
  const fromModal = playerPageState.mailItemInventory.find((x) => Number(x.id) === iid);
  const row = document.querySelector(`.player-mail-compose-item-row[data-id="${iid}"]`);
  const item = fromModal || null;
  if (item) {
    ctx.state.itemLabel = composeItemDisplayName(item).replace(/<[^>]+>/g, "").trim();
  } else {
    ctx.state.itemLabel = row?.querySelector("span:last-child")?.textContent?.trim() || `Предмет #${iid}`;
  }
  if (ctx.pickId === "player-mail-tab-item-pick") {
    renderMailComposeItemPick(item);
  } else {
    const pickEl = document.getElementById(ctx.pickId);
    if (pickEl) pickEl.textContent = ctx.state.itemLabel;
  }
  document.querySelectorAll(".player-mail-compose-item-row").forEach((el) => {
    el.classList.toggle("selected", Number(el.dataset.id) === iid);
  });
  const listEl = document.getElementById(ctx.listId);
  if (listEl) listEl.hidden = true;
  if (
    document.body.classList.contains("page-player") &&
    playerPageState.activeSection === "mail"
  ) {
    closePlayerMailItemModal();
  }
}

async function sendPlayerMail() {
  const ctx = getActiveMailComposeContext();
  const rid = Number(ctx.state.recipientId);
  if (!Number.isFinite(rid) || rid <= 0) {
    showToast("Выберите получателя", "error");
    return;
  }
  const bodyText = (document.getElementById(ctx.bodyId)?.value || "").trim();
  const goldAmount = Math.max(0, safeInt(document.getElementById(ctx.goldId)?.value, 0));
  const inventoryItemId = ctx.state.inventoryItemId;
  const payload = { recipient_player_id: rid, body_text: bodyText || null, gold_amount: goldAmount };
  if (inventoryItemId) payload.inventory_item_id = Number(inventoryItemId);
  try {
    await apiFetch("/mail/send", { method: "POST", body: JSON.stringify(payload) });
    showToast("Письмо отправлено");
    ctx.onSuccess();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(mailApiErrorToUser(detail, "Не удалось отправить"), "error");
  }
}

async function initMailPage() {
  await refreshMailInbox();
  await refreshMailSent().catch(() => {});
}

const playerPageState = {
  activeSection: null,
  profileData: null,
  cachedAvatarUrl: null,
  viewPlayerId: null,
  isViewMode: false,
  selfPlayerId: null,
  mailTab: "inbox",
  mailCompose: { recipientId: null, recipientLabel: "", inventoryItemId: null, itemLabel: "" },
  mailGuildSuggestions: null,
  mailItemInventory: [],
  mailItemPage: 1,
  mailItemPageSize: 12,
};

const PLAYER_AVATAR_PRESET_COUNT = 20;

function getPlayerViewIdFromQuery() {
  const raw = new URLSearchParams(window.location.search).get("playerId");
  const id = Number(raw);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function openPlayerProfile(playerId) {
  const id = Number(playerId);
  if (!Number.isFinite(id) || id <= 0) return;
  window.location.href = `./player.html?playerId=${encodeURIComponent(id)}`;
}

function syncPlayerViewModeUi() {
  const view = playerPageState.isViewMode;
  document.body.classList.toggle("player-view-mode", view);
  document.querySelectorAll(".player-only-self").forEach((el) => {
    el.hidden = view;
  });
  document.querySelectorAll(".player-overflow-item--self").forEach((el) => {
    el.hidden = view;
  });
  const overflowBtn = document.getElementById("player-overflow-btn");
  const topbarOverflowBtn = document.getElementById("player-topbar-overflow-btn");
  if (overflowBtn) overflowBtn.hidden = view;
  if (topbarOverflowBtn) topbarOverflowBtn.hidden = view;
  const avatarBtn = document.getElementById("player-hero-avatar-btn");
  if (avatarBtn) avatarBtn.disabled = view;
  const showcaseToggle = document.getElementById("player-showcase-toggle");
  if (showcaseToggle) showcaseToggle.hidden = view;
}

function syncPlayerChromeMode() {
  const onOverview = !playerPageState.activeSection;
  const view = playerPageState.isViewMode;
  document.body.classList.toggle("player-chrome--overview", onOverview);
  const subpanelTopbar = document.getElementById("player-subpanel-topbar");
  const titleEl = document.getElementById("player-topbar-title");
  const showcaseOverflow = document.getElementById("player-overflow-btn");
  const topbarOverflow = document.getElementById("player-topbar-overflow-btn");
  if (onOverview) {
    if (subpanelTopbar) subpanelTopbar.hidden = true;
    if (showcaseOverflow) showcaseOverflow.hidden = view;
    if (topbarOverflow) topbarOverflow.hidden = true;
  } else {
    if (subpanelTopbar) subpanelTopbar.hidden = false;
    const titles = { mail: "Почта", guild: "Гильдия", settings: "Настройки" };
    if (titleEl) titleEl.textContent = titles[playerPageState.activeSection] || "Профиль";
    if (showcaseOverflow) showcaseOverflow.hidden = true;
    if (topbarOverflow) topbarOverflow.hidden = view;
  }
}

async function rehydratePlayerPage() {
  const menu = document.getElementById("player-overflow-menu");
  if (menu) menu.hidden = true;
  closePlayerMailItemModal();
  playerPageState.mailTab = "inbox";
  setPlayerMailTab("inbox");
  const fallback = profileState.currentProfile || {};
  applyPlayerHashSection();
  syncPlayerChromeMode();
  syncPlayerViewModeUi();
  try {
    if (playerPageState.isViewMode && playerPageState.viewPlayerId) {
      await loadPublicPlayerProfile(playerPageState.viewPlayerId, fallback);
    } else {
      await loadSelfPlayerProfile(fallback);
      if (!playerPageState.isViewMode) {
        refreshAtticMailBadge().catch(() => {});
      }
    }
  } catch {
    /* ignore rehydrate errors */
  }
}

function bindPlayerPageLifecycle() {
  if (window.__waifuPlayerPageshowBound) return;
  window.__waifuPlayerPageshowBound = true;
  window.addEventListener("pageshow", (ev) => {
    if (!document.body.classList.contains("page-player")) return;
    if (!ev.persisted) return;
    rehydratePlayerPage().catch(() => {});
  });
}

function openPlayerSection(section) {
  const name = section || "overview";
  playerPageState.activeSection = name === "overview" ? null : name;
  const menu = document.getElementById("player-overflow-menu");
  if (menu) menu.hidden = true;

  const mainScroll = document.getElementById("player-main-scroll");
  const subpanels = ["mail", "guild", "settings"];

  if (!playerPageState.activeSection) {
    if (mainScroll) mainScroll.hidden = false;
    subpanels.forEach((s) => {
      const el = document.getElementById(`player-panel-${s}`);
      if (el) el.hidden = true;
    });
    syncPlayerChromeMode();
    return;
  }

  if (mainScroll) mainScroll.hidden = true;
  subpanels.forEach((s) => {
    const el = document.getElementById(`player-panel-${s}`);
    if (el) el.hidden = s !== playerPageState.activeSection;
  });
  syncPlayerChromeMode();

  if (playerPageState.activeSection === "mail") {
    setPlayerMailTab(playerPageState.mailTab || "inbox");
    refreshMailInbox().catch(() => {});
  }
  if (playerPageState.activeSection === "guild") {
    renderPlayerGuildBlock().catch(() => {});
  }
  if (playerPageState.activeSection === "settings") {
    ensureDmNotificationPrefsLoaded().catch(() => {});
  }
}

function applyPlayerHashSection() {
  const hash = (window.location.hash || "").replace(/^#/, "").trim();
  if (hash === "mail" || hash === "settings" || hash === "guild") {
    if (playerPageState.isViewMode && (hash === "mail" || hash === "settings")) {
      openPlayerSection("overview");
      return;
    }
    openPlayerSection(hash);
  } else {
    openPlayerSection("overview");
  }
}

function renderPlayerHeroFromProfileData(data, fallbackProfile) {
  const name = (data?.display_name || fallbackProfile?.main_waifu?.name || "Игрок").trim();
  setText("player-hero-name", name);
  const unEl = document.getElementById("player-hero-username");
  const un = (data?.telegram_username || getTelegramUser()?.username || "").trim();
  if (unEl) unEl.textContent = un ? `@${un}` : "";
  playerPageState.cachedAvatarUrl = data?.avatar_url || playerPageState.cachedAvatarUrl;
  applyPlayerAvatarUrl(data?.avatar_url, fallbackProfile || profileState.currentProfile);
}

function renderPlayerWaifuShowcase(data) {
  const img = document.getElementById("player-waifu-showcase-img");
  const emptyEl = document.getElementById("player-waifu-showcase-empty");
  const toggle = document.getElementById("player-showcase-toggle");
  const nameEl = document.getElementById("player-waifu-name");
  const levelEl = document.getElementById("player-waifu-level");
  const mw = data?.main_waifu;
  const mode = (data?.profile_showcase || "portrait").toLowerCase();
  let url = null;
  if (mode === "paperdoll") {
    url = mw?.paperdoll_url || mw?.portrait_url || null;
  } else {
    url = mw?.portrait_url || mw?.paperdoll_url || null;
  }
  if (nameEl) nameEl.textContent = (mw?.name || "").trim() || "—";
  if (levelEl) {
    const lvl = mw?.level;
    const pLvl = mw?.perfection_level;
    levelEl.textContent =
      lvl != null && lvl !== "" ? `Ур. ${formatLevelWithPerfection(lvl, pLvl)}` : "";
  }
  if (img) {
    if (url) {
      if (img.dataset.showcaseSrc !== url) {
        img.dataset.showcaseSrc = url;
        img.src = url;
      }
      img.hidden = false;
      if (emptyEl) emptyEl.hidden = true;
    } else {
      img.hidden = true;
      img.removeAttribute("src");
      if (emptyEl) emptyEl.hidden = false;
    }
  }
  if (toggle && !playerPageState.isViewMode) {
    const hasBoth = !!(mw?.portrait_url && mw?.paperdoll_url);
    toggle.hidden = !hasBoth;
    toggle.querySelectorAll(".player-showcase-switch-btn").forEach((btn) => {
      const m = btn.getAttribute("data-showcase");
      btn.classList.toggle("active", m === mode);
    });
  } else if (toggle) {
    toggle.hidden = true;
  }
}

function formatStoryActDungeon(act, dungeonNumber) {
  const a = Math.max(0, parseInt(act, 10) || 0);
  const n = Math.max(0, parseInt(dungeonNumber, 10) || 0);
  if (a > 0 && n > 0) return `Акт ${a}-${n}`;
  return null;
}

function renderPlayerCampaignCompact(campaign) {
  const el = document.getElementById("player-campaign-compact");
  if (!el) return;
  const c = campaign || {};
  if (c.main_campaign_complete) {
    el.textContent = "🏰 Кампания пройдена";
    el.hidden = false;
    return;
  }
  const code = formatStoryActDungeon(c.story_next_act, c.story_next_dungeon_number);
  if (!code) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.textContent = `🏰 ${code}`;
  el.hidden = false;
}

function renderPlayerAbyssCompact(abyss) {
  const el = document.getElementById("player-abyss-compact");
  if (!el) return;
  const a = abyss || {};
  const maxFloor = safeInt(a.max_floor_reached, 0);
  if (maxFloor <= 0 && !a.session_active) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  const floor =
    a.session_active && a.current_floor != null
      ? safeInt(a.current_floor, 0)
      : maxFloor;
  const chk = a.current_checkpoint != null ? safeInt(a.current_checkpoint, 0) : null;
  const parts = [`Этаж ${floor}`];
  if (chk != null) parts.push(`ЧК ${chk}`);
  el.textContent = `🕳️ ${parts.join(" · ")}`;
  el.hidden = false;
}

function applyPlayerProfilePayload(data, fallbackProfile) {
  playerPageState.profileData = data;
  renderPlayerHeroFromProfileData(data, fallbackProfile);
  renderPlayerWaifuShowcase(data);
  renderPlayerCampaignCompact(data?.campaign);
  renderPlayerAbyssCompact(data?.abyss);
}

async function loadSelfPlayerProfile(fallbackProfile) {
  const data = await apiFetch("/player/profile");
  applyPlayerProfilePayload(data, fallbackProfile);
  return data;
}

async function loadPublicPlayerProfile(targetId, fallbackProfile) {
  const data = await apiFetch(`/player/${encodeURIComponent(targetId)}/profile`);
  applyPlayerProfilePayload(data, fallbackProfile);
  return data;
}

async function renderPlayerGuildBlock() {
  const root = document.getElementById("player-guild-root");
  if (!root) return;
  if (playerPageState.isViewMode) {
    const rank = playerPageState.profileData?.guild_rank;
    root.innerHTML = `<p>${rank ? `<strong>${escapeHtml(rank)}</strong> в вашей гильдии` : "Участник гильдии"}</p>
      <a href="./guild_hall.html" class="btn secondary" style="margin-top:8px;display:inline-block">Зал гильдии</a>`;
    return;
  }
  root.innerHTML = `<p class="muted">Загрузка…</p>`;
  try {
    const data = await apiFetch("/guilds/me");
    if (!data?.in_guild) {
      root.innerHTML = `<p class="muted">Вы не состоите в гильдии.</p>
        <a href="./guild_hall.html" class="btn secondary" style="margin-top:8px;display:inline-block">Зал гильдии</a>`;
      return;
    }
    const rank = data.is_leader ? "Глава" : data.is_officer ? "Офицер" : "Участник";
    const memberCount = Array.isArray(data.members) ? data.members.length : 0;
    const tag = (data.guild_tag || "").trim();
    root.innerHTML = `<p><strong>${escapeHtml(data.guild_name || "Гильдия")}</strong>${tag ? ` [${escapeHtml(tag)}]` : ""} · ${escapeHtml(rank)}</p>
      <p class="muted tiny">Ур. гильдии ${safeInt(data.guild_level, 1)} · участников ${memberCount}</p>
      <a href="./guild_hall.html" class="btn secondary" style="margin-top:8px;display:inline-block">Зал гильдии</a>`;
  } catch {
    root.innerHTML = `<p class="muted">Не удалось загрузить данные гильдии.</p>`;
  }
}

async function refreshMailSent() {
  const root = document.getElementById("mail-sent-root");
  if (!root) return;
  try {
    const data = await apiFetch("/mail/sent?limit=30");
    const items = Array.isArray(data?.items) ? data.items : [];
    if (!items.length) {
      root.innerHTML = `<p class="muted">Исходящих писем нет.</p>`;
      return;
    }
    root.innerHTML = items
      .map((m) => {
        const status =
          m.status === "claimed"
            ? "забрано"
            : m.status === "read"
              ? "прочитано"
              : "доставлено";
        const attach = [];
        if (m.gold_amount > 0) attach.push(`🪙 ${Number(m.gold_amount).toLocaleString("ru-RU")}`);
        if (m.inventory_item_id) attach.push("📦 предмет");
        const preview = (m.body_text || attach.join(" · ") || "—").slice(0, 60);
        return `<div class="mail-inbox-row" style="cursor:default">
          <span style="flex:1;min-width:0">
            <strong>${escapeHtml(m.recipient_label || "Игрок")}</strong>
            <span class="muted tiny"> · ${escapeHtml(status)}</span>
            <div class="muted tiny">${escapeHtml(preview)}</div>
          </span>
        </div>`;
      })
      .join("");
  } catch {
    root.innerHTML = `<p class="muted">Не удалось загрузить отправленные.</p>`;
  }
}

function setPlayerMailTab(tab) {
  const name = tab === "compose" ? "compose" : "inbox";
  playerPageState.mailTab = name;
  document.querySelectorAll(".player-mail-tab").forEach((btn) => {
    const t = btn.getAttribute("data-mail-tab");
    const active = t === name;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  const inboxPane = document.getElementById("player-mail-inbox-pane");
  const composePane = document.getElementById("player-mail-compose-pane");
  if (inboxPane) inboxPane.hidden = name !== "inbox";
  if (composePane) composePane.hidden = name !== "compose";
  if (name === "compose") {
    loadPlayerMailGuildSuggestions().catch(() => {});
  }
}

function resetPlayerMailComposeForm() {
  playerPageState.mailCompose = {
    recipientId: null,
    recipientLabel: "",
    inventoryItemId: null,
    itemLabel: "",
  };
  const input = document.getElementById("player-mail-recipient-input");
  const body = document.getElementById("player-mail-tab-body");
  const gold = document.getElementById("player-mail-tab-gold");
  const suggest = document.getElementById("player-mail-recipient-suggest");
  if (input) input.value = "";
  if (body) body.value = "";
  if (gold) gold.value = "0";
  renderMailComposeItemPick(null);
  if (suggest) suggest.hidden = true;
}

function playerMailRecipientRowLabel(item) {
  const un = (item.username || "").trim();
  if (un) return `@${un.replace(/^@/, "")}`;
  const name = (item.character_name || item.first_name || "").trim();
  if (name) return name;
  const id = item.telegram_id ?? item.player_id;
  return id != null ? `Игрок ${id}` : "Игрок";
}

function renderPlayerMailRecipientSuggest(items, sectionLabel) {
  const box = document.getElementById("player-mail-recipient-suggest");
  if (!box) return;
  if (!items.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const head = sectionLabel
    ? `<div class="player-mail-suggest-section">${escapeHtml(sectionLabel)}</div>`
    : "";
  box.innerHTML =
    head +
    items
      .map((item) => {
        const pid = Number(item.telegram_id ?? item.player_id);
        const label = escapeHtml(playerMailRecipientRowLabel(item));
        return `<button type="button" class="player-mail-suggest-row" data-player-id="${pid}" data-label="${label}">${label}</button>`;
      })
      .join("");
  box.hidden = false;
  box.querySelectorAll(".player-mail-suggest-row").forEach((row) => {
    row.addEventListener("click", () => {
      const pid = Number(row.getAttribute("data-player-id"));
      const label = row.getAttribute("data-label") || "";
      playerPageState.mailCompose.recipientId = pid;
      playerPageState.mailCompose.recipientLabel = label;
      const input = document.getElementById("player-mail-recipient-input");
      if (input) input.value = label;
      box.hidden = true;
    });
  });
}

async function loadPlayerMailGuildSuggestions() {
  if (playerPageState.mailGuildSuggestions) return playerPageState.mailGuildSuggestions;
  try {
    const data = await apiFetch("/guilds/me");
    if (!data?.in_guild || !Array.isArray(data.members)) {
      playerPageState.mailGuildSuggestions = [];
      return [];
    }
    const selfId = Number(profileState.currentProfile?.player_id);
    const items = data.members
      .filter((m) => Number(m.player_id) !== selfId)
      .map((m) => ({
        telegram_id: m.player_id,
        username: m.telegram_username,
        first_name: m.display_name,
        character_name: m.main_waifu_name,
      }));
    playerPageState.mailGuildSuggestions = items;
    return items;
  } catch {
    playerPageState.mailGuildSuggestions = [];
    return [];
  }
}

let playerMailSearchTimer = null;

async function searchPlayerMailRecipients(query) {
  const q = (query || "").trim();
  if (q.length < 1) {
    const guild = await loadPlayerMailGuildSuggestions();
    renderPlayerMailRecipientSuggest(guild, guild.length ? "Гильдия" : "");
    const friendsNote = document.getElementById("player-mail-recipient-suggest");
    if (friendsNote && !guild.length) {
      friendsNote.innerHTML = `<p class="muted tiny" style="padding:10px 12px">Друзья — скоро</p>`;
      friendsNote.hidden = false;
    }
    return;
  }
  try {
    const data = await apiFetch(`/players/search?q=${encodeURIComponent(q)}`);
    const items = Array.isArray(data?.items) ? data.items : [];
    const selfId = Number(profileState.currentProfile?.player_id);
    const filtered = items.filter((it) => Number(it.telegram_id) !== selfId);
    renderPlayerMailRecipientSuggest(filtered, filtered.length ? "Поиск" : "");
    if (!filtered.length) {
      const box = document.getElementById("player-mail-recipient-suggest");
      if (box) {
        box.innerHTML = `<p class="muted tiny" style="padding:10px 12px">Никого не найдено</p>`;
        box.hidden = false;
      }
    }
  } catch {
    const box = document.getElementById("player-mail-recipient-suggest");
    if (box) {
      box.innerHTML = `<p class="muted tiny" style="padding:10px 12px">Ошибка поиска</p>`;
      box.hidden = false;
    }
  }
}

function initPlayerMailTabs() {
  if (window.__waifuPlayerMailTabsBound) return;
  window.__waifuPlayerMailTabsBound = true;
  document.querySelectorAll(".player-mail-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-mail-tab");
      if (tab) setPlayerMailTab(tab);
    });
  });
}

function initPlayerMailCompose() {
  if (window.__waifuPlayerMailComposeBound) return;
  window.__waifuPlayerMailComposeBound = true;
  const input = document.getElementById("player-mail-recipient-input");
  const suggest = document.getElementById("player-mail-recipient-suggest");
  const itemBtn = document.getElementById("player-mail-tab-item-btn");
  const sendBtn = document.getElementById("player-mail-tab-send");

  input?.addEventListener("focus", () => {
    searchPlayerMailRecipients(input.value).catch(() => {});
  });
  input?.addEventListener("input", () => {
    const q = input.value.trim();
    playerPageState.mailCompose.recipientId = null;
    clearTimeout(playerMailSearchTimer);
    playerMailSearchTimer = setTimeout(() => {
      searchPlayerMailRecipients(q).catch(() => {});
    }, 280);
  });
  document.addEventListener("click", (ev) => {
    if (!suggest || suggest.hidden) return;
    if (ev.target === input || suggest.contains(ev.target)) return;
    suggest.hidden = true;
  });
  itemBtn?.addEventListener("click", () => openPlayerMailItemPicker());
  sendBtn?.addEventListener("click", () => sendPlayerMail());
}

function togglePlayerOverflowMenu(ev) {
  ev?.stopPropagation();
  const menu = document.getElementById("player-overflow-menu");
  if (menu) menu.hidden = !menu.hidden;
}

function initPlayerOverflowMenu() {
  if (window.__waifuPlayerOverflowBound) return;
  window.__waifuPlayerOverflowBound = true;
  const menu = document.getElementById("player-overflow-menu");
  const backBtn = document.getElementById("player-topbar-back");
  document.querySelectorAll("#player-overflow-btn, #player-topbar-overflow-btn").forEach((btn) => {
    if (menu) {
      btn.addEventListener("click", togglePlayerOverflowMenu);
    }
  });
  if (menu) {
    document.addEventListener("click", () => {
      if (menu) menu.hidden = true;
    });
    menu.addEventListener("click", (ev) => ev.stopPropagation());
    menu.querySelectorAll("[data-player-section]").forEach((item) => {
      item.addEventListener("click", () => {
        const sec = item.getAttribute("data-player-section");
        if (sec) {
          if (sec === "overview") {
            history.replaceState(null, "", window.location.pathname + window.location.search);
            openPlayerSection("overview");
          } else {
            window.location.hash = sec;
            openPlayerSection(sec);
          }
        }
        menu.hidden = true;
      });
    });
  }
  if (backBtn) {
    backBtn.addEventListener("click", () => {
      history.replaceState(null, "", window.location.pathname + window.location.search);
      openPlayerSection("overview");
    });
  }
}

function initPlayerShowcaseToggle() {
  if (window.__waifuPlayerShowcaseBound) return;
  window.__waifuPlayerShowcaseBound = true;
  document.querySelectorAll(".player-showcase-switch-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-showcase");
      if (!mode || playerPageState.isViewMode) return;
      const prev = playerPageState.profileData?.profile_showcase;
      const data = { ...(playerPageState.profileData || {}), profile_showcase: mode };
      playerPageState.profileData = data;
      renderPlayerWaifuShowcase(data);
      apiFetch("/player/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_showcase: mode }),
      })
        .then((res) => {
          playerPageState.profileData = res;
          renderPlayerWaifuShowcase(res);
        })
        .catch((e) => {
          const rollback = {
            ...(playerPageState.profileData || {}),
            profile_showcase: prev || "portrait",
          };
          playerPageState.profileData = rollback;
          renderPlayerWaifuShowcase(rollback);
          const { detail } = parseHttpErrorDetail(e);
          showToast(detail || "Не удалось сохранить", "error");
        });
    });
  });
}

function fillPlayerAvatarPresetGrid(grid, closeModal) {
  if (!grid || grid.__filled) return;
  grid.__filled = true;
  let html = "";
  for (let i = 1; i <= PLAYER_AVATAR_PRESET_COUNT; i++) {
    const url = `/static/game/ui/player-avatars/preset-${String(i).padStart(2, "0")}.webp`;
    html += `<button type="button" class="player-avatar-preset-btn" data-preset-id="${i}" aria-label="Пресет ${i}"><img src="${url}" alt="" loading="lazy" decoding="async" /></button>`;
  }
  grid.innerHTML = html;
  grid.querySelectorAll(".player-avatar-preset-btn").forEach((b) => {
    b.addEventListener("click", async () => {
      const pid = Number(b.getAttribute("data-preset-id"));
      try {
        const data = await apiFetch("/player/profile", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ avatar_preset_id: pid, clear_custom_avatar: true }),
        });
        playerPageState.cachedAvatarUrl = data.avatar_url;
        applyPlayerProfilePayload(data, profileState.currentProfile);
        applyPlayerAvatarUrl(data.avatar_url, profileState.currentProfile);
        if (typeof closeModal === "function") closeModal();
      } catch (e) {
        const { detail } = parseHttpErrorDetail(e);
        showToast(detail || "Ошибка", "error");
      }
    });
  });
}

function initPlayerAvatarModal() {
  if (window.__waifuPlayerAvatarModalBound) return;
  window.__waifuPlayerAvatarModalBound = true;
  const openBtn = document.getElementById("player-hero-avatar-btn");
  const modal = document.getElementById("player-avatar-modal");
  const closeBtn = document.getElementById("player-avatar-modal-close");
  const grid = document.getElementById("player-avatar-preset-grid");
  const fileInput = document.getElementById("player-avatar-file-input");
  const resetBtn = document.getElementById("player-avatar-reset-preset");

  const closeModal = () => {
    if (!modal) return;
    modal.classList.remove("player-avatar-modal--open");
    modal.style.display = "none";
  };

  const openModal = () => {
    if (playerPageState.isViewMode || !modal) return;
    fillPlayerAvatarPresetGrid(grid, closeModal);
    const cur = playerPageState.profileData?.avatar_preset_id || 1;
    grid?.querySelectorAll(".player-avatar-preset-btn").forEach((x) => {
      x.classList.toggle("selected", Number(x.getAttribute("data-preset-id")) === Number(cur));
    });
    modal.style.display = "";
    modal.classList.add("player-avatar-modal--open");
  };

  openBtn?.addEventListener("click", openModal);
  closeBtn?.addEventListener("click", closeModal);
  modal?.addEventListener("click", (ev) => {
    if (ev.target === modal) closeModal();
  });

  resetBtn?.addEventListener("click", async () => {
    try {
      const data = await apiFetch("/player/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ avatar_preset_id: 1, clear_custom_avatar: true }),
      });
      playerPageState.cachedAvatarUrl = data.avatar_url;
      applyPlayerProfilePayload(data, profileState.currentProfile);
      applyPlayerAvatarUrl(data.avatar_url, profileState.currentProfile);
      closeModal();
    } catch (e) {
      const { detail } = parseHttpErrorDetail(e);
      showToast(detail || "Ошибка", "error");
    }
  });

  fileInput?.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/player/avatar/upload`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.error || err.detail || res.statusText);
      }
      const data = await res.json();
      playerPageState.cachedAvatarUrl = data.avatar_url;
      const full = await apiFetch("/player/profile");
      applyPlayerProfilePayload(full, profileState.currentProfile);
      applyPlayerAvatarUrl(data.avatar_url, profileState.currentProfile);
      fileInput.value = "";
      closeModal();
    } catch (e) {
      showToast(String(e.message || e) || "Не удалось загрузить", "error");
    }
  });
}

async function initPlayerPage(profile, opts = {}) {
  const fallback = profile || profileState.currentProfile || {};
  const viewId = getPlayerViewIdFromQuery();
  let selfId = fallback?.player_id != null ? Number(fallback.player_id) : null;
  if (opts.preloadedPlayerProfile?.player_id != null && opts.preloadedPlayerProfile?.is_self) {
    selfId = Number(opts.preloadedPlayerProfile.player_id);
  }
  playerPageState.viewPlayerId = viewId;
  playerPageState.selfPlayerId = selfId;
  playerPageState.isViewMode = viewId != null && (selfId == null || viewId !== selfId);

  initPlayerOverflowMenu();
  initPlayerShowcaseToggle();
  initPlayerAvatarModal();
  initPlayerMailTabs();
  initPlayerMailCompose();
  bindPlayerPageLifecycle();
  syncPlayerViewModeUi();

  try {
    if (opts.preloadedPlayerProfile != null) {
      applyPlayerProfilePayload(opts.preloadedPlayerProfile, fallback);
    } else if (playerPageState.isViewMode) {
      await loadPublicPlayerProfile(viewId, fallback);
    } else {
      await loadSelfPlayerProfile(fallback);
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить профиль", "error");
  }

  applyPlayerHashSection();
}

async function refreshMailInbox() {
  try {
    const [inbox, badge] = await Promise.all([
      apiFetch("/mail/inbox?limit=50"),
      apiFetch("/mail/badge").catch(() => ({ unread: 0, pending_rewards: 0 })),
    ]);
    guildHallState.mailState.inbox = Array.isArray(inbox?.items) ? inbox.items : [];
    guildHallState.mailState.unreadCount = safeInt(badge?.unread, 0);
    guildHallState.mailState.pendingRewards = safeInt(badge?.pending_rewards, 0);
    renderMailInbox();
    await refreshAtticMailBadge();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const root = document.getElementById("mail-inbox-root");
    if (root) root.innerHTML = `<p class="muted" style="color:#f87171">${escapeHtml(detail || "Не удалось загрузить почту")}</p>`;
  }
}

function formatMailListDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    if (sameDay) {
      return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  } catch {
    return "";
  }
}

function renderMailInbox() {
  const root = document.getElementById("mail-inbox-root");
  const isPlayerPage = document.body.classList.contains("page-player");
  if (!root) return;
  const items = guildHallState.mailState.inbox;
  if (!items.length) {
    root.innerHTML = `<p class="muted">Входящих писем нет.</p>`;
    return;
  }
  if (isPlayerPage) {
    root.innerHTML = items
      .map((m) => {
        const unread = m.status === "unread";
        const sender = escapeHtml(m.sender_label || "Игрок");
        const date = escapeHtml(formatMailListDate(m.created_at));
        const readMark = unread ? "" : `<span class="mail-inbox-read-mark muted tiny">прочитано</span>`;
        return `<button type="button" class="mail-inbox-row${unread ? " unread" : ""}" onclick="WaifuApp.openMailDetail(${Number(m.id)})">
          <span class="mail-inbox-dot" aria-hidden="true"></span>
          <span class="mail-inbox-row-main">
            <span class="mail-inbox-sender">${unread ? `<strong>${sender}</strong>` : sender} ${readMark}</span>
            <span class="mail-inbox-date">${date}</span>
          </span>
        </button>`;
      })
      .join("");
    return;
  }
  root.innerHTML = items
    .map((m) => {
      const unread = m.status === "unread";
      const attach = [];
      if (m.gold_amount > 0) attach.push(`🪙 ${Number(m.gold_amount).toLocaleString("ru-RU")}`);
      if (m.inventory_item_id) attach.push("📦 предмет");
      const preview = (m.body_text || attach.join(" · ") || "—").slice(0, 80);
      return `<button type="button" class="mail-inbox-row${unread ? " unread" : ""}" onclick="WaifuApp.openMailDetail(${Number(m.id)})">
        <span class="mail-inbox-dot"></span>
        <span style="flex:1;min-width:0">
          <strong>${escapeHtml(m.sender_label || "Игрок")}</strong>
          <div class="muted tiny">${escapeHtml(preview)}</div>
        </span>
      </button>`;
    })
    .join("");
}

async function openMailDetail(mailId) {
  const id = Number(mailId);
  if (!Number.isFinite(id)) return;
  try {
    const mail = await apiFetch(`/mail/${encodeURIComponent(id)}`);
    guildHallState.mailState.selectedId = id;
    const panel = document.getElementById("mail-detail-root");
    if (!panel) return;
    const attach = [];
    if (mail.gold_amount > 0) attach.push(`🪙 ${Number(mail.gold_amount).toLocaleString("ru-RU")} золота`);
    if (mail.item_name) attach.push(`📦 ${mail.item_name}`);
    const canClaim =
      mail.status !== "claimed" && (mail.gold_amount > 0 || mail.inventory_item_id);
    panel.innerHTML = `<div class="mail-detail-panel">
      <p><strong>От:</strong> ${escapeHtml(mail.sender_label || "Игрок")}</p>
      <p class="muted tiny">${escapeHtml(new Date(mail.created_at).toLocaleString("ru-RU"))}</p>
      ${mail.body_text ? `<p>${escapeHtml(mail.body_text)}</p>` : ""}
      ${attach.length ? `<p>${attach.map((a) => escapeHtml(a)).join("<br>")}</p>` : ""}
      ${canClaim ? `<button type="button" class="btn primary" onclick="WaifuApp.claimMail(${id})">Забрать награду</button>` : ""}
      <button type="button" class="btn secondary" style="margin-top:8px" onclick="WaifuApp.deleteMail(${id})">Удалить</button>
    </div>`;
    panel.hidden = false;
    await refreshMailInbox();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось открыть письмо", "error");
  }
}

async function claimMail(mailId) {
  try {
    await apiFetch(`/mail/${encodeURIComponent(mailId)}/claim`, { method: "POST" });
    showToast("Награда получена");
    await openMailDetail(mailId);
    await refreshMailInbox();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось забрать награду", "error");
  }
}

async function deleteMail(mailId) {
  try {
    await apiFetch(`/mail/${encodeURIComponent(mailId)}`, { method: "DELETE" });
    showToast("Письмо удалено");
    const panel = document.getElementById("mail-detail-root");
    if (panel) {
      panel.innerHTML = "";
      panel.hidden = true;
    }
    await refreshMailInbox();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось удалить", "error");
  }
}

function onGuildBannerClick() {
  const inp = document.getElementById("guild-banner-file-input");
  if (inp) inp.click();
}

function onGuildEmblemClick() {
  const inp = document.getElementById("guild-icon-file-input");
  if (inp) inp.click();
  else {
    const hidden = document.createElement("input");
    hidden.type = "file";
    hidden.accept = "image/jpeg,image/png,image/webp";
    hidden.id = "guild-icon-file-input";
    hidden.style.display = "none";
    hidden.onchange = () => uploadGuildIcon(hidden);
    document.body.appendChild(hidden);
    hidden.click();
  }
}

async function uploadGuildBanner(fileInput) {
  const file = fileInput?.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch(`${API_BASE}/guilds/me/banner`, {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      showToast(guildApiErrorToUser(detail?.detail || detail, "Не удалось загрузить баннер"), "error");
      return;
    }
    showToast("Баннер гильдии обновлён");
    if (fileInput) fileInput.value = "";
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function uploadGuildIcon(fileInput) {
  const file = fileInput?.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch(`${API_BASE}/guilds/me/icon`, {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text || "failed"}`);
    }
    showToast("Эмблема обновлена");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail || "Ошибка загрузки"), "error");
  } finally {
    if (fileInput) fileInput.value = "";
  }
}

function guildCreateErrorToUser(detail) {
  return guildApiErrorToUser(detail, "Не удалось создать гильдию");
}

async function createGuildFromHall() {
  const nameEl = document.getElementById("guild-create-name");
  const tagEl = document.getElementById("guild-create-tag");
  const descEl = document.getElementById("guild-create-desc");
  const errEl = document.getElementById("guild-create-error");
  const btn = document.getElementById("guild-create-btn");
  const name = (nameEl?.value || "").trim();
  const tag = (tagEl?.value || "").trim();
  const description = (descEl?.value || "").trim();
  if (!name || !tag) {
    if (errEl) errEl.textContent = "Укажите название и тег.";
    return;
  }
  if (errEl) errEl.textContent = "";
  if (btn) btn.disabled = true;
  try {
    let qs = `?name=${encodeURIComponent(name)}&tag=${encodeURIComponent(tag)}`;
    if (description) qs += `&description=${encodeURIComponent(description)}`;
    await apiFetch(`/guilds${qs}`, { method: "POST" });
    showToast("Гильдия создана");
    await loadProfile().catch(() => {});
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const msg = guildCreateErrorToUser(detail);
    if (errEl) errEl.textContent = msg;
    else showToast(msg, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function joinGuildFromSearch(guildId) {
  try {
    const res = await apiFetch(`/guilds/${encodeURIComponent(guildId)}/join`, { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось вступить"), "error");
      return;
    }
    showToast("Вы вступили в гильдию");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function leaveGuildFromHall() {
  if (!confirm("Покинуть гильдию?")) return;
  try {
    const res = await apiFetch("/guilds/leave", { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось выйти"), "error");
      return;
    }
    showToast("Вы покинули гильдию");
    guildHallState.tab = "search";
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function toggleGuildRaidParticipant(playerId, checked) {
  const pid = Number(playerId);
  const set = new Set(guildHallState.raidParticipantIds.map(Number));
  const maxSlots = safeInt(guildHallState.me?.raid?.raid_party_slots, 10) || 10;
  if (checked) {
    if (set.size >= maxSlots) {
      showToast(`Максимум ${maxSlots} участников`, "error");
      void renderGuildTabContent();
      return;
    }
    set.add(pid);
  } else set.delete(pid);
  guildHallState.raidParticipantIds = [...set];
  updateGuildRaidPickedCount();
}

async function startGuildRaidMuster() {
  const d = guildHallState.me;
  const chatId = guildHallState.raidChatId;
  if (!chatId) {
    showToast("Сначала выберите чат для рейда", "error");
    return;
  }
  const pids = guildHallState.raidParticipantIds.filter((x) => Number(x) > 0);
  if (pids.length < 2) {
    showToast("Выберите минимум 2 участников", "error");
    return;
  }
  try {
    const res = await apiFetch("/guilds/raid/muster", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ participant_ids: pids, chat_id: chatId }),
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось начать сбор"), "error");
      return;
    }
    closeGuildRaidParticipantModal();
    guildHallState.raidChatId = null;
    guildHallState.raidChatTitle = null;
    guildHallState.raidEligibleMembers = null;
    guildHallState.raidParticipantIds = [];
    showToast("Сбор начат — приглашения в личку (3 ч)");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function startGuildRaid(templateId) {
  const d = guildHallState.me;
  const chatId = getGuildRaidChatId(d);
  if (!chatId) {
    showToast("Откройте WebApp из группового чата бота или привяжите chat_id гильдии", "error");
    return;
  }
  const pids = guildHallState.raidParticipantIds.filter((x) => Number(x) > 0);
  if (pids.length < 2) {
    showToast("Выберите минимум 2 участников", "error");
    return;
  }
  try {
    const res = await apiFetch("/guilds/raid/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template_id: Number(templateId),
        participant_ids: pids,
        chat_id: chatId,
      }),
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось начать рейд"), "error");
      return;
    }
    showToast("Рейд начат");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function leaveGuildRaid() {
  try {
    const res = await apiFetch("/guilds/raid/leave", { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Ошибка"), "error");
      return;
    }
    showToast(res?.raid_cancelled ? "Рейд завершён — можно начать новый" : "Вы вышли из рейда");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail, "error");
  }
}

async function cancelGuildRaid() {
  if (!confirmAction("Отменить текущий рейд? Отряд не получит награду.")) return;
  try {
    const res = await apiFetch("/guilds/raid/cancel", { method: "POST" });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Ошибка"), "error");
      return;
    }
    showToast("Рейд отменён — можно начать новый");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function loadGuildWarTargets() {
  try {
    const data = await apiFetch("/guilds/war/targets");
    if (data?.error) {
      guildHallState.warTargets = [];
      return [];
    }
    guildHallState.warTargets = data.targets || [];
    return guildHallState.warTargets;
  } catch {
    guildHallState.warTargets = [];
    return [];
  }
}

async function declareGuildWar(targetGuildId, stakeGold) {
  try {
    const res = await apiFetch("/guilds/war/declare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_guild_id: Number(targetGuildId), stake_gold: safeInt(stakeGold, 0) }),
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Не удалось объявить войну"), "error");
      return;
    }
    showToast("Война объявлена");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

async function respondGuildWar(warId, accept) {
  try {
    const res = await apiFetch("/guilds/war/respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ war_id: Number(warId), accept: Boolean(accept) }),
    });
    if (res?.error) {
      showToast(guildApiErrorToUser(res, "Ошибка ответа"), "error");
      return;
    }
    showToast(accept ? "Война принята" : "Война отклонена");
    await refreshGuildHall({ force: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function renderGuildSkillsGrid(d) {
  return renderGuildSkillsPanel(d);
}

const GUILD_SKILL_BRANCH_COMBAT = new Set([
  "gd_party_damage_pct",
  "raid_attack_flat",
  "raid_boss_damage_pct",
  "raid_completion_reward_pct",
  "damage_per_online_member_pct",
  "raid_gxp_multiplier",
]);
const GUILD_SKILL_BRANCH_DEFENSE = new Set(["max_hp_pct", "raid_monster_damage_reduction_pct"]);
const GUILD_SKILL_EFFECT_LABELS = {
  gd_party_damage_pct: "Урон отряда в GD",
  raid_attack_flat: "Атака в рейдах",
  raid_boss_damage_pct: "Урон боссам в рейде",
  raid_completion_reward_pct: "Награда за рейд",
  damage_per_online_member_pct: "Урон за каждого онлайн участника",
  raid_gxp_multiplier: "Множитель GXP рейда",
  max_hp_pct: "Макс. HP",
  raid_monster_damage_reduction_pct: "Снижение урона монстров в рейде",
  monster_gold_pct: "Золото с монстров",
  dungeon_exp_pct: "Опыт в подземельях",
  bank_slots_bonus: "Слоты банка",
  item_drop_pct: "Шанс выпадения предметов",
  tavern_heal_discount_pct: "Скидка на лечение в таверне",
  tavern_hire_discount_pct: "Скидка на найм",
  global_reward_pct: "Глобальный бонус наград",
};
const GUILD_SKILL_BRANCH_ICONS = {
  combat: ["⚔️", "🗡️", "💥", "🔥", "⚡", "🎯"],
  defense: ["🛡️", "🗿", "💪", "🧱"],
  utility: ["🪙", "💰", "📦", "✨", "🏦", "🍺"],
};

function guildSkillBranch(sk) {
  const p = String(sk?.effect_param || "");
  if (GUILD_SKILL_BRANCH_COMBAT.has(p)) return "combat";
  if (GUILD_SKILL_BRANCH_DEFENSE.has(p)) return "defense";
  return "utility";
}

function formatGuildSkillEffectValue(param, val) {
  if (val == null) return "—";
  const n = Number(val);
  if (!Number.isFinite(n)) return String(val);
  const key = String(param || "");
  if (key.endsWith("_multiplier")) {
    return `×${n % 1 === 0 ? n : n.toFixed(1)}`;
  }
  if (key.endsWith("_flat") || key === "bank_slots_bonus") {
    return `+${n % 1 === 0 ? n : n}`;
  }
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  const shown = pct % 1 === 0 ? pct : Math.round(pct * 10) / 10;
  return `+${shown}%`;
}

function formatGuildSkillEffectDesc(sk) {
  const param = String(sk?.effect_param || "");
  const label = GUILD_SKILL_EFFECT_LABELS[param] || sk.name || "Эффект";
  const cur = safeInt(sk.current_level, 0);
  const eff = Array.isArray(sk.effect_per_level) ? sk.effect_per_level : [];
  if (cur >= 3 && eff[2] != null) {
    return `${label} <span class="guild-skill-desc-gold">${formatGuildSkillEffectValue(param, eff[2])}</span>`;
  }
  const fmtCur =
    cur > 0 && eff[cur - 1] != null
      ? `<span class="guild-skill-desc-current">${formatGuildSkillEffectValue(param, eff[cur - 1])}</span>`
      : "";
  const fmtNext =
    cur < 3 && eff[cur] != null
      ? `<span class="guild-skill-desc-arrow"> ➔ </span><span class="guild-skill-desc-next">${formatGuildSkillEffectValue(param, eff[cur])}</span>`
      : "";
  if (cur > 0 && fmtNext) return `${label} ${fmtCur}${fmtNext}`;
  if (cur > 0) return `${label} ${fmtCur}`;
  if (eff[0] != null) {
    return `${label} <span class="guild-skill-desc-current">${formatGuildSkillEffectValue(param, eff[0])}</span>`;
  }
  return label;
}

function guildSkillIcon(sk, branch, locked) {
  if (locked) return "🔒";
  const icons = GUILD_SKILL_BRANCH_ICONS[branch] || ["✨"];
  const idx = (safeInt(sk.sort_order, safeInt(sk.id, 0)) - 1) % icons.length;
  return icons[idx] || icons[0];
}

function renderGuildSkillCard(sk, d) {
  const cur = safeInt(sk.current_level, 0);
  const guildLevel = safeInt(d?.guild_level, 1);
  const tierUnlock = safeInt(d?.skill_tier_unlock, 1);
  const glReq = safeInt(sk.guild_level_req, 1);
  const tier = safeInt(sk.tier, 1);
  const locked = guildLevel < glReq || tier > tierUnlock;
  const maxed = cur >= 3;
  const branch = guildSkillBranch(sk);
  const cost = guildSkillUpgradeCost(sk);
  const canUp = !locked && !maxed && guildSkillCanUpgrade(sk, d);
  const blockReason = sk.upgrade_block_reason;
  const avatarClass = locked
    ? "guild-skill-card-avatar guild-skill-card-avatar--locked"
    : `guild-skill-card-avatar guild-skill-card-avatar--${branch}`;
  const icon = guildSkillIcon(sk, branch, locked);
  const pips = [0, 1, 2]
    .map((i) => {
      const filled = i < cur;
      const cls = maxed && filled
        ? "guild-skill-card-pip guild-skill-card-pip--gold"
        : filled
          ? "guild-skill-card-pip guild-skill-card-pip--filled"
          : "guild-skill-card-pip";
      return `<div class="${cls}"></div>`;
    })
    .join("");
  let lockReq = "";
  if (locked) {
    if (guildLevel < glReq) {
      lockReq = `<div class="guild-skill-card-req">Требуется ${glReq} уровень гильдии</div>`;
    } else if (tier > tierUnlock) {
      lockReq = `<div class="guild-skill-card-req">Требуется тир навыков ${tier}</div>`;
    }
  }
  let action = "";
  if (maxed) {
    action = `<span class="guild-skill-badge-max">Изучено</span>`;
  } else if (locked) {
    action = `<button type="button" class="guild-skill-card-upgrade" disabled aria-label="Заблокировано">🔒</button>`;
  } else if (canUp) {
    action = `<button type="button" class="guild-skill-card-upgrade guild-skill-card-upgrade--primary" onclick="event.stopPropagation();WaifuApp.guildSkillUpgrade(${Number(sk.id)})"><span class="guild-skill-card-upgrade-plus">+</span><span class="guild-skill-card-upgrade-cost">${cost} ОПГ</span></button>`;
  } else {
    const reasonText = escapeHtml(guildSkillBlockReasonRu(sk, d, blockReason));
    action = `<button type="button" class="guild-skill-card-upgrade" disabled onclick="event.stopPropagation()" title="${reasonText}"><span class="guild-skill-card-upgrade-plus">+</span><span class="guild-skill-card-upgrade-cost">${cost} ОПГ</span></button>`;
  }
  const cardClass = `guild-skill-card${maxed ? " maxed" : ""}${locked ? " locked" : ""}`;
  const lvlLabel = maxed
    ? `<span class="guild-skill-card-level guild-skill-card-level--gold">МАКС. ур.</span>`
    : `<span class="guild-skill-card-level">ур. ${cur}/3</span>`;
  return `<div class="${cardClass}" role="button" tabindex="0" onclick="WaifuApp.openGuildSkillModal(${Number(sk.id)})">
    <div class="guild-skill-card-main">
      <div class="${avatarClass}">${icon}</div>
      <div class="guild-skill-card-body">
        <div class="guild-skill-card-title-row">
          <strong class="guild-skill-card-name">${escapeHtml(sk.name || "")}</strong>
          ${lvlLabel}
        </div>
        <p class="guild-skill-card-desc">${formatGuildSkillEffectDesc(sk)}</p>
        ${lockReq}
        <div class="guild-skill-card-pips">${pips}</div>
      </div>
    </div>
    <div class="guild-skill-card-action">${action}</div>
  </div>`;
}

function renderGuildSkillsPanel(d) {
  const avail = safeInt(d?.skill_points_available, 0);
  const spent = safeInt(d?.skill_points_spent, 0);
  const total = safeInt(d?.skill_points_total, 0);
  const activeBranch = guildHallState.skillsBranch || "combat";
  const branches = [
    { id: "combat", icon: "⚔️", label: "Боевые" },
    { id: "defense", icon: "🛡️", label: "Защитные" },
    { id: "utility", icon: "💰", label: "Мирные" },
  ];
  const resetBtn = isGuildLeader(d)
    ? `<button type="button" class="guild-skills-panel-reset" onclick="WaifuApp.guildSkillReset()">🔄 Сбросить</button>`
    : "";
  const tabs = branches
    .map(
      (b) =>
        `<button type="button" role="tab" aria-selected="${activeBranch === b.id ? "true" : "false"}" class="guild-skills-panel-tab${activeBranch === b.id ? " active" : ""}" onclick="WaifuApp.switchGuildSkillsBranch('${b.id}')"><span>${b.icon}</span> ${b.label}</button>`
    )
    .join("");
  const defs = Array.isArray(d?.definitions) ? d.definitions : [];
  const branchSkills = defs
    .filter((sk) => guildSkillBranch(sk) === activeBranch)
    .sort(
      (a, b) =>
        safeInt(a.sort_order, safeInt(a.id, 0)) - safeInt(b.sort_order, safeInt(b.id, 0))
    );
  const cards = branchSkills.map((sk) => renderGuildSkillCard(sk, d)).join("");
  return `
    <div class="guild-skills-panel">
      <div class="guild-skills-panel-header">
        <div>
          <div class="guild-skills-panel-title">Навыки гильдии</div>
          <p class="guild-skills-panel-sp">Доступно: <strong>${avail} ОПГ</strong> <em>(распределено: ${spent}/${total})</em></p>
        </div>
        ${resetBtn}
      </div>
      <div class="guild-skills-panel-tabs" role="tablist">${tabs}</div>
      <div class="guild-skills-panel-list" role="tabpanel">${cards || `<p class="muted tiny">Нет навыков в этой ветке.</p>`}</div>
    </div>`;
}

function switchGuildSkillsBranch(branchId) {
  guildHallState.skillsBranch = branchId || "combat";
  void renderGuildTabContent();
}

function formatGuildBankGold(n) {
  return safeInt(n, 0).toLocaleString("ru-RU");
}

function compareGuildBankItems(a, b) {
  const sortKey = guildHallState.bankSort || "level";
  const dir = guildHallState.bankSortDir === "asc" ? 1 : -1;
  const rarityA = safeNumber(a?.rarity, 1);
  const rarityB = safeNumber(b?.rarity, 1);
  const levelA = safeNumber(a?.level, 0);
  const levelB = safeNumber(b?.level, 0);
  let result = 0;
  if (sortKey === "level") result = levelA - levelB || rarityA - rarityB;
  if (sortKey === "rarity") result = rarityA - rarityB || levelA - levelB;
  if (sortKey === "type") {
    const typeA = slotTypeLabel(a?.slot_type).toLowerCase();
    const typeB = slotTypeLabel(b?.slot_type).toLowerCase();
    result = typeA.localeCompare(typeB, "ru") || levelA - levelB || rarityA - rarityB;
  }
  if (result === 0) {
    const nameA = String(a?.display_name || a?.name || "").toLowerCase();
    const nameB = String(b?.display_name || b?.name || "").toLowerCase();
    result = nameA.localeCompare(nameB, "ru");
  }
  return result * dir;
}

function getGuildBankFilteredSortedItems() {
  const items = Array.isArray(guildHallState.bankItems) ? guildHallState.bankItems : [];
  return items
    .filter((item) => guildHallState.bankFilters[getProfileItemCategory(item)])
    .sort(compareGuildBankItems);
}

function toggleGuildBankFilter(category) {
  if (!Object.prototype.hasOwnProperty.call(guildHallState.bankFilters, category)) return;
  guildHallState.bankFilters[category] = !guildHallState.bankFilters[category];
  guildHallState.bankPage = 1;
  void renderGuildTabContent();
}

function setGuildBankSort(value) {
  guildHallState.bankSort = ["level", "rarity", "type"].includes(value) ? value : "level";
  guildHallState.bankPage = 1;
  void renderGuildTabContent();
}

function toggleGuildBankSortDir() {
  guildHallState.bankSortDir = guildHallState.bankSortDir === "asc" ? "desc" : "asc";
  void renderGuildTabContent();
}

function renderGuildBankItemCell(it) {
  const rCls = rarityClassFromValue(it?.rarity);
  return `<button type="button" class="guild-bank-item-cell ${rCls}" onclick="WaifuApp.openGuildBankItemModal(${Number(it.bank_item_id)})" aria-label="${escapeHtml(composeItemDisplayName(it))}">
    <span class="guild-bank-item-cell-art">${itemArtHtml(it)}</span>
  </button>`;
}

function renderGuildBankPanel(d) {
  const maxItems = safeInt(d?.max_bank_items, 100);
  const count = safeInt(d?.bank_items_count, 0);
  const page = Math.max(1, guildHallState.bankPage);
  const pageSize = guildHallState.bankPageSize;
  const allItems = Array.isArray(guildHallState.bankItems) ? guildHallState.bankItems : [];
  const items = getGuildBankFilteredSortedItems();
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize) || 1);
  const safePage = Math.min(page, totalPages);
  if (safePage !== page) guildHallState.bankPage = safePage;
  const start = (safePage - 1) * pageSize;
  const slice = items.slice(start, start + pageSize);
  const sortDirIcon = guildHallState.bankSortDir === "asc" ? "▲" : "▼";
  const sortOptions = [
    { value: "level", label: "Ур." },
    { value: "rarity", label: "Ред." },
    { value: "type", label: "Тип" },
  ];
  const sortSelectHtml = sortOptions
    .map(
      (opt) =>
        `<option value="${opt.value}"${guildHallState.bankSort === opt.value ? " selected" : ""}>${opt.label}</option>`
    )
    .join("");

  const cells = [];
  for (let i = 0; i < pageSize; i += 1) {
    if (i < slice.length) {
      cells.push(renderGuildBankItemCell(slice[i]));
    } else {
      cells.push(`<div class="guild-bank-item-cell guild-bank-item-cell--empty" aria-hidden="true"></div>`);
    }
  }

  const emptyNote = !allItems.length
    ? `<p class="guild-bank-items-empty-note muted tiny">Банк пуст.</p>`
    : !items.length
      ? `<p class="guild-bank-items-empty-note muted tiny">Нет предметов по выбранным фильтрам.</p>`
      : "";

  const pager =
    totalPages > 1
      ? `<div class="guild-bank-pagination">
          <button type="button" class="guild-bank-pag-btn" ${safePage <= 1 ? "disabled" : ""} onclick="WaifuApp.guildBankPrevPage()">← Назад</button>
          <span class="guild-bank-pag-info">Стр. ${safePage}</span>
          <button type="button" class="guild-bank-pag-btn" ${safePage >= totalPages ? "disabled" : ""} onclick="WaifuApp.guildBankNextPage()">Вперёд →</button>
        </div>`
      : "";

  return `
    <div class="guild-bank-panel">
      <div class="guild-bank-top-row">
        <div class="guild-bank-gold-panel">
          <div class="guild-bank-gold-box">
            <span class="guild-bank-gold-value">${formatGuildBankGold(d?.bank_gold)}</span>
          </div>
          <div class="guild-bank-gold-actions">
            <button type="button" class="guild-bank-gold-btn guild-bank-gold-btn--deposit" aria-label="Внести золото" onclick="WaifuApp.openGuildBankGoldModal('deposit')">+</button>
            <button type="button" class="guild-bank-gold-btn guild-bank-gold-btn--withdraw" aria-label="Снять золото" onclick="WaifuApp.openGuildBankGoldModal('withdraw')">−</button>
          </div>
        </div>
        <div class="guild-bank-storage-panel">
          <div class="guild-bank-storage-main">
            <span class="guild-bank-storage-count">${count} / ${maxItems}</span>
          </div>
          <button type="button" class="guild-bank-add-item-btn" aria-label="Положить предмет" onclick="WaifuApp.openGuildBankDepositModal()">🤲</button>
        </div>
      </div>
      <div class="guild-bank-items-panel">
        <div class="guild-bank-controls">
          <button type="button" class="guild-bank-filter-btn${guildHallState.bankFilters.weapon ? " active" : ""}" onclick="WaifuApp.toggleGuildBankFilter('weapon')">⚔ Оружие</button>
          <button type="button" class="guild-bank-filter-btn${guildHallState.bankFilters.armor ? " active" : ""}" onclick="WaifuApp.toggleGuildBankFilter('armor')">🛡 Броня</button>
          <button type="button" class="guild-bank-filter-btn${guildHallState.bankFilters.accessory ? " active" : ""}" onclick="WaifuApp.toggleGuildBankFilter('accessory')">💍 Акс.</button>
          <div class="guild-bank-sort-wrap">
            <select class="guild-bank-sort-select" onchange="WaifuApp.setGuildBankSort(this.value)">${sortSelectHtml}</select>
            <button type="button" class="guild-bank-sort-dir" onclick="WaifuApp.toggleGuildBankSortDir()">${sortDirIcon}</button>
          </div>
        </div>
        ${emptyNote}
        <div class="guild-bank-items-grid">${cells.join("")}</div>
        ${pager}
      </div>
    </div>`;
}

function renderGuildBankTab(d) {
  return renderGuildBankPanel(d);
}

function guildBankPrevPage() {
  guildHallState.bankPage = Math.max(1, guildHallState.bankPage - 1);
  void renderGuildTabContent();
}

function guildBankNextPage() {
  const pageSize = guildHallState.bankPageSize;
  const totalPages = Math.max(1, Math.ceil(getGuildBankFilteredSortedItems().length / pageSize));
  guildHallState.bankPage = Math.min(guildHallState.bankPage + 1, totalPages);
  void renderGuildTabContent();
}

function renderGuildRaidPane(d) {
  const raid = d?.raid || {};
  const active = raid?.active_raid;
  const muster = raid?.active_muster;
  const chronicle = Array.isArray(raid?.chronicle) ? raid.chronicle : [];
  const members = Array.isArray(d?.members) ? d.members : [];
  const memberById = Object.fromEntries(members.map((m) => [Number(m.player_id), m]));
  let html = "";

  if (muster && muster.status === "pending") {
    html += `<h4 class="guild-activity-section-title">Сбор на рейд</h4>
      <p class="muted tiny">Подтверждение в личке бота · до ${escapeHtml(muster.deadline_at || "—")}</p>
      <ul class="guild-raid-muster-list">${(muster.participants || [])
        .map((p) => {
          const m = memberById[Number(p.player_id)];
          const nm = m ? guildMemberLabel(m) : `Игрок ${p.player_id}`;
          return `<li>${nm}: <strong>${escapeHtml(guildRaidMusterStatusLabel(p.status))}</strong></li>`;
        })
        .join("")}</ul>`;
  }

  if (active) {
    const isV2 = safeInt(active.raid_version, 1) >= 2;
    if (isV2) {
      const vit = safeInt(active.company_vitality, 0);
      const prog = safeInt(active.story_progress, 0);
      const day = safeInt(active.day_index, 0);
      html += `<h4 class="guild-activity-section-title">Рейд · недельная хроника</h4>
        <p>День ${day} / 7 · локация: ${escapeHtml(active.location_archetype_id || "—")}</p>
        <div class="guild-raid-vitals">
          <div class="guild-raid-vital-row"><span>Выносливость</span><div class="guild-raid-bar"><div class="guild-raid-bar-fill guild-raid-bar-fill--vit" style="width:${vit}%"></div></div><span>${vit}%</span></div>
          <div class="guild-raid-vital-row"><span>Прогресс</span><div class="guild-raid-bar"><div class="guild-raid-bar-fill guild-raid-bar-fill--prog" style="width:${prog}%"></div></div><span>${prog}%</span></div>
        </div>`;
      if (active.prologue_html) {
        html += `<details class="guild-raid-chronicle-entry"><summary>Prologue</summary><div class="guild-raid-narrative">${active.prologue_html}</div></details>`;
      }
      chronicle.forEach((c) => {
        html += `<details class="guild-raid-chronicle-entry"><summary>День ${c.day_index}</summary>
          <div class="guild-raid-narrative">${c.narrative_html || ""}</div>
          ${c.winning_tactic ? `<p class="muted tiny">Тактика: ${escapeHtml(c.winning_tactic.label || "—")}</p>` : ""}
        </details>`;
      });
      if (isGuildLeader(d)) {
        html += `<button type="button" class="btn secondary" style="margin-top:8px" onclick="WaifuApp.cancelGuildRaid()">Отменить рейд</button>`;
      }
      html += `<button type="button" class="btn secondary" style="margin-top:8px" onclick="WaifuApp.leaveGuildRaid()">Покинуть рейд</button>`;
    } else {
      const hpPct =
        active.hp_max > 0 ? Math.round((safeInt(active.hp, 0) / safeInt(active.hp_max, 1)) * 100) : 0;
      html += `<h4 class="guild-activity-section-title">Активный рейд (legacy)</h4>
        <p>Этап ${active.stage ?? "—"} · HP ${active.hp ?? 0}/${active.hp_max ?? 0} (${hpPct}%)</p>`;
      if (isGuildLeader(d)) {
        html += `<button type="button" class="btn secondary" onclick="WaifuApp.cancelGuildRaid()">Отменить рейд</button>`;
      }
      html += `<button type="button" class="btn secondary" onclick="WaifuApp.leaveGuildRaid()">Покинуть рейд</button>`;
    }
  } else if (isGuildLeader(d) && !muster) {
    html += `<h4 class="guild-activity-section-title">Начать рейд</h4>
      <p class="muted tiny">Выберите чат гильдии, затем состав. Участникам придёт рейд-чек в личку (3 ч).</p>
      <button type="button" class="btn primary" onclick="WaifuApp.openGuildRaidChatModal()">Выбрать чат</button>`;
  } else if (!isGuildLeader(d)) {
    html += `<p class="muted tiny">${muster ? "Идёт сбор на рейд." : "Рейд запускает глава гильдии."}</p>`;
  }
  return html;
}

function renderGuildWarPane(d) {
  const war = d?.war;
  const canLead = d?.is_leader;
  let html = "";
  if (!d?.wars_unlocked) {
    return `<p class="muted tiny">Войны гильдий открываются с 10 уровня гильдии.</p>`;
  }
  if (war) {
    const opp = war.opponent;
    const oppName = opp ? `[${opp.tag}] ${opp.name}` : "—";
    html += `<h4 class="guild-activity-section-title">Война</h4>
      <p>Статус: <strong>${escapeHtml(String(war.status || ""))}</strong></p>
      <p>Противник: ${escapeHtml(oppName)}</p>
      <p>Счёт: ${safeInt(war.our_score, 0)} : ${safeInt(war.enemy_score, 0)}</p>`;
    if (war.ends_at) html += `<p class="muted tiny">До конца: ${escapeHtml(war.ends_at)}</p>`;
    if (war.status === "pending" && canLead && war.response_deadline_at) {
      html += `<div style="display:flex;gap:8px;margin-top:8px">
        <button type="button" class="btn primary" onclick="WaifuApp.respondGuildWar(${Number(war.id)}, true)">Принять</button>
        <button type="button" class="btn secondary" onclick="WaifuApp.respondGuildWar(${Number(war.id)}, false)">Отклонить</button>
      </div>`;
    }
    return html;
  }
  if (canLead) {
    html += `<h4 class="guild-activity-section-title">Объявить войну</h4>
      <button type="button" class="btn secondary" onclick="WaifuApp.loadGuildWarTargetsForUi()">Загрузить цели</button>
      <div id="guild-war-targets-list" class="guild-search-results" style="margin-top:8px"></div>`;
  } else {
    html += `<p class="muted tiny">Нет активной войны.</p>`;
  }
  return html;
}

async function loadGuildWarTargetsForUi() {
  const targets = await loadGuildWarTargets();
  const box = document.getElementById("guild-war-targets-list");
  if (!box) return;
  if (!targets.length) {
    box.innerHTML = `<p class="muted tiny">Нет подходящих гильдий.</p>`;
    return;
  }
  box.innerHTML = targets
    .map(
      (g) => `<div class="list-item">
        <strong>[${escapeHtml(g.tag)}] ${escapeHtml(g.name)}</strong> — ур. ${g.level}
        <button type="button" class="btn primary" style="margin-top:6px" onclick="WaifuApp.declareGuildWar(${Number(g.id)}, 0)">Объявить</button>
      </div>`
    )
    .join("");
}

function formatGuildQuestVal(n) {
  const v = safeInt(n, 0);
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(v);
}

function guildQuestCategoryMeta(category) {
  const map = {
    chat: { emoji: "💬", cls: "chat" },
    combat: { emoji: "⚔️", cls: "combat" },
    expedition: { emoji: "🗺️", cls: "expedition" },
    economy: { emoji: "💰", cls: "economy" },
  };
  return map[category] || { emoji: "📋", cls: "chat" };
}

function guildQuestProgressFillClass(category) {
  if (category === "combat") return "red";
  if (category === "expedition") return "amber";
  if (category === "economy") return "green";
  return "blue";
}

function renderGuildQuestLeaders(leaders) {
  if (!Array.isArray(leaders) || !leaders.length) return "";
  const items = leaders
    .map((l, idx) => {
      const name = escapeHtml(l.display_name || "?");
      const initial = name.charAt(0).toUpperCase();
      const url = l.avatar_url ? escapeHtml(l.avatar_url) : "";
      const rankCls = idx === 0 ? " guild-quest-leader-avatar--gold" : idx === 1 ? " guild-quest-leader-avatar--silver" : idx === 2 ? " guild-quest-leader-avatar--bronze" : "";
      const img = url
        ? `<img class="guild-quest-leader-avatar${rankCls}" src="${url}" alt="" title="${name}" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'guild-quest-leader-avatar guild-quest-leader-fallback${rankCls}',textContent:'${initial}',title:'${name}'}))" onclick="WaifuApp.openPlayerProfile(${Number(l.player_id)})" />`
        : `<span class="guild-quest-leader-avatar guild-quest-leader-fallback${rankCls}" title="${name}" onclick="WaifuApp.openPlayerProfile(${Number(l.player_id)})">${initial}</span>`;
      return img;
    })
    .join("");
  return `<div class="guild-quest-leaders">${items}</div>`;
}

function renderGuildQuestTiers(tiers) {
  if (!Array.isArray(tiers) || !tiers.length) return "";
  const items = tiers
    .map((t) => {
      const roman = ["I", "II", "III", "IV", "V"][safeInt(t.tier, 1) - 1] || String(t.tier);
      const st = t.status === "done" ? "done-tier" : t.status === "active" ? "active-tier" : "";
      return `<div class="guild-quest-tier-item ${st}">
        <div class="guild-quest-tier-num ${st}">${roman}</div>
        <div class="guild-quest-tier-val">${formatGuildQuestVal(t.target)}</div>
        <div class="guild-quest-tier-xp">+${safeInt(t.reward_xp, 0)} XP</div>
      </div>`;
    })
    .join("");
  return `<div class="guild-quest-tiers">${items}</div>`;
}

function renderGuildQuestCard(q, { done = false } = {}) {
  const cat = guildQuestCategoryMeta(q.category);
  const fillCls = guildQuestProgressFillClass(q.category);
  const typeLabel =
    q.type === "daily" ? "Ежедневный" : q.type === "weekly" ? "Еженедельный" : "Веха";
  const typeCls = q.type === "daily" ? "daily" : q.type === "weekly" ? "weekly" : "milestone";
  const leaders = renderGuildQuestLeaders(q.leaders);
  const other =
    safeInt(q.other_contributors_count, 0) > 0
      ? `<span class="guild-quest-contrib-more">+${safeInt(q.other_contributors_count, 0)} участников</span>`
      : "";
  const tiers = q.type === "milestone" ? renderGuildQuestTiers(q.tiers) : "";
  const doneBlock = done
    ? `<div class="guild-quest-done-badge">✅ Выполнено · +${safeInt(q.reward_xp, 0)} Guild XP получено</div>`
    : `<div class="guild-quest-prog-row">
        <div class="guild-quest-prog-bar"><div class="guild-quest-prog-fill ${fillCls}" style="width:${Math.min(100, Math.max(0, Number(q.progress_pct) || 0))}%"></div></div>
        <span class="guild-quest-prog-val">${formatGuildQuestVal(q.current)} / ${formatGuildQuestVal(q.target)}</span>
      </div>
      <div class="guild-quest-contrib-row">
        <span class="guild-quest-contrib-label">Лидеры:</span>
        ${leaders}
        ${other}
        <span class="guild-quest-reward">+${safeInt(q.reward_xp, 0)} Guild XP</span>
      </div>`;
  return `<div class="guild-quest-card${done ? " guild-quest-card--done" : ""}">
    <div class="guild-quest-card-top">
      <div class="guild-quest-cat guild-quest-cat--${cat.cls}">${cat.emoji}</div>
      <div class="guild-quest-info">
        <div class="guild-quest-name">${escapeHtml(q.name || "")}</div>
        <div class="guild-quest-desc">${escapeHtml(q.description || "")}</div>
      </div>
      <div class="guild-quest-tags">
        <span class="guild-quest-tag guild-quest-tag--${typeCls}">${typeLabel}</span>
      </div>
    </div>
    ${tiers}
    ${doneBlock}
  </div>`;
}

function formatGuildQuestReset(secondsLeft) {
  const s = Math.max(0, safeInt(secondsLeft, 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `Обновляется в 00:00 МСК — осталось ${h}ч ${m}м`;
}

function renderGuildQuestBallot(ballot, viewerOfficer) {
  if (!ballot || ballot.chosen_template_id) return "";
  const opts = (ballot.options || [])
    .map((o) => {
      const cat = guildQuestCategoryMeta(o.category);
      const voteBtn =
        ballot.can_vote && viewerOfficer
          ? `<button type="button" class="guild-quest-vote-btn" onclick="WaifuApp.voteWeeklyQuest(${Number(o.template_id)})">Выбрать</button>`
          : "";
      return `<div class="guild-quest-ballot-option">
        <div class="guild-quest-cat guild-quest-cat--${cat.cls}">${cat.emoji}</div>
        <div class="guild-quest-info">
          <div class="guild-quest-name">${escapeHtml(o.name || "")}</div>
          <div class="guild-quest-desc">${escapeHtml(o.description || "")}</div>
          <div class="guild-quest-ballot-meta">Цель: ${formatGuildQuestVal(o.target)} · +${safeInt(o.reward_xp, 0)} XP</div>
        </div>
        ${voteBtn}
      </div>`;
    })
    .join("");
  return `<div class="guild-quest-section">
    <div class="guild-section-label">Голосование за еженедельный квест</div>
    ${opts || `<p class="muted tiny">Ожидание вариантов…</p>`}
  </div>`;
}

function renderGuildQuestsPaneContent(data) {
  const tab = guildHallState.questsTab || "milestones";
  const tabs = data?.tabs || {};
  const tabBtns = [
    ["milestones", "Вехи"],
    ["daily", "Ежедневные"],
    ["weekly", "Еженедельные"],
  ]
    .map(
      ([id, label]) =>
        `<button type="button" class="guild-quest-tab${tab === id ? " active" : ""}" onclick="WaifuApp.switchGuildQuestTab('${id}')">${label}</button>`
    )
    .join("");

  let body = "";
  if (tab === "milestones") {
    const ms = tabs.milestones || {};
    const inProg = (ms.in_progress || []).map((q) => renderGuildQuestCard(q)).join("");
    const done = (ms.recently_completed || []).map((q) => renderGuildQuestCard(q, { done: true })).join("");
    body = `
      ${inProg ? `<div class="guild-quest-section"><div class="guild-section-label">В процессе</div>${inProg}</div>` : ""}
      ${done ? `<div class="guild-quest-section"><div class="guild-section-label">Недавно выполнено</div>${done}</div>` : ""}
      ${!inProg && !done ? `<p class="muted tiny">Нет активных вех.</p>` : ""}
      <p class="guild-quest-hint">Вехи накапливаются постоянно и никогда не сбрасываются</p>`;
  } else if (tab === "daily") {
    const daily = tabs.daily || {};
    const cards = (daily.quests || []).map((q) => renderGuildQuestCard(q)).join("");
    body = `
      <p class="guild-quest-reset-hint">${formatGuildQuestReset(daily.seconds_left)}</p>
      ${cards || `<p class="muted tiny">Ежедневные квесты появятся после полуночи МСК.</p>`}`;
  } else {
    const weekly = tabs.weekly || {};
    const ballot = renderGuildQuestBallot(weekly.ballot, !!data?.viewer_is_officer);
    const quest = weekly.quest ? renderGuildQuestCard(weekly.quest) : "";
    body = `
      <p class="guild-quest-reset-hint">${formatGuildQuestReset(weekly.seconds_left)}</p>
      ${ballot}
      ${quest || (!ballot ? `<p class="muted tiny">Еженедельный квест ещё не выбран.</p>` : "")}`;
  }

  return `<div class="guild-quests-board">
    <nav class="guild-quest-tabs" aria-label="Типы квестов">${tabBtns}</nav>
    ${body}
  </div>`;
}

function renderGuildQuestsPane() {
  if (guildHallState.questsLoading) {
    return `<p class="muted tiny">Загрузка квестов…</p>`;
  }
  const data = guildHallState.questsData;
  if (!data) {
    return `<p class="muted tiny">Не удалось загрузить квесты.</p>`;
  }
  return renderGuildQuestsPaneContent(data);
}

async function loadGuildQuests() {
  guildHallState.questsLoading = true;
  try {
    const data = await apiFetch("/guilds/me/quests");
    guildHallState.questsData = data;
    return data;
  } catch (e) {
    guildHallState.questsData = null;
    throw e;
  } finally {
    guildHallState.questsLoading = false;
  }
}

function switchGuildQuestTab(tab) {
  guildHallState.questsTab = tab;
  const pane = document.querySelector(".guild-activity-pane");
  if (pane && guildHallState.questsData) {
    pane.innerHTML = renderGuildQuestsPane();
  } else {
    void renderGuildTabContent();
  }
}

async function voteWeeklyQuest(templateId) {
  try {
    await apiFetch("/guilds/me/quests/weekly/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template_id: Number(templateId) }),
    });
    await loadGuildQuests();
    await renderGuildTabContent();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    alert(detail || "Не удалось проголосовать");
  }
}

async function renderGuildTabContent() {
  const root = document.getElementById("guild-tab-content");
  if (!root) return;
  const d = guildHallState.me;
  const tab = guildHallState.tab;

  if (!d?.in_guild) {
    if (tab === "search") {
      root.innerHTML = `
        <h3>Поиск гильдии</h3>
        <div class="guild-search-row">
          <div class="guild-search-row-inner">
            <input id="guild-search-q" type="search" placeholder="Название или тег" autocomplete="off" />
            <button type="button" class="btn primary" onclick="WaifuApp.runGuildSearch()">Найти</button>
          </div>
        </div>
        <div id="guild-search-results" class="guild-search-results"></div>`;
      return;
    }
    root.innerHTML = `<p class="muted">Вы не в гильдии. Создайте гильдию ниже или откройте вкладку 🔍 для поиска.</p>`;
    return;
  }

  if (tab === "main") {
    root.innerHTML = `
      ${renderGuildStatsGrid(d)}
      ${renderGuildActivityFeed(d)}`;
    armGuildMembersModalGuard();
    return;
  }

  if (tab === "skills") {
    root.innerHTML = renderGuildSkillsPanel(d);
    return;
  }

  if (tab === "bank") {
    try {
      await loadGuildBankItems();
    } catch (e) {
      const { detail } = parseHttpErrorDetail(e);
      root.innerHTML = `<p class="muted" style="color:#f87171">${escapeHtml(detail || "Ошибка банка")}</p>`;
      return;
    }
    root.innerHTML = renderGuildBankPanel(d);
    return;
  }

  if (tab === "battles") {
    const sub = guildHallState.activitySubTab || "raid";
    root.innerHTML = `
      <nav class="guild-subtabs" aria-label="Подвкладки битв">
        <button type="button" class="guild-subtab-btn ${sub === "raid" ? "active" : ""}" onclick="WaifuApp.switchGuildActivityTab('raid')">Рейды</button>
        <button type="button" class="guild-subtab-btn ${sub === "war" ? "active" : ""}" onclick="WaifuApp.switchGuildActivityTab('war')">Война</button>
        <button type="button" class="guild-subtab-btn ${sub === "quests" ? "active" : ""}" onclick="WaifuApp.switchGuildActivityTab('quests')">Квесты</button>
      </nav>
      <div class="guild-activity-pane">${
        sub === "raid"
          ? renderGuildRaidPane(d)
          : sub === "war"
            ? renderGuildWarPane(d)
            : renderGuildQuestsPane()
      }</div>`;
    return;
  }

  if (tab === "history") {
    root.innerHTML = `<p class="muted tiny" style="padding:12px 0;text-align:center">Загрузка истории…</p>`;
    try {
      await loadGuildHistoryTab();
      root.innerHTML = `<div class="guild-section-label">История</div>${renderGuildHistoryPane(guildHallState.me)}`;
    } catch (e) {
      const { detail } = parseHttpErrorDetail(e);
      root.innerHTML = `<p class="muted" style="color:#f87171">${escapeHtml(detail || "Не удалось загрузить историю")}</p>`;
    }
    return;
  }

  if (tab === "search") {
    root.innerHTML = `
      <h3>Поиск гильдии</h3>
      <p class="muted tiny">Вы уже в гильдии. Здесь можно искать другие гильдии для справки.</p>
      <div class="guild-search-row">
        <div class="guild-search-row-inner">
          <input id="guild-search-q" type="search" placeholder="Название или тег" autocomplete="off" />
          <button type="button" class="btn primary" onclick="WaifuApp.runGuildSearch()">Найти</button>
        </div>
      </div>
      <div id="guild-search-results" class="guild-search-results"></div>`;
  }
}

async function runGuildSearch() {
  const q = (document.getElementById("guild-search-q")?.value || "").trim();
  const qs = q ? `?query=${encodeURIComponent(q)}` : "";
  try {
    const data = await apiFetch(`/guilds/search${qs}`);
    const list = document.getElementById("guild-search-results");
    if (!list) return data;
    const inGuild = guildHallState.me?.in_guild;
    list.innerHTML = "";
    (data.guilds || []).forEach((g) => {
      const li = document.createElement("div");
      li.className = "list-item";
      const joinBtn =
        !inGuild && g.is_recruiting !== false
          ? `<button type="button" class="btn primary" style="margin-top:6px" onclick="WaifuApp.joinGuildFromSearch(${Number(g.id)})">Вступить</button>`
          : "";
      li.innerHTML = `<strong>[${escapeHtml(g.tag)}] ${escapeHtml(g.name)}</strong> — ур. ${g.level}${g.is_recruiting ? "" : " · набор закрыт"}
        ${joinBtn}`;
      list.appendChild(li);
    });
    if (!(data.guilds || []).length) {
      list.innerHTML = `<p class="muted tiny">Ничего не найдено.</p>`;
    }
    return data;
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Ошибка поиска", "error");
  }
}

async function searchGuilds(query) {
  if (query != null) {
    const inp = document.getElementById("guild-search-q");
    if (inp) inp.value = String(query);
  }
  return runGuildSearch();
}

async function refreshGuildHall(opts = {}) {
  return populateGuildHall(null, opts);
}

async function populateGuildHall(profile, opts = {}) {
  closeGuildMembersModal();
  const p = profile || profileState.currentProfile || {};
  guildHallState.profileGold = safeInt(p?.gold, 0);
  const root = document.getElementById("guild-tab-content");
  if (!root) return;
  const firstLoad = !guildHallState.me;
  if (firstLoad) setGuildPageLoading(true);
  try {
    if (opts.force) guildHallState.historyLoaded = false;
    const data = await fetchGuildMe({ force: Boolean(opts.force) || firstLoad });
    guildHallState.me = data;
    updateGuildHallChrome(Boolean(data?.in_guild));
    if (!data?.in_guild) {
      guildHallState.tab = guildHallState.tab === "main" ? "search" : guildHallState.tab;
      if (
        guildHallState.tab === "main" ||
        guildHallState.tab === "skills" ||
        guildHallState.tab === "bank" ||
        guildHallState.tab === "battles" ||
        guildHallState.tab === "activities" ||
        guildHallState.tab === "history"
      ) {
        guildHallState.tab = "search";
      }
    } else {
      if (guildHallState.tab === "activities") guildHallState.tab = "battles";
      if (guildHallState.tab === "search") guildHallState.tab = "main";
      renderGuildHero(data);
    }
    document.querySelectorAll("[data-guild-tab-btn]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.guildTabBtn === guildHallState.tab);
    });
    await renderGuildTabContent();
    if (!window.__guildHallModalBound) {
      window.__guildHallModalBound = true;
      bindGuildMembersModalChrome();
      bindGuildMembersStatCard();
      document.getElementById("guild-skill-modal-close")?.addEventListener("click", closeGuildSkillModal);
      document.getElementById("guild-member-preview-mail")?.addEventListener("click", openGuildMemberMailCompose);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          const membersModal = document.getElementById("guild-members-modal");
          if (membersModal?.classList.contains("guild-members-modal--open")) {
            closeGuildMembersModal();
            return;
          }
          const compose = document.getElementById("player-mail-compose-modal");
          if (compose && compose.style.display !== "none") {
            closePlayerMailComposeModal();
            return;
          }
          const m = document.getElementById("guild-member-preview-modal");
          if (m && m.style.display !== "none") closeGuildMemberPreviewModal();
        }
      });
    }
  } catch (e) {
    console.error(e);
    if (isWebAppUnauthorizedError(e)) {
      root.innerHTML = webAppAuthNoticeHtml();
      return;
    }
    const { detail } = parseHttpErrorDetail(e);
    root.innerHTML = `<p class="muted" style="color:#f87171">${escapeHtml(detail || "Не удалось загрузить гильдию")}</p>`;
    updateGuildHallChrome(false);
  } finally {
    if (firstLoad) setGuildPageLoading(false);
  }
}

async function initPage(page) {
  applyTheme();
  initNavIcons();
  if (tg) {
    try {
      tg.ready();
      tg.expand();
    } catch (err) {
      console.warn("Telegram WebApp init:", err);
    }
  }
  setActiveNav(page);
  if (page !== "index") {
    connectSSE();
  }
  initAtticChipClicks();
  initAtticMenu();
  initItemArtGenerateDelegated();

  registerWaifuServiceWorker();

  syncAdminUiVisibility();

  // Passive UI refresh: regen is time-based but applied on API calls.
  // Keep numbers fresh without forcing full-page reload.
  if (!window.__waifuProfileAutoRefresh) {
    window.__waifuProfileAutoRefresh = setInterval(async () => {
      if (!document.getElementById("badge-level")) return;
      try {
        const p = await loadProfile({ lite: !isProfilePage() });
        const w = p?.main_waifu;
        if (!w) return;
        // If we're on profile screen, refresh visible stat widgets without refetching inventory/equipment.
        if (window.location.pathname.endsWith("/profile.html")) {
          profileState.currentProfile = { ...(profileState.currentProfile || {}), ...p };
          profileState.currentDetails = p?.main_waifu_details || profileState.currentDetails || null;
          renderProfilePortrait(w, profileState.currentProfile);
          renderProfileHeroBars(w, profileState.currentDetails, profileState.currentProfile);
          renderStatsStrip("profile-stats-strip", w);
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

async function adminRestoreHpEnergy() {
  await apiFetch(`/admin/waifu/restore`, { method: "POST" });
  await loadProfile().catch(() => {});
}

async function _generateMonsterArtByTemplateId(templateId) {
  if (!isAdminUser()) return null;
  const tid = Number(templateId);
  if (!Number.isFinite(tid) || tid < 1) {
    throw new Error("invalid_template");
  }
  return apiFetch(`/admin/monster-art/generate?template_id=${encodeURIComponent(tid)}`, {
    method: "POST",
  });
}

async function adminGenerateMonsterArt() {
  if (!isAdminUser()) return;
  const storyBossId = Number(soloActiveStoryBossId);
  if (Number.isFinite(storyBossId) && storyBossId >= 1) {
    setItemArtGenBusy(true);
    try {
      const payload = await apiFetch(
        `/admin/story-boss-art/generate?story_boss_definition_id=${encodeURIComponent(storyBossId)}`,
        { method: "POST" }
      );
      const visual = document.getElementById("monster-visual");
      const family = visual?.dataset?.family || "unknown";
      const slug = visual?.dataset?.slug || "unknown";
      const tier = Number(visual?.dataset?.tier) || 1;
      let override = String(payload?.image_url || "").trim();
      if (override) {
        override = override + (override.includes("?") ? "&" : "?") + "v=" + Date.now();
      }
      loadMonsterImage(family, slug, tier, override || null);
      showToast("Портрет сюжетного босса сохранён");
    } catch (e) {
      const { detail } = parseHttpErrorDetail(e);
      showToast(detail || "Ошибка генерации", "error");
    } finally {
      setItemArtGenBusy(false);
    }
    return;
  }
  const templateId = Number(soloActiveMonsterTemplateId);
  if (!Number.isFinite(templateId) || templateId < 1) {
    showToast("Нет активного монстра (зайдите в бой)", "error");
    return;
  }
  setItemArtGenBusy(true);
  try {
    const payload = await _generateMonsterArtByTemplateId(templateId);
    const visual = document.getElementById("monster-visual");
    const family = payload?.family || visual?.dataset?.family || "unknown";
    const slug = payload?.slug || visual?.dataset?.slug || "unknown";
    const tier = Number(visual?.dataset?.tier) || 1;
    const bust = Date.now();
    window.monsterArtVersion = window.monsterArtVersion || {};
    window.monsterArtVersion[templateId] = bust;
    let override = String(payload?.image_url || "").trim();
    if (override) {
      override = override + (override.includes("?") ? "&" : "?") + "v=" + bust;
    }
    const loadMonster = window.WaifuApp?.loadMonsterImage;
    if (typeof loadMonster === "function") {
      loadMonster(family, slug, tier, override || null, String(bust));
    }
    showToast("Изображение монстра сохранено");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Ошибка генерации", "error");
  } finally {
    setItemArtGenBusy(false);
  }
}

async function adminGenerateLibraryMonsterArt(templateId) {
  if (!isAdminUser()) return;
  const tid = Number(templateId);
  if (!Number.isFinite(tid) || tid < 1) return;
  setItemArtGenBusy(true);
  try {
    const payload = await _generateMonsterArtByTemplateId(tid);
    libraryArtVersionByTemplate[tid] = Date.now();
    if (libraryCatalogCache?.monsters) {
      const row = libraryCatalogCache.monsters.find((m) => Number(m.template_id) === tid);
      if (row) {
        row.seen = true;
        row.has_image = true;
        row.family = payload?.family || row.family || "unknown";
        row.slug = payload?.slug || row.slug || "unknown";
        row.image_updated_at = new Date().toISOString();
        if (!row.name_known) {
          row.name_known = true;
        }
      }
    }
    if (libraryState.detailId === tid) {
      libraryRenderDetail(tid);
    } else if (libraryState.tab === "bestiary" && !libraryState.detailId) {
      libraryRenderGrid();
    }
    showToast("Изображение монстра сохранено");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Ошибка генерации", "error");
  } finally {
    setItemArtGenBusy(false);
  }
}

// ---- Caravan page ----

const ACT_META = [
  { act: 1, short: "Акт I", name: "Акт I — Начало пути", emoji: "🌿", desc: "Первые шаги. Леса и пещеры вокруг стартового города.", levelRange: "1–9" },
  { act: 2, short: "Акт II", name: "Акт II — Глубины", emoji: "⛏️", desc: "Шахты и подземные твердыни. Опасность возрастает.", levelRange: "11–19" },
  { act: 3, short: "Акт III", name: "Акт III — Руины", emoji: "🏛️", desc: "Древние руины, проклятые земли, элитные враги.", levelRange: "21–29" },
  { act: 4, short: "Акт IV", name: "Акт IV — Бездна", emoji: "🌋", desc: "Вулканические земли, демоны, огненные боссы.", levelRange: "31–39" },
  { act: 5, short: "Акт V", name: "Акт V — Финал", emoji: "🏰", desc: "Цитадель финального зла. Финальное испытание.", levelRange: "41–60" },
];

let caravanPendingAct = null;
let caravanTravelInProgress = false;
let caravanDriverTipInProgress = false;

/**
 * Acts that actually ship pin art under /static/game/ui/caravan/.
 * Empty by default: no pin art exists yet, so the map shows the act emoji from
 * ACT_META. Keeping this empty avoids 5x2 guaranteed 404s on every caravan open.
 * Add an act number here once act-{N}/map-pin.webp (or pin_act{N}.webp) ships.
 */
const CARAVAN_ACTS_WITH_PIN_ART = new Set();

/** Иконка точки на карте каравана (см. static/game/ui/caravan/README.md). */
function caravanPinImageUrls(act) {
  const a = Math.max(1, Math.min(5, safeInt(act, 1)));
  if (!CARAVAN_ACTS_WITH_PIN_ART.has(a)) return [];
  return [`${CARAVAN_STATIC_BASE}/act-${a}/map-pin.webp`, `${CARAVAN_STATIC_BASE}/pin_act${a}.webp`];
}

/** Подбор картинки по цепочке URL (onerror → следующий). */
function attachCaravanImage(el, urls, onGiveUp, onResolved) {
  if (!el) {
    onGiveUp?.();
    return;
  }
  let i = 0;
  function next() {
    if (i >= urls.length) {
      el.style.display = "none";
      onGiveUp?.();
      return;
    }
    const url = urls[i];
    i += 1;
    if (el.dataset.waifuResolvedImg === url) {
      el.style.display = "";
      return;
    }
    el.onerror = () => next();
    el.onload = () => {
      el.dataset.waifuResolvedImg = url;
      el.style.display = "";
      onResolved?.(url);
    };
    el.src = url;
  }
  next();
}

/** Фон и погонщик зависят от текущего акта (см. static/game/ui/caravan/README.md). */
function applyCaravanStageImages(currentAct) {
  const a = Math.max(1, Math.min(5, safeInt(currentAct, 1)));
  const bgImg = document.getElementById("caravan-bg-img");
  const driverImg = document.getElementById("caravan-driver-img");
  const wrap = document.getElementById("caravan-driver-wrap");

  const bgUrls = [
    `${CARAVAN_STATIC_BASE}/act-${a}/caravan.background.webp`,
    `${CARAVAN_STATIC_BASE}/bg_act${a}.webp`,
    `${CARAVAN_STATIC_BASE}/caravan.background.webp`,
  ];
  const driverUrls = [
    `${CARAVAN_STATIC_BASE}/act-${a}/driver.webp`,
    `${CARAVAN_STATIC_BASE}/driver_act${a}.webp`,
    `${CARAVAN_STATIC_BASE}/caravan.driver.webp`,
  ];

  if (wrap) wrap.classList.remove("driver-fallback");

  if (bgImg) {
    bgImg.style.display = "";
    attachCaravanImage(bgImg, bgUrls, null);
  }

  if (driverImg && wrap) {
    driverImg.style.display = "";
    attachCaravanImage(driverImg, driverUrls, () => {
      wrap.classList.add("driver-fallback");
    });
  }
}

/** Hero banners per shop tab (merchant / gambler / blacksmith). */
const SHOP_HERO_KIND = { buy: "merchant", sell: "merchant", gamble: "gambler", smith: "blacksmith" };

function applyShopHeroImages(currentAct) {
  const a = Math.max(1, Math.min(5, safeInt(currentAct, 1)));
  const kindSrc = new Map();
  for (const [tab, kind] of Object.entries(SHOP_HERO_KIND)) {
    const img = document.getElementById(`shop-hero-img-${tab}`);
    const fb = document.getElementById(`shop-hero-fb-${tab}`);
    const cachedSrc = kindSrc.get(kind);
    if (cachedSrc && img) {
      img.style.display = "";
      img.src = cachedSrc;
      if (fb) fb.style.display = "none";
      continue;
    }
    const heroUrls = [
      `${SHOP_STATIC_BASE}/act-${a}/${kind}.webp`,
      `${SHOP_STATIC_BASE}/${kind}_act${a}.webp`,
      `${SHOP_STATIC_BASE}/${kind}.webp`,
    ];
    if (img) {
      img.style.display = "";
      if (fb) fb.style.display = "none";
      attachCaravanImage(
        img,
        heroUrls,
        () => {
          img.style.display = "none";
          if (fb) fb.style.display = "";
        },
        (url) => {
          kindSrc.set(kind, url);
        },
      );
    }
  }
}

function applyShopStageImages(currentAct) {
  applyShopHeroImages(currentAct);
}

function openCaravanTipModal(text) {
  const modal = document.getElementById("caravan-tip-modal");
  const body = document.getElementById("caravan-tip-body");
  if (body) body.textContent = text != null ? String(text) : "—";
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function closeCaravanTipModal() {
  const modal = document.getElementById("caravan-tip-modal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

async function requestCaravanDriverTip() {
  if (caravanDriverTipInProgress) return;
  caravanDriverTipInProgress = true;
  openCaravanTipModal("Загрузка…");
  try {
    const res = await apiFetch("/player/caravan-driver-tip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const text = res?.text != null ? String(res.text).trim() : "";
    if (text) {
      openCaravanTipModal(text);
    } else {
      openCaravanTipModal(res?.error || "Не удалось получить совет.");
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    openCaravanTipModal(detail || "Ошибка сети.");
  } finally {
    caravanDriverTipInProgress = false;
  }
}

async function populateCaravanPage(profile) {
  const p = profile || (await loadProfile());
  const currentAct = safeInt(p?.act, 1);
  const maxAct = safeInt(p?.max_act, currentAct);

  const pinsLayer = document.getElementById("caravan-pins-layer");
  if (!pinsLayer) return;

  const rawCosts = p?.caravan_travel_costs;
  const costs =
    Array.isArray(rawCosts) && rawCosts.length >= 5
      ? rawCosts.map((x) => safeInt(x, 0))
      : [50, 200, 500, 1200, 2500];

  pinsLayer.innerHTML =
    ACT_META.map(({ act, short, emoji, levelRange }) => {
    const unlocked = act <= maxAct;
    const isCurrent = act === currentAct;
    const cost = costs[act - 1] ?? 0;
    const goldLine = isCurrent ? "Здесь" : unlocked ? `🪙 ${cost}` : "🔒";
    const icoInner = `<img class="caravan-pin-img" alt="" src="" /><span class="caravan-pin-emoji" aria-hidden="true">${emoji}</span>`;
    const icoBlock =
      unlocked && !isCurrent
        ? `<button type="button" class="caravan-pin-ico-btn caravan-pin-hit" data-act-pin="${act}" onclick="WaifuApp.travelToAct(${act})" aria-label="Поехать: ${escapeHtml(short)}">${icoInner}</button>`
        : `<div class="caravan-pin-ico-wrap caravan-pin-ico-wrap--static" data-act-pin="${act}" aria-hidden="true">${icoInner}</div>`;
    return `
      <div class="caravan-pin act-btn caravan-pin--${act} ${unlocked ? "" : "locked"} ${isCurrent ? "current" : ""}" role="group" aria-label="${escapeHtml(short)}">
        <div class="caravan-pin-gold">${goldLine}</div>
        ${icoBlock}
        <div class="caravan-pin-title" title="Ур. ${escapeHtml(levelRange)}">${escapeHtml(short)}</div>
      </div>`;
    }).join("") +
    `
    <div class="caravan-pin caravan-pin--library" role="group" aria-label="Библиотека" data-tutorial="caravan-library">
      <button type="button" class="caravan-pin-ico-btn" data-tutorial="caravan-library" onclick="WaifuApp.openLibrary()" aria-label="Библиотека">📖</button>
    </div>`;

  ACT_META.forEach(({ act }) => {
    const wrap = pinsLayer.querySelector(`[data-act-pin="${act}"]`);
    const img = wrap?.querySelector?.(".caravan-pin-img");
    if (!img || !wrap) return;
    wrap.classList.remove("pin-fallback");
    img.style.display = "";
    attachCaravanImage(img, caravanPinImageUrls(act), () => {
      wrap.classList.add("pin-fallback");
    });
  });

  const dbtn = document.getElementById("caravan-driver-btn");
  if (dbtn) {
    dbtn.onclick = () => {
      requestCaravanDriverTip();
    };
  }

  applyCaravanStageImages(currentAct);
}

/** Сразу сменить акт (без модалки). */
async function travelToAct(act) {
  const target = safeInt(act, 0);
  if (!target || target < 1 || target > 5) return;
  if (caravanTravelInProgress) return;

  const errBox = document.getElementById("caravan-error");
  caravanTravelInProgress = true;
  document.querySelectorAll(".caravan-pin-ico-btn.caravan-pin-hit").forEach((b) => {
    b.disabled = true;
  });

  try {
    if (errBox) {
      errBox.style.display = "none";
      errBox.textContent = "";
    }
    await apiFetch(`/player/act?act=${encodeURIComponent(target)}`, { method: "POST" });
    const p = await loadProfile();
    await populateCaravanPage(p);
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    if (errBox) {
      errBox.textContent = detail || "Ошибка перемещения";
      errBox.style.display = "";
    }
  } finally {
    caravanTravelInProgress = false;
    document.querySelectorAll(".caravan-pin-ico-btn.caravan-pin-hit").forEach((b) => {
      b.disabled = false;
    });
  }
}

function openCaravanModal(act) {
  travelToAct(act);
}

function closeCaravanModal() {
  const modal = document.getElementById("caravan-travel-modal");
  if (modal) modal.style.display = "none";
  caravanPendingAct = null;
}

async function confirmTravelToAct() {
  if (!caravanPendingAct) return;
  const act = caravanPendingAct;
  caravanPendingAct = null;
  await travelToAct(act);
}

/* ===================================================================== */
/* Библиотека (Кодекс) + Бестиарий                                        */
/* ===================================================================== */

const LIBRARY_MONSTER_BASE = `${GAME_STATIC_BASE}/monsters`;

let libraryCatalogCache = null;
let libraryFilters = { search: "", act: "all", family: "all", tier: "all", seen: "all" };
let librarySort = "act";
let libraryState = { tab: "bestiary", detailId: null, itemsSubtab: "items", itemDetailId: null, affixDetailKey: null };
let libraryItemsCatalogCache = null;
let libraryAffixesCatalogCache = null;
let libraryItemsFilters = { search: "", tier: "all", seen: "all", slot: "all" };
let libraryAffixFilters = { search: "", kind: "all", seen: "all" };
const libraryArtVersionByTemplate = {};

const LIBRARY_ACT_OPTIONS = [1, 2, 3, 4, 5];

const LIBRARY_TABS = [
  { id: "bestiary", icon: "👹", label: "Монстры", enabled: true },
  { id: "mechanics", icon: "📜", label: "Механики", enabled: true },
  { id: "items", icon: "🎒", label: "Предметы", enabled: true },
  { id: "classes", icon: "🛡️", label: "Классы", enabled: false },
  { id: "races", icon: "🧝", label: "Расы", enabled: false },
];

const LIBRARY_TIER_BORDER = {
  0: "#5a5248",
  1: "#9ca3af",
  2: "#22c55e",
  3: "#3b82f6",
  4: "#a855f7",
  5: "#f59e0b",
  6: "#ef4444",
  7: "#ec4899",
  8: "#06b6d4",
  9: "#eab308",
  10: "#f472b6",
};

function libraryTierClass(tier) {
  const t = Math.max(0, Math.min(10, Number(tier) || 0));
  return `lib-tier-${t}`;
}

function libraryArtCacheBust(templateId, imageUpdatedAt) {
  let v = 0;
  const tid = Number(templateId);
  if (Number.isFinite(tid) && libraryArtVersionByTemplate[tid]) {
    v = Math.max(v, Number(libraryArtVersionByTemplate[tid]) || 0);
  }
  if (imageUpdatedAt) {
    const t = Date.parse(imageUpdatedAt);
    if (!Number.isNaN(t)) v = Math.max(v, t);
  }
  if (v > 0) return String(v);
  return WAIFU_WEBAPP_VERSION || null;
}

function libraryMonsterImageUrls(e) {
  if (!e?.seen || !e.family || !e.slug) return [];
  const ver = libraryArtCacheBust(e.template_id, e.image_updated_at);
  const q = ver ? `?v=${encodeURIComponent(ver)}` : "";
  const family = e.family || "unknown";
  const slug = e.slug || "unknown";
  const tier = e.monster_tier ?? 1;
  return [
    `${LIBRARY_MONSTER_BASE}/${family}/${slug}.webp${q}`,
    `${LIBRARY_MONSTER_BASE}/${family}/_family_t${tier}.webp${q}`,
    `${LIBRARY_MONSTER_BASE}/${family}/_family.webp${q}`,
    `${LIBRARY_MONSTER_BASE}/_unknown.webp${q}`,
  ];
}

function libraryOnArtError(img) {
  const urls = JSON.parse(img?.dataset?.fallbackUrls || "[]");
  let index = parseInt(img?.dataset?.fallbackIndex || "0", 10) + 1;
  if (index < urls.length) {
    img.dataset.fallbackIndex = String(index);
    img.src = urls[index];
  } else {
    img.style.display = "none";
    const wrap = img.closest(".lib-card-art, .lib-mtg-art");
    if (wrap) wrap.classList.add("silhouette");
  }
}

function libraryAttachArt(wrap, e) {
  if (!wrap) return;
  const img = wrap.querySelector("[data-lib-art]");
  const emoji = wrap.querySelector(".lib-art-emoji");
  const seen = Boolean(e?.seen);
  wrap.classList.toggle("silhouette", !seen);
  if (!seen) {
    if (img) {
      img.style.display = "none";
      img.removeAttribute("src");
    }
    if (emoji) {
      emoji.textContent = "👾";
      emoji.style.display = "";
    }
    return;
  }
  const urls = libraryMonsterImageUrls(e);
  if (!img || !urls.length) {
    if (emoji) {
      emoji.textContent = e?.emoji || "👾";
      emoji.style.display = "";
    }
    return;
  }
  if (emoji) emoji.style.display = "none";
  img.style.display = "";
  img.dataset.fallbackUrls = JSON.stringify(urls);
  img.dataset.fallbackIndex = "0";
  img.dataset.family = e.family || "unknown";
  img.dataset.slug = e.slug || "unknown";
  img.onerror = () => libraryOnArtError(img);
  if (img.getAttribute("src") === urls[0] && img.complete && img.naturalWidth > 0) {
    wrap.classList.remove("silhouette");
    return;
  }
  img.src = urls[0];
  img.onload = () => wrap.classList.remove("silhouette");
}

function libraryFmtActRange(mm) {
  const a = Number(mm?.act_min) || 1;
  const b = Number(mm?.act_max) || a;
  return a === b ? `Акт ${a}` : `Акт ${a}–${b}`;
}

function libraryStudyProgressHtml(e, tiers) {
  const kills = Number(e?.kills) || 0;
  const tierRows = Array.isArray(tiers) ? tiers : libraryCatalogCache?.tiers || [];
  const maxKills = tierRows.length
    ? Math.max(...tierRows.map((t) => Number(t.kills_required) || 0), 100)
    : 100;
  const fillPct = maxKills > 0 ? Math.min(100, (kills / maxKills) * 100) : 0;
  const ticks = tierRows
    .filter((t) => Number(t.kills_required) > 0)
    .map((t) => {
      const req = Number(t.kills_required);
      const left = maxKills > 0 ? (req / maxKills) * 100 : 0;
      const reached = kills >= req;
      return `<span class="lib-study-tick ${reached ? "reached" : ""}" style="left:${left}%"><span class="lib-study-tick-dot"></span><span class="lib-study-tick-k">${req}</span></span>`;
    })
    .join("");
  const bonusRows = tierRows
    .filter((t) => Number(t.tier) > 0 && Number(e?.tier) >= Number(t.tier))
    .map((t) => {
      const parts = [];
      if (Array.isArray(t.bonuses) && t.bonuses.length) parts.push(...t.bonuses);
      if (Array.isArray(t.reveals) && t.reveals.length) {
        parts.push(`откр.: ${t.reveals.join(", ")}`);
      }
      if (!parts.length) return "";
      return `<div class="lib-study-bonus-row">${escapeHtml(String(t.kills_required))} уб. · ${escapeHtml(parts.join(" · "))}</div>`;
    })
    .filter(Boolean)
    .join("");
  const bonusesBlock = bonusRows
    ? `<div class="lib-study-bonuses"><div class="lib-study-bonuses-title">Бонусы изучения</div>${bonusRows}</div>`
    : "";
  return `
    <div class="lib-study">
      <div class="lib-study-status">${escapeHtml(e?.tier_name || "—")} · ${kills} уб.</div>
      <div class="lib-study-track-wrap">
        <div class="lib-study-track">
          <div class="lib-study-fill" style="width:${fillPct}%"></div>
          ${ticks}
        </div>
      </div>
      ${bonusesBlock}
    </div>`;
}

function libraryBuildDetailStats(e) {
  const rows = [];
  rows.push(
    `<div class="lib-kv"><span>Убито</span><strong>${Number(e?.kills) || 0}</strong></div>`
  );
  rows.push(
    `<div class="lib-kv"><span>Локация</span><strong>${escapeHtml(libraryFmtActRange(e))}</strong></div>`
  );
  if (e?.name_known && e?.type) {
    const typeLabel = formatMonsterTypeLabelRu(e.type) || e.type;
    rows.push(`<div class="lib-kv"><span>Тип</span><strong>${escapeHtml(typeLabel)}</strong></div>`);
  }
  if (e.hp_base != null) {
    rows.push(
      `<div class="lib-kv"><span>HP (база)</span><strong>${escapeHtml(String(e.hp_base))}+${escapeHtml(String(e.hp_per_level || 0))}/ур.</strong></div>`
    );
  }
  if (e.dmg_base != null) {
    rows.push(
      `<div class="lib-kv"><span>Урон (база)</span><strong>${escapeHtml(String(e.dmg_base))}+${escapeHtml(String(e.dmg_per_level || 0))}/ур.</strong></div>`
    );
  }
  if (e.exp_base != null) {
    rows.push(
      `<div class="lib-kv"><span>Опыт</span><strong>${escapeHtml(String(e.exp_base))}+${escapeHtml(String(e.exp_per_level || 0))}/ур.</strong></div>`
    );
  }
  if (e.gold_base != null) {
    rows.push(
      `<div class="lib-kv"><span>Золото</span><strong>${escapeHtml(String(e.gold_base))}+${escapeHtml(String(e.gold_per_level || 0))}/ур.</strong></div>`
    );
  }
  if (e.level_min != null) {
    rows.push(
      `<div class="lib-kv"><span>Уровень</span><strong>${escapeHtml(String(e.level_min))}–${escapeHtml(String(e.level_max))}</strong></div>`
    );
  }
  if (e.next_tier_kills != null && Number(e.tier) < Number(e.max_tier)) {
    rows.push(
      `<div class="lib-kv"><span>До след. уровня</span><strong>${escapeHtml(String(e.next_tier_kills))} уб.</strong></div>`
    );
  }
  return rows.join("");
}

function statsGuideContentHtml() {
  return `
    <p><strong>Основные характеристики</strong> — база персонажа + раса/класс + экипировка + плоский бонус «Трансценд.»; затем множители «+% ко всем статам» с предметов и пассивов.</p>
    <p><strong>Урон</strong> — отдельно ближний (СИЛ), дальний (ЛОВ), магический (ИНТ); пассивы с одинаковым типом эффекта <em>суммируются</em>, разные типы — перемножаются по цепочке боя.</p>
    <p><strong>Уклонение</strong> (строка в профиле) — один общий шанс: ЛОВ × 0,1% + вторички на предметах + пассивы вроде «Проворство». Потолок 40%. Удача в уклонение не входит.</p>
    <p><strong>Полное уклонение</strong> — отдельная строка и отдельный бросок в бою (например «Шаг тени»). Срабатывает после обычного уклонения, если оно не сработало.</p>
    <p><strong>Снижение урона</strong> — ВЫН + вторички + броня складываются в один пул (до 90%).</p>
    <p><strong>Пассивы с предметов</strong> — «+N к уровню навыка» повышает эффективный уровень. Для части навыков (полное уклонение, instakill и др.) эффект не растёт выше максимума таблицы — смотрите предупреждение в модалке навыка.</p>
    <p><strong>Заточка</strong> — усиливает урон/броню на оружии и доспехах; на аксессуарах — вторичные бонусы (крит, уклонение…). Предметы с бонусом к пассивному навыку заточкой не усиливаются.</p>`;
}

const LIBRARY_MECHANICS_SUBTABS = [
  { id: "waifu", label: "Основная Вайфу" },
  { id: "dungeons", label: "Подземелья" },
  { id: "shop", label: "Магазин" },
  { id: "guilds", label: "Гильдии" },
  { id: "skills", label: "Навыки" },
  { id: "tavern", label: "Таверна" },
];

let libraryMechanicsSubtab = "waifu";

function libraryMechanicsSectionHtml(subtabId) {
  const id = subtabId || "waifu";
  if (id === "waifu") {
    return `
      <h3>Характеристики</h3>
      <p>СИЛ, ЛОВ, ИНТ, ВЫН, ОБА и УДЧ влияют на урон, защиту, крит и награды. Итоговые значения видны в профиле основной вайфу.</p>
      <h3 id="lib-stats-guide">Как считаются статы</h3>
      <div class="lib-stats-guide-body">${statsGuideContentHtml()}</div>
      <h3>Бестиарий и кодекс</h3>
      <p>Встречайте монстров и предметы в игре — в библиотеке открываются карточки с подробностями. У монстров прогресс идёт по убийствам одного шаблона.</p>`;
  }
  if (id === "dungeons") {
    return `
      <h3>Соло-подземелья</h3>
      <p>Атакуйте монстра сообщениями в чате. Урон зависит от статов, оружия и пассивов. Монстр отвечает, когда его HP падает ниже порога.</p>
      <h3>Типы урона</h3>
      <p>Физический, магический и чистый урон по-разному взаимодействуют с защитой и аффиксами элитных монстров.</p>
      <h3>Экспедиции</h3>
      <p>Отправляйте отряд на слот экспедиции: сложность, теги препятствий и аффиксы слота влияют на шанс успеха и награды. Перки наёмниц могут перекрывать теги.</p>
      <h3>Групповые подземелья</h3>
      <p>В групповом чате игроки бьют общего монстра раундами. Награды и прогресс зависят от вклада и настроек цикла.</p>
      <h3>Бездна</h3>
      <p>Отдельный режим с чекпоинтами и усилением врагов. Используйте вкладку «Бездна» на странице подземелий.</p>
      <h3>Акты</h3>
      <p>Караван перемещается между актами. В каждом акте свой пул монстров, уровней лута и цен в магазине.</p>`;
  }
  if (id === "shop") {
    return `
      <h3>Магазин</h3>
      <p>Ежедневные офферы привязаны к акту. Цена зависит от уровня предмета, редкости и скидок (обаяние, пассивы). Имя на витрине уже включает выпавшие префиксы и суффиксы.</p>
      <h3>Gamble</h3>
      <p>Случайный предмет повышенной редкости за золото. Шансы и уровень зависят от акта и уровня вайфу.</p>
      <h3>Кузнец: заточка</h3>
      <p>Усиливает урон и броню на оружии и доспехах; на аксессуарах — вторичные бонусы. Есть риск поломки на высоких уровнях заточки.</p>
      <h3>Кузнец: зачарование</h3>
      <p>Отдельная система шагов зачарования, записанных при создании предмета. Предметы с бонусом к пассивному навыку заточкой не усиливаются.</p>`;
  }
  if (id === "guilds") {
    return `
      <h3>Гильдии</h3>
      <p>Объединение игроков: общий банк, навыки гильдии, рейды и войны. Вклад участников влияет на развитие и награды.</p>
      <h3>Рейды</h3>
      <p>Совместный урон по боссу в окне рейда. Бонусы гильдии могут усиливать урон или награды в бою.</p>
      <h3>Войны</h3>
      <p>Соревнование гильдий по очкам за период. Следите за статусом войны в зале гильдии.</p>`;
  }
  if (id === "skills") {
    return `
      <h3>Пассивные навыки</h3>
      <p>Дерево веток (воин, тень, мудрец): узлы дают плоские бонусы, множители урона, скидки и особые эффекты. Одинаковые типы эффектов суммируются, разные — перемножаются в бою.</p>
      <h3>Скрытые навыки</h3>
      <p>Открываются за особые действия (марафоны, серии побед и т.д.). Не отображаются в основном дереве до разблокировки.</p>
      <h3>Сброс</h3>
      <p>Сброс дерева возвращает очки навыков; скрытые навыки и прогресс аккуратно обрабатываются отдельными правилами.</p>
      <h3>Предметы и навыки</h3>
      <p>Аффиксы «+N к уровню навыка» повышают эффективный уровень. Для части навыков действует потолок таблицы — смотрите предупреждение в модалке навыка.</p>`;
  }
  if (id === "tavern") {
    return `
      <h3>Найм</h3>
      <p>Слоты найма обновляются по расписанию. Наёмницы участвуют в экспедициях; у каждой раса, класс, статы и перки.</p>
      <h3>Прокачка</h3>
      <p>Опыт и уровень наёмниц растут от экспедиций и событий. Перки усиливают подходящие теги слотов.</p>
      <h3>Лечение</h3>
      <p>Восстановление HP наёмниц за золото в таверне. Скидки могут давать пассивы и предметы.</p>`;
  }
  return "";
}

function libraryMechanicsShellHtml() {
  const subTabs = LIBRARY_MECHANICS_SUBTABS.map((t) => {
    const active = t.id === libraryMechanicsSubtab ? " active" : "";
    return `<button type="button" class="lib-mechanics-subtab${active}" data-mech-sub="${t.id}" onclick="WaifuApp.librarySwitchMechanicsSubtab('${t.id}')">${escapeHtml(t.label)}</button>`;
  }).join("");
  return `
    <div class="lib-body-chrome">
      <div class="lib-mechanics-subtabs" role="tablist">${subTabs}</div>
    </div>
    <div class="lib-body-scroll">
      <div class="lib-mechanics">
        <div id="lib-mechanics-body" class="lib-mechanics-body">${libraryMechanicsSectionHtml(libraryMechanicsSubtab)}</div>
      </div>
    </div>`;
}

function librarySwitchMechanicsSubtab(subtabId) {
  libraryMechanicsSubtab = subtabId || "waifu";
  const body = document.getElementById("lib-mechanics-body");
  if (body) body.innerHTML = libraryMechanicsSectionHtml(libraryMechanicsSubtab);
  document.querySelectorAll(".lib-mechanics-subtab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mechSub === libraryMechanicsSubtab);
  });
}

function libraryRenderMechanics() {
  const body = document.getElementById("lib-body");
  if (!body) return;
  body.innerHTML = libraryMechanicsShellHtml();
}

function libraryItemCardArtHtml(entry) {
  if (!entry?.seen) {
    return `<div class="lib-card-art silhouette"><span class="lib-art-emoji">🎒</span></div>`;
  }
  const fakeItem = {
    art_key: entry.art_key,
    tier: entry.tier,
    slot_type: entry.slot_type,
    weapon_type: entry.subtype,
  };
  return `<div class="lib-card-art">${itemArtHtml(fakeItem)}</div>`;
}

function libraryBindItemsFilterHandlers() {
  const search = document.getElementById("lib-items-search");
  const tier = document.getElementById("lib-items-tier");
  const seen = document.getElementById("lib-items-seen");
  const slot = document.getElementById("lib-items-slot");
  if (search && !search.dataset.bound) {
    search.dataset.bound = "1";
    search.addEventListener("input", () => {
      libraryItemsFilters.search = search.value.trim().toLowerCase();
      libraryRenderItemsGrid();
    });
  }
  if (tier && !tier.dataset.bound) {
    tier.dataset.bound = "1";
    tier.addEventListener("change", () => {
      libraryItemsFilters.tier = tier.value;
      libraryRenderItemsGrid();
    });
  }
  if (seen && !seen.dataset.bound) {
    seen.dataset.bound = "1";
    seen.addEventListener("change", () => {
      libraryItemsFilters.seen = seen.value;
      libraryRenderItemsGrid();
    });
  }
  if (slot && !slot.dataset.bound) {
    slot.dataset.bound = "1";
    slot.addEventListener("change", () => {
      libraryItemsFilters.slot = slot.value;
      libraryRenderItemsGrid();
    });
  }
}

function libraryRenderItemsGrid() {
  const grid = document.getElementById("lib-items-grid");
  if (!grid || !libraryItemsCatalogCache) return;
  const f = libraryItemsFilters;
  let items = libraryItemsCatalogCache.items || [];
  if (f.search) {
    items = items.filter((it) => String(it.name || "").toLowerCase().includes(f.search));
  }
  if (f.tier !== "all") {
    const t = Number(f.tier);
    items = items.filter((it) => Number(it.tier) === t);
  }
  if (f.seen === "seen") items = items.filter((it) => it.seen);
  if (f.seen === "unseen") items = items.filter((it) => !it.seen);
  if (f.slot !== "all") {
    items = items.filter((it) => String(it.slot_type || "") === f.slot);
  }
  const summary = libraryItemsCatalogCache.summary || {};
  const sumEl = document.getElementById("lib-items-summary");
  if (sumEl) {
    sumEl.textContent = `Открыто ${summary.seen || 0} из ${summary.total || 0} (${summary.seen_pct || 0}%)`;
  }
  grid.innerHTML = items
    .map((it) => {
      const tid = Number(it.base_template_id);
      const tierCls = libraryTierClass(Math.max(1, Number(it.tier) || 1));
      const label = escapeHtml(it.name || "???");
      return `
        <div class="lib-card ${tierCls}" role="button" tabindex="0" data-base-template-id="${tid}"
          onclick="WaifuApp.libraryOpenItem(${tid})">
          ${libraryItemCardArtHtml(it)}
          <div class="lib-card-meta">
            <div class="lib-card-name">${label}</div>
            <div class="lib-card-tier">T${Number(it.tier) || "?"}</div>
          </div>
        </div>`;
    })
    .join("");
}

function libraryBindAffixFilterHandlers() {
  const search = document.getElementById("lib-affix-search");
  const kind = document.getElementById("lib-affix-kind-filter");
  const seen = document.getElementById("lib-affix-seen");
  if (search && !search.dataset.bound) {
    search.dataset.bound = "1";
    search.addEventListener("input", () => {
      libraryAffixFilters.search = search.value.trim().toLowerCase();
      libraryRenderAffixesList();
    });
  }
  if (kind && !kind.dataset.bound) {
    kind.dataset.bound = "1";
    kind.addEventListener("change", () => {
      libraryAffixFilters.kind = kind.value;
      libraryRenderAffixesList();
    });
  }
  if (seen && !seen.dataset.bound) {
    seen.dataset.bound = "1";
    seen.addEventListener("change", () => {
      libraryAffixFilters.seen = seen.value;
      libraryRenderAffixesList();
    });
  }
}

function libraryAffixDetailKey(entry) {
  return `${entry.catalog_kind}:${entry.catalog_id}`;
}

function libraryRenderAffixesList() {
  const list = document.getElementById("lib-affix-list");
  if (!list || !libraryAffixesCatalogCache) return;
  const f = libraryAffixFilters;
  let rows = libraryAffixesCatalogCache.affixes || [];
  if (f.search) {
    const q = f.search;
    rows = rows.filter(
      (a) =>
        String(a.name_ru || a.name || "")
          .toLowerCase()
          .includes(q) ||
        String(a.description_ru || "")
          .toLowerCase()
          .includes(q)
    );
  }
  if (f.kind !== "all") {
    const k = f.kind === "prefix" ? "affix" : f.kind;
    rows = rows.filter((a) => String(a.kind || "") === k || (f.kind === "prefix" && a.kind === "prefix"));
  }
  if (f.seen === "seen") rows = rows.filter((a) => a.seen);
  if (f.seen === "unseen") rows = rows.filter((a) => !a.seen);
  const summary = libraryAffixesCatalogCache.summary || {};
  const sumEl = document.getElementById("lib-affix-summary");
  if (sumEl) {
    sumEl.textContent = `Открыто ${summary.seen || 0} из ${summary.total || 0} (${summary.seen_pct || 0}%)`;
  }
  if (!rows.length) {
    list.innerHTML = '<p class="muted tiny">Ничего не найдено.</p>';
    return;
  }
  list.innerHTML = rows
    .map((a) => {
      const kindLabel = a.kind === "suffix" ? "Суфф." : a.kind === "affix" || a.kind === "prefix" ? "Преф." : "—";
      const displayName = a.name_ru || a.name || "???";
      if (!a.seen) {
        return `
          <div class="lib-affix-row lib-affix-row--hidden">
            <div class="lib-affix-row-head">
              <span class="lib-affix-row-name">${escapeHtml(displayName)}</span>
              <span class="lib-affix-row-badge">${escapeHtml(kindLabel)}</span>
            </div>
            <div class="lib-affix-row-effect muted tiny">Встретите предмет с этим аффиксом в игре.</div>
          </div>`;
      }
      const desc = a.description_ru || statMeta(a.stat || "").short;
      const range = a.range_label ? ` (${a.range_label})` : "";
      return `
        <div class="lib-affix-row">
          <div class="lib-affix-row-head">
            <span class="lib-affix-row-name">${escapeHtml(displayName)}</span>
            <span class="lib-affix-row-badge">${escapeHtml(kindLabel)}</span>
          </div>
          <div class="lib-affix-row-effect">${escapeHtml(desc)}${escapeHtml(range)}</div>
        </div>`;
    })
    .join("");
}

function libraryItemsSubtabShellHtml() {
  const sub = libraryState.itemsSubtab || "items";
  const itemsActive = sub === "items" ? " active" : "";
  const affActive = sub === "affixes" ? " active" : "";
  if (sub === "affixes") {
    return `
      <div class="lib-body-chrome">
        <div class="lib-items-subtabs">
          <button type="button" class="lib-items-subtab${itemsActive}" onclick="WaifuApp.librarySwitchItemsSubtab('items')">Предметы</button>
          <button type="button" class="lib-items-subtab${affActive}" onclick="WaifuApp.librarySwitchItemsSubtab('affixes')">Аффиксы</button>
        </div>
        <div id="lib-affix-summary" class="lib-summary"></div>
        <div class="lib-filters">
          <input id="lib-affix-search" type="search" placeholder="Поиск…" />
          <select id="lib-affix-kind-filter">
            <option value="all">Все</option>
            <option value="prefix">Префиксы</option>
            <option value="suffix">Суффиксы</option>
          </select>
          <select id="lib-affix-seen">
            <option value="all">Все</option>
            <option value="seen">Открытые</option>
            <option value="unseen">Скрытые</option>
          </select>
        </div>
      </div>
      <div class="lib-body-scroll">
        <div id="lib-affix-list" class="lib-affix-list"></div>
      </div>`;
  }
  return `
    <div class="lib-body-chrome">
      <div class="lib-items-subtabs">
        <button type="button" class="lib-items-subtab${itemsActive}" onclick="WaifuApp.librarySwitchItemsSubtab('items')">Предметы</button>
        <button type="button" class="lib-items-subtab${affActive}" onclick="WaifuApp.librarySwitchItemsSubtab('affixes')">Аффиксы</button>
      </div>
      <div id="lib-items-summary" class="lib-summary"></div>
      <div class="lib-filters">
        <input id="lib-items-search" type="search" placeholder="Поиск…" />
        <select id="lib-items-tier">
          <option value="all">Все тиры</option>
          ${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((t) => `<option value="${t}">T${t}</option>`).join("")}
        </select>
        <select id="lib-items-slot">
          <option value="all">Все слоты</option>
          <option value="weapon_1h">Оружие 1H</option>
          <option value="weapon_2h">Оружие 2H</option>
          <option value="offhand">Offhand</option>
          <option value="costume">Доспех</option>
          <option value="ring">Кольцо</option>
          <option value="amulet">Амулет</option>
        </select>
        <select id="lib-items-seen">
          <option value="all">Все</option>
          <option value="seen">Открытые</option>
          <option value="unseen">Скрытые</option>
        </select>
      </div>
      <p class="lib-tier-hint muted tiny">Цветная рамка — тир предмета (T1–T10).</p>
    </div>
    <div class="lib-body-scroll">
      <div id="lib-items-grid" class="lib-grid lib-grid--items"></div>
    </div>`;
}

function librarySwitchItemsSubtab(subtab) {
  libraryState.itemsSubtab = subtab || "items";
  libraryRenderItemsTab();
}

function libraryRenderItemsTab() {
  const body = document.getElementById("lib-body");
  if (!body) return;
  body.innerHTML = libraryItemsSubtabShellHtml();
  if (libraryState.itemsSubtab === "affixes") {
    libraryBindAffixFilterHandlers();
    libraryRenderAffixesList();
  } else {
    libraryBindItemsFilterHandlers();
    libraryRenderItemsGrid();
  }
}

function ensureLibraryItemModal() {
  let modal = document.getElementById("library-item-modal");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.id = "library-item-modal";
  modal.className = "lib-monster-overlay hidden";
  modal.setAttribute("aria-modal", "true");
  modal.innerHTML = `
    <div class="lib-monster-panel lib-item-detail-panel" role="dialog" aria-label="Карточка предмета" onclick="event.stopPropagation()">
      <button type="button" class="lib-monster-close" aria-label="Закрыть" onclick="WaifuApp.libraryCloseItem()">×</button>
      <div id="library-item-body"></div>
    </div>`;
  modal.addEventListener("click", () => libraryCloseItem());
  document.body.appendChild(modal);
  return modal;
}

function libraryCloseItem() {
  libraryState.itemDetailId = null;
  libraryState.affixDetailKey = null;
  const modal = document.getElementById("library-item-modal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function libraryBuildItemDetailHtml(e) {
  if (!e?.seen) {
    return `<div class="lib-item-detail"><div class="lib-item-detail-name">???</div><p class="muted tiny">Встретите этот предмет в игре.</p></div>`;
  }
  const rows = [];
  if (e.level_min != null) {
    rows.push(
      `<div class="lib-kv"><span>Уровень</span><strong>${escapeHtml(String(e.level_min))}–${escapeHtml(String(e.level_max))}</strong></div>`
    );
  }
  rows.push(`<div class="lib-kv"><span>Тир</span><strong>T${escapeHtml(String(e.tier))}</strong></div>`);
  if (e.damage_min != null) {
    rows.push(
      `<div class="lib-kv"><span>Урон</span><strong>${escapeHtml(String(e.damage_min))}–${escapeHtml(String(e.damage_max))}</strong></div>`
    );
  }
  if (e.armor_base != null) {
    rows.push(`<div class="lib-kv"><span>Броня</span><strong>${escapeHtml(String(e.armor_base))}</strong></div>`);
  }
  if (e.attack_speed != null) {
    rows.push(`<div class="lib-kv"><span>Скорость</span><strong>${escapeHtml(String(e.attack_speed))}</strong></div>`);
  }
  if (e.base_stat) {
    const m = statMeta(e.base_stat);
    rows.push(
      `<div class="lib-kv"><span>${escapeHtml(m.short)}</span><strong>+${escapeHtml(String(e.base_stat_value))}</strong></div>`
    );
  }
  const fakeItem = { art_key: e.art_key, tier: e.tier, slot_type: e.slot_type, weapon_type: e.subtype };
  const artBlock = `<div class="lib-item-detail-art">${itemArtHtml(fakeItem)}</div>`;
  const flavor = String(e.flavor_ru || "").trim();
  const flavorBlock = flavor
    ? `<div class="lib-item-flavor">${escapeHtml(flavor)}</div>`
    : "";
  const tierCls = libraryTierClass(Number(e.tier) || 1);
  return `
    <div class="lib-item-detail lib-mtg ${tierCls}">
      <div class="lib-item-detail-head">
        ${artBlock}
        <div class="lib-item-detail-title">
          <div class="lib-item-detail-name">${escapeHtml(e.name || "???")}</div>
          <div class="lib-item-detail-tier">T${escapeHtml(String(e.tier))}</div>
        </div>
      </div>
      ${flavorBlock}
      <div class="lib-mtg-stats lib-item-detail-stats">${rows.join("")}</div>
    </div>`;
}

function libraryOpenItem(baseTemplateId) {
  const tid = Number(baseTemplateId);
  if (!Number.isFinite(tid)) return;
  libraryCloseMonster();
  libraryState.itemDetailId = tid;
  libraryState.affixDetailKey = null;
  const e = (libraryItemsCatalogCache?.items || []).find((it) => Number(it.base_template_id) === tid);
  ensureLibraryItemModal();
  const body = document.getElementById("library-item-body");
  if (!body) return;
  if (!e) {
    body.innerHTML = '<p class="muted">Нет данных</p>';
  } else {
    body.innerHTML = libraryBuildItemDetailHtml(e);
  }
  const modal = document.getElementById("library-item-modal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

function libraryBuildAffixDetailHtml(a) {
  if (!a?.seen) {
    return `<div class="lib-mtg"><div class="lib-mtg-name">???</div><p class="muted">Встретьте предмет с этим аффиксом в игре.</p></div>`;
  }
  const desc = a.description_ru || statMeta(a.stat || "").short;
  const range = a.range_label ? ` · ${a.range_label}` : "";
  const effectLine = `${escapeHtml(desc)}${escapeHtml(range)}`;
  const kindRu = a.kind === "suffix" ? "Суффикс" : "Префикс";
  return `
    <div class="lib-mtg lib-tier-3">
      <div class="lib-mtg-name"><span class="lib-mtg-name-text">${escapeHtml(a.name || "—")}</span></div>
      <div class="lib-mtg-stats">
        <div class="lib-kv"><span>Тип</span><strong>${escapeHtml(kindRu)}</strong></div>
        <div class="lib-kv"><span>Эффект</span><strong>${effectLine}</strong></div>
      </div>
    </div>`;
}

function libraryOpenAffix(key) {
  libraryCloseMonster();
  libraryState.affixDetailKey = key;
  libraryState.itemDetailId = null;
  const entry = (libraryAffixesCatalogCache?.affixes || []).find((a) => libraryAffixDetailKey(a) === key);
  ensureLibraryItemModal();
  const body = document.getElementById("library-item-body");
  if (!body) return;
  body.innerHTML = entry ? libraryBuildAffixDetailHtml(entry) : '<p class="muted">Нет данных</p>';
  const modal = document.getElementById("library-item-modal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

async function loadLibraryItemsCatalog(force) {
  if (libraryItemsCatalogCache && !force) return libraryItemsCatalogCache;
  const data = await apiFetch("/library/items");
  libraryItemsCatalogCache = data;
  return data;
}

async function loadLibraryAffixesCatalog(force) {
  if (libraryAffixesCatalogCache && !force) return libraryAffixesCatalogCache;
  const data = await apiFetch("/library/affixes");
  libraryAffixesCatalogCache = data;
  return data;
}

async function loadLibraryItemsCatalogs(force) {
  return Promise.all([loadLibraryItemsCatalog(force), loadLibraryAffixesCatalog(force)]);
}

function ensureLibraryStyles() {
  let style = document.getElementById("lib-styles");
  if (!style) {
    style = document.createElement("style");
    style.id = "lib-styles";
    document.head.appendChild(style);
  }
  style.textContent = `
#library-modal.lib-overlay{position:fixed;inset:0;z-index:9000;background:rgba(0,0,0,.72);display:flex;align-items:flex-end;justify-content:center;padding:0}
#library-modal.lib-overlay.hidden{display:none!important}
.lib-panel{width:100%;max-width:480px;max-height:92vh;background:#16100b;border-radius:14px 14px 0 0;border:1px solid rgba(200,146,42,.35);display:flex;flex-direction:column;overflow:hidden}
.lib-head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid rgba(200,146,42,.2);flex-shrink:0}
.lib-head h2{margin:0;font-size:16px;color:#e8b84b}
.lib-close{background:transparent;border:0;color:#c9b8a8;font-size:22px;cursor:pointer;padding:4px 8px}
.lib-tabs{display:flex;gap:6px;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.06);flex-wrap:nowrap;width:100%;box-sizing:border-box;flex-shrink:0;position:relative;z-index:2;background:#16100b}
.lib-tab{display:inline-flex;align-items:center;justify-content:center;flex:1;min-width:0;padding:8px 6px;border:1px solid rgba(200,146,42,.25);border-radius:8px;background:rgba(0,0,0,.25);font-size:18px;line-height:1;cursor:pointer}
.lib-tab.active{border-color:rgba(232,184,75,.7);background:rgba(200,146,42,.15)}
.lib-tab[disabled]{opacity:.35;cursor:not-allowed}
.lib-body{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;padding:0;position:relative;z-index:1}
.lib-body-chrome{flex-shrink:0;padding:10px 12px 0;background:#16100b;position:relative;z-index:2}
.lib-body-scroll{flex:1;min-height:0;overflow-y:auto;padding:8px 12px 16px;-webkit-overflow-scrolling:touch}
#library-modal.lib-overlay.lib-overlay--tutorial-lock{pointer-events:none}
#library-modal.lib-overlay.lib-overlay--tutorial-lock .lib-panel{pointer-events:auto}
#library-monster-modal.lib-monster-overlay,#library-item-modal.lib-monster-overlay{position:fixed;inset:0;z-index:9100;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;padding:12px;box-sizing:border-box}
#library-monster-modal.lib-monster-overlay.hidden,#library-item-modal.lib-monster-overlay.hidden{display:none!important}
.lib-monster-panel{position:relative;width:min(420px,94vw);max-height:88vh;overflow-y:auto;-webkit-overflow-scrolling:touch;border-radius:12px}
.lib-monster-close{position:absolute;top:8px;right:8px;z-index:2;width:32px;height:32px;border-radius:8px;border:1px solid rgba(200,146,42,.4);background:rgba(22,16,11,.92);color:#e8b84b;font-size:20px;line-height:1;cursor:pointer;padding:0}
.lib-summary{font-size:11px;color:rgba(201,184,168,.85);margin-bottom:8px}
.lib-filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.lib-filters select,.lib-filters input{flex:1;min-width:100px;font-size:12px;padding:6px 8px;border-radius:8px;border:1px solid rgba(200,146,42,.3);background:#1f1812;color:#e5e2e1}
.lib-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.lib-grid.lib-grid--items{grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.lib-grid--items .lib-card-meta{padding:3px 4px 5px;font-size:9px}
.lib-tier-hint{margin:-4px 0 8px}
.lib-card{border:2px solid #5a5248;border-radius:10px;background:rgba(0,0,0,.35);cursor:pointer;overflow:hidden;text-align:center}
.lib-card.lib-tier-1{border-color:#9ca3af}.lib-card.lib-tier-2{border-color:#22c55e}.lib-card.lib-tier-3{border-color:#3b82f6}
.lib-card.lib-tier-4{border-color:#a855f7}.lib-card.lib-tier-5{border-color:#f59e0b}.lib-card.lib-tier-6{border-color:#ef4444}
.lib-card.lib-tier-7{border-color:#ec4899}.lib-card.lib-tier-8{border-color:#06b6d4}.lib-card.lib-tier-9{border-color:#eab308}
.lib-card.lib-tier-10{border-color:#f472b6;box-shadow:0 0 8px rgba(234,179,8,.35)}
.lib-card-art{position:relative;aspect-ratio:1;background:#0d0a08;display:flex;align-items:center;justify-content:center}
.lib-card-art.silhouette{filter:brightness(.35) contrast(.9)}
.lib-card-art img{width:100%;height:100%;object-fit:cover}
.lib-art-emoji{font-size:28px}
.lib-card-meta{padding:4px 6px 6px;font-size:10px;line-height:1.2}
.lib-card-name{font-weight:700;color:#e8dcc8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lib-card-tier{color:rgba(201,184,168,.8)}
.lib-mtg{border:2px solid #5a5248;border-radius:12px;background:#f0e6d8;color:#3d2e1f;overflow:hidden;margin:0}
.lib-mtg.lib-tier-1{border-color:#9ca3af}.lib-mtg.lib-tier-2{border-color:#22c55e}.lib-mtg.lib-tier-3{border-color:#3b82f6}
.lib-mtg.lib-tier-4{border-color:#a855f7}.lib-mtg.lib-tier-5{border-color:#f59e0b}.lib-mtg.lib-tier-6{border-color:#ef4444}
.lib-mtg.lib-tier-7{border-color:#ec4899}.lib-mtg.lib-tier-8{border-color:#06b6d4}.lib-mtg.lib-tier-9{border-color:#eab308}
.lib-mtg.lib-tier-10{border-color:#f472b6;box-shadow:0 0 8px rgba(234,179,8,.35)}
.lib-item-detail-panel{width:min(340px,92vw);max-height:85vh}
.lib-item-detail{background:#f0e6d8;color:#3d2e1f;border-radius:12px;overflow:hidden}
.lib-item-detail-head{display:flex;gap:10px;padding:10px 12px;align-items:center;background:#e5d9c8}
.lib-item-detail-art{width:56px;height:56px;flex-shrink:0;border-radius:8px;background:#d8cbb8;display:flex;align-items:center;justify-content:center;overflow:hidden}
.lib-item-detail-art img{width:100%;height:100%;object-fit:contain}
.lib-item-detail-name{font-weight:700;font-size:14px;color:#5c4030}
.lib-item-detail-tier{font-size:11px;color:rgba(92,64,48,.75)}
.lib-item-flavor{margin:0;padding:10px 12px;font-size:12px;line-height:1.55;font-style:italic;color:rgba(61,46,31,.85);border-left:2px solid rgba(200,146,42,.45);background:rgba(61,46,31,.06)}
.lib-item-detail-stats{padding:8px 12px 12px;font-size:12px}
.lib-affix-list{display:flex;flex-direction:column;gap:4px}
.lib-affix-row{padding:8px 10px;border-radius:8px;border:1px solid rgba(200,146,42,.22);background:rgba(0,0,0,.28)}
.lib-affix-row--hidden{opacity:.65}
.lib-affix-row-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px}
.lib-affix-row-name{font-weight:700;font-size:13px;color:#e8dcc8}
.lib-affix-row-badge{font-size:9px;color:rgba(201,184,168,.8);flex-shrink:0}
.lib-affix-row-effect{font-size:11px;line-height:1.4;color:rgba(201,184,168,.92)}
.lib-mtg-name{display:flex;align-items:center;justify-content:flex-start;gap:8px;padding:10px 12px;background:#e5d9c8;font-weight:700;color:#5c4030}
.lib-monster-panel .lib-mtg-name{padding-right:44px}
.lib-mtg-name-text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lib-mtg-admin-art{flex-shrink:0;width:32px;height:32px;border-radius:8px;border:1px solid rgba(92,64,48,.35);background:#f5ebe0;cursor:pointer;font-size:16px;line-height:1}
.lib-mtg-art{position:relative;width:100%;aspect-ratio:4/3;background:#d8cbb8;display:flex;align-items:center;justify-content:center}
.lib-mtg-art.silhouette img{filter:brightness(.4)}
.lib-mtg-art img{width:100%;height:100%;object-fit:contain}
.lib-mtg-stats{padding:10px 12px 12px;font-size:12px}
.lib-kv{display:flex;justify-content:space-between;gap:8px;margin-bottom:4px}
.lib-kv span{color:rgba(61,46,31,.65)}
.lib-study{margin-top:8px;padding-top:8px;border-top:1px solid rgba(61,46,31,.15)}
.lib-study-status{font-weight:600;margin-bottom:6px;color:#5c4030}
.lib-study-track-wrap{position:relative;padding-bottom:24px}
.lib-study-track{position:relative;height:10px;background:rgba(61,46,31,.12);border-radius:6px;overflow:visible}
.lib-study-fill{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#c9a227,#e8b84b);border-radius:6px}
.lib-study-tick{position:absolute;top:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center}
.lib-study-tick-dot{width:8px;height:8px;border-radius:50%;background:#9ca3af;border:2px solid #f0e6d8}
.lib-study-tick.reached .lib-study-tick-dot{background:#e8b84b;border-color:#5c4030}
.lib-study-tick-k{font-size:9px;margin-top:2px;color:rgba(61,46,31,.75)}
.lib-study-bonuses{margin-top:8px}
.lib-study-bonuses-title{font-size:11px;font-weight:600;margin-bottom:4px}
.lib-study-bonus-row{font-size:11px;color:rgba(61,46,31,.85);margin-bottom:2px}
.lib-mechanics h3{font-size:13px;color:#e8b84b;margin:12px 0 6px}
.lib-mechanics p{font-size:12px;color:rgba(201,184,168,.9);line-height:1.45;margin:0 0 8px}
.lib-mechanics-subtabs{display:flex;gap:4px;overflow-x:auto;margin-bottom:10px;padding-bottom:4px;-webkit-overflow-scrolling:touch}
.lib-body-chrome .lib-mechanics-subtabs{margin-bottom:8px}
.lib-body-chrome .lib-filters{margin-bottom:8px}
.lib-body-chrome .lib-summary{margin-bottom:8px}
.lib-body-chrome .lib-tier-hint{margin:0 0 8px}
.lib-mechanics-subtab{flex:0 0 auto;font-size:10px;padding:6px 8px;border-radius:8px;border:1px solid rgba(200,146,42,.25);background:rgba(0,0,0,.25);color:#c9b8a8;cursor:pointer;white-space:nowrap}
.lib-mechanics-subtab.active{border-color:rgba(232,184,75,.7);background:rgba(200,146,42,.15);color:#e8b84b}
.lib-mechanics-body{min-height:40px}
.lib-stats-guide-body p{font-size:12px;color:rgba(201,184,168,.9);line-height:1.45;margin:0 0 8px}
.lib-items-subtabs{display:flex;gap:6px;margin-bottom:10px}
.lib-items-subtab{flex:1;font-size:12px;padding:8px;border-radius:8px;border:1px solid rgba(200,146,42,.25);background:rgba(0,0,0,.25);color:#c9b8a8;cursor:pointer}
.lib-items-subtab.active{border-color:rgba(232,184,75,.7);background:rgba(200,146,42,.15);color:#e8b84b}
.lib-affix-kind{font-size:9px;color:rgba(201,184,168,.75)}
.lib-soon{text-align:center;padding:32px 16px;color:rgba(201,184,168,.7);font-size:13px}
.lib-loading{text-align:center;padding:24px;color:rgba(201,184,168,.8)}
`;
}

function ensureLibraryMonsterModal() {
  let modal = document.getElementById("library-monster-modal");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.id = "library-monster-modal";
  modal.className = "lib-monster-overlay hidden";
  modal.setAttribute("aria-modal", "true");
  modal.innerHTML = `
    <div class="lib-monster-panel" role="dialog" aria-label="Карточка монстра" onclick="event.stopPropagation()">
      <button type="button" class="lib-monster-close" aria-label="Закрыть" onclick="WaifuApp.libraryCloseMonster()">×</button>
      <div id="library-monster-body"></div>
    </div>`;
  modal.addEventListener("click", () => libraryCloseMonster());
  document.body.appendChild(modal);
  return modal;
}

function libraryCloseMonster() {
  libraryState.detailId = null;
  const modal = document.getElementById("library-monster-modal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function libraryBindFilterHandlers() {
  const search = document.getElementById("lib-f-search");
  const act = document.getElementById("lib-f-act");
  const family = document.getElementById("lib-f-family");
  const tier = document.getElementById("lib-f-tier");
  const seen = document.getElementById("lib-f-seen");
  const sort = document.getElementById("lib-f-sort");
  if (search) {
    search.oninput = () => {
      libraryFilters.search = search.value.trim().toLowerCase();
      libraryRenderGrid();
    };
  }
  if (act) {
    act.onchange = () => {
      libraryFilters.act = act.value;
      libraryRenderGrid();
    };
  }
  if (family) {
    family.onchange = () => {
      libraryFilters.family = family.value;
      libraryRenderGrid();
    };
  }
  if (tier) {
    tier.onchange = () => {
      libraryFilters.tier = tier.value;
      libraryRenderGrid();
    };
  }
  if (seen) {
    seen.onchange = () => {
      libraryFilters.seen = seen.value;
      libraryRenderGrid();
    };
  }
  if (sort) {
    sort.onchange = () => {
      librarySort = sort.value;
      libraryRenderGrid();
    };
  }
}

function libraryRenderGrid() {
  const body = document.getElementById("lib-body");
  if (!body || !libraryCatalogCache) return;
  const monsters = libraryCatalogCache.monsters || [];
  const f = libraryFilters;
  const families = [...new Set(monsters.map((m) => m.type || m.family).filter(Boolean))].sort();

  let filtered = monsters.filter((mm) => {
    if (f.search) {
      const hay = `${mm.name || ""} ${mm.type || ""} ${mm.family || ""}`.toLowerCase();
      if (!hay.includes(f.search)) return false;
    }
    if (f.act !== "all") {
      const act = Number(f.act);
      if (act < Number(mm.act_min) || act > Number(mm.act_max)) return false;
    }
    if (f.family !== "all") {
      const fam = mm.type || mm.family || "";
      if (fam !== f.family) return false;
    }
    if (f.seen === "seen" && !mm.seen) return false;
    if (f.seen === "undiscovered" && mm.seen) return false;
    if (f.tier !== "all" && Number(mm.tier) !== Number(f.tier)) return false;
    return true;
  });

  filtered = [...filtered].sort((a, b) => {
    if (librarySort === "name") {
      return String(a.name || "").localeCompare(String(b.name || ""), "ru");
    }
    if (librarySort === "kills") {
      return (Number(b.kills) || 0) - (Number(a.kills) || 0);
    }
    if (librarySort === "tier") {
      return (Number(b.tier) || 0) - (Number(a.tier) || 0);
    }
    const actA = Number(a.act_min) || 0;
    const actB = Number(b.act_min) || 0;
    if (actA !== actB) return actA - actB;
    return Number(a.template_id) - Number(b.template_id);
  });

  const summary = libraryCatalogCache.summary || {};
  const actOpts = LIBRARY_ACT_OPTIONS.map(
    (a) => `<option value="${a}" ${String(f.act) === String(a) ? "selected" : ""}>Акт ${a}</option>`
  ).join("");
  const famOpts =
    `<option value="all">Все типы</option>` +
    families.map((fam) => {
      const label = formatMonsterTypeLabelRu(fam) || fam;
      return `<option value="${escapeHtml(fam)}" ${f.family === fam ? "selected" : ""}>${escapeHtml(label)}</option>`;
    }).join("");
  const tierOpts = `
    <option value="all" ${f.tier === "all" ? "selected" : ""}>Все уровни</option>
    ${[0, 1, 2, 3, 4, 5, 6]
      .map((t) => `<option value="${t}" ${String(f.tier) === String(t) ? "selected" : ""}>Тир ${t}</option>`)
      .join("")}`;
  const seenOpts = `
    <option value="all" ${f.seen === "all" ? "selected" : ""}>Все</option>
    <option value="seen" ${f.seen === "seen" ? "selected" : ""}>Встречено</option>
    <option value="undiscovered" ${f.seen === "undiscovered" ? "selected" : ""}>Не встречены</option>`;

  const cards = filtered
    .map((mm) => {
      const tid = Number(mm.template_id);
      const known = mm.name_known !== false && mm.name !== "???";
      const label = known ? mm.name : "???";
      const artInner = `<img data-lib-art alt="" /><span class="lib-art-emoji" aria-hidden="true">👾</span>`;
      return `
        <div class="lib-card ${libraryTierClass(mm.tier)}" role="button" tabindex="0" data-template-id="${tid}"
          onclick="WaifuApp.libraryOpenMonster(${tid})"
          aria-label="${escapeHtml(label)}">
          <div class="lib-card-art">${artInner}</div>
          <div class="lib-card-meta">
            <div class="lib-card-name">${escapeHtml(label)}</div>
            <div class="lib-card-tier">${Number(mm.kills) || 0} уб.</div>
          </div>
        </div>`;
    })
    .join("");

  body.innerHTML = `
    <div class="lib-body-chrome">
      <div class="lib-summary">Встречено: ${summary.seen ?? 0} / ${summary.total ?? 0} · Покорено: ${summary.completed ?? 0}</div>
      <div class="lib-filters">
        <input id="lib-f-search" type="search" placeholder="Поиск…" value="${escapeHtml(f.search)}" />
        <select id="lib-f-act"><option value="all">Все акты</option>${actOpts}</select>
        <select id="lib-f-family">${famOpts}</select>
        <select id="lib-f-tier">${tierOpts}</select>
        <select id="lib-f-seen">${seenOpts}</select>
        <select id="lib-f-sort">
          <option value="act" ${librarySort === "act" ? "selected" : ""}>По акту</option>
          <option value="name" ${librarySort === "name" ? "selected" : ""}>По имени</option>
          <option value="kills" ${librarySort === "kills" ? "selected" : ""}>По убийствам</option>
          <option value="tier" ${librarySort === "tier" ? "selected" : ""}>По тиру</option>
        </select>
      </div>
    </div>
    <div class="lib-body-scroll">
      <div class="lib-grid" id="lib-grid">${cards || '<p class="muted tiny">Ничего не найдено.</p>'}</div>
    </div>`;

  libraryBindFilterHandlers();
  body.querySelectorAll(".lib-card[data-template-id]").forEach((card) => {
    const tid = Number(card.dataset.templateId);
    const mm = filtered.find((m) => Number(m.template_id) === tid);
    if (mm) libraryAttachArt(card.querySelector(".lib-card-art"), mm);
  });
}

function libraryRenderDetail(templateId) {
  ensureLibraryMonsterModal();
  const body = document.getElementById("library-monster-body");
  if (!body || !libraryCatalogCache) return;
  const tid = Number(templateId);
  libraryState.detailId = tid;
  let e = (libraryCatalogCache.monsters || []).find((m) => Number(m.template_id) === tid);
  if (!e) {
    body.innerHTML = '<p class="muted">Монстр не найден.</p>';
    return;
  }
  const known = e.name_known !== false && e.name !== "???";
  const tiers = libraryCatalogCache.tiers || [];
  const adminBtn = isAdminUser()
    ? `<button type="button" class="lib-mtg-admin-art" title="Сгенерировать изображение (admin)" aria-label="Сгенерировать изображение" onclick="event.stopPropagation();WaifuApp.adminGenerateLibraryMonsterArt(${tid})">🖼</button>`
    : "";
  const artInner = `<img data-lib-art alt="" /><span class="lib-art-emoji" aria-hidden="true">${escapeHtml(e.emoji || "👾")}</span>`;

  body.innerHTML = `
    <div class="lib-mtg ${libraryTierClass(e.tier)}">
      <div class="lib-mtg-name">
        ${adminBtn}
        <span class="lib-mtg-name-text">${escapeHtml(known ? e.name : "Неизвестный монстр")}</span>
      </div>
      <div class="lib-mtg-art">${artInner}</div>
      <div class="lib-mtg-stats">
        ${libraryBuildDetailStats(e)}
        <h4 style="margin:10px 0 4px;font-size:12px;color:#5c4030">Уровни изучения</h4>
        ${libraryStudyProgressHtml(e, tiers)}
      </div>
    </div>`;
  libraryAttachArt(body.querySelector(".lib-mtg-art"), e);
}

function libraryBackToGrid() {
  libraryCloseMonster();
}

function libraryOpenMonster(templateId) {
  ensureLibraryMonsterModal();
  libraryRenderDetail(templateId);
  const modal = document.getElementById("library-monster-modal");
  if (modal) {
    modal.classList.remove("hidden");
    modal.style.display = "flex";
  }
}

async function librarySwitchTab(tabId) {
  libraryCloseMonster();
  libraryCloseItem();
  libraryState.tab = tabId;
  const tabs = document.querySelectorAll("#lib-tabs .lib-tab");
  tabs.forEach((btn) => {
    const active = btn.dataset.libTab === tabId;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  const body = document.getElementById("lib-body");
  if (!body) return;
  if (tabId === "bestiary") {
    libraryRenderGrid();
    return;
  }
  if (tabId === "mechanics") {
    libraryRenderMechanics();
    return;
  }
  if (tabId === "items") {
    if (!libraryItemsCatalogCache || !libraryAffixesCatalogCache) {
      body.innerHTML = '<div class="lib-loading">Загрузка…</div>';
    }
    try {
      await loadLibraryItemsCatalogs(Boolean(!libraryItemsCatalogCache || !libraryAffixesCatalogCache));
      libraryRenderItemsTab();
    } catch (e) {
      const { detail } = parseHttpErrorDetail(e);
      body.innerHTML = `<p class="muted" style="color:#f87171">${escapeHtml(
        detail || "Не удалось загрузить каталог предметов"
      )}</p>`;
    }
    return;
  }
  body.innerHTML = '<div class="lib-soon">Этот раздел появится позже.</div>';
}

function closeLibrary(opts) {
  const force = Boolean(opts && opts.force);
  try {
    const tut = window.WaifuApp && window.WaifuApp.Tutorial;
    if (
      !force &&
      tut &&
      typeof tut.isActive === "function" &&
      tut.isActive() &&
      typeof tut.getFlowId === "function" &&
      tut.getFlowId() === "caravan"
    ) {
      return;
    }
  } catch (e) {
    /* ignore */
  }
  libraryCloseMonster();
  const modal = document.getElementById("library-modal");
  if (modal) {
    modal.classList.add("hidden");
    modal.classList.remove("lib-overlay--tutorial-lock");
    modal.style.display = "none";
    if (Object.prototype.hasOwnProperty.call(modal.dataset, "tutorialPrevZ")) {
      const prev = modal.dataset.tutorialPrevZ;
      delete modal.dataset.tutorialPrevZ;
      if (prev) modal.style.zIndex = prev;
      else modal.style.removeProperty("z-index");
    }
  }
}

async function loadLibraryCatalog(force) {
  if (libraryCatalogCache && !force) return libraryCatalogCache;
  const data = await apiFetch("/library/bestiary");
  libraryCatalogCache = data;
  return data;
}

async function openLibrary(opts) {
  opts = opts || {};
  ensureLibraryStyles();
  let modal = document.getElementById("library-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "library-modal";
    modal.className = "lib-overlay hidden";
    modal.innerHTML = `
      <div class="lib-panel" role="dialog" aria-labelledby="lib-title">
        <div class="lib-head">
          <h2 id="lib-title">Библиотека</h2>
          <button type="button" class="lib-close" aria-label="Закрыть" onclick="WaifuApp.closeLibrary()">×</button>
        </div>
        <div class="lib-tabs" id="lib-tabs"></div>
        <div class="lib-body" id="lib-body"><div class="lib-loading">Загрузка…</div></div>
      </div>`;
    modal.addEventListener("click", (ev) => {
      if (ev.target !== modal) return;
      if (libraryState.detailId != null) {
        libraryCloseMonster();
        return;
      }
      if (libraryState.itemDetailId != null || libraryState.affixDetailKey != null) {
        libraryCloseItem();
        return;
      }
      closeLibrary();
    });
    document.body.appendChild(modal);
  }
  ensureLibraryMonsterModal();
  ensureLibraryItemModal();

  const tabsEl = document.getElementById("lib-tabs");
  if (tabsEl) {
    tabsEl.innerHTML = LIBRARY_TABS.map((t) => {
      const dis = t.enabled ? "" : " disabled";
      const click = t.enabled ? ` onclick="WaifuApp.librarySwitchTab('${t.id}')"` : "";
      return `<button type="button" class="lib-tab${t.id === (opts.tab || "bestiary") ? " active" : ""}" data-lib-tab="${t.id}" data-tutorial="lib-tab-${t.id}" aria-label="${escapeHtml(t.label)}" title="${escapeHtml(t.label)}"${dis}${click}>${t.icon}</button>`;
    }).join("");
  }

  modal.classList.remove("hidden");
  modal.style.display = "flex";
  const body = document.getElementById("lib-body");
  if (body) body.innerHTML = '<div class="lib-loading">Загрузка…</div>';

  const tab = opts.tab || "bestiary";
  libraryState.tab = tab;
  libraryState.detailId = null;

  if (opts.itemsSubtab) {
    libraryState.itemsSubtab = opts.itemsSubtab;
  }

  try {
    const force = Boolean(opts.force);
    if (force) {
      libraryCatalogCache = null;
      libraryItemsCatalogCache = null;
      libraryAffixesCatalogCache = null;
    }
    await Promise.all([
      loadLibraryCatalog(force),
      loadLibraryItemsCatalog(force),
      loadLibraryAffixesCatalog(force),
    ]);
    await librarySwitchTab(tab);
    if (opts.templateId != null) {
      libraryOpenMonster(Number(opts.templateId));
    }
    if (opts.baseTemplateId != null) {
      libraryOpenItem(Number(opts.baseTemplateId));
    }
    if (opts.affixKey) {
      libraryState.itemsSubtab = "affixes";
      librarySwitchItemsSubtab("affixes");
      libraryOpenAffix(String(opts.affixKey));
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    if (body) {
      body.innerHTML = `<p class="muted" style="color:#f87171">${escapeHtml(detail || "Не удалось загрузить библиотеку")}</p>`;
    }
  }
}

let passiveTreeCache = null;
let passiveActiveBranch = "warrior";
/** Вкладка зала: ветка дерева или «hidden» — скрытые навыки. */
let trainingHallTab = "warrior";
let passiveTreeListenersBound = false;
let hiddenSkillsCache = [];
let hiddenSkillsListenersBound = false;
let hiddenSkillsLoaded = false;
let hiddenSkillsLoadInFlight = null;
const HIDDEN_SKILL_WEBP_BASE = `${GAME_STATIC_BASE}/hidden-skills/webp`;
const PASSIVE_SKILL_PLACEHOLDER = `${GAME_STATIC_BASE}/passive-skill-placeholder.svg`;
const PASSIVE_SKILL_WEBP_BASE = `${GAME_STATIC_BASE}/passive-skills/webp`;

function passiveNodeArtUrl(nodeId) {
  const id = String(nodeId || "").trim();
  if (!id) return "";
  return `${PASSIVE_SKILL_WEBP_BASE}/${encodeURIComponent(id)}.webp`;
}

function bindPassiveNodeArt(imgEl, artWrapEl, nodeId) {
  if (!imgEl) return;
  const url = passiveNodeArtUrl(nodeId);
  if (!url) {
    imgEl.src = PASSIVE_SKILL_PLACEHOLDER;
    artWrapEl?.classList.remove("passive-skill-cell-art--has-art");
    if (artWrapEl?.classList.contains("passive-modal-dota-icon-wrap")) {
      artWrapEl.classList.remove("passive-modal-dota-icon-wrap--has-art");
    }
    return;
  }
  imgEl.onerror = () => {
    imgEl.onerror = null;
    imgEl.src = PASSIVE_SKILL_PLACEHOLDER;
    artWrapEl?.classList.remove("passive-skill-cell-art--has-art");
    if (artWrapEl?.classList.contains("passive-modal-dota-icon-wrap")) {
      artWrapEl.classList.remove("passive-modal-dota-icon-wrap--has-art");
    }
  };
  imgEl.onload = () => {
    artWrapEl?.classList.add("passive-skill-cell-art--has-art");
    if (artWrapEl?.classList.contains("passive-modal-dota-icon-wrap")) {
      artWrapEl.classList.add("passive-modal-dota-icon-wrap--has-art");
    }
  };
  imgEl.src = url;
}

/** Иконки узлов пассивного дерева (совпадают с id в БД). */
const PASSIVE_NODE_ICONS = {
  w_bash: "⚔️",
  w_tough: "🛡️",
  w_cry: "🔥",
  w_heavy: "💥",
  w_iron: "🧱",
  w_blood: "🩸",
  w_berserk: "😤",
  w_fort: "🏰",
  w_last: "⚡",
  w_wrath: "👑",
  w_imm: "♾️",
  s_keen: "🎯",
  s_nimble: "💨",
  s_media: "📸",
  s_crit_m: "💎",
  s_shadow: "🌑",
  s_exploit: "🔓",
  s_nth: "🔁",
  s_ghost: "👻",
  s_amp: "📣",
  s_lethal: "☠️",
  s_phantom: "🌫️",
  m_arcane: "🔮",
  m_wisdom: "📖",
  m_trade: "💰",
  m_media_m: "🎬",
  m_lore: "📜",
  m_bargain: "🤝",
  m_surge: "✨",
  m_cmd: "🎖️",
  m_rune: "🛡️",
  m_trans: "🌟",
  m_arch: "👁️",
};

function getPassiveNodeIcon(node) {
  const id = node && node.id;
  if (id && PASSIVE_NODE_ICONS[id]) return PASSIVE_NODE_ICONS[id];
  const b = node && node.branch;
  if (b === "warrior") return "⚔️";
  if (b === "shadow") return "🗡️";
  return "✨";
}

function findPassiveNodeById(nodeId) {
  if (!passiveTreeCache || !passiveTreeCache.branches) return null;
  for (const b of ["warrior", "shadow", "sage"]) {
    const arr = passiveTreeCache.branches[b];
    if (!Array.isArray(arr)) continue;
    const n = arr.find((x) => x.id === nodeId);
    if (n) return n;
  }
  return null;
}

function passiveLearnBlockMessage(node) {
  const reason = node?.learn_block_reason;
  if (!reason) return "";
  const gold = Number(passiveTreeCache?.gold ?? 0);
  const cost = Number(node.cost_gold ?? 0);
  switch (reason) {
    case "locked_waifu_level":
      return `Нужен уровень ОВ ≥ ${node.waifu_level_req}`;
    case "locked_waifu_level_step": {
      const cur = Number(node.current_level) || 0;
      const nextWaifu = Number(node.waifu_level_req) + cur;
      return `Для следующего уровня навыка нужен уровень ОВ ≥ ${nextWaifu}`;
    }
    case "locked_branch_points":
      return `Нужно ≥ ${node.branch_points_req} оч. в этой ветке`;
    case "skill_maxed":
      return "Навык уже максимального уровня";
    case "no_skill_points":
      return "Нет свободных очков навыков (ОПГ)";
    case "insufficient_gold":
      return `Нужно ${cost} 🪙 (у вас ${gold})`;
    default:
      return reason;
  }
}

function passiveLearnErrorToUser(out) {
  const err = (out && out.error) || "";
  if (err === "insufficient_gold") {
    const req = out.required != null ? out.required : "?";
    const have = out.have != null ? out.have : 0;
    return `Нужно ${req} 🪙 (есть ${have})`;
  }
  const map = {
    no_skill_points: "Недостаточно очков навыков (ОПГ)",
    insufficient_waifu_level: "Недостаточный уровень основной вайфу",
    insufficient_branch_points: "Недостаточно очков в ветке",
    waifu_level_step: "Для следующего уровня навыка нужен более высокий уровень ОВ",
    skill_maxed: "Навык уже максимального уровня",
    node_not_found: "Узел не найден",
    player_not_found: "Игрок не найден",
  };
  return map[err] || err || "Ошибка";
}

function passiveNodeCornerOverlay(node) {
  const esc = passiveEscHtml;
  const costNum = Number(node.cost_gold || 0);
  const cost = esc(String(costNum));
  if (node.can_learn) {
    return `<button type="button" class="passive-cell-upgrade passive-cell-upgrade--compact" data-passive-learn="${esc(
      node.id,
    )}" aria-label="Прокачать за ${cost} золота" title="Прокачать · ${cost} 🪙">
      <span class="passive-cell-upgrade-plus" aria-hidden="true">+</span>
      <span class="passive-cell-upgrade-cost">🪙${cost}</span>
    </button>`;
  }
  if (node.learn_block_reason === "insufficient_gold") {
    const hint = esc(passiveLearnBlockMessage(node));
    return `<span class="passive-cell-gold-hint" title="${hint}" aria-label="${hint}">🪙 ${cost}</span>`;
  }
  return "";
}

async function learnPassiveNode(nodeId, triggerEl) {
  const btn = triggerEl;
  if (btn) btn.disabled = true;
  try {
    const out = await apiFetch("/skills/passive/learn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId }),
    });
    if (!out || !out.ok) {
      showToast(passiveLearnErrorToUser(out), "error");
      return;
    }
    closePassiveSkillModal();
    await loadPassiveSkillTree();
    if (typeof refreshAtticChips === "function") refreshAtticChips();
  } catch (e) {
    console.error(e);
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось прокачать узел.", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openPassiveSkillModal(nodeId) {
  const node = findPassiveNodeById(nodeId);
  if (!node) return;
  const m = document.getElementById("passive-skill-modal");
  const title = document.getElementById("passive-modal-title");
  const iconEl = document.getElementById("passive-modal-icon");
  const body = document.getElementById("passive-modal-body");
  if (!m || !title || !body) return;
  m.classList.add("passive-skill-modal--dota");
  const panel = m.querySelector(".passive-skill-modal-panel");
  if (panel) panel.classList.add("passive-skill-modal-panel--dota");
  if (iconEl) iconEl.textContent = getPassiveNodeIcon(node);
  title.textContent = node.name;
  const cur = Number(node.current_level) || 0;
  const max = Number(node.max_level) || 1;
  const eq = Number(node.equipment_level_bonus) || 0;
  const effLv =
    (Number(node.effective_level) > 0 ? Number(node.effective_level) : 0) || cur + eq;
  const brReq =
    node.branch_points_req > 0
      ? `<p class="muted passive-modal-req">Уровень ОВ ≥ ${node.waifu_level_req}, в ветке ≥ ${node.branch_points_req} оч.</p>`
      : `<p class="muted passive-modal-req">Уровень ОВ ≥ ${node.waifu_level_req}</p>`;
  const blockMsg = passiveLearnBlockMessage(node);
  const learnBlock = node.can_learn
    ? `<div class="passive-modal-learn-wrap"><button type="button" class="btn passive-modal-learn-btn" data-passive-modal-learn="${passiveEscHtml(
        node.id,
      )}">Прокачать · 🪙&nbsp;${passiveEscHtml(String(node.cost_gold || 0))}</button></div>`
    : blockMsg
      ? `<p class="passive-modal-blocked muted" role="status">${passiveEscHtml(blockMsg)}</p>`
      : "";
  const ico = getPassiveNodeIcon(node);
  const levelRow = `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Уровень (очки)</span><span class="passive-modal-stat-v">${cur} / ${max}</span></div>`;
  const equipHint =
    eq > 0
      ? `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">От предметов</span><span class="passive-modal-stat-v passive-modal-stat-v--equip">+${eq} к уровню</span></div>`
      : "";
  let curBonusRaw =
    effLv >= 1 && node.effective_effect_value != null && node.effective_effect_value !== undefined
      ? passiveEffectDisplayLabel(node.effect_type, node.effective_effect_value)
      : null;
  if (
    curBonusRaw == null &&
    cur >= 1 &&
    node.current_effect_value != null &&
    node.current_effect_value !== undefined
  ) {
    curBonusRaw = passiveEffectDisplayLabel(node.effect_type, node.current_effect_value);
  }
  if (curBonusRaw == null) curBonusRaw = "—";
  let nextVal = node.next_effective_effect_value;
  if (
    (nextVal == null || nextVal === undefined || nextVal === "") &&
    effLv >= 1 &&
    cur < max
  ) {
    nextVal = passiveExtrapolateEffectValue(node.effect_values, effLv + 1, node.effect_type);
  }
  const nextBonusRaw =
    nextVal != null && nextVal !== undefined && nextVal !== ""
      ? passiveEffectDisplayLabel(node.effect_type, nextVal)
      : "—";
  const cappedEt = PASSIVE_EFFECT_CAPPED_AT_TABLE_MAX.has(String(node.effect_type || ""));
  const cappedWarn =
    cappedEt && eq > 0 && effLv > max
      ? `<p class="muted passive-modal-cap-warn" style="margin:8px 0 0;font-size:12px;">Уровень от предметов не увеличивает эффект — действует максимум по таблице (${curBonusRaw}).</p>`
      : "";
  const curBonusRow = `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Текущий бонус</span><span class="passive-modal-stat-v">${passiveEscHtml(
    curBonusRaw,
  )}</span></div>`;
  const nextBonusRow =
    cur < max
      ? `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Бонус на сл. уровне</span><span class="passive-modal-stat-v">${passiveEscHtml(
          nextBonusRaw,
        )}</span></div>`
      : "";
  body.innerHTML = `
    <div class="passive-modal-dota">
      <div class="passive-modal-dota-top">
        <div class="passive-modal-dota-icon-wrap" aria-hidden="true">
          <img class="passive-modal-dota-placeholder" src="${PASSIVE_SKILL_PLACEHOLDER}" alt="" />
          <span class="passive-modal-dota-emoji">${ico}</span>
        </div>
        <div class="passive-modal-dota-info">
          <p class="passive-modal-dota-tags"><span class="passive-tag passive-tag--type">Пассивный</span></p>
          <p class="passive-modal-dota-desc">${passiveEscHtml(node.description || "—")}</p>
        </div>
      </div>
      ${brReq}
      <div class="passive-modal-dota-stats">
        ${levelRow}
        ${equipHint}
        ${curBonusRow}
        ${nextBonusRow}
        ${cappedWarn}
      </div>
      ${learnBlock}
    </div>
  `;
  bindPassiveNodeArt(
    body.querySelector(".passive-modal-dota-placeholder"),
    body.querySelector(".passive-modal-dota-icon-wrap"),
    node.id
  );
  const learnBtn = body.querySelector("[data-passive-modal-learn]");
  if (learnBtn) {
    learnBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      learnPassiveNode(node.id, learnBtn);
    });
  }
  m.classList.toggle("passive-skill-modal--equip-bonus", eq > 0 || effLv > cur);
  m.style.display = "grid";
  try {
    if (window.WaifuApp?.Tutorial?.isActive?.()) {
      m.dataset.tutorialRaisedZ = "1";
      m.style.zIndex = "99200";
    }
  } catch (e) {
    /* ignore */
  }
}

function closePassiveSkillModal() {
  const m = document.getElementById("passive-skill-modal");
  if (m) {
    m.style.display = "none";
    m.classList.remove("passive-skill-modal--equip-bonus");
    m.classList.remove("passive-skill-modal--dota");
    const panel = m.querySelector(".passive-skill-modal-panel");
    if (panel) panel.classList.remove("passive-skill-modal-panel--dota");
    if (m.dataset.tutorialRaisedZ) {
      delete m.dataset.tutorialRaisedZ;
      m.style.zIndex = "";
    }
  }
}

function passiveEscHtml(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Локальная экстраполяция effect_values (как extrapolate_passive_effect_value на бэкенде),
 * если в ответе API нет next_effective_effect_value.
 */
function passiveExtrapolateEffectValue(effectValues, level, effectType) {
  if (level < 1) return null;
  const raw = Array.isArray(effectValues) ? effectValues : [];
  const vals = raw.map((x) => Number(x)).filter((x) => Number.isFinite(x));
  if (!vals.length) return null;
  const et = String(effectType || "");
  const n = vals.length;
  const capped = PASSIVE_EFFECT_CAPPED_AT_TABLE_MAX;
  if (capped.has(et)) {
    const idx = Math.min(level, n) - 1;
    return idx >= 0 ? vals[idx] : null;
  }
  if (level <= n) return vals[level - 1];
  if (n === 1) return vals[0];
  const vPrev = vals[n - 2];
  const vLast = vals[n - 1];
  const step = vLast - vPrev;
  const over = level - n;
  const out = vLast + step * over;
  if (et === "trade_flat" || et === "nth_hit_crit" || et === "main_stats_flat" || et === "armor_flat") {
    if (et === "nth_hit_crit") return Math.max(1, Math.round(out));
    return Math.round(out);
  }
  return out;
}

/** Форматирование одного значения эффекта (для тултипа и шкалы уровней). */
function formatPassiveEffectValue(effectType, raw) {
  if (raw == null || raw === undefined) return "—";
  if (effectType === "trade_flat" || effectType === "nth_hit_crit" || effectType === "main_stats_flat" || effectType === "armor_flat") return String(raw);
  const n = Number(raw);
  if (Number.isNaN(n)) return String(raw);
  return `+${Math.round(n * 100)}%`;
}

/** Человекочитаемая подпись эффекта пассива (с контекстом механики). */
function passiveEffectDisplayLabel(effectType, raw) {
  if (raw == null || raw === undefined) return "—";
  const et = String(effectType || "");
  if (et === "full_evade_chance") {
    const pct = Math.round(Number(raw) * 100);
    return `Шанс полного уклонения: ${pct}% (отдельный бросок после обычного уклонения)`;
  }
  if (et === "evade_pct") {
    return `${formatPassiveEffectValue(et, raw)} к шансу уклонения (строка «Уклонение» в профиле)`;
  }
  if (et === "instakill_chance") {
    return `Шанс мгновенного убийства: ${Math.round(Number(raw) * 100)}%`;
  }
  if (et === "revive_chance" || et === "survive_chance") {
    return `${formatPassiveEffectValue(et, raw)} (эффект с потолком по таблице уровней)`;
  }
  return formatPassiveEffectValue(et, raw);
}

const PASSIVE_EFFECT_CAPPED_AT_TABLE_MAX = new Set([
  "instakill_chance",
  "revive_chance",
  "survive_chance",
  "full_evade_chance",
]);

function passiveNodeStateClass(node) {
  const cur = Number(node.current_level) || 0;
  const max = Number(node.max_level) || 1;
  const eq = Number(node.equipment_level_bonus) || 0;
  const effLvRaw = Number(node.effective_level);
  const effLv = (Number.isFinite(effLvRaw) && effLvRaw > 0 ? effLvRaw : 0) || cur + eq;
  if (node.is_locked && effLv === 0) return "passive-skill-cell--locked";
  if (effLv >= max) return "passive-skill-cell--maxed";
  if (effLv > 0) return "passive-skill-cell--partial";
  return "passive-skill-cell--available";
}

function passiveBranchPointsInCache(branch) {
  if (!passiveTreeCache || !passiveTreeCache.branches) return 0;
  const arr = passiveTreeCache.branches[branch];
  if (!Array.isArray(arr)) return 0;
  return arr.reduce((s, n) => s + (Number(n.current_level) || 0), 0);
}

function updatePassiveTabLabels(branchPoints) {
  const bp = branchPoints || {};
  const labels = [
    ["warrior", "passive-tab-label-warrior", "Воин"],
    ["shadow", "passive-tab-label-shadow", "Тень"],
    ["sage", "passive-tab-label-sage", "Мудрец"],
  ];
  for (const [key, id, title] of labels) {
    const n = Number(bp[key]) || 0;
    setText(id, `${title} ${n}`);
  }
}

function updatePassiveResetButtonLabel() {
  const btn = document.getElementById("passive-reset-branch");
  if (!btn || !passiveTreeCache) return;
  const pts = passiveBranchPointsInCache(passiveActiveBranch);
  const per = Number(passiveTreeCache.reset_cost_per_point) || 500;
  const cost = Math.round(pts * per);
  btn.textContent =
    pts > 0 ? `Сбросить ветку (~${cost} 🪙)` : "Сбросить очки текущей ветки";
}

/** Одна ячейка дерева: бейдж уровня на art, оверлей +/стоимость. */
function renderPassiveNodeCard(node) {
  const esc = passiveEscHtml;
  const cur = Number(node.current_level) || 0;
  const eq = Number(node.equipment_level_bonus) || 0;
  const effLvRaw = Number(node.effective_level);
  const displayEffLv =
    (Number.isFinite(effLvRaw) && effLvRaw > 0 ? effLvRaw : 0) || cur + eq;
  const hasEquipLift = eq > 0 || displayEffLv > cur;
  const st = `${passiveNodeStateClass(node)}${hasEquipLift ? " passive-skill-cell--equip-bonus" : ""}`;
  const artEquipClass = hasEquipLift ? " passive-skill-cell-art--equip-bonus" : "";
  const ico = getPassiveNodeIcon(node);
  const reqHint =
    node.is_locked && displayEffLv === 0
      ? `ур.${node.waifu_level_req}, в ветке ≥${node.branch_points_req} оч.`
      : "";
  const levelHint = displayEffLv > 0 ? ` · ур. ${displayEffLv}` : "";
  const blockHint = !node.can_learn && node.learn_block_reason ? passiveLearnBlockMessage(node) : "";
  const titleExtra = blockHint ? ` — ${blockHint}` : "";
  const titleAttr = (reqHint ? `${node.name} — ${reqHint}` : `${node.name}${levelHint}${titleExtra}`)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;");
  const cornerOverlay = passiveNodeCornerOverlay(node);
  const badgeEquip = hasEquipLift;
  const levelBadge =
    displayEffLv > 0
      ? `<span class="passive-skill-cell-lv-badge${
          badgeEquip ? " passive-skill-cell-lv-badge--equip" : ""
        }" aria-label="Уровень ${displayEffLv}${
          badgeEquip ? ", есть бонус от предметов" : ""
        }">${esc(String(displayEffLv))}</span>`
      : "";
  return `<div class="passive-skill-cell ${st}" data-node-id="${esc(node.id)}" role="button" tabindex="0" title="${titleAttr}">
    <div class="passive-skill-cell-inner">
      <div class="passive-skill-cell-art${artEquipClass}">
        <img class="passive-skill-cell-img" src="${PASSIVE_SKILL_PLACEHOLDER}" alt="" decoding="async" />
        <span class="passive-skill-cell-emoji" aria-hidden="true">${ico}</span>
        ${levelBadge}
        ${
          node.is_locked && cur === 0 && displayEffLv === 0
            ? `<span class="passive-skill-cell-lock" aria-hidden="true">🔒</span>`
            : ""
        }
        ${cornerOverlay}
      </div>
      <div class="passive-skill-cell-title">${esc(node.name)}</div>
    </div>
  </div>`;
}

function renderPassiveEmptyCell() {
  return `<div class="passive-skill-cell passive-skill-cell--empty" aria-hidden="true">
    <div class="passive-skill-cell-inner">
      <div class="passive-skill-cell-art passive-skill-cell-art--empty"></div>
    </div>
  </div>`;
}

function renderPassiveTree() {
  const root = document.getElementById("passive-tree-root");
  if (!root || !passiveTreeCache) return;
  const branches = passiveTreeCache.branches || {};
  const nodes = Array.isArray(branches[passiveActiveBranch]) ? branches[passiveActiveBranch] : [];
  const byTier = new Map();
  nodes.forEach((n) => {
    const t = Number(n.tier) || 1;
    if (!byTier.has(t)) byTier.set(t, []);
    byTier.get(t).push(n);
  });
  let html = `<div class="passive-tree-panel">`;
  for (let tier = 1; tier <= 4; tier++) {
    const rowSorted = (byTier.get(tier) || []).sort(
      (a, b) => (Number(a.position) || 0) - (Number(b.position) || 0),
    );
    const slots = [];
    for (let i = 0; i < 3; i++) slots.push(rowSorted[i] || null);
    const first = slots.find((n) => n != null);
    const lbl = first ? `Ур. ${first.waifu_level_req}` : `Тир ${tier}`;
    const reqBadge =
      first && first.branch_points_req > 0 ? `нужно ≥${first.branch_points_req} оч. в этой ветке` : "";
    html += `<div class="passive-tier-band" data-tier="${tier}">`;
    html += `<div class="passive-tier-head"><span class="passive-tier-badge">${passiveEscHtml(
      lbl,
    )}</span>`;
    html += reqBadge
      ? `<span class="passive-tier-sub">${passiveEscHtml(reqBadge)}</span>`
      : `<span class="passive-tier-sub passive-tier-sub--empty"></span>`;
    html += `</div>`;
    html += `<div class="passive-tier-nodes passive-tier-nodes--fixed">`;
    slots.forEach((node) => {
      html += node ? renderPassiveNodeCard(node) : renderPassiveEmptyCell();
    });
    html += `</div></div>`;
  }
  html += `</div>`;
  root.innerHTML = html;
  root.classList.remove("placeholder");
  root.querySelectorAll("[data-passive-learn]").forEach((btn) => {
    btn.addEventListener("click", onPassiveLearnClick);
  });
  root.querySelectorAll(".passive-skill-cell[data-node-id]").forEach((el) => {
    const id = el.getAttribute("data-node-id");
    bindPassiveNodeArt(el.querySelector(".passive-skill-cell-img"), el.querySelector(".passive-skill-cell-art"), id);
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-stop-modal]") || ev.target.closest("[data-passive-learn]")) return;
      if (id) openPassiveSkillModal(id);
    });
    el.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      if (ev.target.closest("[data-passive-learn]")) return;
      ev.preventDefault();
      const id = el.getAttribute("data-node-id");
      if (id) openPassiveSkillModal(id);
    });
  });
  updatePassiveTabLabels(passiveTreeCache.branch_points);
  updatePassiveResetButtonLabel();
}

async function onPassiveLearnClick(ev) {
  ev.stopPropagation();
  const id = ev.currentTarget && ev.currentTarget.getAttribute("data-passive-learn");
  if (!id) return;
  await learnPassiveNode(id, ev.currentTarget);
}

function applyTrainingHallTabUI() {
  const passiveView = document.getElementById("training-passive-view");
  const hiddenView = document.getElementById("training-hidden-view");
  const perfectionView = document.getElementById("training-perfection-view");
  document.querySelectorAll(".passive-tab[data-training-tab]").forEach((t) => {
    const tab = t.getAttribute("data-training-tab");
    const active = tab === trainingHallTab;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", active ? "true" : "false");
  });
  if (passiveView) {
    passiveView.hidden = trainingHallTab === "hidden" || trainingHallTab === "perfection";
  }
  if (hiddenView) {
    hiddenView.hidden = trainingHallTab !== "hidden";
  }
  if (perfectionView) {
    perfectionView.hidden = trainingHallTab !== "perfection";
  }
}

function bindPassiveTreeListenersOnce() {
  if (passiveTreeListenersBound) return;
  passiveTreeListenersBound = true;
  const closeM = document.getElementById("passive-modal-close");
  if (closeM) closeM.addEventListener("click", closePassiveSkillModal);
  document.querySelectorAll(".passive-tab[data-training-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      const key = tab.getAttribute("data-training-tab");
      if (!key) return;
      trainingHallTab = key;
      if (key === "hidden") {
        applyTrainingHallTabUI();
        loadHiddenSkillsIfNeeded();
        return;
      }
      if (key === "perfection") {
        applyTrainingHallTabUI();
        loadPerfectionPanel();
        return;
      }
      passiveActiveBranch = key;
      renderPassiveTree();
      updatePassiveResetButtonLabel();
      applyTrainingHallTabUI();
    });
  });
  applyTrainingHallTabUI();
  const resetBtn = document.getElementById("passive-reset-branch");
  if (resetBtn) {
    resetBtn.addEventListener("click", async () => {
      const pts = passiveBranchPointsInCache(passiveActiveBranch);
      if (pts <= 0) {
        showToast("В этой ветке нет вложенных очков.", "error");
        return;
      }
      const per = passiveTreeCache ? Number(passiveTreeCache.reset_cost_per_point) || 500 : 500;
      const cost = Math.round(pts * per);
      const branchRu =
        passiveActiveBranch === "warrior"
          ? "Воин"
          : passiveActiveBranch === "shadow"
            ? "Тень"
            : "Мудрец";
      const confirmed = await confirmAction(`Сбросить ветку «${branchRu}»? Примерно ${cost} 🪙.`);
      if (!confirmed) return;
      resetBtn.disabled = true;
      try {
        const out = await apiFetch(`/skills/passive/reset/${encodeURIComponent(passiveActiveBranch)}`, {
          method: "POST",
        });
        if (!out || !out.ok) {
          let msg = (out && out.error) || "Ошибка";
          if (out && out.error === "insufficient_gold")
            msg = `Нужно ${out.required} 🪙 (есть ${out.have})`;
          showToast(msg, "error");
          return;
        }
        const refunded = Number(out.points_refunded) || pts;
        showToast(`Ветка «${branchRu}» сброшена. Возвращено ${refunded} очк.`, "success");
        await loadPassiveSkillTree();
        if (typeof refreshAtticChips === "function") refreshAtticChips();
      } catch (e) {
        console.error(e);
        const { detail } = parseHttpErrorDetail(e);
        showToast(detail || "Не удалось сбросить ветку.", "error");
      } finally {
        resetBtn.disabled = false;
      }
    });
  }
}

async function loadPassiveSkillTree() {
  const root = document.getElementById("passive-tree-root");
  bindPassiveTreeListenersOnce();
  try {
    const data = await apiFetch("/skills/passive/tree");
    passiveTreeCache = data;
    const ptsWrap = document.getElementById("passive-free-pts-wrap");
    if (ptsWrap) ptsWrap.hidden = false;
    setText("passive-free-pts", data.skill_points);
    if (data.gold != null && typeof setText === "function") setText("badge-gold", data.gold);
    updatePassiveTabLabels(data.branch_points || {});
    renderPassiveTree();
  } catch (e) {
    if (isWebAppUnauthorizedError(e)) {
      console.warn("Дерево навыков: нет авторизации Telegram WebApp.");
    } else {
      console.error(e);
    }
    if (root) {
      root.classList.remove("placeholder");
      if (isWebAppUnauthorizedError(e)) {
        root.innerHTML = webAppAuthNoticeHtml();
      } else {
        const { detail } = parseHttpErrorDetail(e);
        root.innerHTML = `<div class="webapp-auth-notice webapp-auth-notice--error" role="alert"><p>${passiveEscHtml(
          detail || "Не удалось загрузить дерево навыков.",
        )}</p></div>`;
      }
    }
  }
}

function formatHiddenEffectValue(effectType, raw) {
  if (raw == null || raw === undefined) return "—";
  const n = Number(raw);
  if (Number.isNaN(n)) return String(raw);
  const t = String(effectType || "");
  if (t.startsWith("media_") && t.endsWith("_mult")) return `×${n.toFixed(2)}`;
  if (t === "all_stats_pct") return `+${Math.round(n)}% к СИЛ/ЛОВ/ИНТ/УДЧ`;
  if (t === "enchant_cost_pct") {
    return `${n > 0 ? "+" : ""}${Math.round(n)}%`;
  }
  if (t === "enchant_chance_pct") {
    return `+${Math.round(-n)}%`;
  }
  return `+${Math.round(n)}%`;
}

function formatHiddenEffectsBlock(effects) {
  if (!effects || typeof effects !== "object") return "—";
  const keys = Object.keys(effects);
  if (!keys.length) return "—";
  return keys
    .map((k) => `${formatHiddenEffectValue(k, effects[k])}`)
    .join(" · ");
}

function hiddenSkillArtUrl(skill) {
  const direct = String(skill?.image_url || "").trim();
  if (direct) return direct;
  const id = String(skill?.id || "").trim();
  if (!id) return "";
  return `${HIDDEN_SKILL_WEBP_BASE}/${encodeURIComponent(id)}.webp`;
}

function hiddenSkillArtHasClass(artWrapEl) {
  return artWrapEl?.classList.contains("hidden-skill-modal-icon-wrap")
    ? "hidden-skill-modal-icon-wrap--has-art"
    : "hidden-skill-card-art--has-art";
}

function bindHiddenSkillArt(imgEl, artWrapEl, skill) {
  if (!imgEl) return;
  const hasArtClass = hiddenSkillArtHasClass(artWrapEl);
  const url = hiddenSkillArtUrl(skill);
  const clearArt = () => {
    artWrapEl?.classList.remove(hasArtClass);
    imgEl.removeAttribute("src");
  };
  if (!url) {
    clearArt();
    return;
  }
  imgEl.onerror = () => {
    imgEl.onerror = null;
    clearArt();
  };
  imgEl.onload = () => {
    artWrapEl?.classList.add(hasArtClass);
  };
  imgEl.src = url;
}

function findHiddenSkillById(skillId) {
  return hiddenSkillsCache.find((s) => s.id === skillId) || null;
}

function openHiddenSkillModal(skillId) {
  const s = findHiddenSkillById(skillId);
  if (!s) return;
  const m = document.getElementById("hidden-skill-modal");
  const title = document.getElementById("hidden-skill-modal-title");
  const iconWrap = document.getElementById("hidden-skill-modal-icon-wrap");
  const iconImg = document.getElementById("hidden-skill-modal-img");
  const iconEmoji = document.getElementById("hidden-skill-modal-emoji");
  const body = document.getElementById("hidden-skill-modal-body");
  if (!m || !title || !body) return;
  if (iconEmoji) iconEmoji.textContent = s.icon || "✨";
  bindHiddenSkillArt(iconImg, iconWrap, s);
  title.textContent = s.name || "—";
  const lv = Number(s.level) || 0;
  const cnt = Number(s.counter) || 0;
  const next = s.next_threshold != null ? Number(s.next_threshold) : null;
  const curFx = formatHiddenEffectsBlock(s.current_effects);
  const nextFx =
    s.next_effects && Object.keys(s.next_effects).length
      ? formatHiddenEffectsBlock(s.next_effects)
      : "—";
  const unlockHint = s.unlock_hint || "—";
  body.innerHTML = `
    <div class="passive-modal-dota">
      <p class="muted" style="margin:0 0 8px">${passiveEscHtml(s.category || "")}</p>
      <p class="passive-modal-dota-desc">${passiveEscHtml(s.description || "—")}</p>
      <div class="passive-modal-dota-stats">
        <div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Текущий бонус</span><span class="passive-modal-stat-v">${passiveEscHtml(curFx)}</span></div>
        <div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Бонус на сл. уровне</span><span class="passive-modal-stat-v">${passiveEscHtml(nextFx)}</span></div>
        <div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Уровень</span><span class="passive-modal-stat-v">${lv} / ${Number(s.max_level) || 5}</span></div>
      </div>
      <div class="hidden-skill-modal-progress">
        <strong>Прогресс</strong>
        <p>Счётчик: ${cnt}${next != null ? ` / ${next}` : ""}</p>
        ${
          next && next > 0
            ? `<div class="hidden-skill-bar"><div class="hidden-skill-bar-fill" style="width:${Math.min(100, Math.round((cnt / next) * 100))}%"></div></div>`
            : ""
        }
      </div>
      <p class="hidden-skill-modal-hint"><strong>Как открыть:</strong> ${passiveEscHtml(unlockHint)}</p>
    </div>
  `;
  m.style.display = "grid";
}

function closeHiddenSkillModal() {
  const m = document.getElementById("hidden-skill-modal");
  if (m) m.style.display = "none";
}

function bindHiddenSkillsListenersOnce() {
  if (hiddenSkillsListenersBound) return;
  hiddenSkillsListenersBound = true;
  const closeBtn = document.getElementById("hidden-skill-modal-close");
  if (closeBtn) closeBtn.addEventListener("click", closeHiddenSkillModal);
  const root = document.getElementById("hidden-skills-root");
  if (!root) return;
  root.addEventListener("click", (ev) => {
    const card = ev.target.closest("[data-hidden-skill-id]");
    if (!card) return;
    const id = card.getAttribute("data-hidden-skill-id");
    if (id) openHiddenSkillModal(id);
  });
  root.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const card = ev.target.closest("[data-hidden-skill-id]");
    if (!card) return;
    ev.preventDefault();
    const id = card.getAttribute("data-hidden-skill-id");
    if (id) openHiddenSkillModal(id);
  });
}

async function renderHiddenSkillsList() {
  bindHiddenSkillsListenersOnce();
  const root = document.getElementById("hidden-skills-root");
  if (!root) return;
  const skills = hiddenSkillsCache.filter((s) => Boolean(s.revealed));
  if (!skills.length) {
    root.textContent = "Нет открытых скрытых навыков.";
    root.classList.remove("placeholder");
    return;
  }
  const byCat = new Map();
  skills.forEach((s) => {
    const c = s.category || "Прочее";
    if (!byCat.has(c)) byCat.set(c, []);
    byCat.get(c).push(s);
  });
  const esc = (v) =>
    String(v ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  let html = "";
  for (const [cat, list] of byCat) {
    html += `<div class="hidden-skills-cat">${esc(cat)}</div>`;
    list.forEach((s) => {
      const lv = Number(s.level) || 0;
      html += `<div class="hidden-skill-card" data-hidden-skill-id="${esc(s.id)}" role="button" tabindex="0" title="Подробнее">
          <div class="hidden-skill-card-inner">
            <div class="hidden-skill-card-title">${esc(s.name)}</div>
            <div class="hidden-skill-card-art">
              <img class="hidden-skill-card-img" alt="" decoding="async" />
              <span class="hidden-skill-card-emoji" aria-hidden="true">${esc(s.icon || "✨")}</span>
              <span class="hidden-skill-card-lv-badge" aria-label="Уровень ${lv}">${esc(String(lv))}</span>
            </div>
          </div>
        </div>`;
    });
  }
  root.classList.remove("placeholder");
  root.innerHTML = html;
  root.querySelectorAll(".hidden-skill-card[data-hidden-skill-id]").forEach((el) => {
    const id = el.getAttribute("data-hidden-skill-id");
    const skill = findHiddenSkillById(id);
    if (!skill) return;
    bindHiddenSkillArt(
      el.querySelector(".hidden-skill-card-img"),
      el.querySelector(".hidden-skill-card-art"),
      skill,
    );
  });
}

async function loadHiddenSkillsIfNeeded() {
  if (hiddenSkillsLoaded) return;
  if (hiddenSkillsLoadInFlight) return hiddenSkillsLoadInFlight;
  const root = document.getElementById("hidden-skills-root");
  if (!root) return;
  hiddenSkillsLoadInFlight = (async () => {
    try {
      const data = await apiFetch("/skills/hidden");
      hiddenSkillsCache = Array.isArray(data?.skills) ? data.skills : [];
      hiddenSkillsLoaded = true;
      await renderHiddenSkillsList();
    } catch (e) {
      if (isWebAppUnauthorizedError(e)) {
        console.warn("Скрытые навыки: нет авторизации Telegram WebApp.");
      } else {
        console.error(e);
      }
      root.classList.remove("placeholder");
      if (isWebAppUnauthorizedError(e)) {
        root.innerHTML = `<div class="webapp-auth-notice webapp-auth-notice--compact" role="alert"><p>Раздел недоступен без авторизации Telegram (см. блок выше).</p></div>`;
      } else {
        const { detail } = parseHttpErrorDetail(e);
        root.textContent = detail || "Не удалось загрузить скрытые навыки.";
      }
    } finally {
      hiddenSkillsLoadInFlight = null;
    }
  })();
  return hiddenSkillsLoadInFlight;
}

async function populateTrainingHall() {
  await loadHiddenSkillsIfNeeded();
}

const SMITH_HELP_HTML = `
  <h4>Заточка +N</h4>
  <p>Оплачивается золотом. Оружие усиливает урон, броня — броню, аксессуары — вторичный бонус (крит, уклонение и т.д.). Уровни +1…+7 без риска; с +8 возможна неудача. Камень защиты смягчает откат до +6. При первой успешной заточке +1 на подходящем предмете может пробудиться случайная вторичка.</p>
  <h4>Зачарование</h4>
  <p>Оплачивается пылью. Можно выдать, сменить (другой тип и значение) или усилить вторичный бонус на любом предмете. Пассивный бонус предмета зачарованием не меняется.</p>
  <h4>Пыль</h4>
  <p>Получается распылением предметов в инвентаре. Продажа предметов пыль не даёт.</p>
  <h4>Ресурсы</h4>
  <p>Золото отображается в чердаке. Пыль и камни защиты — в строке над кузницей.</p>
`;

function openSmithHelpModal() {
  const modal = document.getElementById("smith-help-modal");
  const body = document.getElementById("smith-help-body");
  if (!modal || !body) return;
  body.innerHTML = SMITH_HELP_HTML;
  modal.style.display = "grid";
  modal.setAttribute("aria-hidden", "false");
}

function closeSmithHelpModal() {
  const modal = document.getElementById("smith-help-modal");
  if (!modal) return;
  modal.style.display = "none";
  modal.setAttribute("aria-hidden", "true");
}

// Page IIFE bundles (dungeons.min.js, tavern.min.js) resolve shell helpers via window.*
function exportWebAppShellGlobals() {
  Object.assign(window, {
    GAME_STATIC_BASE,
    WAIFU_WEBAPP_VERSION,
    DUNGEONS_STATIC_BASE,
    TAVERN_STATIC_BASE,
    EXPEDITION_BIOMES_BASE,
    EXPEDITION_ARCHETYPES_BASE,
    TAVERN_BGM_TRACKS,
    expeditionArchetypeArtVersion,
    PERK_ICONS,
    PERK_DESCS,
    PERK_NAMES,
    PERK_EXPEDITION_COUNTER_HINT,
    WAIFU_RACES,
    WAIFU_CLASSES,
    apiFetch,
    loadProfile,
    safeNumber,
    safeInt,
    clamp01,
    escapeHtml,
    setText,
    setHTML,
    showToast,
    parseHttpErrorDetail,
    confirmAction,
    getPlusLevelForDungeon,
    setPlusLevelForDungeon,
    dungeonPlusStatusById,
    selectedPlusLevelByDungeonId,
    fetchActiveDungeon,
    invalidateActiveDungeonCache,
    formatMonsterTypeLabelRu,
    setSoloExitBtnVisible,
    renderAtticDungeon,
    renderAtticLevelCircle,
    renderAtticExpeditions,
    refreshAtticChips,
    appendEvent,
    expeditionState,
    expeditionUiCache,
    expeditionSend,
    rarityLabel,
    rarityClass,
    slotTypeLabel,
    itemIconForSlotType,
    itemArtHtml,
    hiredWaifuImageUrl,
    resolveImageUrl,
    classIcon,
    raceIcon,
    waifuPortraitEmoji,
    openItemModal,
    isAdminUser,
    isAdminUiEnabled,
    profileState,
    tg,
    className,
    raceName,
  });
}
exportWebAppShellGlobals();

// Expose helpers globally for inline usage (merge, don't clobber handlers assigned earlier)
window.WaifuApp = Object.assign(window.WaifuApp || {}, {
  initPage,
  bootstrapPage,
  bootstrapTrainingHall,
  bootstrapShopPage,
  bootstrapTavernPage,
  bootstrapPlayerPage,
  populateTrainingHall,
  loadPassiveSkillTree,
  loadHiddenSkillsIfNeeded,
  closePassiveSkillModal,
  openHiddenSkillModal,
  closeHiddenSkillModal,
  closePerfectionChooseModal,
  loadPerfectionPanel,
  loadProfile,
  renderAtticDungeon,
  renderAtticLevelCircle,
  renderAtticExpeditions,
  refreshAtticChips,
  shopPageBootstrap,
  loadShop,
  onShopHeroAdvice,
  hideShopHeroDialogs,
  switchShopTab,
  switchSmithSubTab,
  loadSmithTab,
  smithTryEnchant,
  smithAutoSafeEnchant,
  smithTryCraftEnchant,
  refreshSmithCraftPreview,
  openSmithHelpModal,
  closeSmithHelpModal,
  openSmithPickModal,
  closeSmithPickModal,
  pickSmithItem,
  smithPickPrev,
  smithPickNext,
  buyProtectionStoneShop,
  switchProfileTab,
  switchProfileInfoTab,
  populateProfile,
  loadChatRewardsStatus,
  claimChatRewards,
  closeChatRewardClaimModal,
  openProfileStatInfoModal,
  closeProfileStatInfoModal,
  toggleProfileStatAccordion,
  toggleProfileInventoryMode,
  toggleProfileInventoryFilter,
  setProfileInventorySort,
  toggleProfileInventorySortDir,
  changeProfileInventoryPage,
  openProfileSlot,
  openItemById,
  closeSlotModal,
  setSlotSort,
  toggleSlotSortDir,
  togglePaperdollMenu,
  generateMainWaifuPaperdoll,
  closeItemModal,
  equipItemToProfileSlot,
  unequipItemFromModal,
  equipItemFromModal,
  openProfileSlotReplacementFromModal,
  openItemSellConfirmOverlay,
  closeItemSellConfirmOverlay,
  openItemDismantleConfirmOverlay,
  closeItemDismantleConfirmOverlay,
  confirmDismantleSelectedItem,
  closeItemEquipRingOverlay,
  confirmEquipToRingSlot,
  confirmSellSelectedItem,
  goShopSmithEnchant,
  goShopSmithEnchantFromModal,
  resetMainWaifu,
  adminLevelUpWaifu,
  adminAddMainWaifuStat,
  adminAddStatPoints,
  adminResetMainWaifuStatSpend,
  adminClearAllItems,
  adminOpenSpawnItemModal,
  adminCloseSpawnItemModal,
  adminOpenSpawnAffixModal,
  adminCloseSpawnAffixModal,
  adminSpawnOnArtError,
  adminSpawnSelectTemplate,
  adminSpawnToggleAffix,
  adminSpawnToggleAffixFromEl,
  adminSpawnSubmit,
  showToast,
  initWaifuGenerator,
  initTitleScreen,
  initSettingsPage,
  openSettingsNotifyModal,
  closeSettingsNotifyModal,
  isAdminUiEnabled,
  syncAdminUiVisibility,
  setAdminUiEnabled,
  waifuGenGoStep1,
  waifuGenGoStep2,
  waifuGenPreviewPortrait,
  setWaifuGenMagicLoading,
  submitWaifuCreation,
  closeShopModal,
  confirmBuy,
  refreshShopDebug,
  refreshMerchantLine,
  revealMerchantAdvice,
  adminAddGold,
  adminKillMonster,
  adminCompleteDungeon,
  adminRestoreHpEnergy,
  adminGenerateMonsterArt,
  adminGenerateLibraryMonsterArt,
  openLibrary,
  closeLibrary,
  librarySwitchTab,
  librarySwitchMechanicsSubtab,
  librarySwitchItemsSubtab,
  libraryOpenMonster,
  libraryCloseMonster,
  libraryOpenItem,
  libraryCloseItem,
  libraryOpenAffix,
  libraryBackToGrid,
  adminGenerateMainWaifuPaperdoll,
  sellSelected,
  toggleShopSellFilter,
  setShopSellSort,
  toggleShopSellSortDir,
  gambleShop,
  loadGambleTab,
  openGambleConfirm,
  showShopGambleResultModal,
  closeShopGambleResultModal,
  loadSkills,
  searchGuilds,
  populateGuildHall,
  refreshGuildHall,
  setGuildPageLoading,
  switchGuildTab,
  switchGuildActivityTab,
  loadGuildQuests,
  switchGuildQuestTab,
  voteWeeklyQuest,
  createGuildFromHall,
  joinGuildFromSearch,
  leaveGuildFromHall,
  runGuildSearch,
  openGuildBankGoldModal,
  closeGuildBankGoldModal,
  confirmGuildBankGold,
  confirmGuildBankGoldDeposit,
  confirmGuildBankGoldTake,
  openGuildBankDepositModal,
  closeGuildBankDepositModal,
  guildBankDepositPrevPage,
  guildBankDepositNextPage,
  openGuildBankDepositItemPreview,
  closeGuildBankDepositItemPreview,
  confirmGuildBankDepositItem,
  openGuildBankItemModal,
  closeGuildBankItemModal,
  confirmGuildBankTake,
  toggleGuildBankFilter,
  setGuildBankSort,
  toggleGuildBankSortDir,
  guildBankPrevPage,
  guildBankNextPage,
  openGuildSkillModal,
  closeGuildSkillModal,
  guildSkillUpgrade,
  guildSkillReset,
  switchGuildSkillsBranch,
  openGuildMemberPreviewModal,
  closeGuildMemberPreviewModal,
  openGuildMemberMailCompose,
  openPlayerMailComposeModal,
  closePlayerMailComposeModal,
  openPlayerMailItemPicker,
  openPlayerMailItemModal,
  closePlayerMailItemModal,
  playerMailItemPrevPage,
  playerMailItemNextPage,
  selectPlayerMailItem,
  sendPlayerMail,
  initMailPage,
  initPlayerPage,
  openPlayerProfile,
  openPlayerSection,
  refreshAtticMailBadge,
  refreshMailInbox,
  refreshMailSent,
  openMailDetail,
  claimMail,
  deleteMail,
  onGuildBannerClick,
  onGuildEmblemClick,
  uploadGuildIcon,
  uploadGuildBanner,
  openGuildMembersModal,
  closeGuildMembersModal,
  refreshGuildMembersModal,
  toggleGuildMemberActionMenu,
  closeGuildMemberActionMenus,
  guildKickMember,
  guildSetMemberRank,
  toggleGuildHeroMenu,
  closeGuildHeroMenu,
  toggleGuildRaidParticipant,
  openGuildRaidChatModal,
  closeGuildRaidChatModal,
  selectGuildRaidChat,
  openGuildRaidParticipantModal,
  closeGuildRaidParticipantModal,
  startGuildRaidMuster,
  startGuildRaid,
  leaveGuildRaid,
  cancelGuildRaid,
  loadGuildWarTargetsForUi,
  declareGuildWar,
  respondGuildWar,
  apiFetch,
  getInitData,
  getClientEconomy,
  getClientChannel,
  mobileRelativePage,
  requireMobileSessionOrRedirect,
  isMobileClient,
  isDesktopClient,
  spendStatPoint,
  populateCaravanPage,
  travelToAct,
  openCaravanModal,
  closeCaravanModal,
  confirmTravelToAct,
  requestCaravanDriverTip,
  closeCaravanTipModal,
});
