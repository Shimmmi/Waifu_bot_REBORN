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
const API_BASE = "/api";
/** Синхронно с waifu_bot.game.constants (EXP_BASE, MAX_LEVEL). */
const PLAYER_EXP_BASE = 16;
const PLAYER_MAX_LEVEL = 60;
const GAME_STATIC_BASE = "/static/game";
const CARAVAN_STATIC_BASE = `${GAME_STATIC_BASE}/ui/caravan`;
const DUNGEONS_STATIC_BASE = `${GAME_STATIC_BASE}/dungeons`;
const SHOP_STATIC_BASE = `${GAME_STATIC_BASE}/ui/shop`;
const TAVERN_STATIC_BASE = `${GAME_STATIC_BASE}/ui/tavern`;
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

function authHeaders() {
  const initData = getInitData();
  const headers = {};
  if (initData) {
    headers["X-Telegram-Init-Data"] = initData;
  } else {
    const devPid = getDevPlayerIdFromQuery();
    if (devPid != null) headers["X-Player-Id"] = String(devPid);
  }
  return headers;
}

async function apiFetch(path, options = {}) {
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
    meleeRange: profileDamageRange(melee),
    rangedRange: profileDamageRange(ranged),
    magicRange: profileDamageRange(magic),
    critChance: profileFormatPercent(crit, 2),
    dodgeChance: profileFormatPercent(dodge, 2),
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

/** Update the active-dungeon chip in the shared ОЧ header. Short format: "Название - N%" or "Название (+N) - N%". */
function renderAtticDungeon(active) {
  const chip = document.getElementById("attic-dungeon-chip");
  const label = document.getElementById("attic-dungeon-label");
  const progressWrap = document.getElementById("attic-dungeon-progress");
  const progressFill = document.getElementById("attic-dungeon-progress-fill");
  if (!chip || !label) return;
  if (active?.active) {
    const hpPct = active.monster_max_hp > 0
      ? Math.round((active.monster_current_hp / active.monster_max_hp) * 100)
      : 0;
    const name = active.dungeon_name || "Бой";
    const pl = Math.max(0, parseInt(active.plus_level, 10) || 0);
    label.textContent = pl > 0 ? `${name} (+${pl}) - ${hpPct}%` : `${name} - ${hpPct}%`;
    chip.classList.remove("chip-ghost");
    chip.classList.add("chip-active");

    if (progressWrap && progressFill) {
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
      const pct = Math.max(0, Math.min(100, ((curStage - 1 + hpFrac) / totalStages) * 100));
      progressFill.style.width = `${pct}%`;
      progressWrap.setAttribute("aria-label", `Прогресс: ${curStage}/${totalStages}`);
      progressWrap.hidden = false;
    }
  } else {
    label.textContent = "Нет боя";
    chip.classList.add("chip-ghost");
    chip.classList.remove("chip-active");
    if (progressWrap) progressWrap.hidden = true;
    if (progressFill) progressFill.style.width = "0%";
  }
}

/** Update the expeditions chip in the shared ОЧ: 3 slot boxes — green (completed), yellow (in progress), transparent (free). */
function renderAtticExpeditions(slots, activeList) {
  const container = document.getElementById("attic-expedition-chip");
  if (!container) return;
  const list = Array.isArray(activeList) ? activeList : [];
  const slotsArr = Array.isArray(slots) ? slots.slice(0, 3) : [];
  const bySlotId = {};
  list.forEach((e) => {
    const sid = e?.expedition_slot_id ?? e?.slot_id;
    if (sid != null) bySlotId[Number(sid)] = e;
  });
  const slotStates = slotsArr.length
    ? slotsArr.map((s) => {
        const a = bySlotId[Number(s.id)];
        if (!a) return "free";
        return a.can_claim ? "completed" : "in_progress";
      })
    : ["free", "free", "free"];
  if (!container.querySelector(".attic-expedition-slots")) {
    container.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "attic-expedition-slots";
    wrap.setAttribute("aria-label", "Слоты экспедиций");
    for (let i = 0; i < 3; i++) {
      const box = document.createElement("div");
      box.className = "attic-exp-slot";
      box.dataset.slotIndex = String(i);
      wrap.appendChild(box);
    }
    container.appendChild(wrap);
  }
  const boxes = container.querySelectorAll(".attic-exp-slot");
  const hasAny = slotStates.some((s) => s !== "free");
  container.classList.toggle("chip-ghost", !hasAny);
  container.classList.toggle("chip-active", hasAny);
  slotStates.forEach((state, i) => {
    const box = boxes[i];
    if (!box) return;
    box.className = "attic-exp-slot attic-exp-slot--" + state;
    box.title = state === "completed" ? "Завершено" : state === "in_progress" ? "В процессе" : "Свободно";
  });
}

/** Fire-and-forget refresh of both dynamic ОЧ chips (dungeon + expeditions). */
const ACTIVE_DUNGEON_CACHE_MS = 5000;
const activeDungeonCache = {
  lite: { data: null, ts: 0, inFlight: null },
  full: { data: null, ts: 0, inFlight: null },
};

function invalidateActiveDungeonCache() {
  activeDungeonCache.lite = { data: null, ts: 0, inFlight: null };
  activeDungeonCache.full = { data: null, ts: 0, inFlight: null };
}

function isDungeonsPage() {
  return typeof window !== "undefined" && window.location.pathname.endsWith("/dungeons.html");
}

function isProfilePage() {
  return typeof window !== "undefined" && window.location.pathname.endsWith("/profile.html");
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

function refreshAtticChips(opts = {}) {
  const skipDungeon = opts.skipDungeon === true || isDungeonsPage();
  if (!skipDungeon) {
    fetchActiveDungeon({ includeLog: false }).then(renderAtticDungeon).catch(() => {});
  }
  Promise.all([
    apiFetch("/expeditions/slots").catch(() => ({ slots: [] })),
    apiFetch("/expeditions/active").catch(() => ({ active: [] })),
  ]).then(([slotsRes, activeRes]) => {
    renderAtticExpeditions(slotsRes?.slots ?? [], activeRes?.active ?? []);
  });
}

// ─────────────────────────────────────────────────────────────────────────────

function populateFromProfile(profile) {
  if (!profile) return;
  profileState.currentProfile = profile;

  // Shared ОЧ badges — populated on every page that has these IDs in its DOM
  if (profile.act != null) setText("badge-act", profile.act);
  if (profile.gold != null) setText("badge-gold", profile.gold);

  const w = profile.main_waifu;
  if (w) {
    if (w.level != null) setText("badge-level", w.level);

    // Legacy IDs kept for back-compat (silently skipped when not in DOM)
    if (w.name) setText("waifu-name", w.name);
    if (w.name) setText("profile-name", w.name);
    if (w.level != null) setText("profile-level", w.level);

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
      const fill = document.getElementById("profile-xp-fill");
      const atticFill = document.getElementById("attic-xp-fill");
      if (lvl >= PLAYER_MAX_LEVEL) {
        setText("profile-xp-text", `Ур. ${lvl} · макс.`);
        if (fill) fill.style.width = "100%";
        if (atticFill) atticFill.style.width = "100%";
      } else {
        const nextTotal = totalExpForLevel(lvl + 1);
        const curTotal = totalExpForLevel(lvl);
        const span = Math.max(1, nextTotal - curTotal);
        const into = Math.max(0, xp - curTotal);
        const pct = Math.round(clamp01(into / span) * 100);
        setText("profile-xp-text", `Ур. ${lvl} · ${xp} / ${nextTotal} EXP`);
        if (fill) fill.style.width = `${pct}%`;
        if (atticFill) atticFill.style.width = `${pct}%`;
      }
    }
  }

  // Async: update dynamic ОЧ chips on every page load/refresh
  refreshAtticChips();

  if (document.getElementById("shop-gamble-cost")) updateShopGambleCost();
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
  { id: 1, name: "Человек", icon: "🧑" },
  { id: 2, name: "Эльф", icon: "🧝" },
  { id: 3, name: "Зверолюд", icon: "🐾" },
  { id: 4, name: "Ангел", icon: "😇" },
  { id: 5, name: "Вампир", icon: "🦇" },
  { id: 6, name: "Демон", icon: "😈" },
  { id: 7, name: "Фея", icon: "🧚" },
];

const WAIFU_CLASSES = [
  { id: 1, name: "Рыцарь", icon: "🛡️" },
  { id: 2, name: "Воин", icon: "⚔️" },
  { id: 3, name: "Лучник", icon: "🏹" },
  { id: 4, name: "Маг", icon: "🔮" },
  { id: 5, name: "Ассасин", icon: "🗡️" },
  { id: 6, name: "Хилер", icon: "💚" },
  { id: 7, name: "Торговец", icon: "💰" },
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

/** Тексты пассивов расы — ТЗ «Пассивные навыки и расовые бонусы» (числа X,Y,N — из skill_config в БД). */
const WAIFU_GEN_RACE_PASSIVES = {
  1: [
    "«Адаптивность» — каждые 10 уровней (10, 20, 30…) +1 свободное очко характеристики на выбор",
    "+5% к получаемому EXP с монстров",
    "+5% к золоту с монстров",
  ],
  2: [
    "«Лесное чутьё» — вклад ЛОВ в шанс крита удваивается (в формуле крита ЛОВ даёт ×2 к своему слагаемому)",
    "+X% к шансу крит. атаки (базовый расовый бонус, X из БД)",
    "×2 к коэффициенту крита от ЛОВ",
    "−5% к максимальному HP",
  ],
  3: [
    "«Хищный инстинкт» — каждое N-е текстовое сообщение в подземелье: урон ×1,5; N = max(3, 10 − ⌊СИЛ/5⌋) (при СИЛ 10 → N=8, при 25 → 5, при СИЛ ≥ 35 → 3)",
    "+X к урону ближнего боя (плоский бонус, X из БД)",
    "+Y% к шансу уклонения (Y из БД)",
    "−5% к цене продажи предметов",
  ],
  4: [
    "«Благодать» — множитель формулы регенерации HP +50% (пассивная регенерация сильнее); бонус ИНТ к EXP дополнительно +X% (X из БД)",
    "+50% к скорости регенерации HP (множитель к формуле)",
    "+X% к получаемому EXP (дополнительно к бонусу ИНТ, X из БД)",
    "−Y% к урону крит. атак (Y из БД)",
  ],
  5: [
    "«Жизнекрада» — X% урона текстовых атак восстанавливает HP; X = (СИЛ + ЛОВ) × K_vampir (K из БД), исцеление после расчёта урона по монстру",
    "+Y% к шансу крит. атаки (Y из БД)",
    "−10% к навыку «Торговля»",
  ],
  6: [
    "«Инфернальный пакт» — вклад ИНТ к урону медиа-навыков удваивается: множитель (1 + ИНТ × K_инт × 2)",
    "+X% к урону активных навыков (медиа), базовый расовый бонус (X из БД)",
    "×2 к коэффициенту урона навыков от ИНТ",
    "−15% к навыку «Торговля»",
  ],
  7: [
    "«Торговая магия» — Торговля: T = ОБА × K_оба × 2 (двойной бонус от ОБА)",
    "×2 к коэффициенту «Торговля» от ОБА",
    "+X% к цене продажи предметов (X из БД)",
    "−10% к урону ближнего боя",
  ],
};

/** Тексты пассивов класса — то же ТЗ (коэффициенты K_* в skill_config). */
const WAIFU_GEN_CLASS_PASSIVES = {
  1: [
    "«Железная воля» — получаемый урон снижен на X%; X = ВЫН × K_zhv; при HP < 30% бонус удваивается",
    "−X% к получаемому урону (от ВЫН через K_zhv)",
    "+Y к максимальному HP (Y из БД)",
    "−Z% к урону дальнего боя (Z из БД)",
  ],
  2: [
    "«Берсерк» — при HP < 50% урон текстовых атак (ближний бой) +X%; X = СИЛ × K_brs; проверка перед каждой атакой",
    "+X% к урону ближнего боя при HP < 50% (от СИЛ через K_brs)",
    "+Y к урону крит. атак (плоский бонус, Y из БД)",
    "−Z% к урону магических навыков (Z из БД)",
  ],
  3: [
    "«Меткий глаз» — шанс крита от текстовых атак +X%; X = ЛОВ × K_met; каждый 5-й крит — ×2 к крит-урону (счётчик в сессии подземелья)",
    "+X% к шансу крит. атаки (от ЛОВ через K_met)",
    "+Y% к урону дальнего боя (Y из БД)",
    "−Z% к урону ближнего боя (Z из БД)",
  ],
  4: [
    "«Аркана» — урон медиа-навыков +X%; X = ИНТ × K_ark; бонус ИНТ к EXP дополнительно +Y%",
    "+X% к урону медиа-навыков (от ИНТ через K_ark)",
    "+Y% к получаемому EXP (дополнительно к стандартному бонусу ИНТ, Y из БД)",
    "−Z% к урону ближнего боя (Z из БД)",
  ],
  5: [
    "«Тень» — шанс уклонения +X%; X = ЛОВ × K_ten; после уклонения следующее текстовое сообщение-атака +30% урона (флаг сбрасывается после удара)",
    "+X% к шансу уклонения (от ЛОВ через K_ten)",
    "+30% к урону следующей атаки после успешного уклонения",
    "−Y к максимальному HP (штраф, Y из БД)",
  ],
  6: [
    "«Регенерация» — каждые N текстовых сообщений в подземелье +X HP; N = max(2, 8 − ⌊ВЫН/K_n⌋), X = ВЫН × K_reg; параллельно с пассивной регенерацией вне боя",
    "+X HP каждые N сообщений в подземелье (формулы из БД)",
    "+Y% к скорости пассивной регенерации HP (Y из БД)",
    "−Z% к урону ближнего боя (Z из БД)",
  ],
  7: [
    "«Чутьё» — золото с монстров +X%; X = (УДЧ + ОБА) × K_chut; стоимость найма в Таверне −Y%; Y = ОБА × K_hire",
    "+X% к золоту с монстров (от УДЧ + ОБА через K_chut)",
    "+Z% к навыку «Торговля» (Z из БД)",
    "−Y% к стоимости найма вайфу в Таверне (от ОБА через K_hire)",
    "−W% к урону в бою (W из БД)",
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

function waifuGenRefreshPassiveBonuses() {
  const root = document.getElementById("waifu-passive-modal-body");
  if (!root) return;
  const r = waifuGeneratorState.selectedRaceId;
  const c = waifuGeneratorState.selectedClassId;
  const raceLines = WAIFU_GEN_RACE_PASSIVES[r] || [];
  const classLines = WAIFU_GEN_CLASS_PASSIVES[c] || [];
  const ulRace = raceLines.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const ulClass = classLines.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  root.innerHTML =
    `<div class="waifu-gen-passive-sub">Раса</div><ul>${ulRace}</ul>` +
    `<div class="waifu-gen-passive-sub">Класс</div><ul>${ulClass}</ul>`;
}

function waifuGenBuildRaceClassPickers() {
  const raceRoot = document.getElementById("waifu-race-pick");
  const classRoot = document.getElementById("waifu-class-pick");
  if (raceRoot) {
    raceRoot.innerHTML = WAIFU_RACES.map(
      (r) =>
        `<button type="button" class="waifu-gen-pick-btn${r.id === waifuGeneratorState.selectedRaceId ? " waifu-gen-pick-btn--on" : ""}" data-kind="race" data-id="${r.id}" aria-pressed="${r.id === waifuGeneratorState.selectedRaceId}" aria-label="${escapeHtml(r.name)}">
        <span class="waifu-gen-pick-ico" aria-hidden="true">${escapeHtml(r.icon || "•")}</span>
      </button>`
    ).join("");
    raceRoot.querySelectorAll('[data-kind="race"]').forEach((btn) => {
      btn.addEventListener("click", () => {
        waifuGeneratorState.selectedRaceId = Number(btn.getAttribute("data-id"));
        waifuGenSyncHiddenSelects();
        waifuGenBuildRaceClassPickers();
        if (typeof window.__waifuGenRecalc === "function") window.__waifuGenRecalc();
      });
    });
  }
  if (classRoot) {
    classRoot.innerHTML = WAIFU_CLASSES.map(
      (c) =>
        `<button type="button" class="waifu-gen-pick-btn${c.id === waifuGeneratorState.selectedClassId ? " waifu-gen-pick-btn--on" : ""}" data-kind="class" data-id="${c.id}" aria-pressed="${c.id === waifuGeneratorState.selectedClassId}" aria-label="${escapeHtml(c.name)}">
        <span class="waifu-gen-pick-ico" aria-hidden="true">${escapeHtml(c.icon || "•")}</span>
      </button>`
    ).join("");
    classRoot.querySelectorAll('[data-kind="class"]').forEach((btn) => {
      btn.addEventListener("click", () => {
        waifuGeneratorState.selectedClassId = Number(btn.getAttribute("data-id"));
        waifuGenSyncHiddenSelects();
        waifuGenBuildRaceClassPickers();
        if (typeof window.__waifuGenRecalc === "function") window.__waifuGenRecalc();
      });
    });
  }
}

function waifuGenRenderChipGrid(containerId, pairs, currentVal, mode, onPick) {
  const root = document.getElementById(containerId);
  if (!root) return;
  const curSet =
    mode === "multi" || mode === "multi2" ? new Set(currentVal || []) : null;
  root.innerHTML = pairs
    .map(([v, l]) => {
      const on =
        mode === "multi" || mode === "multi2"
          ? curSet && curSet.has(v)
          : String(currentVal) === String(v);
      return `<button type="button" class="waifu-gen-chip${on ? " waifu-gen-chip--on" : ""}" data-val="${String(v).replace(/"/g, "&quot;")}">${escapeHtml(l)}</button>`;
    })
    .join("");
  root.querySelectorAll(".waifu-gen-chip").forEach((btn) => {
    btn.addEventListener("click", () => onPick(btn.getAttribute("data-val") || ""));
  });
}

function waifuGenRefreshHairModal() {
  const c = waifuGeneratorState.cosmetics;
  waifuGenRenderChipGrid("waifu-modal-hair-colors", WAIFU_GEN_COSMETIC.hair, c.hair_color, "single", (v) => {
    waifuGeneratorState.cosmetics.hair_color = v;
    waifuGenRefreshHairModal();
  });
  waifuGenRenderChipGrid("waifu-modal-hair-styles", WAIFU_GEN_COSMETIC.hairstyle, c.hairstyle, "single", (v) => {
    waifuGeneratorState.cosmetics.hairstyle = v;
    waifuGenRefreshHairModal();
  });
}

function waifuGenRefreshEyesModal() {
  const c = waifuGeneratorState.cosmetics;
  let colors = Array.isArray(c.eye_colors) ? c.eye_colors.filter(Boolean) : [];
  if (colors.length === 0) colors = ["amber"];
  waifuGenRenderChipGrid("waifu-modal-eye-colors", WAIFU_GEN_COSMETIC.eyes, colors, "multi2", (v) => {
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
  waifuGenRenderChipGrid("waifu-modal-eye-shapes", WAIFU_GEN_EYE_SHAPES, c.eye_shape, "single", (v) => {
    waifuGeneratorState.cosmetics.eye_shape = v;
    waifuGenRefreshEyesModal();
  });
}

function waifuGenRefreshOutfitModal() {
  const c = waifuGeneratorState.cosmetics;
  waifuGenRenderChipGrid("waifu-modal-outfits", WAIFU_GEN_OUTFITS, c.outfit, "single", (v) => {
    waifuGeneratorState.cosmetics.outfit = v;
    waifuGenRefreshOutfitModal();
  });
}

function waifuGenRefreshAccModal() {
  const c = waifuGeneratorState.cosmetics;
  let acc = Array.isArray(c.accessories) ? [...c.accessories] : [];
  waifuGenRenderChipGrid("waifu-modal-accs", WAIFU_GEN_ACCS_MULTI, acc, "multi", (v) => {
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
  if (id === "waifu-modal-hair") waifuGenRefreshHairModal();
  if (id === "waifu-modal-eyes") waifuGenRefreshEyesModal();
  if (id === "waifu-modal-outfit") waifuGenRefreshOutfitModal();
  if (id === "waifu-modal-acc") waifuGenRefreshAccModal();
  if (id === "waifu-modal-passive") waifuGenRefreshPassiveBonuses();
}

function waifuGenCloseModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.hidden = true;
  el.setAttribute("hidden", "");
}

function waifuGenBindCosmeticModalsOnce() {
  if (window.__waifuGenModalsBound) return;
  window.__waifuGenModalsBound = true;
  ["waifu-open-hair", "waifu-open-eyes", "waifu-open-outfit", "waifu-open-acc"].forEach((bid, i) => {
    const ids = ["waifu-modal-hair", "waifu-modal-eyes", "waifu-modal-outfit", "waifu-modal-acc"];
    const b = document.getElementById(bid);
    if (b) b.addEventListener("click", () => waifuGenOpenModal(ids[i]));
  });
  const openPassive = document.getElementById("waifu-open-passive");
  if (openPassive) openPassive.addEventListener("click", () => waifuGenOpenModal("waifu-modal-passive"));
  document.querySelectorAll("[data-waifu-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => waifuGenCloseModal(btn.getAttribute("data-waifu-close-modal") || ""));
  });
  ["waifu-modal-hair", "waifu-modal-eyes", "waifu-modal-outfit", "waifu-modal-acc", "waifu-modal-passive"].forEach((mid) => {
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
  /** Слот витрины (1–9), который ИИ выделил в реплике «купить» */
  merchantPickBuySlot: null,
  /** inventory_items.id предмета, который ИИ выделил в реплике «продать» */
  merchantPickSellId: null,
  /** Подсветка совета торговца — только после нажатия на торговца */
  merchantAdviceUnlocked: false,
  /** inventory_items.id выбранный для заточки */
  smithSelectedId: null,
  /** кэш списка для модалки выбора (сортировка: экип первыми) */
  smithItems: [],
  /** страница сетки выбора (по 9 предметов) */
  smithPickPage: 0,
};

const SMITH_PICK_PAGE_SIZE = 9;

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

async function loadProfile(options = {}) {
  const lite = options.lite ?? !isProfilePage();
  const initData = getInitData();
  const params = new URLSearchParams();
  if (initData) params.set("initData", initData);
  if (lite) params.set("lite", "1");
  const qs = params.toString();
  const profile = await apiFetch(`/profile${qs ? `?${qs}` : ""}`);
  populateFromProfile(profile);
  return profile;
}

/** One-time bind: ОЧ chip clicks open dungeons.html with the right tab. */
function initAtticChipClicks() {
  if (window.__atticChipClicksBound) return;
  window.__atticChipClicksBound = true;
  const dungeonChip = document.getElementById("attic-dungeon-chip");
  const expeditionChip = document.getElementById("attic-expedition-chip");
  if (dungeonChip) {
    dungeonChip.addEventListener("click", () => {
      window.location.href = "./dungeons.html?tab=solo";
    });
    dungeonChip.style.cursor = "pointer";
  }
  if (expeditionChip) {
    expeditionChip.addEventListener("click", () => {
      window.location.href = "./dungeons.html?tab=expedition";
    });
    expeditionChip.style.cursor = "pointer";
  }
}

async function bootstrapPage(page, afterLoad) {
  await initPage(page);
  let profile = null;
  try {
    profile = await loadProfile({ lite: page !== "profile" });
  } catch (err) {
    if (isWebAppUnauthorizedError(err)) {
      console.warn("Профиль недоступен: откройте WebApp из Telegram или используйте ?devPlayerId= при APP_ENV=dev.");
    } else {
      console.error("Failed to load profile:", err);
    }
  }

  if (typeof afterLoad === "function") {
    try {
      await afterLoad(profile || { act: 1 });
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
      window.WaifuApp?.Tutorial?.maybeRun(page, profile?.tutorial, forced);
    }
  } catch (err) {
    console.warn("Tutorial bootstrap failed:", err);
  }

  return profile;
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

async function shopPageBootstrap(profile, merchantMeta) {
  void merchantMeta;
  const p = profile || profileState.currentProfile || { act: 1 };
  const act = safeInt(p?.act ?? shopState.act, 1);
  shopState.act = act;
  shopState.activeTab = shopState.activeTab || "buy";

  applyShopHeroImages(act);

  const errBox = document.getElementById("shop-profile-error");
  if (errBox) {
    if (!p?.main_waifu) {
      errBox.textContent = "Сначала создайте вайфу.";
      errBox.style.display = "";
    } else {
      errBox.style.display = "none";
      errBox.textContent = "";
    }
  }

  await loadShop(act);
  return p;
}

async function loadShop(act) {
  applyShopHeroImages(act);
  const shopSmithNavIntent = consumeShopSmithIntent();
  const data = await apiFetch(`/shop/inventory?act=${act}`);
  shopState.act = act;
  shopState.size = safeInt(data?.size, 12);
  shopState.offers = Array.isArray(data?.items) ? data.items : [];

  if (typeof window !== "undefined") {
    const adminBtns = document.querySelectorAll(".admin-only");
    adminBtns.forEach((el) => {
      el.style.display = isAdminUser() ? "" : "none";
    });
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
      const iconHtml = offer ? itemArtHtml(offer) : "🎁";
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

    generateMerchantLine(shopState.activeTab || "buy").catch(() => {});
    const sellBtn = document.getElementById("shop-sell-submit");
    if (sellBtn) sellBtn.style.display = (shopState.activeTab || "buy") === "sell" ? "" : "none";
    if ((shopState.activeTab || "buy") === "smith") {
      loadSmithTab().catch(() => {});
    }
    if (shopSmithNavIntent.openSmith) {
      await applyShopSmithNavigationIntent(shopSmithNavIntent);
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
    const iconHtml = offer ? itemArtHtml(offer) : "🎁";
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
  return generateMerchantLine(shopState.activeTab || "buy");
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

/**
 * Подготовка реплики торговца под вкладку: buy / sell / gamble.
 * Выставляет window.__shopMerchantLine и window.__shopMerchantTab.
 */
async function generateMerchantLine(context) {
  const ctx = context || shopState.activeTab || "buy";
  window.__shopMerchantTab = ctx;
  shopState.merchantAdviceUnlocked = false;
  shopState.merchantPickBuySlot = null;
  shopState.merchantPickSellId = null;

  try {
    if (ctx === "buy") {
      const items = shopState.offers || [];
      const available = items.filter((o) => !o?.sold);
      if (!available.length) {
        window.__shopMerchantLine = "На сегодня товара нет, странник. Загляни позже.";
        return;
      }
      const chosen = available[Math.floor(Math.random() * available.length)];
      if (!chosen) return;

      const slot = resolveShopOfferSlot(chosen);
      if (slot != null) shopState.merchantPickBuySlot = slot;

      const fallback = `Странник, присмотрись к <b>${escapeHtml(String(chosen?.display_name || chosen?.name || "товару"))}</b> — отличная вещь для твоего пути.`;

      try {
        const payload = await apiFetch("/shop/merchant-line", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            context: "buy",
            name: chosen?.display_name || chosen?.name || "предмет",
            level: Number(chosen?.level || 1),
            rarity: rarityLabel(chosen?.rarity || 1),
            bonuses: typeof getItemBonusesText === "function" ? getItemBonusesText(chosen) : "",
          }),
        });
        const text = String(payload?.text || "").trim();
        window.__shopMerchantLine = text || fallback;
        if (!text && payload?.error && typeof console !== "undefined" && console.warn) {
          console.warn("[shop merchant-line]", payload.error);
        }
      } catch (e) {
        window.__shopMerchantLine = fallback;
        if (typeof console !== "undefined" && console.warn) console.warn("[shop merchant-line] запрос не удался:", e?.message || e);
      }
      return;
    }

    if (ctx === "sell") {
      const items = shopState.sellItems || [];
      if (!items.length) {
        window.__shopMerchantLine =
          "Развяжи ремни сумки — покажи, что продаёшь, странник. Золото у меня есть, а терпение — на вес.";
        return;
      }
      const chosen = items[Math.floor(Math.random() * items.length)];
      if (chosen?.id != null) shopState.merchantPickSellId = Number(chosen.id);

      const fallback = `Дай глянуть на <b>${escapeHtml(String(chosen?.display_name || chosen?.name || "эту штуку"))}</b>, странник — может, сойдёмся в цене.`;

      try {
        const payload = await apiFetch("/shop/merchant-line", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            context: "sell",
            name: chosen?.display_name || chosen?.name || "предмет",
            level: Number(chosen?.level || 1),
            rarity: rarityLabel(chosen?.rarity || 1),
            bonuses: typeof getItemBonusesText === "function" ? getItemBonusesText(chosen) : "",
          }),
        });
        const text = String(payload?.text || "").trim();
        window.__shopMerchantLine = text || fallback;
        if (!text && payload?.error && typeof console !== "undefined" && console.warn) {
          console.warn("[shop merchant-line]", payload.error);
        }
      } catch (e) {
        window.__shopMerchantLine = fallback;
        if (typeof console !== "undefined" && console.warn) console.warn("[shop merchant-line] запрос не удался:", e?.message || e);
      }
      return;
    }

    if (ctx === "gamble") {
      const fallback =
        "Испытай удачу, странник! Мистическая гемба голодна по золоту — зато сыплет редкостями не хуже драконьего логова.";
      try {
        const payload = await apiFetch("/shop/merchant-line", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            context: "gamble",
            name: "",
            level: 1,
            rarity: "",
            bonuses: "",
          }),
        });
        const text = String(payload?.text || "").trim();
        window.__shopMerchantLine = text || fallback;
        if (!text && payload?.error && typeof console !== "undefined" && console.warn) {
          console.warn("[shop merchant-line]", payload.error);
        }
      } catch (e) {
        window.__shopMerchantLine = fallback;
        if (typeof console !== "undefined" && console.warn) console.warn("[shop merchant-line] запрос не удался:", e?.message || e);
      }
      return;
    }

    if (ctx === "smith") {
      const fallback =
        "Кузнец затачивает сталь до звона. До +7 — без риска; выше удача решает судьбу клинка. Камень защиты убережёт от поломки.";
      window.__shopMerchantLine = fallback;
      try {
        const payload = await apiFetch("/shop/merchant-line", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            context: "smith",
            name: "заточка",
            level: 1,
            rarity: "",
            bonuses: "",
          }),
        });
        const text = String(payload?.text || "").trim();
        if (text) window.__shopMerchantLine = text;
      } catch {
        /* keep fallback */
      }
    }
  } finally {
    applyShopMerchantHighlight();
  }
}

