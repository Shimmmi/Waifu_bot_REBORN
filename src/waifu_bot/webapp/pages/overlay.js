"use strict";

/**
 * Steam desktop client companion overlay (overlay.html).
 *
 * Self-contained on purpose: does NOT depend on app.js or the webapp bundle.
 * Shows the player's main waifu persistently (always-on-top transparent
 * window, see desktop_client/src/windows/overlayWindow.js) with:
 *   - portrait + HP + resources (gold/dust) from GET /api/profile?lite=1
 *   - monster strip from GET /api/dungeons/active while a dungeon is running
 *   - hamburger menu opening other webapp pages as draggable desktop windows
 *     via window.waifuDesktop.openTab()
 *   - a CSS animation state machine driven by local input activity
 *     (window.waifuDesktop.onInputActivity, IPC from the uiohook tracker in
 *     the Electron main process) and dungeon state:
 *
 *       AFK  + no dungeon  -> state-sleep          (waifu sleeps)
 *       AFK  + dungeon     -> state-sleep-dungeon  (waifu AND monster sleep)
 *       active + dungeon   -> state-battle         (hit lunges on every click,
 *                                                   ahead of server damage)
 *       active + no dungeon-> state-idle           (random cute micro-emotes)
 *       waifu HP = 0       -> state-dead           (grayscale + halo, priority)
 *       waifu HP < 25%     -> is-lowhp             (red pulse, additive)
 */

