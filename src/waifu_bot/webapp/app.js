// Basic Telegram WebApp bootstrap + shared UI helpers + API/SSE wiring
const tg = window.Telegram?.WebApp;
const API_BASE = "/api";

const RACES = [
  { id: 1, name: "Человек" },
  { id: 2, name: "Эльф" },
  { id: 3, name: "Зверолюд" },
  { id: 4, name: "Ангел" },
  { id: 5, name: "Вампир" },
  { id: 6, name: "Демон" },
  { id: 7, name: "Фея" },
];

const CLASSES = [
  { id: 1, name: "Рыцарь" },
  { id: 2, name: "Воин" },
  { id: 3, name: "Лучник" },
  { id: 4, name: "Маг" },
  { id: 5, name: "Ассассин" },
  { id: 6, name: "Лекарь" },
  { id: 7, name: "Торговец" },
];

const RACE_BONUSES = {
  1: {},
  2: { agility: 2, intelligence: 2, luck: 1 },
  3: { strength: 2, agility: 2, endurance: 1 },
  4: { charm: 2, intelligence: 1, luck: 1 },
  5: { strength: 1, endurance: 2, charm: 1, luck: 1 },
  6: { strength: 2, intelligence: 1, luck: 1 },
  7: { agility: 2, charm: 2, luck: 2 },
};

const CLASS_BONUSES = {
  1: { strength: 2, endurance: 2 },
  2: { strength: 2, agility: 1, endurance: 1 },
  3: { agility: 3, luck: 1 },
  4: { intelligence: 3, luck: 1 },
  5: { agility: 2, strength: 1, luck: 1 },
  6: { intelligence: 2, charm: 2 },
  7: { charm: 2, luck: 2 },
};

const BASE_STATS = {
  strength: 10,
  agility: 10,
  intelligence: 10,
  endurance: 10,
  charm: 10,
  luck: 10,
};

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
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (err) {
    console.debug("Failed to parse JSON", err, text);
    throw new Error(`HTTP ${res.status}: invalid JSON`);
  }
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? "—";
}

function formatNumber(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  try {
    return new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 }).format(number);
  } catch (err) {
    console.debug("formatNumber failed", err);
    return String(value);
  }
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
function connectSSE() {
  const initData = getInitData();
  if (!initData) return;
  if (sse) sse.close();
  const url = `${API_BASE}/sse/stream?initData=${encodeURIComponent(initData)}`;
  sse = new EventSource(url);
  sse.onmessage = (ev) => appendEvent(ev.data);
  sse.onerror = () => {
    appendEvent("SSE connection lost, retrying...");
    setTimeout(connectSSE, 3000);
  };
}

async function loadProfile() {
  const initData = getInitData();
  const qs = initData ? `?initData=${encodeURIComponent(initData)}` : "";
  const profile = await apiFetch(`/profile${qs}`);
  setText("badge-act", profile.act);
  setText("city-act", profile.act);
  setText("badge-gold", formatNumber(profile.gold));
  if (profile.main_waifu) {
    setText("badge-energy", `${profile.main_waifu.energy}/${profile.main_waifu.max_energy}`);
    setText("badge-level", profile.main_waifu.level);
    setText("waifu-name", profile.main_waifu.name || "—");
    setText("profile-name", profile.main_waifu.name || "—");
    setText("profile-level", profile.main_waifu.level);
    setText("profile-energy", `${profile.main_waifu.energy}/${profile.main_waifu.max_energy}`);
    setText("profile-class-race", `${getClassName(profile.main_waifu.class)} / ${getRaceName(profile.main_waifu.race)}`);
    setText(
      "profile-hp",
      `${profile.main_waifu.current_hp || "-"} / ${profile.main_waifu.max_hp || "-"}`
    );
    setText(
      "profile-hp-details",
      `${profile.main_waifu.current_hp || "-"} / ${profile.main_waifu.max_hp || "-"}`
    );
  } else {
    setText("badge-energy", "—");
    setText("badge-level", "—");
    setText("waifu-name", "—");
    setText("profile-name", "—");
    setText("profile-level", "—");
    setText("profile-energy", "—");
    setText("profile-class-race", "—");
    setText("profile-hp", "—");
    setText("profile-hp-details", "—");
  }
  window.__lastProfile = profile;
  renderProfileStats(profile);
  renderProfileStatsCompact(profile);
  renderProfileGear();

  const details = profile.main_waifu_details || {};
  setText("profile-dmg-melee", details.melee_damage);
  setText("profile-dmg-ranged", details.ranged_damage);
  setText("profile-dmg-magic", details.magic_damage);
  setText("profile-crit-chance", details.crit_chance !== undefined ? `${details.crit_chance}%` : "—");
  setText("profile-defense", details.defense);
  setText(
    "profile-merchant-discount",
    details.merchant_discount !== undefined ? `${details.merchant_discount}%` : "—"
  );
  return profile;
}