const expeditionState = {
  slots: [],
  active: [],
  roster: [],
  refreshAt: null,
};
const expeditionUiCache = { activeById: {}, dailyById: {}, _activeRaw: null };
const expeditionSend = {
  squadSlots: [null, null, null],
  pickerSlot: -1,
  diffVal: 1,
  durVal: 30,
  slotId: null,
  pickerExcludedTags: null,
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
      loadSellInventory()
        .then(() => {
          syncShopSellToolbarUI();
          return generateMerchantLine("sell").catch(() => {});
        })
        .catch(console.error);
    } else if (name === "smith") {
      loadSmithTab().catch(console.error);
      generateMerchantLine("smith").catch(() => {});
    } else if (name === "gamble") {
      loadGambleTab(shopState.act || 1).catch(console.error);
      generateMerchantLine("gamble").catch(() => {});
    } else {
      generateMerchantLine(name).catch(() => {});
    }
  }
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
  const gEl = document.getElementById("shop-smith-gold-hint");
  if (stEl) stEl.textContent = String(pr.protection_stones ?? 0);
  if (gEl) gEl.textContent = String(pr.gold ?? "—");
}

function updateSmithSelectionUI() {
  const id = shopState.smithSelectedId;
  const items = shopState.smithItems || [];
  const it = id ? items.find((x) => x.id === id) : null;
  const wrap = document.getElementById("shop-smith-icon-wrap");
  const lbl = document.getElementById("shop-smith-selected-label");
  const btn = document.getElementById("shop-smith-enchant-btn");
  if (wrap) {
    wrap.innerHTML = it ? itemArtHtml(it) : "⚒";
  }
  if (lbl) {
    if (it) {
      lbl.innerHTML = composeItemDisplayName(it);
      lbl.classList.remove("muted");
    } else {
      lbl.textContent = "Выберите предмет";
      lbl.classList.add("muted");
    }
  }
  if (btn && !it) btn.disabled = true;
}

