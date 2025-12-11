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
  return res.json();
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function appendEvent(text) {
  const log = document.getElementById("event-log");
  if (log) {
    const div = document.createElement("div");
    div.textContent = text;
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
  setText("badge-gold", profile.gold);
  if (profile.main_waifu) {
    setText("badge-energy", `${profile.main_waifu.energy}/${profile.main_waifu.max_energy}`);
  }
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

async function initPage(page) {
  applyTheme();
  if (tg) {
    tg.ready();
    tg.expand();
  }
  setActiveNav(page);
  connectSSE();
}

// Expose helpers globally for inline usage
window.WaifuApp = { initPage, loadProfile, loadShop, loadTavern, apiFetch, getInitData };