async function loadShop(act) {
  const data = await apiFetch(`/shop/inventory?act=${act}`);
  const grid = document.getElementById("shop-items");
  if (!grid) return data;
  grid.innerHTML = "";
  data.items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "list-item";
    card.innerHTML = `<strong>${item.name}</strong><br/><span class="muted">tier ${item.tier} · lvl ${item.level} · rarity ${item.rarity}</span>`;
    grid.appendChild(card);
  });
  return data;
}

async function loadTavern() {
  const data = await apiFetch("/tavern/available");
  const list = document.getElementById("tavern-available");
  if (!list) return data;
  list.innerHTML = "";
  data.waifus.forEach((w) => {
    const li = document.createElement("div");
    li.className = "list-item";
    li.innerHTML = `<strong>${w.name}</strong> — редк. ${w.rarity}, ур. ${w.level}, класс ${w.class}`;
    list.appendChild(li);
  });
  setText("tavern-count", data.count);
  return data;
}

async function loadDungeons(act) {
  const data = await apiFetch(`/dungeons?act=${act}`);
  const list = document.getElementById("dungeon-list");
  if (!list) return data;
  list.innerHTML = "";
  data.dungeons.forEach((d) => {
    const li = document.createElement("div");
    li.className = "list-item";
    li.innerHTML = `<strong>${d.name}</strong> — акт ${d.act}, ур. ${d.level}, тип ${d.dungeon_type}
      <div><button onclick="WaifuApp.startDungeon(${d.id})">Старт</button></div>`;
    list.appendChild(li);
  });
  return data;
}

async function startDungeon(dungeonId) {
  const res = await apiFetch(`/dungeons/${dungeonId}/start`, { method: "POST" });
  appendEvent(`Данж ${dungeonId} стартован: ${res.monster_name} HP ${res.monster_hp}`);
  await loadActiveDungeon();
}

async function loadActiveDungeon() {
  const data = await apiFetch("/dungeons/active");
  const box = document.getElementById("dungeon-active");
  if (!box) return data;
  box.innerHTML = data
    ? `<div class="list-item"><strong>${data.dungeon_name}</strong><br/>Монстр: ${data.current_monster || "-"} HP ${data.monster_hp || "-"} / ${data.monster_max_hp || "-"}</div>`
    : '<div class="muted">Активного данжа нет</div>';
  return data;
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
}

async function bootstrapPage(page, afterProfile) {
  try {
    const profile = await loadProfile();
    const hasMain = !!profile.main_waifu;
    console.debug("[bootstrapPage]", { page, hasMain, main: profile.main_waifu });
    if (!hasMain && page !== "waifu_generator") {
      window.location.href = "./waifu_generator.html";
      return;
    }
    if (hasMain && page === "waifu_generator") {
      window.location.href = "./index.html";
      return;
    }
    if (afterProfile) {
      await afterProfile(profile);
    }
  } catch (err) {
    console.error(err);
    alert(err.message || "Ошибка загрузки профиля");
  }
}

function computeStats(raceId, classId) {
  const stats = { ...BASE_STATS };
  const race = RACE_BONUSES[raceId] || {};
  const cls = CLASS_BONUSES[classId] || {};
  Object.entries(race).forEach(([k, v]) => (stats[k] = (stats[k] || 0) + v));
  Object.entries(cls).forEach(([k, v]) => (stats[k] = (stats[k] || 0) + v));
  return stats;
}