function syncSmithProtectionStoneCheckbox(targetLevel) {
  const stoneRow = document.getElementById("shop-smith-stone-row");
  const stoneCb = document.getElementById("shop-smith-use-stone");
  if (!stoneCb) return;
  const t = Number(targetLevel);
  if (!Number.isFinite(t) || t < 8) {
    stoneCb.checked = false;
    if (stoneRow) stoneRow.style.display = "none";
  } else if (stoneRow) {
    stoneRow.style.display = "";
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
      const lvLine = equipped
        ? `<div class="shop-smith-pick-lv muted tiny">t${safeNumber(it.tier, 1)} · ${lv}</div>`
        : "";
      return `<button type="button" class="shop-smith-pick-card ${cls}${sel}" data-id="${it.id}" onclick="WaifuApp.pickSmithItem(${it.id})">
        ${equipped ? '<span class="shop-smith-pick-equipped" title="Экипировано">⚔</span>' : ""}
        <div class="shop-smith-pick-card-top">
          <div class="shop-smith-pick-icon">${itemArtHtml(it)}</div>
          ${lvLine}
        </div>
        <div class="shop-smith-pick-name tiny">${composeItemDisplayName(it)}</div>
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
}

async function loadSmithTab() {
  const pr = await loadProfile().catch(() => null);
  updateSmithMetaFromProfile(pr);

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
}

async function refreshSmithPreview() {
  const box = document.getElementById("shop-smith-preview");
  if (!box) return;
  const id = shopState.smithSelectedId ? Number(shopState.smithSelectedId) : 0;
  if (!id) {
    box.innerHTML = `<div class="muted tiny">Выберите предмет из инвентаря.</div>`;
    const btn = document.getElementById("shop-smith-enchant-btn");
    if (btn) btn.disabled = true;
    const st = document.getElementById("shop-smith-stone-row");
    if (st) st.style.display = "none";
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

    const chanceLine =
      ch == null
        ? `<div class="muted tiny">✅ Гарантированный успех</div>`
        : `<div class="shop-smith-risk">⚠️ Шанс успеха: <strong>${Math.round(Number(ch) * 100)}%</strong></div>
           <div class="muted tiny">${escapeHtml(String(prev.on_fail_hint || ""))}</div>`;

    const stoneRow = document.getElementById("shop-smith-stone-row");
    if (stoneRow) stoneRow.style.display = tgt >= 8 ? "" : "none";
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
      statRows.push(
        `<div><span class="muted">Вторичка:</span> <strong>${escapeHtml(secStr(sec1))}</strong></div>`
      );
    }

    box.innerHTML = `
      <div><span class="muted">Уровень:</span> <strong>+${cur}</strong> → <strong>+${tgt}</strong></div>
      <div style="margin-top:6px;"><span class="muted">Стоимость:</span> <strong>🪙 ${escapeHtml(String(cost))}</strong></div>
      ${chanceLine}
      ${
        statRows.length
          ? `<div style="margin-top:8px;font-size:12px;">${statRows.join("")}</div>`
          : ""
      }`;
    const btn = document.getElementById("shop-smith-enchant-btn");
    if (btn) btn.disabled = cur >= 10;
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
  const btn = document.getElementById("shop-smith-enchant-btn");
  if (btn) btn.disabled = true;
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
    const pr = await loadProfile().catch(() => null);
    updateSmithMetaFromProfile(pr);
    const it = shopState.smithItems?.find((x) => x.id === id);
    if (it && nl != null) {
      it.enchant_level = nl;
      if (br) it.is_broken = true;
    }
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
    if (btn) btn.disabled = false;
    await refreshSmithPreview().catch(() => {});
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
  if (art) art.innerHTML = itemArtHtml(offer);

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
  try {
    await apiFetch(`/shop/buy?act=${act}&slot=${shopState.selectedSlot}`, { method: "POST" });
  } catch (e) {
    const body = document.getElementById("shop-offer-modal-body");
    if (body) body.innerHTML = `<div class="muted tiny" style="padding:8px 0;">Ошибка покупки: ${escapeHtml(String(e?.message || e))}</div>`;
    return;
  }
  await loadProfile().catch(console.error);
  await loadShop(act).catch(console.error);
  closeShopModal();
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
  await generateMerchantLine("sell").catch(() => {});
}

function openShopGambleResultModal(item, pricePaid, goldRemaining) {
  const m = document.getElementById("shop-gamble-result-modal");
  if (!m || !item) return;

  const nm = String(item.display_name || item.name || "Предмет").trim() || "Предмет";
  setText("shop-gamble-result-name", nm);
  setText("shop-gamble-result-rarity", item.rarity != null ? rarityLabel(item.rarity) : "—");
  setText("shop-gamble-result-level", item.level != null ? `lvl ${item.level}` : "—");

  const art = document.getElementById("shop-gamble-result-art");
  if (art) art.innerHTML = itemArtHtml(item);

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
  renderGambleGrid();
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
    const iconHtml =
      offer && (offer.art_key || offer.image_url || offer.image_key)
        ? itemArtHtml(offer)
        : offer
          ? itemArtEmoji(offer)
          : "❓";
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
}

function closeItemSellConfirmOverlay() {
  const ov = document.getElementById("item-modal-sell-overlay");
  if (!ov) return;
  ov.style.display = "none";
  ov.setAttribute("aria-hidden", "true");
}

function openItemSellConfirmOverlay() {
  const item = profileState.selectedItem;
  if (!item?.id || item.equipment_slot != null) return;
  const ov = document.getElementById("item-modal-sell-overlay");
  if (!ov) return;
  const nmEl = document.getElementById("item-modal-sell-item-name");
  if (nmEl) nmEl.innerHTML = composeItemTitlePlain(item) || escapeHtml(String(item?.name || "—"));
  const gEl = document.getElementById("item-modal-sell-gold");
  if (gEl) gEl.textContent = String(estimateProfileSellPrice(item));
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
  if (m) m.style.display = "none";
  closeItemSellConfirmOverlay();
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
    const lbl = String(a.description || "").trim() || m.short;
    const v = formatAffixCharacteristicValue(sk, a.value, a?.is_percent);
    lines.push(
      `<div><span aria-hidden="true">${m.icon}</span> <span class="muted">${escapeHtml(lbl)}</span> <strong><span class="${cls}">${escapeHtml(v)}</span></strong></div>`
    );
  });

  if (!lines.length) return "";
  return `<div class="affixes">${lines.join("")}</div>`;
}

/** Вторичный бонус + стат/аффиксы — компактный блок карты предмета */
function renderCombinedBonusesHtml(item) {
  const secondary = renderSecondaryBonusHtml(item);
  const bonuses = renderItemBonusesHtml(item);
  const parts = [secondary, bonuses].filter(Boolean);
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

/** Admin: wrap <img> for items under /static/game/items/ with pixel-art generate control. */
function wrapItemImageWithAdminGen(item, imgHtml) {
  if (!isAdminUser() || !item || !imgHtml || !String(imgHtml).includes("<img")) return imgHtml;
  const artKey = String(item.art_key || "").trim();
  if (!artKey) return imgHtml;
  const m = String(imgHtml).match(/src="([^"]*)"/);
  const src = m ? m[1] : "";
  const itemsPath = `${GAME_STATIC_BASE}/items/`;
  if (!src || !src.includes(itemsPath)) return imgHtml;
  const tier = itemArtTierNormalized(item);
  const wtype = String(item?.weapon_type || "").trim();
  const dname = itemArtDisplayLabel(item);
  const wAttr = wtype ? ` data-weapon-type="${escapeHtml(wtype)}"` : "";
  const dAttr = dname ? ` data-display-label="${escapeHtml(dname)}"` : "";
  const btn = `<span class="item-art-generate-btn" role="button" tabindex="0" data-art-key="${escapeHtml(artKey)}" data-art-tier="${tier}"${wAttr}${dAttr} title="Сгенерировать pixel art (admin)" aria-label="Сгенерировать иконку предмета">${ITEM_ART_GEN_SVG}</span>`;
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
    }
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

function itemArtHtml(item) {
  if (!item) return `${itemArtEmoji(item)}`;
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
    const img = `<img src="${webpUrl}" alt="" onerror="${onErr}" />`;
    return wrapItemImageWithAdminGen(item, img);
  }

  const url = itemImageUrl(item);
  if (url) return wrapItemImageWithAdminGen(item, `<img src="${url}" alt="" />`);
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

function composeItemDisplayName(item) {
  const en = safeNumber(item?.enchant_level, 0);
  const enHtml =
    en > 0 && !item?.is_broken ? ` <span class="enchant-badge">+${en}</span>` : "";
  const brk = item?.is_broken ? ` <span class="broken-badge">💔 Сломан</span>` : "";
  if (itemNameAlreadyIncludesAffixRollup(item)) {
    const full = String(item.display_name || item.name || "Предмет");
    return `${escapeHtml(full)}${enHtml}${brk}`.trim();
  }
  const base = String(item?.name || "Предмет");
  const aff = Array.isArray(item?.affixes) ? item.affixes : [];
  const prefix = aff.find((a) => String(a?.kind || "") === "affix")?.name;
  const suffix = aff.find((a) => String(a?.kind || "") === "suffix")?.name;
  const p = prefix ? `${prefix} ` : "";
  const s = suffix ? ` ${suffix}` : "";
  return `${p}${base}${s}${enHtml}${brk}`.trim();
}

/** Название для шапки модалки v2: префикс/база/суффикс без +заточки (она в блоке «Заточка»). */
function composeItemTitlePlain(item) {
  const brk = item?.is_broken ? " 💔" : "";
  if (itemNameAlreadyIncludesAffixRollup(item)) {
    const full = String(item.display_name || item.name || "Предмет");
    return `${escapeHtml(full)}${brk}`.trim();
  }
  const base = String(item?.name || "Предмет");
  const aff = Array.isArray(item?.affixes) ? item.affixes : [];
  const prefix = aff.find((a) => String(a?.kind || "") === "affix")?.name;
  const suffix = aff.find((a) => String(a?.kind || "") === "suffix")?.name;
  const p = prefix ? `${escapeHtml(String(prefix))} ` : "";
  const s = suffix ? ` ${escapeHtml(String(suffix))}` : "";
  return `${p}${escapeHtml(base)}${s}${brk}`.trim();
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

function itemModalV2StatRow(name, valHtml, valCls, secHtml) {
  const [emoji, icl] = itemModalV2NextIcon();
  const sec = secHtml ? `<div class="item-modal-v2-ssec">${secHtml}</div>` : "";
  const vc = valCls ? ` ${valCls}` : "";
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

function buildItemModalEnchantRowHtml(item) {
  const br = Boolean(item?.is_broken);
  const en = safeNumber(item?.enchant_level, 0);
  const mx = ITEM_MODAL_ENCHANT_PIP_MAX;
  const pips = Array.from({ length: mx }, (_, i) => {
    const f = i < en;
    const mxf = f && en >= mx;
    const cls = mxf ? " item-modal-v2-pip--mx" : f ? " item-modal-v2-pip--f" : "";
    return `<div class="item-modal-v2-pip${cls}" aria-hidden="true"></div>`;
  }).join("");
  if (br) {
    return `<span class="item-modal-v2-ench-val item-modal-v2-ench-val--muted" title="Сломан">—</span><div class="item-modal-v2-pips">${pips}</div>`;
  }
  const valCell =
    en > 0
      ? `<span class="item-modal-v2-ench-val">+${en}</span>`
      : `<span class="item-modal-v2-ench-val item-modal-v2-ench-val--empty" aria-hidden="true"></span>`;
  return `${valCell}<div class="item-modal-v2-pips">${pips}</div>`;
}

function renderItemModalV2CharacteristicsHtml(item) {
  if (!item) return "";
  itemModalV2NextIcon._i = 0;
  const rows = [];

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
    rows.push(
      itemModalV2StatRow("Броня", escapeHtml(String(armorEff)), "item-modal-v2-sv-te", null)
    );
  }
  if (isWeapon && Number.isFinite(dmgMinE) && Number.isFinite(dmgMaxE)) {
    rows.push(
      itemModalV2StatRow("Урон", escapeHtml(`${dmgMinE}–${dmgMaxE}`), "item-modal-v2-sv-re", null)
    );
  }
  if (isWeapon && speed != null) {
    rows.push(
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
    rows.push(itemModalV2StatRow(m.short, escapeHtml(v), cls, null));
  }

  const t = String(item?.secondary_bonus_type || "").trim();
  const v0 = Number(item?.secondary_bonus_value ?? 0);
  const vEff =
    item?.secondary_bonus_effective != null ? Number(item.secondary_bonus_effective) : v0;
  if (t && Number.isFinite(vEff) && vEff > 0) {
    const label = secondaryBonusTitleRu(t);
    const valDisp = formatSecondaryBonusValueDisplay(t, vEff);
    rows.push(
      itemModalV2StatRow(
        label,
        escapeHtml(valDisp),
        "item-modal-v2-sv-go",
        secondaryBonusModalSubtitle(t)
      )
    );
  }

  const aff = Array.isArray(item.affixes) ? item.affixes : [];
  aff.forEach((a) => {
    const sk = String(a.stat || "").trim();
    const skl = sk.toLowerCase();
    const m = statMeta(sk);
    const label = String(a.description || "").trim() || m.short;
    let v = formatAffixCharacteristicValue(sk, a.value, a?.is_percent);
    if (
      skl.startsWith("passive_node_level_add:") ||
      skl.startsWith("passive_branch_level_add:") ||
      skl === "passive_all_nodes_level_add"
    ) {
      v = `${v} ур.`;
    }
    rows.push(itemModalV2StatRow(label, escapeHtml(v), "item-modal-v2-sv-pu", null));
  });

  return rows.join("");
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
  if (low.startsWith("passive_node_level_add:")) return "К уровню узла на дереве пассивов";
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
    const m = statMeta(sk);
    const lbl = String(a.description || "").trim() || m.short;
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

function renderProfilePortrait(waifu) {
  setText("profile-portrait-name", waifu?.name || "—");
  const metaEl = document.getElementById("profile-mtg-meta");
  if (metaEl) {
    metaEl.textContent = `${raceName(waifu?.race)} · ${className(waifu?.class ?? waifu?.class_)}`;
  }

  const portraitUrl = String(
    waifu?.portrait_url || waifu?.image_url || waifu?.sprite_url || waifu?.avatar_url || ""
  ).trim();
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

function renderProfileHeroBars(waifu, details = null) {
  const d = details || profileState.currentDetails || null;
  const hpCur = safeNumber(d?.hp_current ?? waifu?.current_hp, 0);
  const hpMax = Math.max(1, safeNumber(d?.hp_max ?? waifu?.max_hp, 1));
  setText("profile-hp-text", `${hpCur}/${hpMax}`);
  const hpFill = document.getElementById("profile-hp-fill");
  if (hpFill) hpFill.style.width = `${Math.round(clamp01(hpCur / hpMax) * 100)}%`;

  const lvl = safeNumber(waifu?.level, 1);
  const xp = safeNumber(waifu?.experience, 0);
  const xpFill = document.getElementById("profile-xp-fill");
  if (lvl >= PLAYER_MAX_LEVEL) {
    setText("profile-xp-text", `Ур. ${lvl} · макс.`);
    if (xpFill) xpFill.style.width = "100%";
  } else {
    const curTotal = totalExpForLevel(lvl);
    const nextTotal = totalExpForLevel(lvl + 1);
    const xpPct = curTotal > 0 && nextTotal > curTotal
      ? Math.round(clamp01((xp - curTotal) / (nextTotal - curTotal)) * 100)
      : Math.round(clamp01(xp / nextTotal) * 100);
    setText("profile-xp-text", `Ур. ${lvl} · ${xp} / ${nextTotal} EXP`);
    if (xpFill) xpFill.style.width = `${Math.max(0, xpPct)}%`;
  }
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
    ["Уклонение", indicators.dodgeChance],
    ["Бонус EXP", indicators.expBonus],
    ["Бонус золота", indicators.goldBonus],
    ["Скидка найма", indicators.hireDiscount],
    ["Скидка трен.", indicators.trainingDiscount],
    ["Реген HP", indicators.hpRegen],
  ];

  const cells = rows
    .map(
      ([label, value]) =>
        `<div class="profile-detail-cell"><span class="profile-detail-label">${escapeHtml(label)}</span><strong class="profile-detail-value">${escapeHtml(
          String(value)
        )}</strong></div>`
    )
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

  return `
    <button type="button" class="profile-slot-card profile-slot-card--mini ${item ? rarity : "empty"}" title="${escapeHtml(titleText)}" aria-label="${escapeHtml(slotName)}" onclick="WaifuApp.openProfileSlot(${slot})">
      <div class="profile-slot-media">
        ${mediaHtml}
      </div>
      <div class="profile-slot-mini-level">Ур. ${lvl}</div>
    </button>
  `;
}

function renderProfilePaperDoll(waifu) {
  const paperdollUrl = String(waifu?.paperdoll_url || "").trim();
  const portraitUrl = String(
    waifu?.portrait_url || waifu?.image_url || waifu?.sprite_url || waifu?.avatar_url || ""
  ).trim();
  const hasPortrait = Boolean(portraitUrl);
  const admin = isAdminUser();
  const name = escapeHtml(String(waifu?.name || "Основная вайфу"));
  const meta = `${escapeHtml(className(waifu?.class ?? waifu?.class_))} · ${escapeHtml(raceName(waifu?.race))}`;

  let bodyInner = "";
  let bodyClass = "profile-paperdoll-body";
  if (paperdollUrl) {
    bodyClass += " profile-paperdoll-body--stage";
    bodyInner = `<img class="profile-paperdoll-img" src="${escapeHtml(paperdollUrl)}" alt="${name}" />`;
    if (admin) {
      bodyInner += `<button type="button" class="profile-paperdoll-regenerate" title="Перегенерировать образ (admin)" aria-label="Перегенерировать образ" onclick="WaifuApp.adminGenerateMainWaifuPaperdoll()">${ITEM_ART_GEN_SVG}</button>`;
    }
  } else {
    bodyInner = escapeHtml(waifuPortraitEmoji(waifu) || "👤");
    if (admin) {
      const dis = hasPortrait ? "" : " disabled";
      const title = hasPortrait
        ? "Сгенерировать образ с экипировкой (admin)"
        : "Нужен портрет основной вайфу";
      bodyInner += `<button type="button" class="btn profile-paperdoll-generate"${dis} title="${escapeHtml(title)}" onclick="WaifuApp.adminGenerateMainWaifuPaperdoll()">Сгенерировать образ</button>`;
    }
  }

  const ariaHidden = paperdollUrl || admin ? "" : ' aria-hidden="true"';
  return `
    <div class="profile-paperdoll">
      <div class="${bodyClass}"${ariaHidden}>${bodyInner}</div>
      <div class="profile-paperdoll-caption">
        <strong>${name}</strong>
        <span class="muted tiny">${meta}</span>
      </div>
    </div>
  `;
}

async function adminGenerateMainWaifuPaperdoll() {
  if (!isAdminUser()) return;
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
  setItemArtGenBusy(true);
  try {
    const payload = await apiFetch("/profile/main-waifu/paperdoll/regenerate", { method: "POST" });
    const url = String(payload?.paperdoll_url || "").trim();
    if (url && profileState.currentProfile?.main_waifu) {
      profileState.currentProfile.main_waifu.paperdoll_url = url;
    }
    renderProfileEquipment();
    showToast("Образ с экипировкой сохранён");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const msg =
      detail === "portrait_required_for_paperdoll"
        ? "Сначала нужен портрет вайфу"
        : detail === "paperdoll_generation_failed"
          ? "Не удалось сгенерировать образ"
          : detail || "Ошибка генерации";
    showToast(msg, "error");
  } finally {
    setItemArtGenBusy(false);
  }
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
      cells.push(`
        <button type="button" class="item-card profile-inv-item ${rarity} ${locked ? "empty" : ""}" title="${name}" onclick="WaifuApp.openItemById(${Number(
          item?.id || 0
        )})">
          <div class="item-icon">${iconHtml}</div>
          ${upgrade ? `<div class="upgrade-arrow" title="Улучшение относительно экипировки">▲</div>` : ""}
          <div class="item-level">Ур. ${item?.level ?? "?"}</div>
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

