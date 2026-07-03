"use strict";

/**
 * Steam desktop client companion overlay (overlay.html).
 *
 * Self-contained on purpose: does NOT depend on app.js or the webapp bundle.
 */

(function () {
  const AFK_AFTER_MS = 60_000;
  const POLL_DUNGEON_ACTIVE_MS = 10_000;
  const POLL_DUNGEON_AFK_MS = 60_000;
  const POLL_PROFILE_MS = 60_000;
  const IDLE_EMOTE_MIN_MS = 6_000;
  const IDLE_EMOTE_MAX_MS = 16_000;
  const LOW_HP_FRACTION = 0.25;
  const MONSTER_ATTACK_INTERVAL_MS = 8_000;

  const IDLE_EMOTES = ["💖", "🎵", "✨", "🌸", "☕", "📖", "🧶", "🍰"];

  const MONSTER_STATIC_BASE = "/static/game/monsters";

  // Steam tab windows use dedicated layouts under webapp/steam/.
  const STEAM_PAGE_MAP = {
    "profile.html": "steam/profile.html",
    "dungeons.html": "steam/dungeons.html",
    "shop.html": "steam/shop.html",
  };

  function resolveSteamPage(page) {
    return STEAM_PAGE_MAP[page] || page;
  }

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

  function isFetchNetworkError(err) {
    if (!err) return false;
    return err.name === "TypeError" && /fetch|network|failed/i.test(String(err.message || ""));
  }

  async function apiFetch(path) {
    const headers = authHeaders();
    let lastErr;
    for (let attempt = 1; attempt <= 5; attempt += 1) {
      try {
        const res = await fetch(`/api${path}`, { headers });
        if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
        return res.json();
      } catch (err) {
        lastErr = err;
        if (attempt < 5 && isFetchNetworkError(err)) {
          await new Promise((r) => setTimeout(r, 400 + attempt * 300));
          continue;
        }
        throw err;
      }
    }
    throw lastErr;
  }

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
    monsterAttackFx: $("ov-monster-attack-fx"),
    scene: $("ov-scene"),
    portraitWrap: $("ov-portrait-wrap"),
    portrait: $("ov-portrait"),
    portraitFallback: $("ov-portrait-fallback"),
    idleEmote: $("ov-idle-emote"),
    fx: $("ov-fx"),
    waifuName: $("ov-waifu-name"),
    waifuLevel: $("ov-waifu-level"),
    waifuHpFill: $("ov-waifu-hp-fill"),
    waifuHpText: $("ov-waifu-hp-text"),
    attackCharge: $("ov-attack-charge"),
    attackChargeFill: $("ov-attack-charge-fill"),
    status: $("ov-status"),
  };

  const state = {
    lastInputAt: Date.now(),
    dungeon: null,
    waifu: { name: null, hp: null, maxHp: null, level: null },
    attackSpeed: 1,
    pendingClicks: 0,
    dead: false,
    currentClass: "state-loading",
    idleEmoteTimer: null,
    monsterAttackTimer: null,
    statusClearTimer: null,
  };

  function isAfk() {
    return Date.now() - state.lastInputAt > AFK_AFTER_MS;
  }

  function dungeonActive() {
    return Boolean(state.dungeon && state.dungeon.active);
  }

  function effectiveAttackSpeed() {
    const n = Number(state.attackSpeed);
    if (!Number.isFinite(n) || n < 1) return 1;
    return Math.min(10, Math.max(1, Math.floor(n)));
  }

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

  function updateAttackChargeUi() {
    if (!el.attackCharge || !el.attackChargeFill) return;
    const speed = effectiveAttackSpeed();
    const inBattle = state.currentClass === "state-battle";
    el.attackCharge.setAttribute("aria-hidden", inBattle ? "false" : "true");
    if (!inBattle) {
      el.attackChargeFill.style.width = "0%";
      return;
    }
    const pct = Math.min(100, (state.pendingClicks / speed) * 100);
    el.attackChargeFill.style.width = `${pct}%`;
    el.portraitWrap.classList.toggle("charging", state.pendingClicks > 0 && state.pendingClicks < speed);
  }

  function flashStatus(msg, ms = 2500) {
    if (!el.status) return;
    el.status.textContent = msg;
    if (state.statusClearTimer) clearTimeout(state.statusClearTimer);
    state.statusClearTimer = setTimeout(() => {
      if (el.status.textContent === msg) el.status.textContent = "";
    }, ms);
  }

  function computeStateClass() {
    if (state.dead) return "state-dead";
    if (isAfk()) return dungeonActive() ? "state-sleep-dungeon" : "state-sleep";
    return dungeonActive() ? "state-battle" : "state-idle";
  }

  function applyState() {
    const next = computeStateClass();
    if (next === state.currentClass) {
      updateAttackChargeUi();
      return;
    }
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
    if (next === "state-battle" || next === "state-sleep-dungeon") startMonsterAttackLoop();
    else stopMonsterAttackLoop();
    updateAttackChargeUi();
  }

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
        void el.idleEmote.offsetWidth;
        el.idleEmote.classList.add("play");
        if (Math.random() < 0.5) {
          el.portraitWrap.classList.remove("hop");
          void el.portraitWrap.offsetWidth;
          el.portraitWrap.classList.add("hop");
        }
      }
      scheduleIdleEmote();
    }, delay);
  }

  function playHitAnimation() {
    el.portraitWrap.classList.remove("lunge", "charging");
    void el.portraitWrap.offsetWidth;
    el.portraitWrap.classList.add("lunge");
    if (dungeonActive()) {
      el.monsterHitFx.classList.remove("flash");
      void el.monsterHitFx.offsetWidth;
      el.monsterHitFx.classList.add("flash");
    }
    updateAttackChargeUi();
  }

  function playMonsterAttackFx() {
    if (!el.monsterAttackFx || !dungeonActive()) return;
    el.monsterAttackFx.classList.remove("play");
    void el.monsterAttackFx.offsetWidth;
    el.monsterAttackFx.classList.add("play");
  }

  function startMonsterAttackLoop() {
    stopMonsterAttackLoop();
    if (!dungeonActive()) return;
    state.monsterAttackTimer = setInterval(() => {
      if (dungeonActive() && !state.dead && !isAfk()) playMonsterAttackFx();
    }, MONSTER_ATTACK_INTERVAL_MS);
  }

  function stopMonsterAttackLoop() {
    if (state.monsterAttackTimer) clearInterval(state.monsterAttackTimer);
    state.monsterAttackTimer = null;
  }

  function noteInputActivity() {
    state.lastInputAt = Date.now();
    if (state.currentClass === "state-battle") {
      state.pendingClicks += 1;
      const speed = effectiveAttackSpeed();
      updateAttackChargeUi();
      if (state.pendingClicks >= speed) {
        state.pendingClicks = 0;
        playHitAnimation();
      }
    } else if (state.currentClass === "state-idle") {
      playHitAnimation();
    }
    applyState();
  }

  function showDamageNumber(damage, isCrit) {
    const span = document.createElement("span");
    span.className = `ov-dmg${isCrit ? " crit" : ""}`;
    span.textContent = `-${damage}`;
    el.fx.appendChild(span);
    setTimeout(() => span.remove(), 1200);
  }

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

  function setWaifuLevel(level) {
    if (level == null) {
      el.waifuLevel.textContent = "";
      return;
    }
    state.waifu.level = Number(level);
    el.waifuLevel.textContent = `Lv.${state.waifu.level}`;
  }

  async function loadProfile() {
    try {
      const profile = await apiFetch("/profile?lite=1");
      el.gold.textContent = `💰 ${profile.gold ?? 0}`;
      el.dust.textContent = `✨ ${profile.enchant_dust ?? 0}`;
      el.stones.textContent = `🪨 ${profile.protection_stones ?? 0}`;
      state.attackSpeed = profile.main_weapon_attack_speed ?? 1;
      const mw = profile.main_waifu;
      if (mw) {
        state.waifu.name = mw.name || "Вайфу";
        el.waifuName.textContent = state.waifu.name;
        setWaifuLevel(mw.level);
        setPortrait(mw.portrait_url || null);
        setWaifuHp(mw.current_hp, mw.max_hp);
        if (!el.status.textContent || el.status.textContent === "Нет связи с сервером") {
          el.status.textContent = "";
        }
      } else {
        el.waifuName.textContent = "Нет вайфу";
        el.waifuLevel.textContent = "";
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
        state.pendingClicks = 0;
        if (wasActive) loadProfile();
      }
      applyState();
    } catch (err) {
      console.warn("[overlay] dungeon load failed:", err.message);
    }
  }

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
    const page = resolveSteamPage(btn.dataset.page);
    if (window.waifuDesktop?.openTab) {
      window.waifuDesktop.openTab(page);
    } else {
      window.open(`./${page}${window.location.search}`, "_blank");
    }
    toggleMenu(false);
  });

  if (window.waifuDesktop?.onInputActivity) {
    window.waifuDesktop.onInputActivity(() => noteInputActivity());
  }

  if (window.waifuDesktop?.onHitBatchSent) {
    window.waifuDesktop.onHitBatchSent((payload) => {
      const batch = payload && typeof payload === "object" ? payload : {};
      const api = batch.result && typeof batch.result === "object" ? batch.result : null;
      const rejected = api?.rejected_reason;
      if (batch.hitCount != null && batch.hitCount > 0 && rejected) {
        const reasonLabels = {
          spam_detected: "Слишком быстро",
          no_active_battle: "Нет активного боя",
          no_waifu: "Нет вайфу",
          no_monster: "Нет монстра",
          batch_capped: "Лимит пакета",
        };
        flashStatus(reasonLabels[rejected] || rejected, 2000);
      }
      const inner = api?.result && typeof api.result === "object" ? api.result : api;
      if (!inner || typeof inner !== "object") return;
      if (inner.monster_hp != null && inner.monster_max_hp != null) {
        setMonsterHp(inner.monster_hp, inner.monster_max_hp);
      }
      if (inner.waifu_current_hp != null && inner.waifu_max_hp != null) {
        setWaifuHp(inner.waifu_current_hp, inner.waifu_max_hp);
      }
      if (inner.damage != null && Number(inner.damage) > 0) {
        showDamageNumber(inner.damage, Boolean(inner.is_crit));
      }
      if (inner.waifu_damage != null && Number(inner.waifu_damage) > 0) {
        playMonsterAttackFx();
      }
      if (inner.monster_defeated || inner.dungeon_completed) {
        setTimeout(loadDungeon, 500);
      }
      if (inner.error === "no_active_battle" && dungeonActive()) {
        loadDungeon();
      }
    });
  }

  for (const evt of ["mousedown", "keydown"]) {
    window.addEventListener(evt, () => noteInputActivity());
  }

  function scheduleDungeonPoll() {
    const interval = isAfk() ? POLL_DUNGEON_AFK_MS : POLL_DUNGEON_ACTIVE_MS;
    setTimeout(async () => {
      await loadDungeon();
      scheduleDungeonPoll();
    }, interval);
  }

  setInterval(loadProfile, POLL_PROFILE_MS);
  setInterval(applyState, 5_000);

  (async function boot() {
    await loadProfile();
    await loadDungeon();
    applyState();
    scheduleDungeonPoll();
  })();
})();
