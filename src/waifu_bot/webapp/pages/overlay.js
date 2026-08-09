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
  const POLL_EQUIPPED_VISUALS_MS = 12_000;
  const IDLE_EMOTE_MIN_MS = 6_000;
  const IDLE_EMOTE_MAX_MS = 16_000;
  const LOW_HP_FRACTION = 0.25;
  const MONSTER_ATTACK_INTERVAL_MS = 8_000;
  const STATUS_TOAST_DELAY_MS = 30_000;
  const STATUS_TOAST_VISIBLE_MS = 3_000;

  const STATUS_REASON_LABELS = {
    spam_detected: "Слишком быстро",
    no_active_battle: "Нет активного боя",
    no_waifu: "Нет вайфу",
    no_monster: "Нет монстра",
    batch_capped: "Лимит пакета",
  };


  const IDLE_ACTIONS = [
    { id: "stretch", emoji: "🙆" },
    { id: "yawn", emoji: "🥱" },
    { id: "wave", emoji: "👋" },
    { id: "read", emoji: "📖" },
    { id: "tea", emoji: "☕" },
  ];

  const MONSTER_STATIC_BASE = "/static/game/monsters";
  const MONSTER_PLACEHOLDER = "/static/game/overlay/placeholder/monster.webp";

  // Steam tab windows use dedicated layouts under webapp/steam/.
  const STEAM_PAGE_MAP = {
    "profile.html": "steam/profile.html",
    "dungeons.html": "steam/dungeons.html",
    "shop.html": "steam/shop.html",
    "waifu_generator.html": "steam/waifu_generator.html",
    "login.html": "steam/login.html",
  };

  function resolveSteamPage(page) {
    return STEAM_PAGE_MAP[page] || page;
  }

  function authHeaders() {
    const headers = {};
    try {
      const params = new URLSearchParams(window.location.search);
      const session =
        window.waifuDesktop?.getDesktopSessionToken?.() ||
        (typeof localStorage !== "undefined" ? localStorage.getItem("waifuDesktopSession") : null);
      const devPid = params.get("devPlayerId");
      const real = window.waifuDesktop?.getSteamTicket?.();
      const devStub =
        window.waifuDesktop?.steamTicketDev || params.get("steamTicketDev");
      if (session) headers["X-Desktop-Session"] = String(session);
      else if (real) headers["X-Steam-Ticket"] = String(real);
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

  async function apiFetch(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = authHeaders();
    let lastErr;
    for (let attempt = 1; attempt <= 5; attempt += 1) {
      try {
        const res = await fetch(`/api${path}`, { method, headers });
        if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
        if (res.status === 204) return null;
        const text = await res.text();
        if (!text) return null;
        return JSON.parse(text);
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

  function openSteamPage(page) {
    const resolved = resolveSteamPage(page);
    if (window.waifuDesktop?.openTab) {
      window.waifuDesktop.openTab(resolved);
    } else {
      window.open(`./${resolved}${window.location.search}`, "_blank");
    }
  }

  function setResetWaifuVisible(show) {
    const btn = $("ov-reset-waifu");
    if (!btn) return;
    btn.hidden = !show;
    btn.classList.toggle("hidden", !show);
  }

  async function resetMainWaifuFromOverlay() {
    if (
      !confirm(
        "Удалить основную вайфу и начать создание заново? Инвентарь и прогресс сохранятся."
      )
    ) {
      return;
    }
    try {
      await apiFetch("/profile/main-waifu", { method: "DELETE" });
      openSteamPage("waifu_generator.html");
      await loadProfile();
    } catch (err) {
      console.warn("[overlay] reset waifu failed:", err.message);
      alert(err?.message || "Не удалось сбросить вайфу");
    }
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
    monsterTarget: $("ov-monster-target"),
    monsterTargetImg: $("ov-monster-target-img"),
    monsterTargetHitFx: $("ov-monster-target-hitfx"),
    monsterAttackFx: $("ov-monster-attack-fx"),
    scene: $("ov-scene"),
    portraitWrap: $("ov-portrait-wrap"),
    paperdoll: $("ov-paperdoll"),
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
    statusToast: $("ov-status-toast"),
  };

  const state = {
    lastInputAt: Date.now(),
    dungeon: null,
    abyss: null,
    combatMode: "none",
    weaponType: "unarmed",
    attackType: "melee",
    attackVariant: 0,
    waifu: { name: null, hp: null, maxHp: null, level: null },
    attackSpeed: 1,
    pendingClicks: 0,
    dead: false,
    currentClass: "state-loading",
    idleEmoteTimer: null,
    monsterAttackTimer: null,
    statusToastTimer: null,
    statusToastHideTimer: null,
    pendingStatusReason: null,
    paperdollCosmetics: null,
    equippedVisuals: null,
    usePaperdoll: false,
    skeletonRuntime: null,
  };

  function retriggerClass(node, className) {
    if (!node) return;
    node.classList.remove(className);
    void node.offsetWidth;
    node.classList.add(className);
  }

  function syncPortraitCombatMeta() {
    if (!el.portraitWrap) return;
    el.portraitWrap.dataset.weaponType = state.weaponType || "unarmed";
    el.portraitWrap.dataset.attackType = state.attackType || "melee";
    el.portraitWrap.dataset.combatMode = state.combatMode || "none";
    if (el.paperdoll) {
      el.paperdoll.dataset.weaponType = state.weaponType || "unarmed";
      el.paperdoll.dataset.attackType = state.attackType || "melee";
      el.paperdoll.dataset.combatMode = state.combatMode || "none";
    }
  }

  function ensureSkeletonRuntime() {
    if (!el.paperdoll || !window.RoPaperdollSkeleton) return null;
    if (!state.skeletonRuntime) {
      state.skeletonRuntime = window.RoPaperdollSkeleton.createRuntime(el.paperdoll);
    }
    return state.skeletonRuntime;
  }

  function refreshPaperdollLayers() {
    const Comp = window.RoPaperdollCompositor;
    if (!el.paperdoll || !Comp || !state.usePaperdoll || !state.paperdollCosmetics) {
      return false;
    }
    const ok = Comp.renderOverlayPaperdoll(el.paperdoll, {
      cosmetics: state.paperdollCosmetics,
      raceId: state.paperdollCosmetics.race,
      equippedVisuals: state.equippedVisuals,
      showWeapon: combatActive(),
    });
    if (ok) {
      el.paperdoll.hidden = false;
      if (el.portrait) el.portrait.style.display = "none";
      if (el.portraitFallback) el.portraitFallback.style.display = "none";
      const rt = ensureSkeletonRuntime();
      if (rt) {
        rt.start();
        const mode =
          state.currentClass === "state-dead"
            ? "dead"
            : state.currentClass === "state-sleep"
              ? "sleep"
              : state.currentClass === "state-sleep-dungeon"
                ? "sleep_dungeon"
                : state.currentClass === "state-battle"
                  ? "battle"
                  : "idle";
        rt.setMode(mode);
      }
    }
    return ok;
  }

  function soloCombatActive() {
    return Boolean(state.dungeon && state.dungeon.active);
  }

  function abyssCombatActive() {
    return Boolean(
      state.abyss &&
        state.abyss.session_active &&
        state.abyss.current_monster
    );
  }

  function combatActive() {
    return soloCombatActive() || abyssCombatActive();
  }

  function dungeonActive() {
    return combatActive();
  }

  function syncCombatTargetUi() {
    const show = combatActive();
    root.classList.toggle("has-combat-target", show);
    if (el.monsterTarget) el.monsterTarget.classList.toggle("hidden", !show);
    if (el.monster) el.monster.classList.toggle("hidden", !show);
  }

  function isAfk() {
    return Date.now() - state.lastInputAt > AFK_AFTER_MS;
  }

  function resolveCombatMode() {
    if (soloCombatActive()) return "solo";
    if (abyssCombatActive()) return "abyss";
    return "none";
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

  function hideStatusToast() {
    if (state.statusToastHideTimer) {
      clearTimeout(state.statusToastHideTimer);
      state.statusToastHideTimer = null;
    }
    if (!el.statusToast) return;
    el.statusToast.textContent = "";
    el.statusToast.classList.remove("visible");
  }

  function cancelStatusToast() {
    if (state.statusToastTimer) {
      clearTimeout(state.statusToastTimer);
      state.statusToastTimer = null;
    }
    state.pendingStatusReason = null;
    hideStatusToast();
  }

  function showStatusToast(msg) {
    if (!el.statusToast || !msg) return;
    el.statusToast.textContent = msg;
    el.statusToast.classList.add("visible");
    if (state.statusToastHideTimer) clearTimeout(state.statusToastHideTimer);
    state.statusToastHideTimer = setTimeout(() => {
      hideStatusToast();
    }, STATUS_TOAST_VISIBLE_MS);
  }

  function scheduleStatusToast(reason) {
    if (!reason) return;
    state.pendingStatusReason = reason;
    if (state.statusToastTimer) clearTimeout(state.statusToastTimer);
    state.statusToastTimer = setTimeout(() => {
      state.statusToastTimer = null;
      if (state.pendingStatusReason !== reason) return;
      const label = STATUS_REASON_LABELS[reason] || reason;
      showStatusToast(label);
      state.pendingStatusReason = null;
    }, STATUS_TOAST_DELAY_MS);
  }

  function computeStateClass() {
    if (state.dead) return "state-dead";
    if (isAfk()) return dungeonActive() ? "state-sleep-dungeon" : "state-sleep";
    return dungeonActive() ? "state-battle" : "state-idle";
  }

  function applyState() {
    const next = computeStateClass();
    if (next === state.currentClass) {
      state.combatMode = resolveCombatMode();
      syncPortraitCombatMeta();
      syncCombatTargetUi();
      updateAttackChargeUi();
      if (state.usePaperdoll) refreshPaperdollLayers();
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
    state.combatMode = resolveCombatMode();
    syncPortraitCombatMeta();
    syncCombatTargetUi();
    updateAttackChargeUi();
    if (state.usePaperdoll) refreshPaperdollLayers();
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
        const action = IDLE_ACTIONS[Math.floor(Math.random() * IDLE_ACTIONS.length)];
        el.portraitWrap.dataset.idleAction = action.id;
        retriggerClass(el.portraitWrap, "idle-action-play");
        el.idleEmote.textContent = action.emoji;
        el.idleEmote.classList.remove("play");
        void el.idleEmote.offsetWidth;
        el.idleEmote.classList.add("play");
      }
      scheduleIdleEmote();
    }, delay);
  }

  function flashMonsterTarget() {
    if (!combatActive() || !el.monsterTargetHitFx) return;
    el.monsterTargetHitFx.classList.remove("flash");
    void el.monsterTargetHitFx.offsetWidth;
    el.monsterTargetHitFx.classList.add("flash");
  }

  function playAttackAnimation() {
    const variant = state.attackVariant % 2;
    state.attackVariant += 1;
    const key = `${state.combatMode}-${state.attackType}-${state.weaponType}-${variant}`;
    el.portraitWrap.dataset.attackAnim = key;
    el.portraitWrap.classList.remove("lunge", "attack-play", "charging");
    void el.portraitWrap.offsetWidth;
    el.portraitWrap.classList.add("attack-play", "lunge");
    if (state.usePaperdoll && state.skeletonRuntime) {
      state.skeletonRuntime.playAttack(state.attackType, state.weaponType);
    }
    flashMonsterTarget();
    updateAttackChargeUi();
  }

  function playHitAnimation() {
    playAttackAnimation();
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
    if (state.usePaperdoll && refreshPaperdollLayers()) {
      return;
    }
    if (el.paperdoll) {
      el.paperdoll.hidden = true;
      if (window.RoPaperdollCompositor) {
        window.RoPaperdollCompositor.clearOverlayPaperdoll(el.paperdoll);
      }
    }
    if (state.skeletonRuntime) {
      state.skeletonRuntime.stop();
    }
    if (!url) {
      el.portrait.style.display = "none";
      el.portraitFallback.style.display = "";
      return;
    }
    if (el.portrait.getAttribute("src") === url) {
      el.portrait.style.display = "";
      el.portraitFallback.style.display = "none";
      return;
    }
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

  function applyEquippedVisuals(ev) {
    state.equippedVisuals = ev && typeof ev === "object" ? ev : null;
    if (state.usePaperdoll) refreshPaperdollLayers();
  }

  async function loadProfile() {
    try {
      const profile = await apiFetch("/profile?lite=1");
      el.gold.textContent = `💰 ${profile.gold ?? 0}`;
      el.dust.textContent = `✨ ${profile.enchant_dust ?? 0}`;
      el.stones.textContent = `🪨 ${profile.protection_stones ?? 0}`;
      state.attackSpeed = profile.main_weapon_attack_speed ?? 1;
      state.weaponType = profile.main_weapon_type || "unarmed";
      state.attackType = profile.main_weapon_attack_type || "melee";
      applyEquippedVisuals(profile.equipped_visuals || null);
      syncPortraitCombatMeta();
      const mw = profile.main_waifu;
      if (mw) {
        state.waifu.name = mw.name || "Вайфу";
        el.waifuName.textContent = state.waifu.name;
        setWaifuLevel(mw.level);
        const cosmetics =
          mw.paperdoll_cosmetics && typeof mw.paperdoll_cosmetics === "object"
            ? mw.paperdoll_cosmetics
            : null;
        state.paperdollCosmetics = cosmetics;
        state.usePaperdoll = Boolean(mw.has_paperdoll_layers && cosmetics);
        setPortrait(mw.portrait_url || null);
        setWaifuHp(mw.current_hp, mw.max_hp);
      } else {
        el.waifuName.textContent = "Нет вайфу";
        el.waifuLevel.textContent = "";
        state.paperdollCosmetics = null;
        state.usePaperdoll = false;
        state.equippedVisuals = null;
        setPortrait(null);
      }
      setResetWaifuVisible(
        Boolean(profile?.is_admin || profile?.allow_waifu_recreate)
      );
      applyState();
    } catch (err) {
      console.warn("[overlay] profile load failed:", err.message);
    }
  }

  function monsterImageUrls(d) {
    const family = d.monster_family || d.family || "unknown";
    const slug = d.monster_slug || d.slug || "unknown";
    const tier = d.monster_tier || d.level || 1;
    return [
      `${MONSTER_STATIC_BASE}/${family}/${slug}.webp`,
      `${MONSTER_STATIC_BASE}/${family}/_family_t${tier}.webp`,
      `${MONSTER_STATIC_BASE}/${family}/_family.webp`,
      `${MONSTER_STATIC_BASE}/_unknown.webp`,
    ];
  }

  function setMonsterTargetImage() {
    if (!el.monsterTargetImg) return;
    el.monsterTargetImg.onerror = null;
    if (el.monsterTargetImg.getAttribute("src") !== MONSTER_PLACEHOLDER) {
      el.monsterTargetImg.src = MONSTER_PLACEHOLDER;
    }
  }

  function setMonsterStripImage(d) {
    if (!el.monsterImg) return;
    const urls = monsterImageUrls(d);
    let i = 0;
    el.monsterImg.onerror = () => {
      i += 1;
      if (i < urls.length) el.monsterImg.src = urls[i];
      else el.monsterImg.onerror = null;
    };
    if (el.monsterImg.getAttribute("src") !== urls[0]) el.monsterImg.src = urls[0];
  }

  function setMonsterImage(d) {
    setMonsterStripImage(d);
    setMonsterTargetImage();
  }

  async function loadDungeon() {
    try {
      const d = await apiFetch("/dungeons/active");
      const wasActive = soloCombatActive();
      state.dungeon = d;
      if (d && d.active) {
        el.monsterName.textContent = d.monster_name || "Монстр";
        setMonsterHp(d.monster_current_hp, d.monster_max_hp);
        setMonsterImage(d);
        if (d.waifu_current_hp != null) setWaifuHp(d.waifu_current_hp, d.waifu_max_hp);
      } else if (!abyssCombatActive()) {
        state.pendingClicks = 0;
        if (wasActive) loadProfile();
      }
      state.combatMode = resolveCombatMode();
      syncPortraitCombatMeta();
      syncCombatTargetUi();
      applyState();
    } catch (err) {
      console.warn("[overlay] dungeon load failed:", err.message);
    }
  }

  async function loadAbyss() {
    try {
      const a = await apiFetch("/abyss/status");
      state.abyss = a;
      if (!soloCombatActive() && a && a.session_active && a.current_monster) {
        const m = a.current_monster;
        el.monsterName.textContent = m.name || "Монстр";
        setMonsterHp(m.hp_current, m.hp_max);
        setMonsterImage({
          family: m.family,
          slug: m.slug,
          level: m.level,
        });
        if (a.waifu_hp != null && a.waifu_max_hp != null) {
          setWaifuHp(a.waifu_hp, a.waifu_max_hp);
        }
      }
      state.combatMode = resolveCombatMode();
      syncPortraitCombatMeta();
      syncCombatTargetUi();
      applyState();
    } catch (err) {
      console.warn("[overlay] abyss load failed:", err.message);
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
    const actionBtn = e.target.closest("button[data-action]");
    if (actionBtn) {
      e.stopPropagation();
      toggleMenu(false);
      if (actionBtn.dataset.action === "reset-waifu") {
        resetMainWaifuFromOverlay();
      }
      return;
    }
    const btn = e.target.closest("button[data-page]");
    if (!btn) return;
    e.stopPropagation();
    openSteamPage(btn.dataset.page);
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
        console.warn("[overlay] hit batch rejected:", rejected);
        scheduleStatusToast(rejected);
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
        cancelStatusToast();
        showDamageNumber(inner.damage, Boolean(inner.is_crit));
      }
      if (inner.waifu_damage != null && Number(inner.waifu_damage) > 0) {
        playMonsterAttackFx();
      }
      if (inner.monster_defeated || inner.dungeon_completed) {
        setTimeout(loadDungeon, 500);
      }
      if (inner.error === "no_active_battle" && combatActive()) {
        loadDungeon();
        loadAbyss();
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
      await loadAbyss();
      scheduleDungeonPoll();
    }, interval);
  }

  setInterval(loadProfile, POLL_PROFILE_MS);
  setInterval(() => {
    if (document.visibilityState === "visible") loadProfile();
  }, POLL_EQUIPPED_VISUALS_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") loadProfile();
  });
  setInterval(applyState, 5_000);

  (async function boot() {
    if (el.monsterTargetImg && !el.monsterTargetImg.getAttribute("src")) {
      el.monsterTargetImg.src = MONSTER_PLACEHOLDER;
    }
    await loadProfile();
    await loadDungeon();
    await loadAbyss();
    syncCombatTargetUi();
    applyState();
    scheduleDungeonPoll();
  })();
})();