async function populateProfile(profile) {
  const p = profile || (await loadProfile());
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
  setText("profile-level", w.level ?? "—");

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
  renderStatsStrip("profile-stats-strip", w);
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

  await loadChatRewardsStatus().catch(() => null);

  try {
    const tab = new URLSearchParams(window.location.search).get("tab");
    if (tab) switchProfileTab(tab);
  } catch {
    // ignore
  }
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

async function openSlotModal(slot) {
  profileState.selectedSlot = slot;
  const modal = document.getElementById("slot-modal");
  const body = document.getElementById("slot-modal-body");
  if (!modal || !body) return;

  setText("slot-modal-title", `Замена: ${EQUIPMENT_SLOT_NAMES[slot] || `Слот ${slot}`}`);
  setText("slot-modal-subtitle", "Нажмите на предмет, чтобы экипировать его в этот слот.");
  body.innerHTML = `<div class="placeholder">Загрузка...</div>`;
  modal.style.display = "grid";

  const data = await apiFetch(`/waifu/equipment/available?slot=${slot}`);
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    body.innerHTML = `<div class="placeholder">Нет подходящих предметов для этого слота.</div>`;
    return;
  }

  const equipped = getProfileEquippedItem(slot);

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

async function equipItemToProfileSlot(itemId, slot) {
  await apiFetch(`/waifu/equipment/equip?inventory_item_id=${itemId}&slot=${slot}`, { method: "POST" });
  closeSlotModal();
  closeItemModal();
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

/** Требования v2: пилюли «Ур.» / «ВЫН» и т.д.; без текущих статов ОВ; fail — красная рамка. */
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
    const ok = !hasWaifu || have >= lvlNeed;
    pushPill("Ур.", String(lvlNeed), ok);
  }

  const statBits = [
    ["strength", "СИЛ", "strength"],
    ["agility", "ЛОВ", "agility"],
    ["intelligence", "ИНТ", "intelligence"],
    ["endurance", "ВЫН", "endurance"],
  ];
  statBits.forEach(([rk, abbrev, wk]) => {
    const need = safeNumber(req[rk], 0);
    if (need <= 0) return;
    const have = safeNumber(w[wk], 0);
    const ok = !hasWaifu || have >= need;
    pushPill(abbrev, String(need), ok);
  });

  if (req.waifu_race != null && req.waifu_race !== "") {
    const need = Number(req.waifu_race);
    const have = w.race != null ? Number(w.race) : NaN;
    const ok = !hasWaifu || (Number.isFinite(have) && have === need);
    pushPill("Раса", raceName(need), ok);
  }
  if (req.waifu_class != null && req.waifu_class !== "") {
    const need = Number(req.waifu_class);
    const wc = w.class != null ? w.class : w.class_;
    const have = wc != null ? Number(wc) : NaN;
    const ok = !hasWaifu || (Number.isFinite(have) && have === need);
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
  if (art) art.innerHTML = itemArtHtml(item);

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
  const enchBtn = document.getElementById("item-modal-enchant");
  const unequipBtn = document.getElementById("item-modal-unequip");
  const replaceBtn = document.getElementById("item-modal-replace");
  const equipBtn = document.getElementById("item-modal-equip");
  const actionsRow = document.getElementById("item-modal-actions-row");

  if (sellBtn) sellBtn.style.display = isEquipped ? "none" : "";
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
  if (enchBtn && enchBtn.style.display !== "none") visibleFooter += 1;
  if (unequipBtn && unequipBtn.style.display !== "none") visibleFooter += 1;
  if (replaceBtn && replaceBtn.style.display !== "none") visibleFooter += 1;
  if (equipBtn && equipBtn.style.display !== "none") visibleFooter += 1;
  if (actionsRow) {
    actionsRow.setAttribute("data-cols", visibleFooter <= 2 ? "2" : "3");
  }

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
  await bootstrapPage("profile", populateProfile);
}

async function confirmSellSelectedItem() {
  const item = profileState.selectedItem;
  if (!item?.id) return;
  closeItemSellConfirmOverlay();
  await apiFetch(`/inventory/sell`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inventory_item_ids: [item.id] }),
  });
  closeItemModal();
  await refreshAfterInventoryModalAction();
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

  const stub = profile && typeof profile.player_id === "undefined";
  if (stub && authEl) {
    authEl.style.display = "block";
    authEl.innerHTML = getWebAppAuthNoticeHtml();
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
  const summary = document.getElementById("waifu-summary");
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
  waifuGenBindCosmeticModalsOnce();

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

    nextBtn.disabled = !name;
    waifuGenRefreshPassiveBonuses();
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
  if (waifuGenGensUsed() >= 3) {
    if (errP) errP.textContent = "Достигнут лимит трёх генераций.";
    return;
  }

  if (errP) errP.textContent = "";
  if (genBtn) genBtn.disabled = true;

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
    waifuGenRefreshGenerateButton();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const lim = (detail || "").includes("portrait_preview_limit");
    if (errP) {
      errP.textContent = lim
        ? "Лимит трёх генераций. Обновите страницу или создайте персонажа с уже выбранным портретом."
        : detail || String(e?.message || e);
    }
    if (lim) waifuGenSetGensUsed(3);
    waifuGenRefreshGenerateButton();
    waifuGenRefreshHint();
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
  warTargets: null,
  heroMenuListener: false,
};

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
    max_level: "Навык уже максимального уровня.",
    no_skill_points: "Недостаточно очков прокачки (ОПГ).",
    raid_already_active: "Рейд уже идёт.",
    need_participants: "Нужно минимум 2 участника.",
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
    not_same_guild: "Писать можно только участникам своей гильдии.",
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
      <button type="button" class="guild-stat-card guild-stat-card--btn" onclick="WaifuApp.openGuildMembersModal()">
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