function renderStats(stats) {
  const box = document.getElementById("waifu-stats");
  if (!box) return;
  const labels = {
    strength: "СИЛ",
    agility: "ЛОВ",
    intelligence: "ИНТ",
    endurance: "ВЫН",
    charm: "ОБА",
    luck: "УДЧ",
  };
  box.innerHTML = "";
  Object.entries(labels).forEach(([key, label]) => {
    const val = stats[key] ?? "-";
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<span class="muted">${label}</span><strong>${val}</strong>`;
    box.appendChild(div);
  });
}

function renderStartKit(classId) {
  const box = document.getElementById("waifu-start-kit");
  if (!box) return;
  const data = {
    1: ["Щит и меч (базовые)", "Тяжёлая броня (обычная)", "Пассивка: Стойкость"],
    2: ["Двуручное оружие (базовое)", "Средняя броня", "Пассивка: Ярость"],
    3: ["Лук (базовый)", "Лёгкая броня", "Пассивка: Меткий глаз"],
    4: ["Посох (базовый)", "Одеяние", "Пассивка: Мана-поток"],
    5: ["Парные клинки (базовые)", "Лёгкая броня", "Пассивка: Удар в тень"],
    6: ["Жезл (базовый)", "Одеяние", "Пассивка: Свет исцеления"],
    7: ["Кинжал и кошель", "Лёгкая броня", "Пассивка: Торговая хватка"],
  };
  box.classList.remove("placeholder");
  box.classList.add("list", "compact");
  box.innerHTML = "";
  (data[classId] || ["Стартовый набор будет добавлен позже."]).forEach((item) => {
    const li = document.createElement("div");
    li.className = "list-item";
    li.textContent = item;
    box.appendChild(li);
  });
}

function getRaceName(id) {
  return RACES.find((r) => r.id === id)?.name || "—";
}

function getClassName(id) {
  return CLASSES.find((c) => c.id === id)?.name || "—";
}

function renderSummary(name, raceId, classId) {
  const el = document.getElementById("waifu-summary");
  if (!el) return;
  const race = getRaceName(raceId);
  const cls = getClassName(classId);
  el.textContent = `${name || "Имя"} · ${cls} · ${race}`;
}

function renderProfileStats(profile) {
  const box = document.getElementById("profile-stats");
  if (!box) return;
  box.innerHTML = "";
  const labels = {
    strength: "СИЛ",
    agility: "ЛОВ",
    intelligence: "ИНТ",
    endurance: "ВЫН",
    charm: "ОБА",
    luck: "УДЧ",
  };
  Object.entries(labels).forEach(([key, label]) => {
    const val = profile?.main_waifu ? profile.main_waifu[key] : "—";
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<span class="muted">${label}</span><strong>${val ?? "—"}</strong>`;
    box.appendChild(div);
  });
  setText(
    "profile-hp",
    profile?.main_waifu
      ? `${profile.main_waifu.current_hp || "-"} / ${profile.main_waifu.max_hp || "-"}`
      : "—"
  );
}

function renderProfileGear() {
  const box = document.getElementById("profile-gear");
  if (!box) return;
  const slots = [
    { key: "weapon_1", name: "Оружие 1", icon: "⚔️" },
    { key: "weapon_2", name: "Оружие 2", icon: "🗡️" },
    { key: "costume", name: "Костюм", icon: "🛡️" },
    { key: "ring_1", name: "Кольцо 1", icon: "💍" },
    { key: "ring_2", name: "Кольцо 2", icon: "💍" },
    { key: "amulet", name: "Амулет", icon: "📿" },
  ];

  const equipment = (window.__lastProfile?.main_waifu?.equipment) || [];
  const equipmentBySlot = {};
  equipment.forEach((item) => {
    if (item.slot) equipmentBySlot[item.slot] = item;
  });

  box.innerHTML = "";
  slots.forEach((slot) => {
    const data = equipmentBySlot[slot.key];
    const div = document.createElement("div");
    div.className = "slot-card";
    if (!data) {
      div.innerHTML = `<span>${slot.icon} ${slot.name}</span><span class="muted">пусто</span>`;
    } else {
      const rarityMap = {
        1: "common",
        2: "uncommon",
        3: "rare",
        4: "epic",
        5: "legendary",
      };
      const rarityClass = rarityMap[data.rarity] || "common";
      const dmg =
        data.damage_min !== undefined && data.damage_max !== undefined
          ? `${data.damage_min}-${data.damage_max}`
          : null;
      const atkSpeed = data.attack_speed ? ` · скор. атаки ${data.attack_speed}` : "";
      const atkType = data.attack_type ? ` · тип атаки ${data.attack_type}` : "";
      const weaponType = data.weapon_type ? ` · тип оружия ${data.weapon_type}` : "";
      const tier = data.tier ? ` · tier ${data.tier}` : "";
      const level = data.level ? ` · ур. ${data.level}` : "";

      const affixes =
        data.affixes && data.affixes.length
          ? data.affixes.map((a) => `${a.stat || a.name || "—"}: ${a.value}`).join("<br/>")
          : "Без аффиксов";

      div.innerHTML = `
        <div class="gear-item">
          <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;">
            <span>${slot.icon} ${slot.name}</span>
            <span class="rarity ${rarityClass}">${data.name || "Предмет"}</span>
          </div>
          <div class="muted tiny">
            ${[dmg, atkSpeed, atkType, weaponType, level, tier].filter(Boolean).join(" ")}
          </div>
          <div class="affixes">${affixes}</div>
        </div>
      `;
    }
    box.appendChild(div);
  });
}

