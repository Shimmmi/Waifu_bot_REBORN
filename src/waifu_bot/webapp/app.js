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
  const stagesEl = document.getElementById("attic-dungeon-stages");
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

    if (stagesEl) {
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
      const safeTotal = Math.min(8, totalStages); // avoid ultra-long headers
      const safeCur = Math.max(1, Math.min(safeTotal, curStage));

      let html = "";
      for (let i = 1; i <= safeTotal; i += 1) {
        const state = i < safeCur ? "done" : i === safeCur ? "active" : "pending";
        html += `<span class="attic-stage-pixel attic-stage-pixel--${state}" aria-hidden="true"></span>`;
      }
      stagesEl.innerHTML = html;
    }
  } else {
    label.textContent = "Нет боя";
    chip.classList.add("chip-ghost");
    chip.classList.remove("chip-active");
    if (stagesEl) stagesEl.innerHTML = "";
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
function refreshAtticChips() {
  apiFetch("/dungeons/active").then(renderAtticDungeon).catch(() => {});
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

const SELL_PAGE_SIZE = 9;

const shopState = {
  act: 1,
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
  /** Активная вкладка магазина: buy | sell | gamble */
  activeTab: "buy",
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

async function loadProfile() {
  const initData = getInitData();
  const qs = initData ? `?initData=${encodeURIComponent(initData)}` : "";
  const profile = await apiFetch(`/profile${qs}`);
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
    profile = await loadProfile();
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

  applyShopStageImages(act);

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
  updateShopGambleCost();
  return p;
}

async function loadShop(act) {
  applyShopStageImages(act);
  const shopSmithNavIntent = consumeShopSmithIntent();
  const data = await apiFetch(`/shop/inventory?act=${act}`);
  shopState.act = act;
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
    for (let s = 1; s <= 9; s += 1) {
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
    if (typeof document !== "undefined" && document.body) {
      document.body.classList.toggle("shop-tab-smith", (shopState.activeTab || "buy") === "smith");
    }
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

async function loadTavern(profile) {
  const p = profile || (await loadProfile().catch(() => null));
  return loadTavernWithProfile(p || { act: 1 });
}

const tavernState = {
  act: 1,
  available: null,
  squad: [],
  reserve: [],
  perksMap: {},
  selectedWaifu: null,
  pendingHireSlot: null, // 1..4
  lastHiredResult: null, // result of last successful hire for result modal
};

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
const TAVERN_POOL_MAX = 10;

function hiredWaifuHp(w) {
  const max = Number(w?.hpMax ?? w?.max_hp ?? 65);
  const cur = Number(w?.hpCurrent ?? w?.current_hp ?? max);
  return { cur, max };
}

function hiredWaifuImageUrl(w) {
  const u = w?.imageUrl ?? w?.image_url;
  return u ? String(u) : "";
}

/** Статус в пуле наёмниц: экспедиция / обморок (0 HP) / готова. Без «отряд vs запас». */
function hiredWaifuPoolUiStatus(w) {
  const expId = w?.expedition_id ?? w?.expeditionId;
  if (w?.status === "expedition" || (expId != null && Number(expId) > 0)) {
    return { key: "traveling", label: "В пути" };
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
  const root = `${TAVERN_STATIC_BASE}/tavern.background`;
  return n === 0 ? `${root}.webp` : `${root}_${n}.webp`;
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

let tavernBgmAudio = null;
let tavernBgmFadeRaf = null;
let tavernBgmLastIndex = -1;
let tavernBgmHooksBound = false;
let tavernBgmGestureArmed = false;

function isTavernBgmMuted() {
  try {
    return localStorage.getItem(TAVERN_BGM_MUTED_KEY) === "1";
  } catch (e) {
    return false;
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
  const muted = isTavernBgmMuted();
  btn.classList.toggle("tavern-tab-bgm--muted", muted);
  btn.setAttribute("aria-pressed", muted ? "true" : "false");
  if (muted) {
    btn.textContent = "🔇";
    btn.title = "Включить музыку";
    btn.setAttribute("aria-label", "Включить музыку");
  } else {
    btn.textContent = "🔊";
    btn.title = "Выключить музыку";
    btn.setAttribute("aria-label", "Выключить музыку");
  }
}

function toggleTavernBgmMuted() {
  if (isTavernBgmMuted()) {
    setTavernBgmMuted(false);
    startTavernBgm();
  } else {
    setTavernBgmMuted(true);
    stopTavernBgm(400);
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
  if (!a) return;
  const startVol = Number(a.volume) || 0;
  const t0 = performance.now();
  const dur = Math.max(0, fadeOutMs);
  if (dur === 0 || startVol <= 0.01) {
    try {
      a.pause();
    } catch (e) {
      /* ignore */
    }
    a.src = "";
    tavernBgmAudio = null;
    return;
  }
  function tick(now) {
    const t = Math.min(1, (now - t0) / dur);
    a.volume = startVol * (1 - t);
    if (t >= 1) {
      tavernBgmFadeRaf = null;
      try {
        a.pause();
      } catch (e) {
        /* ignore */
      }
      a.src = "";
      tavernBgmAudio = null;
      return;
    }
    tavernBgmFadeRaf = requestAnimationFrame(tick);
  }
  tavernBgmFadeRaf = requestAnimationFrame(tick);
}

function fadeInTavernBgm(audio, durationMs) {
  cancelTavernBgmFade();
  const t0 = performance.now();
  const dur = Math.max(200, durationMs);
  function tick(now) {
    if (!tavernBgmAudio || tavernBgmAudio !== audio) {
      tavernBgmFadeRaf = null;
      return;
    }
    const t = Math.min(1, (now - t0) / dur);
    audio.volume = t;
    if (t >= 1) {
      tavernBgmFadeRaf = null;
      return;
    }
    tavernBgmFadeRaf = requestAnimationFrame(tick);
  }
  audio.volume = 0;
  tavernBgmFadeRaf = requestAnimationFrame(tick);
}

function pickTavernBgmStartIndex() {
  const n = TAVERN_BGM_TRACKS.length;
  if (n <= 0) return -1;
  if (n === 1) return 0;
  let i = Math.floor(Math.random() * n);
  if (i === tavernBgmLastIndex) i = (i + 1) % n;
  return i;
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

function startTavernBgm() {
  if (typeof document === "undefined" || !document.body?.classList?.contains("page-tavern")) return;
  if (isTavernBgmMuted()) return;
  if (!TAVERN_BGM_TRACKS.length) return;
  ensureTavernBgmPageHooks();
  stopTavernBgm(0);

  const n = TAVERN_BGM_TRACKS.length;
  const startIdx = pickTavernBgmStartIndex();
  if (startIdx < 0) return;
  const order = [];
  for (let k = 0; k < n; k += 1) {
    order.push((startIdx + k) % n);
  }
  let i = 0;

  function tryNext() {
    if (i >= order.length) return;
    const idx = order[i++];
    const url = `${TAVERN_STATIC_BASE}/audio/${TAVERN_BGM_TRACKS[idx]}`;
    const a = new Audio();
    a.loop = true;
    a.preload = "auto";
    a.volume = 0;
    const fail = () => {
      a.removeEventListener("error", fail);
      try {
        a.pause();
      } catch (e) {
        /* ignore */
      }
      a.src = "";
      tryNext();
    };
    a.addEventListener("error", fail, { once: true });
    a.src = url;
    a.load();
    a.play()
      .then(() => {
        a.removeEventListener("error", fail);
        tavernBgmLastIndex = idx;
        tavernBgmAudio = a;
        fadeInTavernBgm(a, 3200);
      })
      .catch(() => {
        armTavernBgmUserGesture();
      });
  }
  tryNext();
}

function firstAvailableTavernSlot(available) {
  const slots = available?.slots || [];
  for (let i = 1; i <= 4; i += 1) {
    const slotObj = slots.find((s) => Number(s?.slot) === i);
    if (slotObj?.available) return i;
  }
  return null;
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
  document.querySelectorAll(".tavern-tabs .tab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  ["hire", "squad", "heal", "upgrade"].forEach((t) => {
    const panel = document.getElementById(`tab-${t}`);
    if (!panel) return;
    const isActive = t === name;
    panel.classList.toggle("active", isActive);
    panel.style.display = isActive ? "" : "none";
  });
  const footer = document.getElementById("tavern-hire-footer");
  if (footer) footer.style.display = name === "hire" ? "flex" : "none";
  if (name === "heal") renderTavernHealList();
  if (name === "squad") renderTavernSquad();
  if (name === "upgrade") renderTavernUpgradeList();
}

function renderTavernHealList() {
  const container = document.getElementById("tavern-heal-list");
  if (!container) return;
  const squad = Array.isArray(tavernState.squad) ? tavernState.squad : [];
  const reserve = Array.isArray(tavernState.reserve) ? tavernState.reserve : [];
  const all = [...squad, ...reserve];
  const wounded = all.filter((w) => {
    const { cur, max: maxHp } = hiredWaifuHp(w);
    return cur < maxHp;
  });
  if (wounded.length === 0) {
    container.innerHTML = '<p class="muted" style="font-style:italic;">Нет раненых наёмниц.</p>';
    container.className = "placeholder muted";
    return;
  }
  container.className = "";
  container.innerHTML = wounded
    .map((w) => {
      const { cur, max: maxHp } = hiredWaifuHp(w);
      const need = maxHp - cur;
      const mult = cur === 0 ? 2 : 1;
      const cost = need * TAVERN_HEAL_GOLD_PER_HP * mult;
      const pct = maxHp > 0 ? Math.round((cur / maxHp) * 100) : 0;
      const label = cur === 0 ? "В обмороке" : `HP ${cur}/${maxHp}`;
      return `
        <div class="tavern-heal-card" data-waifu-id="${w.id}">
          <div class="tavern-heal-info">
            <span class="tavern-waifu-name">${escapeHtml(w.name || "Наёмница")}</span>
            <span class="tavern-heal-hp">${label}</span>
            <div class="tavern-hp-bar-wrap"><div class="tavern-hp-bar" style="width:${pct}%"></div></div>
          </div>
          <div class="tavern-heal-action">
            <span class="tavern-heal-cost">🪙 ${cost}</span>
            <button type="button" class="btn btn-primary tavern-heal-btn" data-waifu-id="${w.id}" data-cost="${cost}">Лечить</button>
          </div>
        </div>`;
    })
    .join("");
  container.querySelectorAll(".tavern-heal-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.waifuId, 10);
      if (!id) return;
      (async () => {
        try {
          const res = await apiFetch(`/tavern/heal?hired_waifu_id=${encodeURIComponent(id)}`, { method: "POST" });
          if (res && res.success) {
            showToast("Наёмница вылечена");
            if (typeof res.gold_total === "number") profileState.gold = res.gold_total;
            const { squad: s, reserve: r } = await loadTavernWithProfile(undefined, { innerRefresh: true });
            tavernState.squad = s || tavernState.squad;
            tavernState.reserve = r || tavernState.reserve;
            renderTavernHealList();
            renderTavernSquad();
          }
        } catch (e) {
          showToast("Ошибка лечения: " + (e?.message || ""), "error");
        }
      })();
    });
  });
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
          <span class="tavern-upgrade-perk-ico" aria-hidden="true">${PERK_ICONS[pid] || "✦"}</span>
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
      const portrait = hiredWaifuImageUrl(w);
      const portraitHtml = portrait
        ? `<img src="${escapeHtml(portrait)}" alt="">`
        : `<span aria-hidden="true">🛡️</span>`;
      const perkGrid = tavernUpgradePerkGridHtml(w, perksMap, inExpedition);
      return `
      <div class="tavern-upgrade-card">
        <div class="tavern-upgrade-card-portrait">${portraitHtml}</div>
        <div class="tavern-upgrade-card-info">
          <div class="tavern-upgrade-card-title">
            <div class="tavern-upgrade-card-name">${escapeHtml(w.name || "Наёмница")}</div>
            <div class="tavern-upgrade-card-level">Ур. ${w.level ?? "—"}</div>
          </div>
          <div class="tavern-upgrade-points-badge ${points > 0 ? "has-points" : ""}" title="Очки улучшения перков">
            <span class="tavern-upgrade-points-num">${points}</span>
            <span class="tavern-upgrade-points-label">очк.</span>
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

async function loadTavernWithProfile(profile, opts = {}) {
  const inner = Boolean(opts.innerRefresh);
  if (!inner) {
    syncTavernBgmMuteButton();
    setTavernPageLoading(true);
  }
  let loadOk = false;
  try {
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
    const perksList = Array.isArray(available?.perks) ? available.perks : [];
    tavernState.perksMap = Object.fromEntries(perksList.map((x) => [x.id, x.name || x.id]));

    renderTavernHire(p, available);
    renderTavernSquad();

    if (!inner) {
      const pageBg = document.getElementById("tavern-page-bg");
      const url = pageBg?.currentSrc || pageBg?.src || "";
      await preloadTavernBg(url);
    }
    loadOk = true;
    return { available, squad: tavernState.squad, reserve: tavernState.reserve };
  } finally {
    if (!inner) {
      setTavernPageLoading(false);
      syncTavernBgmMuteButton();
      if (loadOk && !isTavernBgmMuted()) startTavernBgm();
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
  const price = Number(available?.price ?? 10000);
  const freeSlot = firstAvailableTavernSlot(available);

  const pageBg = document.getElementById("tavern-page-bg");
  if (pageBg) {
    pageBg.style.display = "";
    pageBg.src = tavernHireBackgroundUrl(remaining);
  }

  const hireBtn = document.getElementById("tavern-hire-primary-btn");
  if (hireBtn) {
    if (freeSlot != null) {
      hireBtn.textContent = `Нанять — 🪙 ${price.toLocaleString("ru-RU")}`;
      hireBtn.disabled = false;
      hireBtn.setAttribute("aria-label", `Нанять наёмницу. Осталось слотов: ${remaining}`);
    } else {
      hireBtn.textContent = "Слоты заняты";
      hireBtn.disabled = true;
      hireBtn.setAttribute("aria-label", "Все слоты найма на сегодня заняты");
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
  const portraitUrl = hiredWaifuImageUrl(w);
  const portraitContent = portraitUrl
    ? `<img src="${escapeHtml(portraitUrl)}" alt="" style="width:100%;height:100%;object-fit:cover;" />`
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
        <div class="pill"><span class="muted">Мощь</span><strong>${power}</strong></div>
        <div class="pill"><span class="muted">Перки</span><strong>${perksCount}</strong></div>
      </div>
    </div>
  `;
}

function renderTavernSquad() {
  const box = document.getElementById("tavern-squad-grid");
  if (!box) return;

  const roster = sortTavernPool(tavernState.squad, tavernState.reserve);
  const pool = roster.slice(0, TAVERN_POOL_MAX);
  const perksMap = tavernState.perksMap || {};

  const countersEl = document.getElementById("tavern-squad-counters");
  if (countersEl) {
    let nReady = 0;
    let nTravel = 0;
    let nFaint = 0;
    roster.forEach((w) => {
      const ui = hiredWaifuPoolUiStatus(w);
      if (ui.key === "traveling") nTravel += 1;
      else if (ui.key === "fainted") nFaint += 1;
      else nReady += 1;
    });
    countersEl.textContent = `${nReady} готовы · ${nTravel} в пути · ${nFaint} в обмороке`;
  }

  box.innerHTML = "";

  for (let i = 0; i < TAVERN_POOL_MAX; i += 1) {
    const w = pool[i] || null;
    if (!w) {
      const empty = document.createElement("div");
      empty.className = "squad-slot";
      empty.innerHTML = `<span style="font-size:24px;opacity:.3">＋</span><span style="font-size:11px;">Пустой слот</span>`;
      empty.onclick = () => {
        if (roster.length >= TAVERN_POOL_MAX) {
          showToast("Пул наёмниц заполнен", "error");
          return;
        }
        switchTavernTab("hire");
      };
      box.appendChild(empty);
      continue;
    }

    const uiSt = hiredWaifuPoolUiStatus(w);
    const badge =
      uiSt.key === "traveling"
        ? "🗺 В пути"
        : uiSt.key === "fainted"
          ? "💤 В обмороке"
          : "✓ Готова";

    const rarity = Number(w?.rarity ?? 1);
    const rCls = rarityClass(rarity);
    const clsId = Number(w?.class ?? w?.class_ ?? 0);
    const raceId = Number(w?.race ?? 0);
    const nm = escapeHtml(String(w?.name || "Вайфу"));
    const meta = `${escapeHtml(raceName(raceId))} · ${escapeHtml(className(clsId))} · Ур.${escapeHtml(String(w?.level ?? "—"))} · Мощь ${escapeHtml(String(w?.power ?? "—"))}`;
    const perkIds = Array.isArray(w.perks) ? w.perks : [];
    const perkBadges = perkIds.length
      ? perkIds
          .map((pid) => `<span class="perk-badge">${escapeHtml(String(perksMap[pid] || pid))}</span>`)
          .join("")
      : `<span class="muted tiny" style="opacity:.75;">—</span>`;

    const url = hiredWaifuImageUrl(w);
    const portraitLayer = url ? `<img class="squad-mtg-bg-img" src="${escapeHtml(url)}" alt="" />` : "";
    const bgCls = url ? "squad-mtg-bg" : "squad-mtg-bg squad-mtg-bg--placeholder";

    const slot = document.createElement("div");
    slot.className = "squad-slot occupied";
    slot.setAttribute("role", "button");
    slot.tabIndex = 0;
    slot.innerHTML = `
      <div class="squad-mtg-card ${rCls}">
        <div class="${bgCls}" role="img" aria-label="">${portraitLayer}</div>
        <div class="squad-mtg-scrim-top" aria-hidden="true"></div>
        <div class="squad-mtg-scrim-bottom" aria-hidden="true"></div>
        <div class="squad-mtg-slot-mark" aria-hidden="true">${escapeHtml(badge)}</div>
        <div class="squad-mtg-top">
          <div class="squad-mtg-name">${nm}</div>
          <div class="squad-mtg-meta">${meta}</div>
        </div>
        <div class="squad-mtg-bottom">
          <div class="squad-mtg-perks">${perkBadges}</div>
        </div>
      </div>`;

    const open = () => openTavernWaifuModal(w);
    slot.onclick = open;
    slot.onkeydown = (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        open();
      }
    };
    box.appendChild(slot);
  }
}

function openTavernConfirmHire(slot) {
  const id = Number(slot || 0);
  if (!Number.isFinite(id) || id < 1 || id > 4) return;
  const available = tavernState.available;
  const price = Number(available?.price ?? 10000);
  tavernState.pendingHireSlot = id;
  const priceEl = document.getElementById("confirm-price");
  if (priceEl) priceEl.textContent = `🪙 ${price}`;
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
  setText("result-meta", `${raceName(raceId)} · ${className(classId)}`);
  const bioText =
    result?.bio ||
    newWaifu?.bio ||
    "Новая наёмница присоединилась к вашему отряду. Управляйте ею во вкладке «Отряд».";
  setText("result-bio-back", bioText);
  const statsEl = document.getElementById("result-hire-stats");
  if (statsEl) {
    statsEl.textContent = newWaifu
      ? `Ур. ${newWaifu.level ?? "—"} · Мощь ${newWaifu.power ?? "—"}`
      : "—";
  }
  const perksEl = document.getElementById("result-perks");
  const perkIds = Array.isArray(newWaifu?.perks) ? newWaifu.perks : [];
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

function hiredWaifuExpForLevel(level) {
  if (level <= 1) return 0;
  let total = 0;
  for (let lvl = 2; lvl <= level; lvl++) total += 50 * (lvl * lvl);
  return total;
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

function openTavernWaifuModal(w) {
  tavernState.selectedWaifu = w || null;
  const m = document.getElementById("tavern-waifu-modal");
  const body = document.getElementById("tavern-waifu-modal-body");
  if (!m || !body || !w) return;

  const clsId = Number(w?.class ?? w?.class_ ?? w?.["class"]);
  const raceId = Number(w?.race);
  const rarity = Number(w?.rarity ?? 1);
  const rCls = rarityClass(rarity);
  const nm = String(w?.name || "Вайфу");
  const perksMap = tavernState.perksMap || {};
  const perkIds = Array.isArray(w?.perks) ? w.perks : [];
  const perkCells = perkIds.length
    ? perkIds
        .map((pid) => {
          const p = String(pid);
          const icon = PERK_ICONS[p] || "✦";
          const label = String(perksMap[p] || p);
          return `<button type="button" class="waifu-mtg-perk-cell" data-perk-id="${escapeHtml(p)}" aria-label="${escapeHtml(label)}"><span class="waifu-mtg-perk-ico" aria-hidden="true">${icon}</span></button>`;
        })
        .join("")
    : `<div class="waifu-mtg-no-perks">Нет перков</div>`;

  const imgUrl = hiredWaifuImageUrl(w);
  const portraitInner = imgUrl
    ? `<img class="waifu-mtg-art-img" src="${escapeHtml(imgUrl)}" alt="" />`
    : `<div class="waifu-mtg-art-placeholder" aria-hidden="true">${waifuPortraitEmoji(w)}</div>`;

  const level = Number(w?.level ?? 1);
  const exp = Number(w?.experience ?? 0);
  const expCur = hiredWaifuExpForLevel(level);
  const expNext = hiredWaifuExpForLevel(level + 1);
  const expInLevel = Math.max(0, exp - expCur);
  const expNeed = Math.max(1, expNext - expCur);
  const expPct = Math.min(100, Math.round((expInLevel / expNeed) * 100));
  const xpBarHtml =
    level >= 1 && level < 50
      ? `<div class="waifu-mtg-xp full-bar-row"><div class="full-bar-label"><span>Опыт</span><span>${expInLevel}/${expNeed}</span></div><div class="full-bar"><div class="full-bar-fill" style="width:${expPct}%;background:linear-gradient(90deg,#c8922a,#e8b84b);"></div></div></div>`
      : level >= 50
        ? `<div class="waifu-mtg-xp waifu-mtg-xp--max">Макс. уровень</div>`
        : "";

  const bioText = (w?.bio && String(w.bio).trim()) ? String(w.bio).trim() : "Биография не задана.";

  body.innerHTML = `
    <div class="tavern-waifu-mtg-wrap">
      <div class="waifu-mtg-flip-scene">
        <div class="waifu-mtg-flip-inner" id="waifu-mtg-flip-inner">
          <div class="waifu-mtg-face waifu-mtg-face--front">
            <div class="waifu-mtg-card ${rCls}">
              <div class="waifu-mtg-art">
                ${portraitInner}
                <div class="waifu-mtg-art-scrim" aria-hidden="true"></div>
                <header class="waifu-mtg-header-row">
                  <h2 class="waifu-mtg-name">${escapeHtml(nm)}</h2>
                  <div class="waifu-mtg-lvl-badge" title="Уровень"><span class="waifu-mtg-lvl-num">${escapeHtml(String(level))}</span></div>
                </header>
                <div class="waifu-mtg-lower-overlay">
                  <div class="waifu-mtg-typebar">
                    ${escapeHtml(raceName(raceId))} · ${escapeHtml(className(clsId))} · ${escapeHtml(rarityLabel(rarity))} · Мощь ${escapeHtml(String(w?.power ?? "—"))}
                  </div>
                  <div class="waifu-mtg-perks-head">
                    <span class="waifu-mtg-perks-label">Перки</span>
                    <button type="button" class="waifu-mtg-bio-chip" data-flip-to="back">BIO</button>
                  </div>
                  <div class="waifu-mtg-perk-grid">${perkCells}</div>
                </div>
                <div class="tavern-perk-tip" id="tavern-perk-tip" role="dialog" aria-modal="true" hidden>
                  <div class="tavern-perk-tip-name" id="tavern-perk-tip-name"></div>
                  <div class="tavern-perk-tip-desc" id="tavern-perk-tip-desc"></div>
                  <div class="tavern-perk-tip-diff" id="tavern-perk-tip-diff"></div>
                  <button type="button" class="tavern-perk-tip-close tavern-btn-mini">Понятно</button>
                </div>
              </div>
            </div>
          </div>
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
      </div>
      ${xpBarHtml}
    </div>
  `;

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
      tipName.textContent = String(perksMap[pid] ?? perksMap[String(pid)] ?? pid);
      tipDesc.textContent = PERK_DESCS[pid] || "Специальное умение для экспедиций.";
      tipDiff.textContent = PERK_EXPEDITION_COUNTER_HINT;
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

  setTavernWaifuModalPageScrollLocked(true);
  m.style.display = "grid";
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
    const perkPips = (u.perks || []).slice(0, 3).map((pid) => `<span class="perk-pip" title="${PERK_DESCS[pid] || ""}">${(perksMap[pid] || pid).toString().split(" ")[0] || "?"}</span>`).join("");
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

async function dismissTavernWaifu() {
  const w = tavernState.selectedWaifu;
  if (!w?.id) return;
  const nm = String(w?.name || "наёмницу").trim() || "наёмницу";
  const ok = window.confirm(`Уволить «${nm}»? Уровень передастся следующей нанятой наёмнице.`);
  if (!ok) return;
  try {
    const res = await apiFetch(`/tavern/dismiss?waifu_id=${encodeURIComponent(w.id)}`, { method: "POST" });
    closeTavernWaifuModal();
    showTavernError(res.hint || "Вайфу уволена. Уровень сохранён для следующей нанятой.");
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true }).catch(() => {});
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showTavernError(detail || "Ошибка увольнения", "danger");
  }
}

/** Кнопка 🔄 у вкладок: у игрока — перезагрузка с сервера; у админа — принудительное обновление слотов найма. */
async function refreshTavernPage() {
  if (isAdminUser()) {
    await adminRefreshTavern();
    return;
  }
  showTavernError("");
  try {
    await loadTavernWithProfile({ act: tavernState.act });
  } catch (e) {
    showTavernError("Не удалось обновить таверну.", "danger");
  }
}

async function adminRefreshTavern() {
  showTavernError("");
  try {
    const response = await apiFetch(`/admin/tavern/refresh`, { method: "POST" });
    tavernState.available = response;
    const perksList = Array.isArray(response?.perks) ? response.perks : [];
    tavernState.perksMap = Object.fromEntries(perksList.map((x) => [x.id, x.name || x.id]));
    renderTavernHire({ act: tavernState.act }, response);
    await loadProfile().catch(() => {});
    await loadTavernWithProfile({ act: tavernState.act }, { innerRefresh: true }).catch(() => {});
    showTavernError("Слоты найма обновлены.", "info");
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showTavernError(detail || "Ошибка обновления слотов", "danger");
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
let soloActiveMonsterTemplateId = null;

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

/** FastAPI/Pydantic: detail может быть строкой, массивом {loc,msg,type} или объектом — не использовать String(arr). */
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
  // "HTTP 400: {json}" -> try to parse json and extract detail
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

function renderSoloDungeonTile(d, waifuLevel) {
  const did = Number(d?.id);
  const lvlReq = safeInt(d?.level, 1);
  const baseCanEnter = safeInt(waifuLevel, 0) >= lvlReq;
  const lockedByAct = Boolean(d?.locked_by_act);
  const lockedByPrev = Boolean(d?.locked_by_prev);
  const pl = getPlusLevelForDungeon(did);
  const st = dungeonPlusStatusById?.[did];
  const unlocked = Number(st?.unlocked_plus_level || 0);
  const isPlusLocked = pl > 0 && pl > unlocked;
  const canEnter =
    !lockedByAct &&
    !lockedByPrev &&
    (pl > 0 ? !isPlusLocked : baseCanEnter);
  const act = safeInt(d?.act, 1);
  const dungeonNum = safeInt(d?.dungeon_number, 1);
  const artUrl = `${DUNGEONS_STATIC_BASE}/act-${act}/dungeon-${dungeonNum}.webp`;
  const lockedClass = canEnter ? "" : "locked";
  let lockReason = "";
  if (!canEnter) {
    if (lockedByAct) lockReason = "Акт не открыт";
    else if (lockedByPrev) lockReason = "Сначала пройдите предыдущее";
    else if (pl > 0 && isPlusLocked) lockReason = `Нужен разблокированный +${pl}`;
    else if (!baseCanEnter) lockReason = `Требуется ур. ${lvlReq}+`;
  }
  const lockHint = lockReason ? ` title="${escapeHtml(lockReason)}"` : "";
  const plusLabel = pl > 0 ? `+${pl}` : "0";
  const showPlusBtn = Boolean(plusBottomSheetUnlocked);
  const maxUn = Math.max(1, unlocked);
  const hue = Math.round(120 * (1 - Math.min(1, pl / maxUn)));
  const plusHueStyle = ` style="--plus-hue:${hue}"`;
  const plusBtn = showPlusBtn
    ? `<button type="button" class="chip chip-plus solo-dungeon-plus-btn"${plusHueStyle} data-dungeon-id="${did}" title="Сложность этого подземелья" aria-label="Выбрать сложность" onclick="event.stopPropagation(); event.preventDefault(); WaifuApp.openPlusBottomSheet(${did});">
        <span aria-hidden="true">➕</span>
        <span class="solo-dungeon-plus-label">${plusLabel}</span>
      </button>`
    : "";
  const nm = escapeHtml(String(d.name || "Подземелье"));
  const showMinLvl = safeInt(waifuLevel, 0) < lvlReq;
  const lvlLine = showMinLvl
    ? `<div class="solo-dungeon-card__meta-line solo-dungeon-card__meta-line--lvl">Мин. ур.: <strong>${lvlReq}</strong></div>`
    : "";
  const lineDiff =
    pl > 0
      ? `<div class="solo-dungeon-card__meta-line solo-dungeon-card__meta-line--diff">Сложность <strong>+${pl}</strong></div>`
      : `<div class="solo-dungeon-card__meta-line solo-dungeon-card__meta-line--diff solo-dungeon-card__meta-line--spacer" aria-hidden="true">&nbsp;</div>`;
  const lockLine =
    lockReason && !canEnter
      ? `<div class="solo-dungeon-card__meta-line solo-dungeon-card__meta-line--lock">${escapeHtml(lockReason)}</div>`
      : `<div class="solo-dungeon-card__meta-line solo-dungeon-card__meta-line--lock solo-dungeon-card__meta-line--spacer" aria-hidden="true">&nbsp;</div>`;
  const bottomClass =
    "solo-dungeon-card__bottombar" + (showMinLvl ? "" : " solo-dungeon-card__bottombar--compact");
  return `
    <div class="solo-dungeon-card dungeon-tile ${lockedClass}" data-dungeon-id="${did}" data-can-enter="${canEnter ? "1" : "0"}"${lockHint}
      onclick="WaifuApp.handleSoloDungeonTileClick(event, ${did})">
      <div class="solo-dungeon-card__frame">
        <img class="solo-dungeon-card__bg" src="${artUrl}" alt="" loading="lazy" decoding="async" />
        <div class="solo-dungeon-card__overlay">
          <div class="solo-dungeon-card__hdr">
            <h3 class="solo-dungeon-card__title">${nm}</h3>
            ${plusBtn}
          </div>
          <div class="${bottomClass}">
            ${lvlLine}
            ${lineDiff}
            ${lockLine}
          </div>
        </div>
      </div>
    </div>
  `;
}

function handleSoloDungeonTileClick(ev, dungeonId) {
  if (ev?.target?.closest?.(".solo-dungeon-plus-btn")) return;
  const tile = ev?.currentTarget;
  if (!tile || !dungeonId) return;
  const can = tile.getAttribute("data-can-enter") === "1";
  if (!can) {
    const t = tile.getAttribute("title");
    if (t) showDungeonsError(t, "info");
    return;
  }
  const pl = getPlusLevelForDungeon(dungeonId);
  startDungeon(dungeonId, pl);
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

// ─── Monster image (WebP) system ─────────────────────────────────────────
const MONSTER_STATIC_BASE =
  (typeof window !== "undefined" && window.APP_CONFIG?.staticBase) || `${GAME_STATIC_BASE}/monsters`;

function buildMonsterImageUrls(family, slug, tier, imageOverride) {
  if (imageOverride) return [imageOverride, `${MONSTER_STATIC_BASE}/_unknown.webp`];
  return [
    `${MONSTER_STATIC_BASE}/${family}/${slug}.webp`,
    `${MONSTER_STATIC_BASE}/${family}/_family_t${tier}.webp`,
    `${MONSTER_STATIC_BASE}/${family}/_family.webp`,
    `${MONSTER_STATIC_BASE}/_unknown.webp`,
  ];
}

function loadMonsterImage(family, slug, tier, imageOverride) {
  const visual = document.getElementById("monster-visual");
  const img = document.getElementById("monster-img");
  const placeholder = document.getElementById("monster-placeholder");
  if (!visual || !img || !placeholder) return;

  const urls = buildMonsterImageUrls(family, slug, tier, imageOverride);
  img.dataset.fallbackUrls = JSON.stringify(urls);
  img.dataset.fallbackIndex = "0";

  img.classList.add("fading");
  placeholder.classList.add("visible");

  visual.dataset.family = family || "";
  visual.dataset.slug = slug || "";
  visual.dataset.tier = String(tier || 1);

  img.style.display = "";
  img.src = urls[0];
  img.alt = `Монстр ${slug}`;
}

function onMonsterImageLoad(img) {
  const placeholder = document.getElementById("monster-placeholder");
  if (placeholder) placeholder.classList.remove("visible");
  if (img) img.classList.remove("fading");
}

function formatSoloBattleLogStepHtml(step) {
  if (!step || typeof step !== "object") return "";
  const kind = step.kind || "";
  const label = String(step.label_ru || step.source || "").replace(/</g, "&lt;");
  if (kind === "contrib") {
    const pct = step.pct_add != null ? ` (+${(Number(step.pct_add) * 100).toFixed(2)}%)` : "";
    const flat = step.flat_add != null ? ` (+${step.flat_add})` : "";
    return `<div class="solo-battle-log-step solo-battle-log-step--contrib"><span class="solo-battle-log-step-lbl">${label}${pct}${flat}</span></div>`;
  }
  if (kind === "cap") {
    return `<div class="solo-battle-log-step solo-battle-log-step--cap"><span class="solo-battle-log-step-lbl">${label}</span></div>`;
  }
  const vb = step.value_before;
  const va = step.value_after;
  let val = "";
  if (vb != null && va != null) val = `: ${vb} → ${va}`;
  else if (va != null) val = `: ${va}`;
  return `<div class="solo-battle-log-step"><span class="solo-battle-log-step-lbl">${label}${val}</span></div>`;
}

function buildSoloBattleLogHtml(entries) {
  const list = Array.isArray(entries) ? entries : [];
  if (!list.length) {
    return '<div class="solo-battle-log-empty muted tiny">Журнал боя пуст.</div>';
  }
  return list
    .map((entry, idx) => {
      const media = entry.log_media_label_ru || entry.log_media_key || "";
      const sum = entry.summary_ru || "—";
      const head = `<div class="solo-battle-log-entry-sum">#${idx + 1}${media ? ` [${media}]` : ""} ${sum}</div>`;
      const steps = entry.damage_breakdown || entry.incoming_breakdown;
      const stepsHtml = Array.isArray(steps)
        ? `<div class="solo-battle-log-steps">${steps.map(formatSoloBattleLogStepHtml).join("")}</div>`
        : "";
      return `<details class="solo-battle-log-entry"><summary>${head}</summary>${stepsHtml}</details>`;
    })
    .join("");
}

function mountSoloBattleLog(entries) {
  const host = document.getElementById("solo-battle-log-host");
  if (!host) return;
  const list = Array.isArray(entries) ? entries : [];
  if (!list.length) {
    host.style.display = "none";
    host.innerHTML = "";
    return;
  }
  host.style.display = "";
  host.innerHTML = `<div class="solo-battle-log-root"><div class="solo-battle-log-inner">${buildSoloBattleLogHtml(list)}</div></div>`;
}

function onMonsterImageError(img) {
  const urls = JSON.parse(img?.dataset?.fallbackUrls || "[]");
  let index = parseInt(img?.dataset?.fallbackIndex || "0", 10) + 1;
  if (index < urls.length) {
    img.dataset.fallbackIndex = String(index);
    img.src = urls[index];
  } else {
    if (img) img.style.display = "none";
  }
}

function renderSoloBattleCard(monster, dungeon, waifu) {
  const card = document.getElementById("solo-active");
  if (!card) return;
  const list = document.getElementById("solo-dungeons");
  if (list) list.style.display = "none";
  card.style.display = "block";

  setText("solo-dungeon-name", dungeon.name ?? "—");
  const total = dungeon.total_rooms || 0;
  const current = dungeon.current_room || 1;
  const progressDots = Array.from({ length: total }, (_, i) =>
    i < current - 1 ? "⚫" : i === current - 1 ? "🔴" : "⚪"
  ).join("");
  const progressEl = document.getElementById("solo-dungeon-progress");
  if (progressEl) progressEl.textContent = progressDots;

  const visual = document.getElementById("monster-visual");
  if (visual) {
    visual.className = "monster-visual";
    if (monster.is_boss) visual.classList.add("boss");
    else if (monster.is_elite) {
      const glow = monster.affix_count >= 4 ? "elite-red" : monster.affix_count >= 3 ? "elite-gold" : "elite-blue";
      visual.classList.add(glow);
    }
  }

  setText("monster-name-text", (monster.emoji ? monster.emoji + " " : "") + (monster.name ?? "—"));
  setText("monster-name-level", `Ур. ${monster.level ?? "—"}`);

  const emojiEl = document.getElementById("monster-emoji");
  if (emojiEl) emojiEl.textContent = monster.emoji ?? "👾";
  const placeholderLabel = document.getElementById("monster-placeholder-label");
  if (placeholderLabel) placeholderLabel.textContent = monster.family ?? "";

  const img = document.getElementById("monster-img");
  if (img) img.classList.add("fading");
  setTimeout(() => {
    loadMonsterImage(
      monster.family || "unknown",
      monster.slug || "unknown",
      monster.tier ?? 1,
      monster.image_override ?? null
    );
  }, 150);

  const monsterPct = monster.max_hp > 0 ? Math.max(0, Math.min(100, (monster.current_hp / monster.max_hp) * 100)) : 0;
  setText("monster-hp-text", `${monster.current_hp} / ${monster.max_hp}`);
  const hpFill = document.getElementById("monster-hp-fill");
  if (hpFill) hpFill.style.width = monsterPct + "%";

  const affixesEl = document.getElementById("monster-affixes");
  if (affixesEl) {
    if (monster.is_elite && monster.affixes?.length) {
      const colorClass = monster.affix_count >= 4 ? "red" : monster.affix_count >= 3 ? "gold" : "blue";
      affixesEl.innerHTML = monster.affixes.map((a) => `<span class="affix-chip ${colorClass}">${a.name}</span>`).join("");
      affixesEl.style.display = "flex";
    } else {
      affixesEl.style.display = "none";
    }
  }

  setText("solo-waifu-name", waifu.name ?? "—");
  setText("solo-waifu-hp-text", `${waifu.current_hp} / ${waifu.max_hp}`);
  const waifuPct = waifu.max_hp > 0 ? Math.max(0, Math.min(100, (waifu.current_hp / waifu.max_hp) * 100)) : 0;
  const waifuHpFill = document.getElementById("solo-waifu-hp-fill");
  if (waifuHpFill) waifuHpFill.style.width = waifuPct + "%";

  const unconsciousBanner = document.getElementById("unconscious-banner");
  if (unconsciousBanner) unconsciousBanner.style.display = waifu.current_hp <= 0 ? "block" : "none";
  const unconsciousTimer = document.getElementById("unconscious-timer");
  if (unconsciousTimer) unconsciousTimer.textContent = "восстановление...";

  const metaEl = document.getElementById("solo-active-meta");
  if (metaEl) {
    const lastDmg = typeof window._lastSoloDamage === "number" ? window._lastSoloDamage : null;
    const lastCrit = window._lastSoloCrit === true;
    const dealt = typeof window._lastSoloDealt === "number" ? window._lastSoloDealt : null;
    const parts = [];
    if (lastDmg != null) parts.push(`<div class="meta-tag">Последний удар: <strong>${lastDmg}</strong>${lastCrit ? " <span style=\"color:#fbbf24\">★крит</span>" : ""}</div>`);
    if (dealt != null && dealt > 0) parts.push(`<div class="meta-tag">Нанесено: <strong>${dealt}</strong></div>`);
    metaEl.innerHTML = parts.length ? parts.join("") : "";
  }
}

function renderSoloActiveProgress(active) {
  const host = document.getElementById("solo-active");
  const list = document.getElementById("solo-dungeons");
  if (!host || !list) return;

  if (!active?.active) {
    soloActiveMonsterTemplateId = null;
    host.style.display = "none";
    list.style.display = "";
    return;
  }

  soloActiveMonsterTemplateId =
    active.monster_template_id != null ? Number(active.monster_template_id) : null;

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
  window._lastSoloDamage = lastDmg;
  window._lastSoloCrit = lastCrit;
  window._lastSoloDealt = dealt;

  const monster = {
    name: active.monster_name,
    level: active.monster_level,
    current_hp: hpCur,
    max_hp: hpMax,
    family: active.monster_family || "unknown",
    slug: active.monster_slug || "unknown",
    tier: active.monster_tier ?? 1,
    has_image: active.monster_has_image === true,
    image_override: active.monster_image_override || null,
    emoji: active.monster_emoji || "👾",
    is_boss: active.is_boss === true,
    is_elite: active.is_elite === true,
    affix_count: active.affix_count ?? 0,
    affixes: Array.isArray(active.affixes) ? active.affixes : [],
  };
  const dungeon = {
    name: active.dungeon_name,
    total_rooms: total || 0,
    current_room: pos || 1,
  };
  const waifu = {
    name: active.waifu_name,
    current_hp: safeNumber(active.waifu_current_hp, 0),
    max_hp: Math.max(1, safeNumber(active.waifu_max_hp, 1)),
  };
  host.style.display = "";
  list.style.display = "none";
  const content = document.getElementById("solo-active-content");
  const fallback = document.getElementById("solo-active-fallback");
  if (content) content.style.display = "";
  if (fallback) fallback.style.display = "none";
  renderSoloBattleCard(monster, dungeon, waifu);
  mountSoloBattleLog(active.battle_log_entries || []);
}

function renderSoloActiveFallback(reason) {
  const host = document.getElementById("solo-active");
  const list = document.getElementById("solo-dungeons");
  const content = document.getElementById("solo-active-content");
  const fallback = document.getElementById("solo-active-fallback");
  if (!host || !list) return;
  host.style.display = "";
  list.style.display = "none";
  if (content) content.style.display = "none";
  if (fallback) {
    fallback.style.display = "block";
    fallback.innerHTML = `
      <div class="solo-active-head">
        <div class="solo-active-title">🏰 Активное подземелье</div>
        <div style="display:flex; align-items:center; gap:8px;">
          <div class="muted tiny">Прогресс недоступен</div>
          <button class="icon-btn" title="Покинуть подземелье" aria-label="Покинуть подземелье" onclick="WaifuApp.openExitDungeonConfirm()">✕</button>
        </div>
      </div>
      <div class="detail-row">
        <span class="muted">Причина</span>
        <strong>${String(reason || "—").replace(/</g, "&lt;")}</strong>
      </div>
      <div style="margin-top:6px;">
        <button class="btn" onclick="WaifuApp.refreshSoloActive()">🔄 Обновить</button>
      </div>
    `;
  }
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
    if (evt && evt.type === "gd") {
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => {
        loadActiveGdDungeons().catch?.(() => {});
        updateGdSessionUI().catch?.(() => {});
      }, 150);
      return;
    }
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

  // Open tab from URL (e.g. from ОЧ chip click)
  const tabParam = new URLSearchParams(window.location.search).get("tab");
  if (tabParam === "solo" || tabParam === "expedition" || tabParam === "group") {
    showTab(tabParam);
  }
}

let plusBottomSheetUnlocked = false;

function initPlusSelect(globalUnlocked, statusById) {
  plusBottomSheetUnlocked = globalUnlocked;
  for (const idStr of Object.keys(selectedPlusLevelByDungeonId)) {
    const id = Number(idStr);
    if (!Number.isFinite(id)) continue;
    const u = Number(statusById?.[id]?.unlocked_plus_level || 0);
    const raw = Number(selectedPlusLevelByDungeonId[id] ?? 0);
    if (raw > u) selectedPlusLevelByDungeonId[id] = u;
  }
}

function getDifficultyDescription(n) {
  const lvl = Number(n || 0);
  if (lvl === 0) return "Базовая сложность.";
  const hpDmg = Math.round(lvl * 20);
  const reward = (1 + lvl * 0.15 + Math.log1p(lvl) * 0.10).toFixed(2);
  const rarityLabels = ["обычная", "необычная", "редкая", "эпическая", "легендарная"];
  const rarity = rarityLabels[Math.min(Math.floor(lvl / 2), 4)];
  const elite = Math.min(40, lvl * 2);
  return `+${hpDmg}% HP/урон. Награды x${reward}. Предмет +${lvl} ур. Редкость: ${rarity}. Элиты +${elite}%.`;
}

window.WaifuApp.openPlusBottomSheet = (dungeonId) => {
  const did = Number(dungeonId);
  if (!Number.isFinite(did)) return;
  const bs = document.getElementById("plus-bottomsheet");
  const list = document.getElementById("plus-options-list");
  if (!bs || !list) return;
  const max = plusBottomSheetUnlocked ? Math.max(0, Number(dungeonPlusStatusById[did]?.unlocked_plus_level || 0)) : 0;
  const current = getPlusLevelForDungeon(did);
  list.innerHTML = "";
  const titleEl = bs.querySelector(".bottomsheet-title");
  if (titleEl) {
    titleEl.textContent = max > 0 ? "Сложность ➕ (это подземелье)" : "Сложность ➕";
  }
  for (let i = 0; i <= Math.max(0, max); i++) {
    const hue = max > 0 ? Math.round(120 * (1 - i / Math.max(1, max))) : 120;
    const bgColor = `hsla(${hue},70%,45%,0.22)`;
    const borderColor = `hsla(${hue},60%,55%,0.50)`;
    const desc = getDifficultyDescription(i);
    const btn = document.createElement("button");
    btn.className = "plus-option" + (i === current ? " selected" : "");
    btn.innerHTML = `
      <div class="plus-option-badge" style="background:${bgColor};border-color:${borderColor};color:#fff;">
        ${i === 0 ? "0" : `+${i}`}
      </div>
      <div class="plus-option-info">
        <div class="plus-option-label">${i === 0 ? "Обычная" : `Сложность +${i}`}</div>
        <div class="plus-option-desc">${desc}</div>
      </div>`;
    btn.addEventListener("click", () => {
      setPlusLevelForDungeon(did, i);
      window.WaifuApp.closePlusBottomSheet();
      const p = window.__lastProfileForDungeons || null;
      if (p) renderSoloDungeonsForAct(p).catch?.(() => {});
    });
    list.appendChild(btn);
  }
  bs.dataset.plusDungeonId = String(did);
  bs.style.display = "flex";
  document.body.style.overflow = "hidden";
};

window.WaifuApp.closePlusBottomSheet = () => {
  const bs = document.getElementById("plus-bottomsheet");
  if (bs) bs.style.display = "none";
  document.body.style.overflow = "";
};

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
  const invId = item.inventory_item_id ?? item.id ?? null;
  return `
    <div class="reward-item-card ${rc}" id="reward-item-card-${invId}">
      <div class="reward-item-top">
        <div class="reward-item-icon">${icon}</div>
        <div style="display:grid;gap:2px;min-width:0;flex:1;">
          <div class="reward-item-name ${rc}">${item.display_name || item.name || "Предмет"}</div>
          <div class="muted tiny">lvl ${item.level ?? "—"} · ${rarityLabel(item.rarity)} · ${slotTypeLabel(item.slot_type)}</div>
        </div>
        ${invId ? `<button type="button" class="secondary" style="flex-shrink:0;font-size:12px;padding:4px 10px;" onclick="event.stopPropagation();WaifuApp.viewRewardItem(${invId})">Подробнее</button>` : ""}
      </div>
    </div>`;
}

async function viewRewardItem(inventoryItemId) {
  try {
    const item = await apiFetch(`/inventory/${inventoryItemId}`);
    openItemModal(item);
  } catch (e) {
    showToast("Не удалось загрузить предмет: " + (e?.message || e), "error");
  }
}

function openRewardModal(payload) {
  const m = document.getElementById("reward-modal");
  const body = document.getElementById("reward-modal-body");
  const sub = document.getElementById("reward-modal-subtitle");
  if (!m || !body) return;

  if (sub) sub.textContent = "Победа над боссом!";

  const expMobs = payload.exp_from_monsters ?? payload.experience_gained ?? null;
  const expBoss = payload.exp_from_boss ?? null;
  const expTotal =
    payload.total_experience_gained ??
    (expMobs != null && expBoss != null ? expMobs + expBoss : expMobs ?? expBoss);

  const goldMobs = payload.gold_from_monsters ?? payload.gold_gained ?? null;
  const goldBoss = payload.gold_from_boss ?? null;
  const goldTotal =
    payload.total_gold_gained ??
    (goldMobs != null && goldBoss != null ? goldMobs + goldBoss : goldMobs ?? goldBoss);

  const itemsRaw = Array.isArray(payload.items_dropped)
    ? payload.items_dropped
    : payload.item_dropped
      ? [payload.item_dropped]
      : [];
  const guaranteedItem = payload.guaranteed_item || null;
  if (guaranteedItem) {
    const gId = guaranteedItem.inventory_item_id ?? guaranteedItem.id;
    const has = itemsRaw.some((i) => (i.inventory_item_id ?? i.id) === gId);
    if (!has) itemsRaw.push({ ...guaranteedItem, _guaranteed: true });
  }

  const fmt = (v) => (v != null ? Number(v).toLocaleString() : "—");

  const totalsBlock = `
    <div class="reward-totals-panel">
      <div class="reward-total-row"><span class="muted">Опыт</span><strong>+${fmt(expTotal)} ✨</strong></div>
      <div class="reward-total-row"><span class="muted">Золото</span><strong>+${fmt(goldTotal)} 🪙</strong></div>
    </div>`;

  const itemsHtml = itemsRaw.length
    ? `<div class="reward-section-title reward-section-title--items">Предметы</div>
       <div class="reward-items-list">
        ${itemsRaw.map((it) => buildRewardItemCard(it)).join("")}
       </div>`
    : `<div class="reward-section-title reward-section-title--items">Предметы</div>
       <div class="reward-item-card"><div class="muted tiny">Ничего не выпало</div></div>`;

  body.innerHTML = `
    <div class="reward-grid reward-grid--compact">
      ${totalsBlock}
      ${itemsHtml}
    </div>
  `;
  m.style.display = "grid";
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
  const result = await apiFetch("/dungeons/exit", { method: "POST" });
  const profile = await loadProfile().catch(() => null);
  if (profile) await renderSoloDungeonsForAct(profile);
  renderSoloActiveProgress({ active: false });
  await loadActiveDungeon();
  // Show a brief summary if rewards were accumulated
  if (result?.exp_gained > 0 || result?.gold_gained > 0) {
    appendEvent(`🚪 Покинули подземелье · +${result.exp_gained ?? 0} EXP · +${result.gold_gained ?? 0} 🪙`);
  }
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

  const enemyFill = document.getElementById("enemy-hp-fill");
  if (enemyFill) enemyFill.style.width = `${Math.round(clamp01(enemyHp / enemyHpMax) * 100)}%`;
  setText("enemy-hp-text", `HP: ${enemyHp}/${enemyHpMax}`);

  const waifuFill = document.getElementById("waifu-hp-fill");
  if (waifuFill) waifuFill.style.width = `${Math.round(clamp01(waifuHp / waifuHpMax) * 100)}%`;
  setText("waifu-hp-text", `HP: ${waifuHp}/${waifuHpMax}`);

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
    if (res?.error) {
      appendBattleLog(`Ошибка: ${res.message || res.error}`);
      return;
    }
    if (res?.elite_spawn) {
      const es = res.elite_spawn;
      const color = es.elite_color || "blue";
      const affixNames = (es.applied_affixes || []).map(a => a.name || a).join(" ");
      appendBattleLog(`⚠️ Элитный монстр! ${affixNames ? `[${affixNames}]` : ""} (${color})`);
    }
    const dmg = res?.damage ?? null;
    const crit = res?.is_crit;
    const dodged = res?.monster_dodged === true;
    if (dodged) {
      appendBattleLog("🛡️ Монстр уклонился!");
    } else if (dmg != null) {
      appendBattleLog(crit ? `⚔️ Удар ${dmg} (крит!)` : `⚔️ Удар ${dmg}`);
    }
    if (res?.experience_gained) appendBattleLog(`✨ +${res.experience_gained} EXP`);
    if (res?.gold_gained) appendBattleLog(`🪙 +${res.gold_gained} золото`);
    // Death: waifu left dungeon at 1 HP
    if (res?.waifu_died) {
      const penalty = res.gold_penalty_pct ?? 50;
      appendBattleLog(`💀 Вайфу погибла! Штраф к золоту: −${penalty}%. XP сохранён.`);
      setTimeout(() => { window.location.href = "./dungeons.html"; }, 1800);
      return;
    }
    if (res?.dungeon_completed) {
      openRewardModal(res);
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
  shopState.merchantAdviceUnlocked = false;
  shopState.activeTab = name;
  if (typeof document !== "undefined" && document.body) {
    document.body.classList.toggle("shop-tab-smith", name === "smith");
  }

  document.querySelectorAll(".tabs .tab, .shop-btab").forEach((btn) => {
    if (btn.dataset.tab) btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
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
    } else {
      generateMerchantLine(name).catch(() => {});
    }
    if (name === "gamble") updateShopGambleCost();
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
    wrap.innerHTML = it ? itemArtHtml(it) : '<span class="muted">—</span>';
  }
  if (lbl) {
    if (it) {
      lbl.innerHTML = composeItemDisplayName(it);
      lbl.classList.remove("muted");
    } else {
      lbl.textContent = "выбор предмета";
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
    const m = document.getElementById("shop-smith-pick-modal");
    if (m) m.style.display = "grid";
  } catch (e) {
    console.error(e);
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
      <div class="shop-smith-block">
        <div class="muted tiny">Текущий уровень: <strong>+${cur}</strong> → цель: <strong>+${tgt}</strong></div>
        <div class="muted tiny" style="margin-top:6px;">Стоимость: <strong>🪙 ${escapeHtml(String(cost))}</strong></div>
        ${chanceLine}
        ${
          statRows.length
            ? `<div style="margin-top:8px;font-size:12px;line-height:1.45;">${statRows.join("")}</div>`
            : ""
        }
      </div>`;
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
        <p>Присоединяйтесь к групповому чату и запишитесь в поход командой /gd_join</p>
      </div>`;
    return;
  }
  dungeons.forEach((dungeon) => {
    const card = createGdDungeonCard(dungeon);
    container.appendChild(card);
  });
}

function gdV1WaveLabelRu(wave) {
  const m = {
    trash: "обычные враги",
    boss: "босс",
    done: "завершено",
    pending_init: "ожидание боя",
  };
  if (wave == null || wave === "") return "—";
  return m[wave] || String(wave);
}

/** Короткая метка на карточке: для active — номер сбора действий (collecting_for_round). */
function gdV1StageBadge(dungeon) {
  if (!dungeon.v1) {
    return `${dungeon.stage || 1}/4`;
  }
  if (dungeon.cycle_status === "registration") {
    return "регистрация";
  }
  const m = Number(dungeon.collecting_for_round);
  return Number.isFinite(m) && m > 0 ? `сбор №${m}` : "поход";
}

function createGdDungeonCard(dungeon) {
  const hpBarWidth = `${Math.max(0, Math.min(100, dungeon.hp_percent || 0))}%`;
  const card = document.createElement("div");
  card.className = "dungeon-card gd-dungeon-card";
  card.dataset.dungeonId = dungeon.id;
  const stageRight = dungeon.v1 ? gdV1StageBadge(dungeon) : `${dungeon.stage || 1}/4`;
  const roundsStat = dungeon.v1
    ? `🎯 раундов с вкладом: ${Number(dungeon.contrib_rounds || 0).toLocaleString()}`
    : `Этап ${dungeon.joined_at_stage || 1}`;
  card.innerHTML = `
    <div class="dungeon-header">
      <span class="dungeon-name">${escapeHtml(dungeon.dungeon_name || "—")}</span>
      <span class="dungeon-stage">${escapeHtml(stageRight)}</span>
    </div>
    <div class="dungeon-monster">
      <span class="monster-name">${escapeHtml(dungeon.monster_name || "—")}</span>
      <div class="hp-bar">
        <div class="hp-fill" style="width: ${hpBarWidth}"></div>
      </div>
      <div class="hp-text">${Number(dungeon.hp_current || 0).toLocaleString()} / ${Number(dungeon.hp_max || 0).toLocaleString()}</div>
    </div>
    <div class="dungeon-stats">
      <span class="stat">⚔️ ${Number(dungeon.total_damage || 0).toLocaleString()} (текст+навыки)</span>
      <span class="stat">👥 ${escapeHtml(roundsStat)}</span>
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
  const lastRec = Number(dungeon.stage) || 0;
  const collecting = Number(dungeon.collecting_for_round) || 1;
  const deadlineStr = dungeon.round_deadline_at
    ? new Date(dungeon.round_deadline_at).toLocaleString()
    : "—";
  const stageSection = dungeon.v1
    ? `<div class="details-section">
        <h3>Поход GD v1</h3>
        <p class="muted tiny">${escapeHtml(
          dungeon.cycle_status === "registration" ? "Регистрация открыта" : "Поход идёт"
        )} · на карточке: ${escapeHtml(gdV1StageBadge(dungeon))}</p>
        ${
          dungeon.cycle_status === "active"
            ? `<p class="muted tiny">Последний записанный в журнале раунд: <strong>${lastRec}</strong></p>
        <p class="muted tiny">Сбор действий в чате на раунд: <strong>${collecting}</strong></p>
        <p class="muted tiny">Волна: ${escapeHtml(gdV1WaveLabelRu(dungeon.wave))}</p>
        <p class="muted tiny">Дедлайн сбора раунда: ${escapeHtml(deadlineStr)}</p>`
            : ""
        }
      </div>`
    : `<div class="details-section">
        <h3>Текущий этап</h3>
        <div class="stage-progress">${renderStageProgress(dungeon.stage || 1)}</div>
      </div>`;
  const effectsSection =
    dungeon.v1 && (!dungeon.active_effects || dungeon.active_effects.length === 0)
      ? ""
      : `<div class="details-section">
        <h3>Активные эффекты</h3>
        <div class="effects-list">${effects}</div>
      </div>`;
  return `
    <div class="dungeon-details">
      <h2>${escapeHtml(dungeon.dungeon_name || "—")}</h2>
      ${stageSection}
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
              <span>~${Math.round(Number(dungeon.hp_percent) || 0)}% здоровья</span>
            </div>
          </div>
        </div>
      </div>
      <div class="details-section">
        <h3>Ваш вклад</h3>
        <div class="contribution-stats">
          <div class="stat-row">
            <span>⚔️ Условный урон (текст + навыки):</span>
            <span>${Number(dungeon.total_damage || 0).toLocaleString()}</span>
          </div>
          <div class="stat-row">
            <span>${dungeon.v1 ? "🎯 Раундов с вашим вкладом:" : "👥 Присоединились на этапе:"}</span>
            <span>${
              dungeon.v1
                ? `${Number(dungeon.contrib_rounds || 0).toLocaleString()}`
                : `${dungeon.joined_at_stage || 1}/4`
            }</span>
          </div>
          <div class="stat-row">
            <span>⏱️ Время в подземелье:</span>
            <span>${formatDuration(dungeon.duration_seconds || 0)}</span>
          </div>
        </div>
      </div>
      ${effectsSection}
      ${
        dungeon.v1 && dungeon.id
          ? `<div class="details-section gd-battle-log-wrap">
        <h3>Полный лог боя</h3>
        <p class="muted tiny">Действия отряда и монстров по инициативе (если ИИ дал короткий текст — детали здесь).</p>
        <div class="gd-battle-log-status muted">Загрузка…</div>
        <div class="gd-battle-log-body" style="display:none" aria-live="polite"></div>
      </div>`
          : ""
      }
      <div class="modal-actions">
        <button type="button" class="btn-primary gd-open-chat" data-chat-id="${dungeon.chat_id || ""}">Перейти в чат</button>
      </div>
    </div>`;
}

async function loadGdBattleLog(modalEl, cycleId) {
  const status = modalEl.querySelector(".gd-battle-log-status");
  const body = modalEl.querySelector(".gd-battle-log-body");
  if (!status || !body) return;
  try {
    const data = await apiFetch(`/gd/cycles/${cycleId}/battle-log`);
    const rounds = Array.isArray(data?.rounds) ? data.rounds : [];
    if (rounds.length === 0) {
      status.textContent = "В журнале пока нет завершённых раундов.";
      return;
    }
    const maxRn = Math.max(...rounds.map((r) => Number(r.round_number) || 0));
    status.style.display = "none";
    body.style.display = "block";
    body.innerHTML = rounds
      .map((r) => {
        const rn = Number(r.round_number) || 0;
        const outcome = escapeHtml(r.round_outcome || "—");
        const narr = (r.ai_narrative || "").trim();
        const narrHtml = narr ? escapeHtml(narr) : "—";
        const lines = Array.isArray(r.lines) ? r.lines : [];
        const linesHtml =
          lines.length > 0
            ? `<ul class="gd-battle-log-lines">${lines.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul>`
            : '<p class="muted tiny">Нет строк журнала для этого раунда.</p>';
        const openAttr = rn === maxRn ? " open" : "";
        return `<details class="gd-battle-round"${openAttr}><summary>Раунд ${rn} · ${outcome}</summary><p class="gd-battle-narrative"><span class="muted tiny">ИИ:</span> ${narrHtml}</p>${linesHtml}</details>`;
      })
      .join("");
  } catch (e) {
    console.error("loadGdBattleLog", e);
    status.textContent = "Не удалось загрузить лог боя.";
  }
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
  if (dungeon.v1 && dungeon.id) {
    loadGdBattleLog(modal, dungeon.id);
  }
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
    const v1 = await apiFetch(`/gd/cycle/${chatId}`).catch(() => ({ v1: false }));
    if (v1 && v1.v1) {
      if (infoBlock) infoBlock.style.display = "none";
      card.style.display = "";
      const st = v1.status === "registration" ? "Регистрация" : "Поход идёт";
      const closes = v1.registration_closes
        ? new Date(v1.registration_closes).toLocaleString()
        : "—";
      const title = escapeHtml(v1.dungeon_name || "Групповой поход GD v1");
      const lastR = Number(v1.current_round) || 0;
      const coll = Number(v1.collecting_for_round) || 1;
      const deadline =
        v1.round_deadline_at && v1.status === "active"
          ? new Date(v1.round_deadline_at).toLocaleString()
          : null;
      const hpPct = Math.max(0, Math.min(100, Number(v1.hp_percent) || 0));
      const waveLine =
        v1.status === "active"
          ? `<div class="muted tiny">Волна: ${escapeHtml(gdV1WaveLabelRu(v1.wave))}</div>`
          : "";
      const deadlineLine =
        deadline != null
          ? `<div class="muted tiny">Дедлайн сбора раунда: ${escapeHtml(deadline)}</div>`
          : "";
      const hpBlock =
        v1.status === "active"
          ? `<div class="gd-session-monster" style="margin-top:8px;">
          <span id="gd-session-monster-name">${escapeHtml(v1.monster_name || "—")}</span>
          <span id="gd-session-hp">${Number(v1.hp_current || 0).toLocaleString()} / ${Number(v1.hp_max || 0).toLocaleString()}</span>
        </div>
        <div class="gd-session-hp-bar"><div id="gd-session-hp-fill" class="gd-hp-fill" style="width:${hpPct}%"></div></div>`
          : "";
      card.innerHTML = `
        <h3 class="gd-session-title" id="gd-session-dungeon-name">${title}</h3>
        <div class="muted tiny" style="margin:6px 0;">${escapeHtml(st)}</div>
        <div class="muted tiny">Регистрация до: ${escapeHtml(closes)}</div>
        ${
          v1.status === "active"
            ? `<div class="muted tiny" style="margin-top:6px;">В журнале записан раунд: <strong>${lastR}</strong> · сбор на раунд: <strong>${coll}</strong></div>
        ${waveLine}
        ${deadlineLine}
        ${hpBlock}`
            : ""
        }
        <p class="muted tiny" style="margin-top:8px;">Команда в чате: <code>/gd_join</code>. Сообщения в чат попадают в буфер текущего раунда; закрытие по таймеру (~30 мин) или админ-команде.</p>
      `;
      return;
    }
    card.style.display = "none";
    if (infoBlock) infoBlock.style.display = "";
  } catch {
    card.style.display = "none";
    if (infoBlock) infoBlock.style.display = "";
  }
}

function showExpeditionError(msg, tone = "danger") {
  const box = document.getElementById("expedition-error");
  if (!box) return;
  if (!msg) {
    box.style.display = "none";
    box.textContent = "";
    return;
  }
  box.classList.remove("success", "warning", "danger");
  if (tone) box.classList.add(tone);
  box.textContent = String(msg);
  box.style.display = "block";
}

async function loadExpeditionTab() {
  showExpeditionError("");
  try {
    const [slotsRes, activeRes, rosterRes] = await Promise.all([
      apiFetch("/expeditions/daily-slots").catch(() => apiFetch("/expeditions/slots")),
      apiFetch("/expeditions/active"),
      apiFetch("/expeditions/roster").catch(() => ({ waifus: [] })),
    ]);
    expeditionState.slots = Array.isArray(slotsRes?.slots) ? slotsRes.slots : [];
    expeditionState.active = Array.isArray(activeRes?.active) ? activeRes.active : [];
    expeditionState.roster = Array.isArray(rosterRes?.waifus) ? rosterRes.waifus : [];
    expeditionState.refreshAt = slotsRes?.refresh_at || null;
    expeditionUiCache.activeById = {};
    expeditionUiCache.dailyById = {};
    (expeditionState.active || []).forEach((a) => {
      expeditionUiCache.activeById[a.id] = a;
    });
    (expeditionState.slots || []).forEach((s) => {
      expeditionUiCache.dailyById[s.id] = s;
    });
    renderExpeditionGrids();
    updateExpeditionRefreshLabel();
    wireExpeditionTabTimers();
    refreshAtticChips();
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

function biomeBg(tag) {
  const t = String(tag || "")
    .toLowerCase()
    .trim();
  const map = {
    cave: "linear-gradient(135deg,#1a0d2e,#0d0819)",
    forest: "linear-gradient(135deg,#0d2e1a,#081908)",
    ruins: "linear-gradient(135deg,#2e1a0d,#190d08)",
    swamp: "linear-gradient(135deg,#0d2e12,#081208)",
    temple: "linear-gradient(135deg,#1a0d2e,#0d0819)",
    dark_temple: "linear-gradient(135deg,#1a0d2e,#12081a)",
    fortress: "linear-gradient(135deg,#2e1a0d,#120804)",
    crypt: "linear-gradient(135deg,#0d0d12,#050508)",
    desert: "linear-gradient(135deg,#2e220d,#190f04)",
    volcano: "linear-gradient(135deg,#2e0d0d,#190808)",
    abyss: "linear-gradient(135deg,#0d0518,#020008)",
    sky: "linear-gradient(135deg,#0d1a2e,#081018)",
    sea_depth: "linear-gradient(135deg,#0d1e2e,#081318)",
    tundra: "linear-gradient(135deg,#1a252e,#0d1418)",
  };
  return map[t] || "linear-gradient(135deg,#1a1008,#0d0808)";
}

function normalizeBiomeTag(tag) {
  return String(tag || "")
    .trim()
    .toLowerCase()
    .replace(/ /g, "_")
    .replace(/-/g, "_");
}

function biomeImageUrls(tag) {
  const key = normalizeBiomeTag(tag);
  const urls = [];
  if (key) urls.push(`${EXPEDITION_BIOMES_BASE}/${encodeURIComponent(key)}.webp`);
  urls.push(`${EXPEDITION_BIOMES_BASE}/default.webp`);
  return urls;
}

function applyExpeditionBiomeBackground(el, tag, emojiEl) {
  if (!el) return;
  const fallback = biomeBg(tag);
  const isModal = el.classList.contains("exp-modal-img");
  const biomeCls = isModal ? "exp-modal-img--biome" : "exp-card-img--biome";
  el.classList.remove("exp-modal-img--biome", "exp-card-img--biome");
  el.style.backgroundImage = "";
  el.style.background = fallback;
  if (emojiEl) emojiEl.style.display = "";
  const urls = biomeImageUrls(tag);
  let i = 0;
  function tryNext() {
    if (i >= urls.length) return;
    const url = urls[i++];
    const probe = new Image();
    probe.onload = () => {
      el.style.background = fallback;
      el.style.backgroundImage = `url("${url}")`;
      el.style.backgroundSize = "cover";
      el.style.backgroundPosition = "center";
      el.classList.add(biomeCls);
      if (emojiEl) emojiEl.style.display = "none";
    };
    probe.onerror = tryNext;
    probe.src = url;
  }
  tryNext();
}

function wireExpeditionCardBiomes(root) {
  (root || document).querySelectorAll(".exp-card-img[data-biome-tag]").forEach((imgEl) => {
    const tag = imgEl.getAttribute("data-biome-tag") || "";
    const emojiEl = imgEl.querySelector(".exp-card-emoji");
    applyExpeditionBiomeBackground(imgEl, tag, emojiEl);
  });
}

const EXPEDITION_DIFFICULTY_TAG_RU = {
  monsters: "Монстры",
  undead: "Нежить",
  dark_magic: "Тёмная магия",
  elements: "Стихии",
  traps: "Ловушки",
  curses: "Проклятия",
  knowledge: "Знания",
  social: "Социум",
};

const EXPEDITION_TAG_PRIORITY = [
  "undead",
  "monsters",
  "dark_magic",
  "curses",
  "traps",
  "elements",
  "knowledge",
  "social",
];

const EXPEDITION_ROMAN = ["I", "II", "III", "IV", "V"];

function primaryObstacleLabel(tags, affixes, diffVal) {
  const tagList = tags || [];
  let primaryTag = null;
  for (const t of EXPEDITION_TAG_PRIORITY) {
    if (tagList.includes(t)) {
      primaryTag = EXPEDITION_DIFFICULTY_TAG_RU[t] || t;
      break;
    }
  }
  if (!primaryTag && affixes && affixes.length) {
    primaryTag = affixes[0].name || "Препятствие";
  }
  if (!primaryTag) primaryTag = "Препятствия";
  const roman = EXPEDITION_ROMAN[Math.max(0, Math.min(4, (diffVal || 1) - 1))];
  return `${primaryTag} ${roman}`;
}

function updateExpeditionObstacleLevel() {
  const el = expG("esm-obstacle-level");
  const slot = expeditionSend.currentSlot;
  if (!el || !slot) return;
  el.textContent = primaryObstacleLabel(slot.difficulty_tags, slot.affixes, expeditionSend.diffVal);
}

function updateExpeditionSendAffixes() {
  const slot = expeditionSend.currentSlot;
  const affixEl = expG("esm-affixes");
  if (!slot || !affixEl) return;
  affixEl.innerHTML = expeditionAffixChipsHtml(slot.affixes || [], expeditionSend.diffVal, true);
}

function expeditionDifficultyTagsHtml(tagIds, coveredIds) {
  const covered = new Set(coveredIds || []);
  return (tagIds || [])
    .map((id) => {
      const label = EXPEDITION_DIFFICULTY_TAG_RU[id] || id;
      const isCov = covered.has(id);
      const cls = isCov ? "exp-diff-tag exp-diff-tag-covered" : "exp-diff-tag";
      const title = isCov
        ? "Тип закрыт отрядом (снижение сложности на 1/N)"
        : "Активный тип сложности";
      return `<span class="${cls}" title="${title}">${escapeHtml(label)}</span>`;
    })
    .join("");
}

function getExpPickerHighlightTags() {
  const all = expeditionSend.currentSlot?.difficulty_tags || [];
  const excluded = expeditionSend.pickerExcludedTags || new Set();
  return all.filter((t) => !excluded.has(t));
}

function expeditionPickerFilterTagsHtml(tagIds, excludedSet) {
  const excluded = excludedSet instanceof Set ? excludedSet : new Set(excludedSet || []);
  const hint = "Нажмите, чтобы вкл/выкл подсветку подходящих наёмниц";
  return (tagIds || [])
    .map((id) => {
      const label = EXPEDITION_DIFFICULTY_TAG_RU[id] || id;
      const on = !excluded.has(id);
      const cls = on
        ? "exp-pick-filter-tag exp-pick-filter-tag--on"
        : "exp-pick-filter-tag exp-pick-filter-tag--off";
      const title = on ? `${hint} (подсветка включена)` : `${hint} (подсветка выключена)`;
      return `<button type="button" class="${cls}" data-pick-filter-tag="${escapeHtml(id)}" title="${escapeHtml(title)}">${escapeHtml(label)}</button>`;
    })
    .join("");
}

function expeditionUnitMatchedPerkIds(unit, activeTags) {
  const active = new Set(activeTags || []);
  const matched = new Set();
  const perkTags = unit?.perk_tags || {};
  for (const pid of unit?.perks || []) {
    const tags = perkTags[pid] || [];
    if (tags.some((t) => active.has(t))) matched.add(pid);
  }
  return matched;
}

function expeditionUnitMatchIndicators(unit, activeTags) {
  const active = new Set(activeTags || []);
  const indicators = [];
  const matchedPerks = expeditionUnitMatchedPerkIds(unit, activeTags);
  for (const pid of unit?.perks || []) {
    if (!matchedPerks.has(pid)) continue;
    const tags = (unit.perk_tags || {})[pid] || [];
    const hit = tags.filter((t) => active.has(t)).map((t) => EXPEDITION_DIFFICULTY_TAG_RU[t] || t);
    indicators.push({
      kind: "perk",
      id: pid,
      icon: PERK_ICONS[pid] || "✦",
      title: `${PERK_DESCS[pid] || pid}${hit.length ? " · " + hit.join(", ") : ""}`,
    });
  }
  const raceTags = (unit?.race_tags || []).filter((t) => active.has(t));
  if (raceTags.length) {
    const rid = Number(unit.race);
    const race = WAIFU_RACES.find((r) => r.id === rid);
    const hit = raceTags.map((t) => EXPEDITION_DIFFICULTY_TAG_RU[t] || t);
    indicators.push({
      kind: "race",
      id: rid,
      icon: race?.icon || raceIcon(rid),
      title: `${race?.name || "Раса"} · ${hit.join(", ")}`,
    });
  }
  const classTags = (unit?.class_tags || []).filter((t) => active.has(t));
  if (classTags.length) {
    const cid = Number(unit.class ?? unit.class_);
    const cls = WAIFU_CLASSES.find((c) => c.id === cid);
    const hit = classTags.map((t) => EXPEDITION_DIFFICULTY_TAG_RU[t] || t);
    indicators.push({
      kind: "class",
      id: cid,
      icon: cls?.icon || classIcon(cid),
      title: `${cls?.name || "Класс"} · ${hit.join(", ")}`,
    });
  }
  return indicators;
}

function expPickPortraitHtml(u, extraClass) {
  const cls = extraClass ? ` ${extraClass}` : "";
  const url = hiredWaifuImageUrl(u);
  if (url) {
    return `<div class="exp-pick-portrait${cls}"><img src="${escapeHtml(url)}" alt="" class="exp-pick-portrait-img" /></div>`;
  }
  return `<div class="exp-pick-portrait${cls}"><span class="exp-pick-portrait-emoji">${waifuPortraitEmoji(u)}</span></div>`;
}

function expPickMatchRowHtml(indicators) {
  if (!indicators.length) return "";
  return `<div class="exp-pick-match-row">${indicators
    .map(
      (ind) =>
        `<span class="perk-icon-badge perk-icon-badge--match" title="${escapeHtml(ind.title)}">${ind.icon}</span>`
    )
    .join("")}</div>`;
}

function expPickPerksHtml(u, matchedPerkIds) {
  const perks = u?.perks || [];
  if (!perks.length) return "";
  return `<div class="exp-pick-perks">${perks
    .map((pid) => {
      const isMatch = matchedPerkIds.has(pid);
      const title = PERK_DESCS[pid] || pid;
      return `<span class="perk-icon-badge${isMatch ? " perk-icon-badge--match" : ""}" title="${escapeHtml(title)}">${PERK_ICONS[pid] || "✦"}</span>`;
    })
    .join("")}</div>`;
}

function expeditionSquadCoveredTags(squadSlots, activeTags) {
  const active = new Set(activeTags || []);
  const out = new Set();
  for (const u of (squadSlots || []).filter(Boolean)) {
    for (const t of u.covered_tags || []) {
      if (active.has(t)) out.add(t);
    }
  }
  return [...out];
}

function updateExpeditionSendTags(coveredIds) {
  const slot = expeditionSend.currentSlot;
  const tagsEl = expG("esm-difficulty-tags");
  if (!slot || !tagsEl) return;
  tagsEl.innerHTML = expeditionDifficultyTagsHtml(slot.difficulty_tags || [], coveredIds || []);
}

async function refreshExpeditionTagPreview() {
  const slot = expeditionSend.currentSlot;
  const effEl = expG("esm-tag-effectiveness");
  if (!slot || !expG("esm-difficulty-tags")) return;
  const unitIds = expeditionSend.squadSlots.filter(Boolean).map((u) => u.id);
  const baseTags = slot.difficulty_tags || [];
  if (!unitIds.length) {
    updateExpeditionSendTags([]);
    if (effEl) effEl.textContent = "Снижение сложности: ~100% (выберите отряд)";
    return;
  }
  const clientCovered = expeditionSquadCoveredTags(expeditionSend.squadSlots, baseTags);
  updateExpeditionSendTags(clientCovered);
  try {
    const prev = await apiFetch("/expeditions/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slot_id: slot.id,
        unit_ids: unitIds,
        duration_minutes: expeditionSend.durVal,
        difficulty_level: expeditionSend.diffVal,
      }),
    });
    updateExpeditionSendTags(prev.covered_tags || clientCovered);
    if (effEl) {
      const tagPct = Math.round(Number(prev.tag_effectiveness_pct ?? 100));
      const perkPct =
        prev.perk_effectiveness_pct != null ? Math.round(Number(prev.perk_effectiveness_pct)) : null;
      let txt = `Снижение сложности: ~${tagPct}%`;
      if (perkPct != null && unitIds.length) {
        txt += ` · эффективность перков: ~${perkPct}%`;
      }
      effEl.textContent = txt;
    }
  } catch (_) {
    updateExpeditionSendTags(clientCovered);
    if (effEl) effEl.textContent = "";
  }
}

function expeditionAffixChipsHtml(affixes, affixLevel, withLevelOnFirst) {
  const roman =
    affixLevel >= 1 && affixLevel <= 5 ? ["I", "II", "III", "IV", "V"][affixLevel - 1] : "";
  return (affixes || [])
    .map((a, i) => {
      const cat = String(a.category || "enemy")
        .toLowerCase()
        .replace(/[^a-z]/g, "") || "enemy";
      const label =
        withLevelOnFirst && roman && i === 0
          ? `${a.icon || "✦"} ${a.name} ${roman}`
          : `${a.icon || "✦"} ${a.name}`;
      return `<span class="exp-aff-chip exp-cat-${cat}">${label}</span>`;
    })
    .join("");
}

function renderExpeditionGrids() {
  const activeSection = document.getElementById("exp-active-section");
  const activeGrid = document.getElementById("exp-active-grid");
  const dailyGrid = document.getElementById("exp-daily-grid");
  if (!activeGrid || !dailyGrid) return;

  const actives = expeditionState.active || [];
  if (activeSection) {
    if (actives.length) {
      activeSection.style.display = "";
      activeGrid.innerHTML = actives
        .map((a) => {
          const name = escapeHtml(a.base_location || a.expedition_name || "—");
          const affixIcos = (a.affixes || [])
            .slice(0, 4)
            .map((x) => `<div class="exp-affix-ico">${x.icon || "✦"}</div>`)
            .join("");
          const prog = a.progress_pct != null ? Math.min(100, Number(a.progress_pct)) : 0;
          const sec = a.seconds_left != null ? a.seconds_left : 0;
          const timeStr = a.can_claim ? "—" : formatExpeditionTime(sec);
          const emoji = a.biome_emoji || "🗺";
          const biomeTag = escapeHtml(a.biome_tag || "");
          return `<div class="exp-card-item exp-is-active" data-exp-kind="active" data-exp-id="${a.id}">
            <div class="exp-card-img" data-biome-tag="${biomeTag}">
              <div class="exp-card-emoji">${emoji}</div>
              <div class="exp-card-affix-icons">${affixIcos}</div>
              <div class="exp-card-name">${name}</div>
            </div>
            <div class="exp-card-progbar"><div class="exp-card-progfill" style="width:${prog}%"></div></div>
            <div class="exp-card-foot"><span class="exp-foot-active">● В пути</span><span class="exp-foot-timer">${timeStr}</span></div>
          </div>`;
        })
        .join("");
    } else {
      activeSection.style.display = "none";
      activeGrid.innerHTML = "";
    }
  }

  const slots = expeditionState.slots || [];
  if (!slots.length) {
    dailyGrid.innerHTML = '<div class="placeholder muted tiny">Нет доступных экспедиций</div>';
  } else {
    dailyGrid.innerHTML = slots
      .map((s) => {
        const used = Boolean(s.is_used);
        const name = escapeHtml(s.base_location || s.name || "—");
        const affixIcos = (s.affixes || [])
          .slice(0, 4)
          .map((x) => `<div class="exp-affix-ico">${x.icon || "✦"}</div>`)
          .join("");
        const emoji = s.biome_emoji || "🗺";
        const biomeTag = escapeHtml(s.biome_tag || "");
        const cls = used ? " exp-card-used" : "";
        const foot = used
          ? `<div class="exp-card-foot"><span class="exp-foot-muted">● Отправлена</span></div>`
          : `<div class="exp-card-foot"><span class="exp-foot-ready">● Доступна</span></div>`;
        return `<div class="exp-card-item${cls}" data-exp-kind="daily" data-exp-id="${s.id}" data-exp-used="${used ? "1" : "0"}">
            <div class="exp-card-img" data-biome-tag="${biomeTag}">
              <div class="exp-card-emoji">${emoji}</div>
              <div class="exp-card-affix-icons">${affixIcos}</div>
              <div class="exp-card-name">${name}</div>
            </div>
            ${foot}
          </div>`;
      })
      .join("");
  }

  wireExpeditionCardBiomes(activeGrid);
  wireExpeditionCardBiomes(dailyGrid);

  document.querySelectorAll("#exp-active-grid [data-exp-kind], #exp-daily-grid [data-exp-kind]").forEach((el) => {
    el.addEventListener("click", () => {
      const kind = el.getAttribute("data-exp-kind");
      const id = Number(el.getAttribute("data-exp-id"));
      if (kind === "daily" && el.getAttribute("data-exp-used") === "1") return;
      expOpenCard(kind, id);
    });
  });
}

let expeditionTimerId = null;
let expActiveModalTimer = null;

function wireExpeditionTabTimers() {
  const hasRunning = (expeditionState.active || []).some((a) => !a.can_claim);
  if (hasRunning && !expeditionTimerId) {
    expeditionTimerId = setInterval(() => {
      if (document.getElementById("tab-expedition")?.style.display !== "none") {
        loadExpeditionTab().catch(() => {});
      }
    }, 15000);
  } else if (!hasRunning && expeditionTimerId) {
    clearInterval(expeditionTimerId);
    expeditionTimerId = null;
  }
}

function updateExpeditionRefreshLabel() {
  const el = document.getElementById("exp-daily-refresh-label");
  if (!el || !expeditionState.refreshAt) {
    if (el) el.textContent = "Обновляются в 00:00 МСК";
    return;
  }
  const end = new Date(expeditionState.refreshAt).getTime();
  const fmt = () => {
    const sec = Math.max(0, Math.floor((end - Date.now()) / 1000));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    el.textContent = `Обновляются в 00:00 МСК — осталось ${h}ч ${m}м`;
  };
  fmt();
}

function expG(id) {
  return document.getElementById(id);
}

function expOpenOverlay(id) {
  const el = expG(id);
  if (el) {
    el.style.display = "flex";
    el.classList.add("exp-open");
  }
}

function expCloseOverlay(id) {
  const el = expG(id);
  if (el) {
    el.style.display = "none";
    el.classList.remove("exp-open");
  }
}

function expOpenCard(kind, id) {
  if (kind === "active") {
    const raw = expeditionUiCache.activeById[id];
    if (raw) openActiveExpModal(raw);
  } else {
    const slot = expeditionUiCache.dailyById[id];
    if (slot) openSendExpModal(slot);
  }
}

function openActiveExpModal(raw) {
  expeditionUiCache._activeRaw = raw;
  expG("eam-title").textContent = raw.base_location || raw.expedition_name || "—";
  const affHtml = expeditionAffixChipsHtml(raw.affixes || [], raw.affix_level, true);
  expG("eam-affixes").innerHTML = affHtml;
  const img = expG("eam-img");
  const emo = expG("eam-emoji");
  if (emo) emo.textContent = raw.biome_emoji || "🗺";
  applyExpeditionBiomeBackground(img, raw.biome_tag, emo);

  tickActiveModal();
  if (expActiveModalTimer) clearInterval(expActiveModalTimer);
  expActiveModalTimer = setInterval(tickActiveModal, 1000);

  const squad = raw.squad_snapshot || [];
  expG("eam-squad").innerHTML = squad.map(expeditionActiveUnitRow).join("");

  window._activeExpId = raw.id;
  const claimBtn = expG("eam-claim-btn");
  const abortBtn = expG("eam-abort-btn");
  if (claimBtn) {
    claimBtn.onclick = () => {
      closeActiveExpModal();
      openExpeditionResult(raw.id);
    };
  }
  if (claimBtn && abortBtn) {
    const canClaim = Boolean(raw.can_claim);
    claimBtn.style.display = canClaim ? "block" : "none";
    abortBtn.style.display = canClaim ? "none" : "";
  }
  expOpenOverlay("exp-active-modal");
}

function expeditionActiveUnitRow(u) {
  const pct = u.hp_max > 0 ? Math.round((u.hp_current / u.hp_max) * 100) : 0;
  const color = pct > 50 ? "#4ade80" : pct > 25 ? "#fbbf24" : "#f87171";
  const sub = [u.unit_class, u.race].filter(Boolean).join(" · ");
  const warn = pct <= 25 ? '<span style="color:#f87171;font-size:9px"> ⚠ Лечение</span>' : "";
  return `<div class="exp-unit-row">
    <div class="exp-unit-ico">${u.icon || "⚔️"}</div>
    <div class="exp-unit-inf">
      <div class="exp-unit-name">${escapeHtml(u.name || "—")}</div>
      <div class="exp-unit-sub">${escapeHtml(sub)}${warn}</div>
    </div>
    <div style="text-align:right;flex-shrink:0">
      <div style="font-size:10px;color:${color};font-weight:700;margin-bottom:3px">${u.hp_current}/${u.hp_max}</div>
      <div class="exp-unit-hpbar"><div class="exp-unit-hpfill" style="width:${pct}%;background:${color}"></div></div>
    </div>
  </div>`;
}

function tickActiveModal() {
  const raw = expeditionUiCache._activeRaw;
  if (!raw) return;
  const endMs = new Date(raw.ends_at).getTime();
  const sec = Math.max(0, Math.floor((endMs - Date.now()) / 1000));
  const canClaim = Date.now() >= endMs;
  const tEl = expG("eam-timer");
  if (tEl) tEl.textContent = canClaim ? "Готово" : formatExpeditionTime(sec);
  const prog = raw.progress_pct != null ? Math.min(100, Number(raw.progress_pct)) : 0;
  const pTxt = expG("eam-prog-txt");
  const pFill = expG("eam-prog-fill");
  if (pTxt) pTxt.textContent = prog + "%";
  if (pFill) pFill.style.width = prog + "%";
  const ev = expG("eam-events");
  if (ev) ev.textContent = `${raw.events_done ?? 0} / ${raw.events_total ?? 0}`;
  const claimBtn = expG("eam-claim-btn");
  const abortBtn = expG("eam-abort-btn");
  if (claimBtn && abortBtn) {
    claimBtn.style.display = canClaim ? "block" : "none";
    abortBtn.style.display = canClaim ? "none" : "";
  }
}

function closeActiveExpModal() {
  if (expActiveModalTimer) {
    clearInterval(expActiveModalTimer);
    expActiveModalTimer = null;
  }
  expeditionUiCache._activeRaw = null;
  expCloseOverlay("exp-active-modal");
}

function openSendExpModal(slot) {
  expeditionSend.slotId = slot.id;
  expeditionSend.currentSlot = slot;
  expeditionSend.diffVal = 1;
  expeditionSend.durVal = 30;
  expeditionSend.squadSlots = [null, null, null];
  expG("esm-title").textContent = slot.base_location || slot.name || "—";
  updateExpeditionSendAffixes();
  const tagsEl = expG("esm-difficulty-tags");
  if (tagsEl) updateExpeditionSendTags([]);
  updateExpeditionObstacleLevel();
  const effEl = expG("esm-tag-effectiveness");
  if (effEl) effEl.textContent = "Снижение сложности: ~100% (выберите отряд)";
  const img = expG("esm-img");
  const emo = expG("esm-emoji");
  if (emo) emo.textContent = slot.biome_emoji || "🗺";
  applyExpeditionBiomeBackground(img, slot.biome_tag, emo);

  expG("esm-diff-row").querySelectorAll(".exp-opt-btn").forEach((b, i) => b.classList.toggle("active", i === 0));
  expG("esm-dur-row").querySelectorAll(".exp-opt-btn").forEach((b, i) => b.classList.toggle("active", i === 0));
  renderExpeditionSquadSlots();
  expOpenOverlay("exp-send-modal");
}

function closeSendExpModal() {
  expCloseOverlay("exp-send-modal");
}

function expSelDiff(val, btn) {
  expeditionSend.diffVal = val;
  expG("esm-diff-row").querySelectorAll(".exp-opt-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  updateExpeditionObstacleLevel();
  updateExpeditionSendAffixes();
  refreshExpeditionTagPreview();
}

function expSelDur(val, btn) {
  expeditionSend.durVal = val;
  expG("esm-dur-row").querySelectorAll(".exp-opt-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  refreshExpeditionTagPreview();
}

function getAvailableUnits() {
  return expeditionState.roster || [];
}

function renderExpeditionSquadSlots() {
  for (let i = 0; i < 3; i++) {
    const slot = expG("exp-sl-" + i);
    const unit = expeditionSend.squadSlots[i];
    if (!slot) continue;
    if (unit) {
      slot.className = "exp-squad-slot exp-slot-filled";
      const hpC = unit.hp_current ?? unit.current_hp ?? 0;
      const hpM = unit.hp_max ?? unit.max_hp ?? 1;
      slot.innerHTML = `${expPickPortraitHtml(unit, "exp-pick-portrait--squad")}
        <div class="exp-squad-name">${escapeHtml(unit.name || "")}</div>
        <div class="exp-squad-hp">${hpC}/${hpM}</div>`;
    } else {
      slot.className = "exp-squad-slot";
      slot.innerHTML = '<span class="exp-squad-empty">+ Добавить</span>';
    }
    slot.onclick = () => expOpenPicker(i);
  }
  const btn = expG("exp-send-btn");
  if (btn) btn.disabled = expeditionSend.squadSlots.every((s) => !s);
  refreshExpeditionTagPreview();
}

let expPickerTagsWired = false;

function wireExpPickerTagsFilter() {
  const tagsEl = expG("exp-picker-tags");
  if (!tagsEl || expPickerTagsWired) return;
  expPickerTagsWired = true;
  tagsEl.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-pick-filter-tag]");
    if (!btn) return;
    e.preventDefault();
    expTogglePickerFilterTag(btn.getAttribute("data-pick-filter-tag"));
  });
}

function expTogglePickerFilterTag(tagId) {
  if (!tagId) return;
  if (!expeditionSend.pickerExcludedTags) expeditionSend.pickerExcludedTags = new Set();
  if (expeditionSend.pickerExcludedTags.has(tagId)) {
    expeditionSend.pickerExcludedTags.delete(tagId);
  } else {
    expeditionSend.pickerExcludedTags.add(tagId);
  }
  renderExpPickerContent();
}

function renderExpPickerContent() {
  const slotIdx = expeditionSend.pickerSlot;
  const takenIds = new Set(
    expeditionSend.squadSlots
      .map((u, i) => (i !== slotIdx && u ? u.id : null))
      .filter(Boolean)
  );
  const units = getAvailableUnits();
  const list = expG("exp-unit-list");
  const tagsEl = expG("exp-picker-tags");
  const allTags = expeditionSend.currentSlot?.difficulty_tags || [];
  const highlightTags = getExpPickerHighlightTags();
  const excluded = expeditionSend.pickerExcludedTags || new Set();

  if (tagsEl) {
    tagsEl.innerHTML = allTags.length
      ? `<div class="muted tiny" style="margin-bottom:4px">Типы сложности:</div><div class="exp-pick-filter-tags">${expeditionPickerFilterTagsHtml(allTags, excluded)}</div>`
      : "";
  }

  if (!list) return;
  list.innerHTML =
    units
      .map((u) => {
        const inExp = u.expedition_id != null;
        const inSquad = takenIds.has(u.id);
        const disabled = inExp || inSquad;
        const hpM = u.hp_max ?? u.max_hp ?? 1;
        const hpC = u.current_hp ?? u.hp_current ?? hpM;
        const pct = hpM > 0 ? Math.round((hpC / hpM) * 100) : 0;
        const hpColor = pct > 50 ? "#4ade80" : pct > 25 ? "#fbbf24" : "#f87171";
        const cid = Number(u.class ?? u.class_);
        const rid = Number(u.race);
        const cls = WAIFU_CLASSES.find((c) => c.id === cid);
        const race = WAIFU_RACES.find((r) => r.id === rid);
        const note = inExp ? "🔒 В экспедиции" : `${cls?.name || "—"} · ${race?.name || "—"}`;
        const matchedPerks = expeditionUnitMatchedPerkIds(u, highlightTags);
        const indicators = expeditionUnitMatchIndicators(u, highlightTags);
        const hasMatch = indicators.length > 0;
        const clickAttr = disabled ? "" : ` onclick="WaifuApp.expPickUnit(${u.id})"`;
        const cardCls = `exp-pick-card${disabled ? " exp-pick-card--disabled" : ""}${hasMatch ? " exp-pick-card--match" : ""}`;
        const power = u.power != null ? u.power : "—";
        return `<div class="${cardCls}"${clickAttr}>
          <div class="exp-pick-head">
            ${expPickPortraitHtml(u)}
            <div class="exp-pick-info">
              <div class="exp-pick-name-row">
                <div class="exp-pick-name">${escapeHtml(u.name || "")}</div>
                ${expPickMatchRowHtml(indicators)}
              </div>
              <div class="exp-pick-sub">${note}</div>
            </div>
          </div>
          <div class="exp-pick-stats">
            <span class="exp-pick-stat" title="Мощь">⚔ ${power}</span>
            <span class="exp-pick-stat" title="Здоровье">❤ ${hpC}/${hpM}</span>
          </div>
          <div class="exp-pick-hpbar">
            <div class="exp-pick-hpfill" style="width:${pct}%;background:${hpColor}"></div>
          </div>
          ${expPickPerksHtml(u, matchedPerks)}
        </div>`;
      })
      .join("") || '<div class="placeholder muted tiny">Нет доступных наёмниц</div>';
}

function expOpenPicker(slotIdx) {
  expeditionSend.pickerSlot = slotIdx;
  expeditionSend.pickerExcludedTags = new Set();
  wireExpPickerTagsFilter();
  renderExpPickerContent();
  closeSendExpModal();
  expOpenOverlay("exp-picker-overlay");
}

function expPickUnit(id) {
  const units = getAvailableUnits();
  const unit = units.find((u) => u.id === id);
  if (!unit || unit.expedition_id) return;
  expeditionSend.squadSlots[expeditionSend.pickerSlot] = unit;
  expClosePicker();
  expOpenOverlay("exp-send-modal");
  renderExpeditionSquadSlots();
}

function expClosePicker() {
  expCloseOverlay("exp-picker-overlay");
}

async function submitExpeditionStart() {
  const unitIds = expeditionSend.squadSlots.filter(Boolean).map((u) => u.id);
  if (!unitIds.length || !expeditionSend.slotId) {
    showExpeditionError("Выберите отряд и слот.");
    return;
  }
  try {
    await apiFetch("/expeditions/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slot_id: expeditionSend.slotId,
        unit_ids: unitIds,
        difficulty_level: expeditionSend.diffVal,
        duration_minutes: expeditionSend.durVal,
      }),
    });
    closeSendExpModal();
    expClosePicker();
    showExpeditionError("");
    showDungeonsError("Экспедиция отправлена.");
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showExpeditionError(detail || "Ошибка запуска экспедиции");
  }
}

function expeditionHelpHtml() {
  const effRows = [1, 2, 3, 4, 5]
    .map((pl) => {
      const cells = [1, 2, 3, 4, 5]
        .map((al) => {
          const pct = Math.round(Math.min(100, (pl / al) * 100));
          return `<td>${pct}%</td>`;
        })
        .join("");
      return `<tr><th>${pl}</th>${cells}</tr>`;
    })
    .join("");
  return `
    <p><strong>Слот.</strong> Локация + типы сложности (Монстры, Нежить…). Закрытые отрядом типы снижают урон. Пример: «Нежить III» — основной тип + выбранный уровень I–V.</p>
    <p><strong>Уровень I–V.</strong> Сила препятствий и наград. Урон за событие: 6% / 10% / 15% / 20% / 28% HP отряда. Награды: +6% за каждый уровень выше I.</p>
    <p><strong>Длительность.</strong> Каждые 15 мин = 1 событие. Больше времени — больше событий, выше риск по HP, но больше награда.</p>
    <p><strong>Перки.</strong> Прокачка во вкладке ⬆ LVL таверны (очки за лвлап после экспедиции). Эффективность перка против уровня препятствия:</p>
    <table class="exp-help-table" aria-label="Эффективность перка">
      <thead><tr><th>Перк↓ / Ур.→</th><th>I</th><th>II</th><th>III</th><th>IV</th><th>V</th></tr></thead>
      <tbody>${effRows}</tbody>
    </table>
    <p><strong>Исход.</strong> По HP отряда в конце: &lt;12% — провал, ≥52% — успех, иначе частичный (награда ×0.7). Досрочное завершение — ×0.5 награды.</p>
  `;
}

function openExpeditionHelp() {
  const body = document.getElementById("expedition-help-body");
  if (body) body.innerHTML = expeditionHelpHtml();
  expOpenOverlay("expedition-help-modal");
}

function closeExpeditionHelp() {
  expCloseOverlay("expedition-help-modal");
}

async function abortExpedition(activeId) {
  if (!activeId) return;
  try {
    await apiFetch(`/expeditions/${activeId}/abort`, { method: "POST" });
    showToast?.("Экспедиция завершена (≈50% награды)", "success");
    closeActiveExpModal();
    await loadProfile().catch(() => {});
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast?.(detail || e?.message || "Ошибка", "error");
  }
}
async function claimExpedition(activeId) {
  try {
    const res = await apiFetch(`/expeditions/claim?active_id=${activeId}`, { method: "POST" });
    let msg = `Награда: 🪙 +${res.gold_gained} · ✨ +${res.experience_gained}`;
    if (res.event_text) {
      msg += "\n\n" + res.event_text;
    }
    showDungeonsError(msg);
    await loadProfile().catch(() => {});
    await loadExpeditionTab();
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showDungeonsError(detail || "Ошибка получения награды", "danger");
  }
}

async function openExpeditionResult(expeditionId) {
  const modal = document.getElementById("expedition-result-modal");
  const loading = document.getElementById("exp-result-loading");
  const content = document.getElementById("exp-result-content");
  const fill = document.getElementById("exp-result-loading-fill");
  const sub = document.getElementById("exp-result-loading-sub");
  if (!modal || !loading || !content) return;

  modal.style.display = "flex";
  modal.style.alignItems = "flex-end";
  modal.style.justifyContent = "center";
  loading.style.display = "flex";
  content.style.display = "none";
  if (fill) fill.style.width = "0%";

  const loadingSteps = [
    [10, "Отряд возвращается в таверну..."],
    [30, "Считаем потери и трофеи..."],
    [55, "Начисляем опыт наёмницам..."],
    [75, "Рассказчик пишет историю..."],
    [90, "Почти готово..."],
  ];
  let stepIdx = 0;
  const progressInterval = setInterval(() => {
    if (stepIdx < loadingSteps.length && fill && sub) {
      const [pct, text] = loadingSteps[stepIdx++];
      fill.style.width = pct + "%";
      sub.textContent = text;
    }
  }, 600);

  try {
    const result = await apiFetch(`/expeditions/${expeditionId}/claim`, { method: "POST" });
    clearInterval(progressInterval);
    if (fill) fill.style.width = "100%";
    if (sub) sub.textContent = "Готово!";
    await new Promise((r) => setTimeout(r, 400));
    fillExpeditionResult(result);
    loading.style.display = "none";
    content.style.display = "block";
  } catch (e) {
    clearInterval(progressInterval);
    modal.style.display = "none";
    showToast("Ошибка получения наград: " + (e?.message || e), "error");
  }
}

function fillExpeditionResult(result) {
  const OUTCOME_CONFIG = {
    success: { icon: "✅", title: "Успешно завершена!", color: "#4ade80", mult: "×1.0" },
    partial_success: { icon: "⚠️", title: "Завершена с потерями", color: "#facc15", mult: "×0.7" },
    failure: { icon: "❌", title: "Провал", color: "#f87171", mult: "×0.4" },
  };
  const cfg = OUTCOME_CONFIG[result.outcome] || OUTCOME_CONFIG.partial_success;

  const outcomeEl = document.getElementById("exp-result-outcome");
  if (outcomeEl) {
    outcomeEl.innerHTML = `
      <div class="exp-result-outcome-icon">${cfg.icon}</div>
      <div class="exp-result-outcome-title" style="color:${cfg.color}">${escapeHtml(result.expedition_name || "Экспедиция")}</div>
      <div class="exp-result-outcome-sub">${cfg.title}</div>`;
  }
  const narrativeEl = document.getElementById("exp-result-narrative");
  if (narrativeEl) narrativeEl.textContent = result.ai_narrative || "Отряд вернулся из экспедиции.";

  const rewardsEl = document.getElementById("exp-result-rewards");
  if (rewardsEl) {
    rewardsEl.innerHTML = `
      <div class="exp-result-reward-box">
        <div class="exp-result-reward-label">Золото</div>
        <div class="exp-result-reward-value">🪙 ${result.gold_earned ?? 0}</div>
        <div class="exp-result-reward-mult">${cfg.mult}</div>
      </div>
      <div class="exp-result-reward-box">
        <div class="exp-result-reward-label">Опыт наёмниц</div>
        <div class="exp-result-reward-value">✨ ${result.exp_earned ?? 0}</div>
        <div class="exp-result-reward-mult">${cfg.mult}</div>
      </div>`;
  }

  const squadEl = document.getElementById("exp-result-squad");
  if (squadEl && Array.isArray(result.squad_state)) {
    squadEl.innerHTML = result.squad_state
      .map((u) => {
        const hpPct = u.hp_max ? Math.round((u.hp_current / u.hp_max) * 100) : 100;
        const needsHeal = u.hp_current < u.hp_max;
        return `
          <div class="exp-result-unit">
            <div class="exp-result-unit-icon">${u.class_icon || "⚔️"}</div>
            <div class="exp-result-unit-info">
              <div class="exp-result-unit-name">${escapeHtml(u.name || "—")}</div>
              <div class="exp-result-unit-stats">
                ❤ ${u.hp_current}/${u.hp_max}
                ${needsHeal ? ' · <span style="color:#f87171">Нужно лечение</span>' : " · ✓ Здорова"}
                ${u.leveled_up ? ' · <span style="color:#4ade80">⭐ Новый уровень!</span>' : ""}
              </div>
            </div>
            <div class="exp-result-unit-bar">
              <div class="exp-result-unit-bar-fill" style="width:${hpPct}%"></div>
            </div>
          </div>`;
      })
      .join("");
  }

  const itemsWrap = document.getElementById("exp-result-items-wrap");
  const itemsEl = document.getElementById("exp-result-items");
  if (result.items_earned?.length > 0 && itemsWrap && itemsEl) {
    itemsEl.innerHTML = result.items_earned
      .map((item) => `<div class="exp-result-item">${item.emoji || "🎁"} ${escapeHtml(item.name || "—")}</div>`)
      .join("");
    itemsWrap.style.display = "block";
  } else if (itemsWrap) {
    itemsWrap.style.display = "none";
  }
}

function closeExpeditionResult() {
  const modal = document.getElementById("expedition-result-modal");
  if (modal) modal.style.display = "none";
  loadExpeditionTab?.();
  loadProfile?.catch(() => {});
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
  const btn = document.getElementById("expedition-admin-refresh");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳";
  }
  try {
    await apiFetch("/admin/expeditions/refresh", { method: "POST" });
    await loadExpeditionTab();
  } catch (e) {
    const msg = (e && e.message) || parseHttpErrorDetail(e).detail || "Ошибка обновления слотов";
    showToast("Ошибка обновления: " + msg, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🔄";
    }
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
    }, 15000);
  } else {
    if (gdSessionRefreshTimer) {
      clearInterval(gdSessionRefreshTimer);
      gdSessionRefreshTimer = null;
    }
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
  shopState.sellSort = ["level", "rarity", "equipability"].includes(value) ? value : "equipability";
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
  bankPageSize: 16,
  selectedBankItem: null,
  depositSelectedIds: [],
  memberPreviewView: "portrait",
  memberPreviewData: null,
  raidParticipantIds: [],
  warTargets: null,
};

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
  const emblemBtn = document.getElementById("guild-hero-emblem");
  const emblemInner = document.getElementById("guild-hero-emblem-inner");
  const fileInp = document.getElementById("guild-icon-file-input");
  const bar = formatGuildGxpBar(d);
  const canEditIcon = d.is_leader || d.is_officer;
  if (tagEl) tagEl.textContent = `[${d.guild_tag || ""}]`;
  if (nameEl) nameEl.textContent = d.guild_name || "—";
  if (levelEl) levelEl.textContent = `Ур. гильдии ${d.guild_level ?? "—"}`;
  if (xpFill) xpFill.style.width = `${bar.pct}%`;
  if (xpLabel) xpLabel.textContent = bar.label;
  const iconUrl = d.guild_icon_url
    ? d.guild_icon_url.startsWith("http")
      ? d.guild_icon_url
      : d.guild_icon_url
    : "";
  if (emblemInner) {
    if (iconUrl) {
      emblemInner.innerHTML = `<img src="${escapeHtml(iconUrl)}" alt="" />`;
    } else {
      emblemInner.textContent = "🏛️";
    }
  }
  if (emblemBtn) {
    emblemBtn.classList.toggle("guild-hero-emblem--readonly", !canEditIcon);
    emblemBtn.onclick = canEditIcon ? () => onGuildEmblemClick() : null;
  }
  if (fileInp) {
    fileInp.onchange = () => uploadGuildIcon(fileInp);
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
      <div class="guild-stat-card">
        <div class="guild-stat-label">Участники</div>
        <div class="guild-stat-val">${members.length} <span class="guild-stat-sub">/ ${slots}</span></div>
      </div>
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

function renderGuildActivityFeed(d) {
  const feed = Array.isArray(d?.activity_feed) ? d.activity_feed : [];
  if (!feed.length) {
    return `
      <div class="guild-section-label">Активность</div>
      <p class="muted tiny" style="margin-bottom:18px">Пока нет событий.</p>`;
  }
  const items = feed
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
    .join("");
  return `<div class="guild-section-label">Активность</div><div class="guild-activity-list">${items}</div>`;
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
    return `<div class="guild-member-row">
      <span class="guild-member-dot ${dotCls}" aria-hidden="true"></span>
      <button type="button" class="guild-member-preview-btn" onclick="WaifuApp.openGuildMemberPreviewModal(${Number(m.player_id)})">${guildMemberLabel(m)}</button>
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

function fillGuildBankOfferModal(item) {
  const offer = item;
  const contentEl = document.getElementById("guild-bank-offer-modal-content");
  const nameEl = document.getElementById("guild-bank-offer-modal-name");
  const subEl = document.getElementById("guild-bank-offer-modal-subline");
  const rpill = document.getElementById("guild-bank-offer-modal-rpill");
  const art = document.getElementById("guild-bank-offer-modal-art");
  const body = document.getElementById("guild-bank-offer-modal-body");
  const upHint = document.getElementById("guild-bank-offer-modal-upgrade-hint");
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
  const reqSec = document.getElementById("guild-bank-offer-modal-req-section");
  const reqFoot = document.getElementById("guild-bank-offer-modal-requirements");
  const mw = profileState.currentProfile?.main_waifu || null;
  const pillsHtml = buildItemModalRequirementsPillsHtml(offer, mw);
  if (reqFoot) reqFoot.innerHTML = pillsHtml;
  if (reqSec) reqSec.style.display = pillsHtml ? "" : "none";
  const descEl = document.getElementById("guild-bank-offer-modal-desc");
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

function openGuildBankGoldModal() {
  const d = guildHallState.me;
  const bal = document.getElementById("guild-bank-gold-modal-balance");
  const pl = document.getElementById("guild-bank-gold-modal-player");
  if (bal) bal.textContent = String(d?.bank_gold ?? 0);
  if (pl) pl.textContent = String(guildHallState.profileGold ?? 0);
  const m = document.getElementById("guild-bank-gold-modal");
  if (m) {
    m.style.display = "flex";
    m.setAttribute("aria-hidden", "false");
  }
}

function closeGuildBankGoldModal() {
  const m = document.getElementById("guild-bank-gold-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
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
    showToast("Золото положено в банк");
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

async function openGuildBankDepositModal() {
  try {
    const eq = await apiFetch("/waifu/equipment");
    const inv = (Array.isArray(eq?.inventory) ? eq.inventory : []).filter((i) => i?.id);
    guildHallState.depositSelectedIds = [];
    const list = document.getElementById("guild-bank-deposit-list");
    if (!list) return;
    if (!inv.length) {
      list.innerHTML = `<p class="muted tiny">Нет предметов для вложения (только неэкипированные).</p>`;
    } else {
      list.innerHTML = inv
        .map((it) => {
          const iid = Number(it.id);
          return `<label class="guild-bank-deposit-row" data-id="${iid}">
            <input type="checkbox" value="${iid}" onchange="WaifuApp.toggleGuildBankDepositSelect(${iid}, this.checked)" />
            <span class="guild-bank-cell-art">${itemArtHtml(it)}</span>
            <span class="guild-bank-cell-meta">${composeItemDisplayName(it)}</span>
          </label>`;
        })
        .join("");
    }
    const m = document.getElementById("guild-bank-deposit-modal");
    if (m) {
      m.style.display = "flex";
      m.setAttribute("aria-hidden", "false");
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить инвентарь", "error");
  }
}

function toggleGuildBankDepositSelect(id, checked) {
  const n = Number(id);
  const set = new Set(guildHallState.depositSelectedIds.map(Number));
  if (checked) set.add(n);
  else set.delete(n);
  guildHallState.depositSelectedIds = [...set];
  document.querySelectorAll(".guild-bank-deposit-row").forEach((row) => {
    const rid = Number(row.dataset.id);
    row.classList.toggle("selected", set.has(rid));
  });
}

function closeGuildBankDepositModal() {
  const m = document.getElementById("guild-bank-deposit-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
}

async function confirmGuildBankDeposit() {
  const ids = guildHallState.depositSelectedIds;
  if (!ids.length) {
    showToast("Выберите предметы", "error");
    return;
  }
  let ok = 0;
  for (const iid of ids) {
    try {
      const res = await apiFetch(`/guilds/deposit/item?inventory_item_id=${encodeURIComponent(iid)}`, {
        method: "POST",
      });
      if (!res?.error) ok += 1;
    } catch {
      /* continue */
    }
  }
  showToast(ok ? `Вложено предметов: ${ok}` : "Не удалось вложить", ok ? "success" : "error");
  closeGuildBankDepositModal();
  await populateGuildHall();
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
  const canUp =
    d?.is_leader &&
    cur < 3 &&
    safeInt(d?.guild_level, 1) >= safeInt(sk.guild_level_req, 1) &&
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

function closeGuildMemberPreviewModal() {
  const m = document.getElementById("guild-member-preview-modal");
  if (m) {
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }
  guildHallState.memberPreviewData = null;
}

function setGuildMemberPreviewView(view) {
  guildHallState.memberPreviewView = view === "paperdoll" ? "paperdoll" : "portrait";
  renderGuildMemberPreviewBody();
  document.querySelectorAll(".guild-member-preview-view-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === guildHallState.memberPreviewView);
  });
}

function renderGuildMemberPreviewBody() {
  const body = document.getElementById("guild-member-preview-body");
  const data = guildHallState.memberPreviewData;
  if (!body || !data) return;
  const mw = data.main_waifu;
  const view = guildHallState.memberPreviewView;
  const url =
    view === "paperdoll" && mw?.paperdoll_url
      ? mw.paperdoll_url
      : mw?.portrait_url || null;
  const portraitHtml = url
    ? `<div class="guild-member-preview-portrait"><img src="${escapeHtml(url)}" alt="" /></div>`
    : `<div class="guild-member-preview-portrait guild-member-preview-portrait--empty">Нет изображения</div>`;
  const un = (data.telegram_username || "").trim();
  const nameLine = un ? `@${escapeHtml(un)}` : escapeHtml(data.first_name || "Участник");
  const waifuBlock = mw
    ? `<p class="guild-member-preview-waifu-name"><strong>${escapeHtml(mw.name || "—")}</strong> · ур. ${mw.level ?? "—"}</p>
       <p class="muted tiny">${escapeHtml(raceName(mw.race))} · ${escapeHtml(className(mw.class ?? mw.class_))}</p>`
    : `<p class="muted tiny">Основная вайфу не создана.</p>`;
  const toggles =
    mw?.paperdoll_url && mw?.portrait_url
      ? `<div class="guild-member-preview-view-toggle">
          <button type="button" class="guild-member-preview-view-btn ${view === "portrait" ? "active" : ""}" data-view="portrait" onclick="WaifuApp.setGuildMemberPreviewView('portrait')">Портрет</button>
          <button type="button" class="guild-member-preview-view-btn ${view === "paperdoll" ? "active" : ""}" data-view="paperdoll" onclick="WaifuApp.setGuildMemberPreviewView('paperdoll')">Paperdoll</button>
        </div>`
      : "";
  body.innerHTML = `${toggles}${portraitHtml}<p>${nameLine}</p>${waifuBlock}`;
}

async function openGuildMemberPreviewModal(playerId) {
  try {
    const data = await apiFetch(`/guilds/members/${encodeURIComponent(playerId)}/preview`);
    guildHallState.memberPreviewData = data;
    guildHallState.memberPreviewView = "portrait";
    const title = document.getElementById("guild-member-preview-title");
    const un = (data.telegram_username || "").trim();
    if (title) title.textContent = un ? `@${un}` : data.first_name || "Участник";
    renderGuildMemberPreviewBody();
    const m = document.getElementById("guild-member-preview-modal");
    if (m) {
      m.style.display = "flex";
      m.setAttribute("aria-hidden", "false");
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || "Не удалось загрузить профиль", "error");
  }
}

function onGuildEmblemClick() {
  const d = guildHallState.me;
  if (!d?.is_leader && !d?.is_officer) {
    showToast("Эмблему меняют глава или офицер", "error");
    return;
  }
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
  const defs = Array.isArray(d?.definitions) ? d.definitions : [];
  const byTier = {};
  defs.forEach((sk) => {
    const t = safeInt(sk.tier, 1);
    if (!byTier[t]) byTier[t] = [];
    byTier[t].push(sk);
  });
  const tiers = Object.keys(byTier)
    .map(Number)
    .sort((a, b) => a - b);
  const avail = safeInt(d?.skill_points_available, 0);
  let html = `<p class="muted tiny">ОПГ: ${safeInt(d?.skill_points_spent, 0)} / ${safeInt(d?.skill_points_total, 0)} (доступно ${avail})</p>`;
  if (d?.is_leader) {
    html += `<button type="button" class="btn secondary" style="margin:8px 0" onclick="WaifuApp.guildSkillReset()">Сбросить навыки</button>`;
  }
  tiers.forEach((tier) => {
    html += `<div class="guild-skill-tier"><h4 class="guild-skill-tier-title">Тир ${tier}</h4><div class="guild-skills-grid">`;
    byTier[tier].forEach((sk) => {
      const cur = safeInt(sk.current_level, 0);
      const cost = cur === 0 ? safeInt(sk.cost_sp, 1) : safeInt(sk.cost_per_upgrade, 1);
      const canUp =
        d?.is_leader &&
        cur < 3 &&
        safeInt(d?.guild_level, 1) >= safeInt(sk.guild_level_req, 1) &&
        avail >= cost;
      const upBtn = canUp
        ? `<button type="button" class="btn tiny primary" onclick="event.stopPropagation();WaifuApp.guildSkillUpgrade(${Number(sk.id)})">+1 ОПГ</button>`
        : "";
      html += `<button type="button" class="guild-skill-cell section" onclick="WaifuApp.openGuildSkillModal(${Number(sk.id)})">
        <div class="guild-skill-cell-meta"><strong>${escapeHtml(sk.name || "")}</strong>
        <span class="muted tiny">ур. ${cur}/3 · треб. гильдия ${sk.guild_level_req}</span></div>
        <div class="guild-skill-cell-actions">${upBtn}</div>
      </button>`;
    });
    html += `</div></div>`;
  });
  return html;
}

function renderGuildBankTab(d) {
  const maxItems = safeInt(d?.max_bank_items, 100);
  const count = safeInt(d?.bank_items_count, 0);
  const page = Math.max(1, guildHallState.bankPage);
  const pageSize = guildHallState.bankPageSize;
  const items = guildHallState.bankItems;
  const start = (page - 1) * pageSize;
  const slice = items.slice(start, start + pageSize);
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  let grid = "";
  if (!slice.length) {
    grid = `<p class="muted tiny">Банк пуст.</p>`;
  } else {
    grid = `<div class="guild-bank-grid">${slice
      .map(
        (it) => `<button type="button" class="guild-bank-cell" onclick="WaifuApp.openGuildBankItemModal(${Number(it.bank_item_id)})">
          <span class="guild-bank-cell-art">${itemArtHtml(it)}</span>
          <span class="guild-bank-cell-meta">${composeItemDisplayName(it)}</span>
        </button>`
      )
      .join("")}</div>`;
  }
  const pager =
    totalPages > 1
      ? `<div style="display:flex;gap:8px;align-items:center;margin-top:8px">
          <button type="button" class="btn secondary" ${page <= 1 ? "disabled" : ""} onclick="WaifuApp.guildBankPrevPage()">‹</button>
          <span class="muted tiny">${page} / ${totalPages}</span>
          <button type="button" class="btn secondary" ${page >= totalPages ? "disabled" : ""} onclick="WaifuApp.guildBankNextPage()">›</button>
        </div>`
      : "";
  return `
    <div class="guild-bank-toolbar">
      <button type="button" class="guild-bank-gold-hit" onclick="WaifuApp.openGuildBankGoldModal()">🪙 ${safeInt(d?.bank_gold, 0)} · предметы ${count}/${maxItems}</button>
      <button type="button" class="btn secondary" onclick="WaifuApp.openGuildBankDepositModal()">Положить</button>
    </div>
    ${grid}
    ${pager}`;
}

function guildBankPrevPage() {
  guildHallState.bankPage = Math.max(1, guildHallState.bankPage - 1);
  void renderGuildTabContent();
}

function guildBankNextPage() {
  guildHallState.bankPage += 1;
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
      ${renderGuildActivityFeed(d)}
      <div class="guild-section-label">Участники</div>
      ${renderGuildMembersHtml(d.members)}
      ${
        !d.is_leader
          ? `<button type="button" class="btn secondary" style="margin-top:12px" onclick="WaifuApp.leaveGuildFromHall()">Покинуть гильдию</button>`
          : ""
      }`;
    return;
  }

  if (tab === "skills") {
    root.innerHTML = `<h3>Навыки гильдии</h3>${renderGuildSkillsGrid(d)}`;
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
    root.innerHTML = `<h3>Банк гильдии</h3>${renderGuildBankTab(d)}`;
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
  root.innerHTML = `<p class="muted tiny">Загрузка…</p>`;
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
      document.getElementById("guild-member-preview-close")?.addEventListener("click", closeGuildMemberPreviewModal);
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

/** Фон и портрет торговца по акту (см. static/game/ui/shop/README.md). */
function applyShopStageImages(currentAct) {
  const a = Math.max(1, Math.min(5, safeInt(currentAct, 1)));
  const bgImg = document.getElementById("shop-bg-img");
  const merchantImg = document.getElementById("shop-merchant-img");
  const fallback = document.querySelector(".shop-merchant-visual .fallback");

  const bgUrls = [
    `${SHOP_STATIC_BASE}/act-${a}/shop.background.webp`,
    `${SHOP_STATIC_BASE}/bg_act${a}.webp`,
    `${SHOP_STATIC_BASE}/background.webp`,
  ];
  const merchantUrls = [
    `${SHOP_STATIC_BASE}/act-${a}/merchant.webp`,
    `${SHOP_STATIC_BASE}/merchant_act${a}.webp`,
    `${SHOP_STATIC_BASE}/merchant.webp`,
  ];

  if (bgImg) {
    bgImg.style.display = "";
    attachCaravanImage(bgImg, bgUrls, null);
  }

  if (merchantImg) {
    merchantImg.style.display = "";
    if (fallback) fallback.style.display = "none";
    attachCaravanImage(merchantImg, merchantUrls, () => {
      merchantImg.style.display = "none";
      if (fallback) fallback.style.display = "";
    });
  }
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
  if (et === "trade_flat" || et === "nth_hit_crit") {
    if (et === "nth_hit_crit") return Math.max(1, Math.round(out));
    return Math.round(out);
  }
  return out;
}

/** Форматирование одного значения эффекта (для тултипа и шкалы уровней). */
function formatPassiveEffectValue(effectType, raw) {
  if (raw == null || raw === undefined) return "—";
  if (effectType === "trade_flat" || effectType === "nth_hit_crit") return String(raw);
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
  loadTavern,
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
  dismissTavernWaifu,
  closeTavernSlotModal,
  openAddToSquadPicker,
  closeSquadPickerModal,
  pickForSquad,
  adminRefreshTavern,
  refreshTavernPage,
  toggleTavernBgmMuted,
  loadDungeons,
  handleSoloDungeonTileClick,
  startDungeon,
  loadActiveDungeon,
  continueActiveDungeon,
  exitDungeon,
  openExitDungeonConfirm,
  onMonsterImageLoad,
  onMonsterImageError,
  closeExitDungeonConfirm,
  confirmExitDungeon,
  adminExitDungeon,
  loadBattle,
  continueBattle,
  exitBattle,
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
  showTab,
  loadExpeditionTab,
  populateProfile,
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
  closeShopGambleResultModal,
  loadSkills,
  searchGuilds,
  populateGuildHall,
  switchGuildTab,
  switchGuildActivityTab,
  createGuildFromHall,
  joinGuildFromSearch,
  leaveGuildFromHall,
  runGuildSearch,
  openGuildBankGoldModal,
  closeGuildBankGoldModal,
  confirmGuildBankGoldDeposit,
  confirmGuildBankGoldTake,
  openGuildBankDepositModal,
  closeGuildBankDepositModal,
  toggleGuildBankDepositSelect,
  confirmGuildBankDeposit,
  openGuildBankItemModal,
  closeGuildBankItemModal,
  confirmGuildBankTake,
  guildBankPrevPage,
  guildBankNextPage,
  openGuildSkillModal,
  closeGuildSkillModal,
  guildSkillUpgrade,
  guildSkillReset,
  openGuildMemberPreviewModal,
  closeGuildMemberPreviewModal,
  setGuildMemberPreviewView,
  onGuildEmblemClick,
  uploadGuildIcon,
  toggleGuildRaidParticipant,
  startGuildRaid,
  leaveGuildRaid,
  loadGuildWarTargetsForUi,
  declareGuildWar,
  respondGuildWar,
  apiFetch,
  getInitData,
  spendStatPoint,
  populateDungeonsPage,
  refreshSoloActive,
  closeRewardModal,
  viewRewardItem,
  loadExpeditionTab,
  submitExpeditionStart,
  expSelDiff,
  expSelDur,
  expPickUnit,
  expClosePicker,
  closeActiveExpModal,
  closeSendExpModal,
  abortExpedition,
  getAvailableUnits,
  claimExpedition,
  openExpeditionResult,
  closeExpeditionResult,
  cancelExpedition,
  adminRefreshExpeditions,
  openExpeditionHelp,
  closeExpeditionHelp,
  populateCaravanPage,
  travelToAct,
  openCaravanModal,
  closeCaravanModal,
  confirmTravelToAct,
  requestCaravanDriverTip,
  closeCaravanTipModal,
});