function openGuildMembersModal() {
  const d = guildHallState.me;
  if (!d?.in_guild) return;
  const body = document.getElementById("guild-members-modal-body");
  const modal = document.getElementById("guild-members-modal");
  if (body) body.innerHTML = renderGuildMembersHtml(d.members);
  if (modal) {
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
  }
}

function closeGuildMembersModal() {
  const modal = document.getElementById("guild-members-modal");
  if (modal) {
    modal.style.display = "none";
    modal.setAttribute("aria-hidden", "true");
  }
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

function renderGuildMembersHtml(members) {
  if (!Array.isArray(members) || !members.length) {
    return `<p class="muted tiny">Нет участников.</p>`;
  }
  const online = members.filter((m) => m.online);
  const offline = members.filter((m) => !m.online);
  const row = (m) => {
    const badges = [
      m.is_leader ? `<span class="guild-member-badge">Глава</span>` : "",
      m.is_officer && !m.is_leader ? `<span class="guild-member-badge">Офицер</span>` : "",
    ]
      .filter(Boolean)
      .join("");
    const dotCls = m.online ? "guild-member-dot--online" : "guild-member-dot--offline";
    const pwr =
      m.member_power != null && m.member_power !== ""
        ? formatGuildPower(m.member_power)
        : "—";
    return `<div class="guild-member-row">
      <span class="guild-member-dot ${dotCls}" aria-hidden="true"></span>
      <button type="button" class="guild-member-preview-btn" onclick="WaifuApp.openGuildMemberPreviewModal(${Number(m.player_id)})">${guildMemberLabel(m)}</button>
      <span class="guild-member-power">${escapeHtml(String(pwr))}</span>
      ${badges}
    </div>`;
  };
  let html = "";
  if (online.length) {
    html += `<h4 class="guild-activity-section-title">Онлайн</h4><div class="guild-members-list">${online.map(row).join("")}</div>`;
  }
  if (offline.length) {
    html += `<h4 class="guild-activity-section-title">Оффлайн</h4><div class="guild-members-list">${offline.map(row).join("")}</div>`;
  }
  return html;
}

function getGuildRaidChatId(d) {
  const fromGuild = d?.raid?.telegram_chat_id ?? d?.telegram_chat_id;
  if (fromGuild != null && Number(fromGuild) > 0) return Number(fromGuild);
  const chat = tg?.initDataUnsafe?.chat;
  if (chat?.id) return Number(chat.id);
  return null;
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
    await populateGuildHall();
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
    await populateGuildHall();
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
    await populateGuildHall();
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
    await populateGuildHall();
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
  const cost =
    cur === 0 ? safeInt(sk.cost_sp, 1) : cur < 3 ? safeInt(sk.cost_per_upgrade, 1) : 0;
  const avail = safeInt(d?.skill_points_available, 0);
  const tierUnlock = safeInt(d?.skill_tier_unlock, 1);
  const canUp =
    d?.is_leader &&
    cur < 3 &&
    safeInt(d?.guild_level, 1) >= safeInt(sk.guild_level_req, 1) &&
    safeInt(sk.tier, 1) <= tierUnlock &&
    avail >= cost;
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
      : `<span class="muted tiny">${d?.is_leader ? "Нельзя улучшить (нет ОПГ или макс.)" : "Только глава может улучшать"}</span>`;
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
    await populateGuildHall();
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
    await populateGuildHall();
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

  if (levelEl) levelEl.textContent = mw?.level != null ? String(mw.level) : "—";
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

async function openPlayerMailItemPicker() {
  const listEl = document.getElementById("player-mail-compose-item-list");
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
          const sel = guildHallState.mailCompose.inventoryItemId === iid ? " selected" : "";
          return `<div class="player-mail-compose-item-row${sel}" data-id="${iid}" onclick="WaifuApp.selectPlayerMailItem(${iid})">
            <span>${itemArtHtml(it)}</span>
            <span>${escapeHtml(composeItemDisplayName(it))}</span>
          </div>`;
        })
        .join("");
    }
    listEl.style.display = "";
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить инвентарь", "error");
  }
}

