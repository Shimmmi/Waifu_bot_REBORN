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
  selectedWaifu: null,
  pendingHireSlot: null, // 1..4
  lastHiredResult: null, // result of last successful hire for result modal
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

function hiredWaifuNameLines(name) {
  const parts = String(name || "Наёмница").trim().split(/\s+/);
  if (parts.length <= 1) return { first: parts[0] || "Наёмница", last: "" };
  return { first: parts[0], last: parts.slice(1).join(" ") };
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
  const needsRoster = name === "heal" || name === "squad" || name === "upgrade";
  if (needsRoster) {
    ensureTavernRosterLoaded()
      .then(() => {
        if (name === "heal") renderTavernHealList();
        if (name === "squad") renderTavernSquad();
        if (name === "upgrade") renderTavernUpgradeList();
      })
      .catch(() => {});
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
    const { cur, max: maxHp } = hiredWaifuHp(w);
    return cur < maxHp;
  });
  if (wounded.length === 0) {
    container.innerHTML = '<p class="muted" style="font-style:italic;">Нет раненых наёмниц.</p>';
    container.className = "placeholder muted";
    return;
  }
  container.className = "tavern-heal-grid";
  container.innerHTML = wounded
    .map((w) => {
      const { cur, max: maxHp } = hiredWaifuHp(w);
      const need = maxHp - cur;
      const mult = cur === 0 ? 2 : 1;
      const cost = need * TAVERN_HEAL_GOLD_PER_HP * mult;
      const pct = maxHp > 0 ? Math.round((cur / maxHp) * 100) : 0;
      const portrait = hiredWaifuImageUrl(w);
      const portraitHtml = portrait
        ? `<img src="${escapeHtml(portrait)}" alt="">`
        : `<span aria-hidden="true">🛡️</span>`;
      return `
        <div class="tavern-heal-card" data-waifu-id="${w.id}" data-cost="${cost}" role="button" tabindex="0" aria-label="Лечить ${escapeHtml(w.name || "наёмницу")} за ${cost} золота">
          <div class="tavern-heal-card-portrait">${portraitHtml}</div>
          <div class="tavern-heal-card-hp">
            <div class="tavern-hp-bar-wrap"><div class="tavern-hp-bar" style="width:${pct}%"></div></div>
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

  container.querySelectorAll(".tavern-heal-card").forEach((card) => {
    card.addEventListener("click", () => healWaifu(card));
    card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        healWaifu(card);
      }
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
      const portraitInner = portrait
        ? `<img src="${escapeHtml(portrait)}" alt="">`
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
      const [availRes, squadRes, reserveRes] = await Promise.all([
        apiFetch("/tavern/available"),
        apiFetch("/tavern/squad"),
        apiFetch("/tavern/reserve"),
      ]);
      available = availRes;
      tavernState.squad = Array.isArray(squadRes?.squad) ? squadRes.squad : [];
      tavernState.reserve = Array.isArray(reserveRes?.reserve) ? reserveRes.reserve : [];
      tavernRosterLoaded = true;
    } else {
      available = await apiFetch("/tavern/available");
    }

    tavernState.available = available;
    const perksList = Array.isArray(available?.perks) ? available.perks : [];
    tavernState.perksMap = Object.fromEntries(perksList.map((x) => [x.id, x.name || x.id]));

    renderTavernHire(p, available);
    if (loadRoster) renderTavernSquad();

    if (!inner) {
      const pageBg = document.getElementById("tavern-page-bg");
      const url = pageBg?.currentSrc || pageBg?.src || "";
      preloadTavernBg(url);
    }
    loadOk = true;
    return { available, squad: tavernState.squad, reserve: tavernState.reserve };
  } finally {
    if (!inner) {
      setTavernPageLoading(false);
      syncTavernBgmMuteButton();
      if (loadOk && !isTavernBgmMuted()) {
        loadTavernBgmConfig().then(() => {
          syncTavernBgmPlayerUi();
          if (!isTavernBgmMuted()) startTavernBgm();
        });
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

    const rarity = Number(w?.rarity ?? 1);
    const rCls = rarityClass(rarity);
    const clsId = Number(w?.class ?? w?.class_ ?? 0);
    const raceId = Number(w?.race ?? 0);
    const { first, last } = hiredWaifuNameLines(w?.name);
    const meta = `${escapeHtml(raceName(raceId))} · ${escapeHtml(className(clsId))} · Ур.${escapeHtml(String(w?.level ?? "—"))} · Мощь ${escapeHtml(String(w?.power ?? "—"))}`;
    const perkIds = Array.isArray(w.perks) ? w.perks : [];
    const perkBadges = perkIds.length
      ? perkIds
          .map(
            (pid) =>
              `<span class="squad-mtg-perk-ico" title="${escapeHtml(String(perksMap[pid] || pid))}">${PERK_ICONS[pid] || "✦"}</span>`
          )
          .join("")
      : `<span class="muted tiny" style="opacity:.75;">—</span>`;

    const url = hiredWaifuImageUrl(w);
    const portraitLayer = url ? `<img class="squad-mtg-bg-img" src="${escapeHtml(url)}" alt="" />` : "";
    const bgCls = url ? "squad-mtg-bg" : "squad-mtg-bg squad-mtg-bg--placeholder";

    const uiSt = hiredWaifuPoolUiStatus(w);
    const statusCls = `squad-mtg-card--${uiSt.key}`;

    const slot = document.createElement("div");
    slot.className = "squad-slot occupied";
    slot.setAttribute("role", "button");
    slot.tabIndex = 0;
    slot.innerHTML = `
      <div class="squad-mtg-card ${rCls} ${statusCls}">
        <div class="${bgCls}" role="img" aria-label="">${portraitLayer}</div>
        <div class="squad-mtg-scrim-top" aria-hidden="true"></div>
        <div class="squad-mtg-scrim-bottom" aria-hidden="true"></div>
        <div class="squad-mtg-status-hatch" aria-hidden="true"></div>
        <div class="squad-mtg-top">
          <div class="squad-mtg-name-lines">
            <div class="squad-mtg-name-first">${escapeHtml(first)}</div>
            ${last ? `<div class="squad-mtg-name-last">${escapeHtml(last)}</div>` : ""}
          </div>
        </div>
        <div class="squad-mtg-bottom">
          <div class="squad-mtg-meta">${meta}</div>
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


Object.assign(window.WaifuApp, {
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
  openTavernDismissConfirm,
  closeTavernDismissConfirm,
  confirmTavernDismiss,
  dismissTavernWaifu,
  closeTavernSlotModal,
  openAddToSquadPicker,
  closeSquadPickerModal,
  pickForSquad,
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