(function () {
  const AFK_AFTER_MS = 60_000; // no local input for this long => AFK
  const POLL_DUNGEON_ACTIVE_MS = 10_000; // active player: keep monster fresh
  const POLL_DUNGEON_AFK_MS = 60_000;
  const POLL_PROFILE_MS = 60_000;
  const IDLE_EMOTE_MIN_MS = 6_000;
  const IDLE_EMOTE_MAX_MS = 16_000;
  const LOW_HP_FRACTION = 0.25;

  const IDLE_EMOTES = ["💖", "🎵", "✨", "🌸", "☕", "📖", "🧶", "🍰"];

  const MONSTER_STATIC_BASE = "/static/game/monsters";

  // ── Auth (mirrors app.js authHeaders(), desktop subset) ────────────────
  function authHeaders() {
    const headers = {};
    try {
      const params = new URLSearchParams(window.location.search);
      const devPid = params.get("devPlayerId");
      const real = window.waifuDesktop?.getSteamTicket?.();
      const devStub =
        window.waifuDesktop?.steamTicketDev || params.get("steamTicketDev");
      if (real) headers["X-Steam-Ticket"] = String(real);
      else if (devPid) headers["X-Player-Id"] = String(devPid);
      else if (devStub) headers["X-Steam-Ticket-Dev"] = String(devStub);
    } catch {
      /* ignore */
    }
    return headers;
  }

  async function apiFetch(path) {
    const res = await fetch(`/api${path}`, { headers: authHeaders() });
    if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
    return res.json();
  }

  // ── DOM refs ────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const root = $("ov-root");
  const el = {
    gold: $("ov-gold"),
    dust: $("ov-dust"),
    stones: $("ov-stones"),
    menuBtn: $("ov-menu-btn"),
    menu: $("ov-menu"),
    monster: $("ov-monster"),
    monsterImg: $("ov-monster-img"),
    monsterName: $("ov-monster-name"),
    monsterHpFill: $("ov-monster-hp-fill"),
    monsterHpText: $("ov-monster-hp-text"),
    monsterHitFx: $("ov-monster-hitfx"),
    scene: $("ov-scene"),
    portraitWrap: $("ov-portrait-wrap"),
    portrait: $("ov-portrait"),
    portraitFallback: $("ov-portrait-fallback"),
    idleEmote: $("ov-idle-emote"),
    fx: $("ov-fx"),
    waifuName: $("ov-waifu-name"),
    waifuHpFill: $("ov-waifu-hp-fill"),
    waifuHpText: $("ov-waifu-hp-text"),
    status: $("ov-status"),
  };

  // ── State ───────────────────────────────────────────────────────────────
  const state = {
    lastInputAt: Date.now(),
    dungeon: null, // last /dungeons/active payload (or {active:false})
    waifu: { name: null, hp: null, maxHp: null },
    dead: false,
    currentClass: "state-loading",
    idleEmoteTimer: null,
  };

  function isAfk() {
    return Date.now() - state.lastInputAt > AFK_AFTER_MS;
  }

  function dungeonActive() {
    return Boolean(state.dungeon && state.dungeon.active);
  }

  // ── HP bars ─────────────────────────────────────────────────────────────
  function setBar(fillEl, textEl, cur, max) {
    const c = Math.max(0, Number(cur) || 0);
    const m = Math.max(1, Number(max) || 1);
    fillEl.style.width = `${Math.min(100, (c / m) * 100)}%`;
    textEl.textContent = `${c}/${m}`;
  }

  function setWaifuHp(cur, max) {
    if (cur == null || max == null) return;
    state.waifu.hp = Number(cur);
    state.waifu.maxHp = Number(max);
    setBar(el.waifuHpFill, el.waifuHpText, cur, max);
    state.dead = state.waifu.hp <= 0;
    root.classList.toggle(
      "is-lowhp",
      !state.dead && state.waifu.maxHp > 0 && state.waifu.hp / state.waifu.maxHp < LOW_HP_FRACTION
    );
    applyState();
  }

  function setMonsterHp(cur, max) {
    if (cur == null || max == null) return;
    setBar(el.monsterHpFill, el.monsterHpText, cur, max);
  }

  // ── Animation state machine ─────────────────────────────────────────────
  function computeStateClass() {
    if (state.dead) return "state-dead";
    if (isAfk()) return dungeonActive() ? "state-sleep-dungeon" : "state-sleep";
    return dungeonActive() ? "state-battle" : "state-idle";
  }

  function applyState() {
    const next = computeStateClass();
    if (next === state.currentClass) return;
    root.classList.remove(
      "state-loading",
      "state-sleep",
      "state-sleep-dungeon",
      "state-battle",
      "state-idle",
      "state-dead"
    );
    root.classList.add(next);
    state.currentClass = next;
    if (next === "state-idle") scheduleIdleEmote();
    else stopIdleEmotes();
  }

  // ── Idle micro-emotes (random cute animations) ──────────────────────────
  function stopIdleEmotes() {
    if (state.idleEmoteTimer) clearTimeout(state.idleEmoteTimer);
    state.idleEmoteTimer = null;
  }

  function scheduleIdleEmote() {
    stopIdleEmotes();
    const delay =
      IDLE_EMOTE_MIN_MS + Math.random() * (IDLE_EMOTE_MAX_MS - IDLE_EMOTE_MIN_MS);
    state.idleEmoteTimer = setTimeout(() => {
      if (state.currentClass === "state-idle") {
        el.idleEmote.textContent =
          IDLE_EMOTES[Math.floor(Math.random() * IDLE_EMOTES.length)];
        el.idleEmote.classList.remove("play");
        void el.idleEmote.offsetWidth; // restart CSS animation
        el.idleEmote.classList.add("play");
        // Occasionally add a little hop to the portrait too.
        if (Math.random() < 0.5) {
          el.portraitWrap.classList.remove("hop");
          void el.portraitWrap.offsetWidth;
          el.portraitWrap.classList.add("hop");
        }
      }
      scheduleIdleEmote();
    }, delay);
  }

  // ── Battle hit FX (responsive, ahead of real server damage) ─────────────
  let hitCooldownUntil = 0;
  function playHitAnimation() {
    // Small cooldown so key-mashing doesn't restart the animation every 10ms.
    const now = Date.now();
    if (now < hitCooldownUntil) return;
    hitCooldownUntil = now + 120;
    el.portraitWrap.classList.remove("lunge");
    void el.portraitWrap.offsetWidth;
    el.portraitWrap.classList.add("lunge");
    if (dungeonActive()) {
      el.monsterHitFx.classList.remove("flash");
      void el.monsterHitFx.offsetWidth;
      el.monsterHitFx.classList.add("flash");
    }
  }

  function showDamageNumber(damage, isCrit) {
    const span = document.createElement("span");
    span.className = `ov-dmg${isCrit ? " crit" : ""}`;
    span.textContent = `-${damage}`;
    el.fx.appendChild(span);
    setTimeout(() => span.remove(), 1200);
  }

  // ── Data loading ────────────────────────────────────────────────────────
  function setPortrait(url) {
    if (!url) {
      el.portrait.style.display = "none";
      el.portraitFallback.style.display = "";
      return;
    }
    if (el.portrait.getAttribute("src") === url) return;
    el.portrait.onload = () => {
      el.portrait.style.display = "";
      el.portraitFallback.style.display = "none";
    };
    el.portrait.onerror = () => {
      el.portrait.style.display = "none";
      el.portraitFallback.style.display = "";
    };
    el.portrait.src = url;
  }

  async function loadProfile() {
    try {
      const profile = await apiFetch("/profile?lite=1");
      el.gold.textContent = `💰 ${profile.gold ?? 0}`;
      el.dust.textContent = `✨ ${profile.enchant_dust ?? 0}`;
      el.stones.textContent = `🪨 ${profile.protection_stones ?? 0}`;
      const mw = profile.main_waifu;
      if (mw) {
        state.waifu.name = mw.name || "Вайфу";
        el.waifuName.textContent = state.waifu.name;
        setPortrait(mw.portrait_url || null);
        setWaifuHp(mw.current_hp, mw.max_hp);
        el.status.textContent = "";
      } else {
        el.waifuName.textContent = "Нет вайфу";
        el.status.textContent = "Создайте персонажа в основном окне";
        setPortrait(null);
      }
      applyState();
    } catch (err) {
      el.status.textContent = "Нет связи с сервером";
      console.warn("[overlay] profile load failed:", err.message);
    }
  }

  function monsterImageUrls(d) {
    const family = d.monster_family || "unknown";
    const slug = d.monster_slug || "unknown";
    const tier = d.monster_tier || 1;
    return [
      `${MONSTER_STATIC_BASE}/${family}/${slug}.webp`,
      `${MONSTER_STATIC_BASE}/${family}/_family_t${tier}.webp`,
      `${MONSTER_STATIC_BASE}/${family}/_family.webp`,
      `${MONSTER_STATIC_BASE}/_unknown.webp`,
    ];
  }

  function setMonsterImage(d) {
    const urls = monsterImageUrls(d);
    let i = 0;
    el.monsterImg.onerror = () => {
      i += 1;
      if (i < urls.length) el.monsterImg.src = urls[i];
      else el.monsterImg.onerror = null;
    };
    if (el.monsterImg.getAttribute("src") !== urls[0]) el.monsterImg.src = urls[0];
  }

  async function loadDungeon() {
    try {
      const d = await apiFetch("/dungeons/active");
      const wasActive = dungeonActive();
      state.dungeon = d;
      if (d && d.active) {
        el.monster.classList.remove("hidden");
        el.monsterName.textContent = d.monster_name || "Монстр";
        setMonsterHp(d.monster_current_hp, d.monster_max_hp);
        setMonsterImage(d);
        if (d.waifu_current_hp != null) setWaifuHp(d.waifu_current_hp, d.waifu_max_hp);
      } else {
        el.monster.classList.add("hidden");
        if (wasActive) loadProfile(); // dungeon just ended: refresh gold/HP
      }
      applyState();
    } catch (err) {
      console.warn("[overlay] dungeon load failed:", err.message);
    }
  }

  // ── Menu ────────────────────────────────────────────────────────────────
  function toggleMenu(force) {
    const show = force != null ? force : el.menu.classList.contains("hidden");
    el.menu.classList.toggle("hidden", !show);
    el.menu.setAttribute("aria-hidden", show ? "false" : "true");
  }

  el.menuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMenu();
  });
  document.addEventListener("click", () => toggleMenu(false));
  el.menu.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-page]");
    if (!btn) return;
    e.stopPropagation();
    const page = btn.dataset.page;
    if (window.waifuDesktop?.openTab) {
      window.waifuDesktop.openTab(page);
    } else {
      window.open(`./${page}${window.location.search}`, "_blank");
    }
    toggleMenu(false);
  });

  // ── IPC wiring (desktop client only) ────────────────────────────────────
  // Global input activity: instant hit animation + AFK reset. Emitted by the
  // Electron main process from the same uiohook hook that feeds the damage
  // batcher, throttled there (~100ms) — see desktop_client/src/main.js.
  if (window.waifuDesktop?.onInputActivity) {
    window.waifuDesktop.onInputActivity(() => {
      state.lastInputAt = Date.now();
      if (state.currentClass === "state-battle") playHitAnimation();
      applyState();
    });
  }

  // Server-confirmed damage batches: authoritative HP + floating damage text.
  if (window.waifuDesktop?.onHitBatchSent) {
    window.waifuDesktop.onHitBatchSent((payload) => {
      const r = payload && payload.result;
      if (!r || typeof r !== "object") return;
      const inner = r.result && typeof r.result === "object" ? r.result : r;
      if (inner.monster_hp != null && inner.monster_max_hp != null) {
        setMonsterHp(inner.monster_hp, inner.monster_max_hp);
      }
      if (inner.waifu_current_hp != null && inner.waifu_max_hp != null) {
        setWaifuHp(inner.waifu_current_hp, inner.waifu_max_hp);
      }
      if (inner.damage != null && Number(inner.damage) > 0) {
        showDamageNumber(inner.damage, Boolean(inner.is_crit));
      }
      if (inner.monster_defeated || inner.dungeon_completed) {
        // Monster/dungeon transition: re-pull authoritative state promptly.
        setTimeout(loadDungeon, 500);
      }
      if (inner.error === "no_active_battle" && dungeonActive()) {
        loadDungeon();
      }
    });
  }

  // Browser fallback (no Electron IPC): local mouse/keyboard on the page
  // itself still counts as activity so the state machine works in dev.
  for (const evt of ["mousedown", "keydown"]) {
    window.addEventListener(evt, () => {
      state.lastInputAt = Date.now();
      if (state.currentClass === "state-battle") playHitAnimation();
      applyState();
    });
  }

  // ── Polling loops ───────────────────────────────────────────────────────
  function scheduleDungeonPoll() {
    const interval = isAfk() ? POLL_DUNGEON_AFK_MS : POLL_DUNGEON_ACTIVE_MS;
    setTimeout(async () => {
      await loadDungeon();
      scheduleDungeonPoll();
    }, interval);
  }

  setInterval(loadProfile, POLL_PROFILE_MS);
  setInterval(applyState, 5_000); // AFK transition even with zero events

  // ── Boot ────────────────────────────────────────────────────────────────
  (async function boot() {
    await loadProfile();
    await loadDungeon();
    applyState();
    scheduleDungeonPoll();
  })();
})();