function selectPlayerMailItem(id) {
  const iid = Number(id);
  guildHallState.mailCompose.inventoryItemId = iid;
  const row = document.querySelector(`.player-mail-compose-item-row[data-id="${iid}"]`);
  const label = row?.querySelector("span:last-child")?.textContent?.trim() || `Предмет #${iid}`;
  guildHallState.mailCompose.itemLabel = label;
  const pickEl = document.getElementById("player-mail-compose-item-pick");
  if (pickEl) pickEl.textContent = label;
  document.querySelectorAll(".player-mail-compose-item-row").forEach((el) => {
    el.classList.toggle("selected", Number(el.dataset.id) === iid);
  });
  const listEl = document.getElementById("player-mail-compose-item-list");
  if (listEl) listEl.style.display = "none";
}

async function sendPlayerMail() {
  const rid = Number(guildHallState.mailCompose.recipientId);
  if (!Number.isFinite(rid) || rid <= 0) return;
  const bodyText = (document.getElementById("player-mail-compose-body")?.value || "").trim();
  const goldAmount = Math.max(0, safeInt(document.getElementById("player-mail-compose-gold")?.value, 0));
  const inventoryItemId = guildHallState.mailCompose.inventoryItemId;
  const payload = { recipient_player_id: rid, body_text: bodyText || null, gold_amount: goldAmount };
  if (inventoryItemId) payload.inventory_item_id = Number(inventoryItemId);
  try {
    await apiFetch("/mail/send", { method: "POST", body: JSON.stringify(payload) });
    showToast("Письмо отправлено");
    closePlayerMailComposeModal();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(mailApiErrorToUser(detail, "Не удалось отправить"), "error");
  }
}