function renderProfileStatsCompact(profile) {
  const box = document.getElementById("profile-stats-compact");
  if (!box) return;
  box.innerHTML = "";
  const labels = {
    strength: "СИЛ",
    agility: "ЛОВ",
    intelligence: "ИНТ",
    endurance: "ВЫН",
    charm: "ОБА",
    luck: "УДЧ",
  };
  Object.entries(labels).forEach(([key, label]) => {
    const val = profile?.main_waifu ? profile.main_waifu[key] : "—";
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<span class="muted">${label}</span><strong>${val ?? "—"}</strong>`;
    box.appendChild(div);
  });
}

function switchProfileTab(tab) {
  document.querySelectorAll(".tab").forEach((el) => {
    if (el.dataset.tab === tab) el.classList.add("active");
    else el.classList.remove("active");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    if (panel.id === `tab-${tab}`) panel.classList.add("active");
    else panel.classList.remove("active");
  });
}

function updateGeneratorState() {
  const nameInput = document.getElementById("waifu-name-input");
  const classSelect = document.getElementById("waifu-class-select");
  const raceSelect = document.getElementById("waifu-race-select");
  const button = document.getElementById("waifu-create-btn");
  if (!nameInput || !classSelect || !raceSelect || !button) return;
  const race = Number(raceSelect.value);
  const cls = Number(classSelect.value);
  const stats = computeStats(race, cls);
  renderStats(stats);
  renderStartKit(cls);
  renderSummary(nameInput.value.trim(), race, cls);
  const valid = nameInput.value.trim().length > 0 && race && cls;
  button.disabled = !valid;
}

async function initWaifuGenerator() {
  const raceSelect = document.getElementById("waifu-race-select");
  const classSelect = document.getElementById("waifu-class-select");
  if (raceSelect && raceSelect.options.length === 0) {
    RACES.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r.id;
      opt.textContent = r.name;
      raceSelect.appendChild(opt);
    });
  }
  if (classSelect && classSelect.options.length === 0) {
    CLASSES.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      classSelect.appendChild(opt);
    });
  }
  ["waifu-name-input", "waifu-class-select", "waifu-race-select"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", updateGeneratorState);
    if (el && el.tagName === "SELECT") el.addEventListener("change", updateGeneratorState);
  });
  updateGeneratorState();
}

async function submitWaifuCreation() {
  const name = document.getElementById("waifu-name-input")?.value.trim();
  const race = Number(document.getElementById("waifu-race-select")?.value);
  const cls = Number(document.getElementById("waifu-class-select")?.value);
  const errorEl = document.getElementById("waifu-create-error");
  if (errorEl) errorEl.textContent = "";
  if (!name || !race || !cls) {
    if (errorEl) errorEl.textContent = "Заполните имя, расу и класс.";
    return;
  }
  const payload = { name, race, class: cls };
  try {
    await apiFetch("/profile/main-waifu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    window.location.href = "./index.html";
  } catch (err) {
    console.error(err);
    if (errorEl) errorEl.textContent = err.message || "Не удалось создать вайфу";
    else alert(err.message || "Не удалось создать вайфу");
  }
}

async function resetMainWaifu() {
  if (!confirm("Сбросить основную вайфу и создать заново?")) return;
  try {
    const initData = getInitData();
    const qs = initData ? `?initData=${encodeURIComponent(initData)}` : "";
    await apiFetch(`/profile/main-waifu${qs}`, { method: "DELETE" });
    window.location.href = "./waifu_generator.html";
  } catch (err) {
    console.error(err);
    // Если вайфу уже нет или сервер вернул 404/409, всё равно отправим на генератор
    if (String(err).includes("404") || String(err).includes("409")) {
      window.location.href = "./waifu_generator.html";
      return;
    }
    alert(err.message || "Не удалось сбросить вайфу");
  }
}

// Expose helpers globally for inline usage
window.WaifuApp = {
  initPage,
  loadProfile,
  bootstrapPage,
  loadShop,
  loadTavern,
  loadDungeons,
  startDungeon,
  loadActiveDungeon,
  loadSkills,
  searchGuilds,
  apiFetch,
  getInitData,
  initWaifuGenerator,
  submitWaifuCreation,
  resetMainWaifu,
  switchProfileTab,
  populateProfile: renderProfileStats,
};