async function initMailPage() {
  await refreshMailInbox();
}

async function refreshMailInbox() {
  try {
    const [inbox, unread] = await Promise.all([
      apiFetch("/mail/inbox?limit=50"),
      apiFetch("/mail/unread-count"),
    ]);
    guildHallState.mailState.inbox = Array.isArray(inbox?.items) ? inbox.items : [];
    guildHallState.mailState.unreadCount = safeInt(unread?.count, 0);
    renderMailInbox();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    const root = document.getElementById("mail-inbox-root");
    if (root) root.innerHTML = `<p class="muted" style="color:#f87171">${escapeHtml(detail || "Не удалось загрузить почту")}</p>`;
  }
}

function renderMailInbox() {
  const root = document.getElementById("mail-inbox-root");
  const unreadEl = document.getElementById("mail-unread-count");
  const rewardsEl = document.getElementById("mail-rewards-count");
  if (unreadEl) unreadEl.textContent = String(guildHallState.mailState.unreadCount);
  if (rewardsEl) {
    const pending = guildHallState.mailState.inbox.filter(
      (m) => (m.gold_amount > 0 || m.inventory_item_id) && m.status !== "claimed"
    ).length;
    rewardsEl.textContent = String(pending);
  }
  if (!root) return;
  const items = guildHallState.mailState.inbox;
  if (!items.length) {
    root.innerHTML = `<p class="muted">Входящих писем нет.</p>`;
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
    panel.style.display = "";
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
      panel.style.display = "none";
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
    await populateGuildHall();
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
    await populateGuildHall();
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
    await populateGuildHall();
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
    await populateGuildHall();
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
    await populateGuildHall();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(guildApiErrorToUser(detail, detail), "error");
  }
}

function toggleGuildRaidParticipant(playerId, checked) {
  const pid = Number(playerId);
  const set = new Set(guildHallState.raidParticipantIds.map(Number));
  if (checked) set.add(pid);
  else set.delete(pid);
  guildHallState.raidParticipantIds = [...set];
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
    await populateGuildHall();
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
    showToast("Вы вышли из рейда");
    await populateGuildHall();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail, "error");
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
    await populateGuildHall();
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
    await populateGuildHall();
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
  const avail = safeInt(d?.skill_points_available, 0);
  const cost = cur === 0 ? safeInt(sk.cost_sp, 1) : safeInt(sk.cost_per_upgrade, 1);
  const canUp = d?.is_leader && !locked && !maxed && avail >= cost;
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
    action = `<button type="button" class="guild-skill-card-upgrade" disabled onclick="event.stopPropagation()"><span class="guild-skill-card-upgrade-plus">+</span><span class="guild-skill-card-upgrade-cost">${cost} ОПГ</span></button>`;
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
  const resetBtn = d?.is_leader
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
  const templates = Array.isArray(raid?.templates) ? raid.templates : [];
  const members = Array.isArray(d?.members) ? d.members : [];
  const canManage = d?.is_leader || d?.is_officer;
  let html = "";
  if (active) {
    const hpPct =
      active.hp_max > 0 ? Math.round((safeInt(active.hp, 0) / safeInt(active.hp_max, 1)) * 100) : 0;
    html += `<h4 class="guild-activity-section-title">Активный рейд</h4>
      <p>Этап ${active.stage ?? "—"} · HP ${active.hp ?? 0}/${active.hp_max ?? 0} (${hpPct}%)</p>
      <ul>${(active.participants || [])
        .map((p) => `<li>Игрок ${p.player_id}: ${p.messages ?? 0} сообщ., урон ${p.damage ?? 0}</li>`)
        .join("")}</ul>
      <button type="button" class="btn secondary" onclick="WaifuApp.leaveGuildRaid()">Покинуть рейд</button>`;
  } else if (canManage && templates.length) {
    const viewerId = safeInt(d?.viewer_player_id, 0);
    if (!guildHallState.raidParticipantIds.length && viewerId) {
      guildHallState.raidParticipantIds = [viewerId];
    }
    html += `<h4 class="guild-activity-section-title">Начать рейд</h4>
      <p class="muted tiny">Выберите участников (мин. 2) и шаблон.</p>
      <div class="guild-raid-party-row">${members
        .map((m) => {
          const pid = Number(m.player_id);
          const checked = guildHallState.raidParticipantIds.includes(pid);
          return `<label><input type="checkbox" ${checked ? "checked" : ""} onchange="WaifuApp.toggleGuildRaidParticipant(${pid}, this.checked)" /> ${guildMemberLabel(m)}</label>`;
        })
        .join("")}</div>`;
    html += templates
      .map(
        (t) => `<div class="list-item" style="margin-top:8px">
          <strong>${escapeHtml(t.name || "")}</strong> — тир ${t.tier}, GXP ${t.gxp}, мин. ур. гильдии ${t.min_level}
          <button type="button" class="btn primary" style="margin-top:6px" onclick="WaifuApp.startGuildRaid(${Number(t.id)})">Начать</button>
        </div>`
      )
      .join("");
  } else {
    html += `<p class="muted tiny">${canManage ? "Нет доступных шаблонов рейда." : "Рейды запускает глава или офицер."}</p>`;
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

function renderGuildQuestsPane() {
  return `<p class="muted tiny">Гильдейские квесты в разработке (см. ТЗ).</p>`;
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
    root.innerHTML = `<div class="guild-section-label">История</div>${renderGuildHistoryPane(d)}`;
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

async function populateGuildHall(profile) {
  const p = profile || profileState.currentProfile || {};
  guildHallState.profileGold = safeInt(p?.gold, 0);
  const root = document.getElementById("guild-tab-content");
  if (!root) return;
  const firstLoad = !guildHallState.me;
  if (firstLoad) setGuildPageLoading(true);
  try {
    const data = await apiFetch("/guilds/me");
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
      document.getElementById("guild-skill-modal-close")?.addEventListener("click", closeGuildSkillModal);
      document.getElementById("guild-member-preview-mail")?.addEventListener("click", openGuildMemberMailCompose);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
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
  if (tg) {
    tg.ready();
    tg.expand();
  }
  setActiveNav(page);
  if (page !== "index") {
    connectSSE();
  }
  initAtticChipClicks();
  initItemArtGenerateDelegated();

  if ("serviceWorker" in navigator && !window.__waifuSwRegistered) {
    window.__waifuSwRegistered = true;
    navigator.serviceWorker.register("/webapp/sw.js").catch(() => {});
  }

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
        const p = await loadProfile({ lite: !isProfilePage() });
        const w = p?.main_waifu;
        if (!w) return;
        // If we're on profile screen, refresh visible stat widgets without refetching inventory/equipment.
        if (window.location.pathname.endsWith("/profile.html")) {
          profileState.currentProfile = { ...(profileState.currentProfile || {}), ...p };
          profileState.currentDetails = p?.main_waifu_details || profileState.currentDetails || null;
          renderProfilePortrait(w);
          renderProfileHeroBars(w, profileState.currentDetails);
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
    const payload = await apiFetch(
      `/admin/monster-art/generate?template_id=${encodeURIComponent(templateId)}`,
      { method: "POST" }
    );
    const visual = document.getElementById("monster-visual");
    const family = payload?.family || visual?.dataset?.family || "unknown";
    const slug = payload?.slug || visual?.dataset?.slug || "unknown";
    const tier = Number(visual?.dataset?.tier) || 1;
    let override = String(payload?.image_url || "").trim();
    if (override) {
      override = override + (override.includes("?") ? "&" : "?") + "v=" + Date.now();
    }
    loadMonsterImage(family, slug, tier, override || null);
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

/** Иконка точки на карте каравана (см. static/game/ui/caravan/README.md). */
function caravanPinImageUrls(act) {
  const a = Math.max(1, Math.min(5, safeInt(act, 1)));
  return [`${CARAVAN_STATIC_BASE}/act-${a}/map-pin.webp`, `${CARAVAN_STATIC_BASE}/pin_act${a}.webp`];
}

/** Подбор картинки по цепочке URL (onerror → следующий). */
function attachCaravanImage(el, urls, onGiveUp) {
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
    el.onerror = () => next();
    el.onload = () => {
      el.style.display = "";
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
  for (const [tab, kind] of Object.entries(SHOP_HERO_KIND)) {
    const img = document.getElementById(`shop-hero-img-${tab}`);
    const fb = document.getElementById(`shop-hero-fb-${tab}`);
    const heroUrls = [
      `${SHOP_STATIC_BASE}/act-${a}/${kind}.webp`,
      `${SHOP_STATIC_BASE}/${kind}_act${a}.webp`,
      `${SHOP_STATIC_BASE}/${kind}.webp`,
    ];
    if (img) {
      img.style.display = "";
      if (fb) fb.style.display = "none";
      attachCaravanImage(img, heroUrls, () => {
        img.style.display = "none";
        if (fb) fb.style.display = "";
      });
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

  pinsLayer.innerHTML = ACT_META.map(({ act, short, emoji, levelRange }) => {
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
  }).join("");

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

let passiveTreeCache = null;
let passiveActiveBranch = "warrior";
/** Вкладка зала: ветка дерева или «hidden» — скрытые навыки. */
let trainingHallTab = "warrior";
let passiveTreeListenersBound = false;
let hiddenSkillsCache = [];
let hiddenSkillsListenersBound = false;
const PASSIVE_SKILL_PLACEHOLDER = `${GAME_STATIC_BASE}/passive-skill-placeholder.svg`;

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
      let msg = (out && out.error) || "Ошибка";
      if (out && out.error === "insufficient_gold") msg = `Нужно ${out.required} 🪙`;
      showToast(msg, "error");
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
  const learnBlock =
    node.can_learn
      ? `<div class="passive-modal-learn-wrap"><button type="button" class="btn passive-modal-learn-btn" data-passive-modal-learn="${passiveEscHtml(
          node.id,
        )}">Прокачать · 🪙&nbsp;${passiveEscHtml(String(node.cost_gold || 0))}</button></div>`
      : "";
  const ico = getPassiveNodeIcon(node);
  const levelRow = `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Уровень (очки)</span><span class="passive-modal-stat-v">${cur} / ${max}</span></div>`;
  const equipHint =
    eq > 0
      ? `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">От предметов</span><span class="passive-modal-stat-v passive-modal-stat-v--equip">+${eq} к уровню</span></div>`
      : "";
  let curBonusRaw =
    effLv >= 1 && node.effective_effect_value != null && node.effective_effect_value !== undefined
      ? formatPassiveEffectValue(node.effect_type, node.effective_effect_value)
      : null;
  if (
    curBonusRaw == null &&
    cur >= 1 &&
    node.current_effect_value != null &&
    node.current_effect_value !== undefined
  ) {
    curBonusRaw = formatPassiveEffectValue(node.effect_type, node.current_effect_value);
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
      ? formatPassiveEffectValue(node.effect_type, nextVal)
      : "—";
  const curBonusRow = `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Текущий бонус</span><span class="passive-modal-stat-v">${passiveEscHtml(
    curBonusRaw,
  )}</span></div>`;
  const nextBonusRow = `<div class="passive-modal-stat-row"><span class="passive-modal-stat-k">Бонус на сл. уровне</span><span class="passive-modal-stat-v">${passiveEscHtml(
    nextBonusRaw,
  )}</span></div>`;
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
      </div>
      ${learnBlock}
    </div>
  `;
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
}

function closePassiveSkillModal() {
  const m = document.getElementById("passive-skill-modal");
  if (m) {
    m.style.display = "none";
    m.classList.remove("passive-skill-modal--equip-bonus");
    m.classList.remove("passive-skill-modal--dota");
    const panel = m.querySelector(".passive-skill-modal-panel");
    if (panel) panel.classList.remove("passive-skill-modal-panel--dota");
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
  const capped = new Set(["instakill_chance", "revive_chance", "survive_chance", "full_evade_chance"]);
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

function passiveNodeStateClass(node) {
  const cur = Number(node.current_level) || 0;
  const max = Number(node.max_level) || 1;
  if (node.is_locked && cur === 0) return "passive-skill-cell--locked";
  if (cur >= max) return "passive-skill-cell--maxed";
  if (cur > 0) return "passive-skill-cell--partial";
  return "passive-skill-cell--available";
}

function passiveBranchPointsInCache(branch) {
  if (!passiveTreeCache || !passiveTreeCache.branches) return 0;
  const arr = passiveTreeCache.branches[branch];
  if (!Array.isArray(arr)) return 0;
  return arr.reduce((s, n) => s + (Number(n.current_level) || 0), 0);
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

/** Одна ячейка дерева: картинка-заглушка, эффективный уровень одной цифрой, оверлей +/стоимость. */
function renderPassiveNodeCard(node) {
  const esc = passiveEscHtml;
  const cur = Number(node.current_level) || 0;
  const max = Number(node.max_level) || 1;
  const eq = Number(node.equipment_level_bonus) || 0;
  const effLvRaw = Number(node.effective_level);
  const displayEffLv =
    (Number.isFinite(effLvRaw) && effLvRaw > 0 ? effLvRaw : 0) || cur + eq;
  const hasEquipLift = eq > 0 || displayEffLv > cur;
  const st = `${passiveNodeStateClass(node)}${hasEquipLift ? " passive-skill-cell--equip-bonus" : ""}`;
  const ico = getPassiveNodeIcon(node);
  const reqHint =
    node.is_locked && cur === 0
      ? `ур.${node.waifu_level_req}, в ветке ≥${node.branch_points_req} оч.`
      : "";
  const titleAttr = (reqHint ? `${node.name} — ${reqHint}` : node.name)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;");
  const upgradeOverlay = node.can_learn
    ? `<button type="button" class="passive-cell-upgrade" data-passive-learn="${esc(
        node.id,
      )}" aria-label="Прокачать за ${esc(String(node.cost_gold || 0))} золота">
        <span class="passive-cell-upgrade-plus" aria-hidden="true">+</span>
        <span class="passive-cell-upgrade-cost">🪙&nbsp;${esc(String(node.cost_gold || 0))}</span>
      </button>`
    : "";
  return `<div class="passive-skill-cell ${st}" data-node-id="${esc(node.id)}" role="button" tabindex="0" title="${titleAttr}">
    <div class="passive-skill-cell-inner">
      <div class="passive-skill-cell-art">
        <img class="passive-skill-cell-img" src="${PASSIVE_SKILL_PLACEHOLDER}" alt="" decoding="async" />
        <span class="passive-skill-cell-emoji" aria-hidden="true">${ico}</span>
        ${node.is_locked && cur === 0 ? `<span class="passive-skill-cell-lock" aria-hidden="true">🔒</span>` : ""}
        ${upgradeOverlay}
      </div>
      <div class="passive-skill-cell-title">${esc(node.name)}</div>
      <div class="passive-skill-cell-levels" aria-label="Эффективный уровень ${displayEffLv}, очки ${cur} из ${max}${
        hasEquipLift ? ", есть бонус от предметов" : ""
      }">
        <span class="passive-skill-cell-lv-single${
          displayEffLv === 0 ? " passive-skill-cell-lv-single--zero" : ""
        }${hasEquipLift && displayEffLv > 0 ? " passive-skill-cell-lv-single--equip" : ""}">${esc(
          String(displayEffLv),
        )}</span>
      </div>
    </div>
  </div>`;
}

function renderPassiveEmptyCell() {
  return `<div class="passive-skill-cell passive-skill-cell--empty" aria-hidden="true">
    <div class="passive-skill-cell-inner">
      <div class="passive-skill-cell-art passive-skill-cell-art--empty"></div>
      <div class="passive-skill-cell-levels passive-skill-cell-levels--empty" aria-hidden="true"></div>
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
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-stop-modal]") || ev.target.closest("[data-passive-learn]")) return;
      const id = el.getAttribute("data-node-id");
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
  document.querySelectorAll(".passive-tab[data-training-tab]").forEach((t) => {
    const tab = t.getAttribute("data-training-tab");
    const active = tab === trainingHallTab;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", active ? "true" : "false");
  });
  if (passiveView && hiddenView) {
    const showHidden = trainingHallTab === "hidden";
    passiveView.hidden = showHidden;
    hiddenView.hidden = !showHidden;
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
      if (!window.confirm(`Сбросить ветку «${branchRu}»? Примерно ${cost} 🪙.`)) return;
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
    setText("passive-free-pts", data.skill_points);
    const bp = data.branch_points || {};
    setText("passive-branch-pts", `${bp.warrior ?? 0} / ${bp.shadow ?? 0} / ${bp.sage ?? 0}`);
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
  if (t === "enchant_cost_pct" || t === "enchant_chance_pct") {
    return `${n > 0 ? "+" : ""}${Math.round(n)}%`;
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

function findHiddenSkillById(skillId) {
  return hiddenSkillsCache.find((s) => s.id === skillId) || null;
}

function openHiddenSkillModal(skillId) {
  const s = findHiddenSkillById(skillId);
  if (!s) return;
  const m = document.getElementById("hidden-skill-modal");
  const title = document.getElementById("hidden-skill-modal-title");
  const iconEl = document.getElementById("hidden-skill-modal-icon");
  const body = document.getElementById("hidden-skill-modal-body");
  if (!m || !title || !body) return;
  if (iconEl) iconEl.textContent = s.icon || "✨";
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

async function populateTrainingHall() {
  await loadPassiveSkillTree();
  bindHiddenSkillsListenersOnce();
  const root = document.getElementById("hidden-skills-root");
  if (!root) return;
  try {
    const data = await apiFetch("/skills/hidden");
    hiddenSkillsCache = Array.isArray(data?.skills) ? data.skills : [];
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
        const cnt = Number(s.counter) || 0;
        const next = s.next_threshold != null ? Number(s.next_threshold) : null;
        let pct = 0;
        if (next && next > 0) {
          pct = Math.min(100, Math.round((cnt / next) * 100));
        }
        const hint = s.description || "";
        const curFxShort = formatHiddenEffectsBlock(s.current_effects);
        html += `<div class="hidden-skill-card" data-hidden-skill-id="${esc(s.id)}" role="button" tabindex="0" title="Подробнее">
          <div class="hidden-skill-card-top"><span>${esc(s.icon || "✨")}</span>
            <span class="hidden-skill-card-title">${esc(s.name)}</span></div>
          <div class="hidden-skill-meta">${esc(hint)}</div>
          <div class="hidden-skill-meta">${esc(curFxShort)}</div>
          <div class="hidden-skill-meta">Ур. ${lv} / ${s.max_level || 5} · ${cnt}${
            next != null ? ` / ${next}` : ""
          }</div>
          <div class="hidden-skill-bar"><div class="hidden-skill-bar-fill" style="width:${pct}%"></div></div>
        </div>`;
      });
    }
    root.classList.remove("placeholder");
    root.innerHTML = html;
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
  }
}

// Expose helpers globally for inline usage (merge, don't clobber handlers assigned earlier)
window.WaifuApp = Object.assign(window.WaifuApp || {}, {
  initPage,
  bootstrapPage,
  populateTrainingHall,
  loadPassiveSkillTree,
  closePassiveSkillModal,
  openHiddenSkillModal,
  closeHiddenSkillModal,
  loadProfile,
  renderAtticDungeon,
  renderAtticExpeditions,
  refreshAtticChips,
  shopPageBootstrap,
  loadShop,
  switchShopTab,
  loadSmithTab,
  smithTryEnchant,
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
  closeItemModal,
  equipItemToProfileSlot,
  unequipItemFromModal,
  equipItemFromModal,
  openProfileSlotReplacementFromModal,
  openItemSellConfirmOverlay,
  closeItemSellConfirmOverlay,
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
  showToast,
  initWaifuGenerator,
  initTitleScreen,
  waifuGenGoStep1,
  waifuGenGoStep2,
  waifuGenPreviewPortrait,
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
  setGuildPageLoading,
  switchGuildTab,
  switchGuildActivityTab,
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
  selectPlayerMailItem,
  sendPlayerMail,
  initMailPage,
  refreshMailInbox,
  openMailDetail,
  claimMail,
  deleteMail,
  onGuildBannerClick,
  onGuildEmblemClick,
  uploadGuildIcon,
  uploadGuildBanner,
  openGuildMembersModal,
  closeGuildMembersModal,
  toggleGuildHeroMenu,
  closeGuildHeroMenu,
  toggleGuildRaidParticipant,
  startGuildRaid,
  leaveGuildRaid,
  loadGuildWarTargetsForUi,
  declareGuildWar,
  respondGuildWar,
  apiFetch,
  getInitData,
  spendStatPoint,
  closeRewardModal,
  viewRewardItem,
  populateCaravanPage,
  travelToAct,
  openCaravanModal,
  closeCaravanModal,
  confirmTravelToAct,
  requestCaravanDriverTip,
  closeCaravanTipModal,
});
