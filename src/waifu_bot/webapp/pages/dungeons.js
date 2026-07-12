/** Dungeons page bundle. */

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

let dungeonsFinishBlockedMsg = null;
let soloActiveMonsterTemplateId = null;
let soloActiveStoryBossId = null;
/** @type {object | null} Snapshot for incremental SSE battle updates */
let soloActiveSnapshot = null;
let soloHpRefetchTimer = null;

function scheduleSoloHpRefetch() {
  clearTimeout(soloHpRefetchTimer);
  soloHpRefetchTimer = setTimeout(() => {
    soloHpRefetchTimer = null;
    refreshSoloActive({ includeLog: false }).catch(() => {});
  }, 150);
}

function canUpdateSoloBattleHp() {
  if (soloActiveSnapshot) return true;
  const host = document.getElementById("solo-active");
  if (!host || host.style.display === "none") return false;
  const content = document.getElementById("solo-active-content");
  if (content && content.style.display === "none") return false;
  return true;
}

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
  const blockedByAbyss = Boolean(abyssState?.session_active);
  const canEnter =
    !blockedByAbyss &&
    !lockedByAct &&
    !lockedByPrev &&
    (pl > 0 ? !isPlusLocked : baseCanEnter);
  const act = safeInt(d?.act, 1);
  const dungeonNum = safeInt(d?.dungeon_number, 1);
  const dungeonArtBase = window.DUNGEONS_STATIC_BASE || "/static/game/dungeons";
  const artUrl = `${dungeonArtBase}/act-${act}/dungeon-${dungeonNum}.webp`;
  const lockedClass = canEnter ? "" : "locked";
  let lockReason = "";
  if (!canEnter) {
    if (blockedByAbyss) lockReason = "Сначала выйдите из Бездны";
    else if (lockedByAct) lockReason = "Акт не открыт";
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

  const abyssBanner = abyssState?.session_active
    ? `<div class="banner banner--abyss-active">🕳️ ОВ в Бездне — завершите спуск, чтобы начать соло-данж.</div>`
    : "";

  box.innerHTML = `
    ${abyssBanner}
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
  (typeof window !== "undefined" && window.APP_CONFIG?.staticBase) ||
  `${window.GAME_STATIC_BASE || "/static/game"}/monsters`;

if (typeof window !== "undefined") {
  window.monsterArtVersion = window.monsterArtVersion || {};
}

function globalMonsterArtCacheBust() {
  return (typeof window !== "undefined" && window.WAIFU_WEBAPP_VERSION) || null;
}

// Cache-bust version for a monster's generated art: prefer the freshest of the
// session-generated timestamp and the API's image_updated_at.
function monsterArtCacheBust(templateId, imageUpdatedAt) {
  let v = 0;
  try {
    const sess =
      templateId != null && window.monsterArtVersion
        ? window.monsterArtVersion[templateId]
        : 0;
    if (sess) v = Math.max(v, Number(sess) || 0);
  } catch (e) {
    /* monsterArtVersion may be undefined in isolation; ignore */
  }
  if (imageUpdatedAt) {
    const t = Date.parse(imageUpdatedAt);
    if (!Number.isNaN(t)) v = Math.max(v, t);
  }
  if (v > 0) return String(v);
  return globalMonsterArtCacheBust();
}

function buildMonsterImageUrls(family, slug, tier, imageOverride, version) {
  const ver = version || globalMonsterArtCacheBust();
  const q = ver ? `?v=${encodeURIComponent(ver)}` : "";
  if (imageOverride) {
    return [imageOverride, `${MONSTER_STATIC_BASE}/_unknown.webp${q}`];
  }
  return [
    `${MONSTER_STATIC_BASE}/${family}/${slug}.webp${q}`,
    `${MONSTER_STATIC_BASE}/${family}/_family_t${tier}.webp${q}`,
    `${MONSTER_STATIC_BASE}/${family}/_family.webp${q}`,
    `${MONSTER_STATIC_BASE}/_unknown.webp${q}`,
  ];
}

function loadMonsterImage(family, slug, tier, imageOverride, version) {
  const visual = document.getElementById("monster-visual");
  const img = document.getElementById("monster-img");
  const placeholder = document.getElementById("monster-placeholder");
  if (!visual || !img || !placeholder) return;

  const urls = buildMonsterImageUrls(family, slug, tier, imageOverride, version);
  img.dataset.fallbackUrls = JSON.stringify(urls);
  img.dataset.fallbackIndex = "0";

  img.classList.add("fading");
  placeholder.classList.add("visible");

  visual.dataset.family = family || "";
  visual.dataset.slug = slug || "";
  visual.dataset.tier = String(tier || 1);

  img.style.display = "";
  img.alt = `Монстр ${slug}`;
  const targetUrl = urls[0];
  // If the same URL is already loaded, onload may not refire — reveal it manually
  // so the emoji overlay does not stay stuck over a valid image.
  if (img.getAttribute("src") === targetUrl && img.complete && img.naturalWidth > 0) {
    onMonsterImageLoad(img);
    return;
  }
  img.src = targetUrl;
  if (img.complete && img.naturalWidth > 0) {
    onMonsterImageLoad(img);
  }
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
  const list = Array.isArray(entries) ? entries : [];
  const host = document.getElementById("solo-battle-log-host");
  if (host) {
    host.style.display = "none";
    host.innerHTML = "";
  }
  const btn = document.getElementById("battle-log-btn");
  const body = document.getElementById("battle-log-modal-body");
  if (!btn) return;
  if (!list.length) {
    btn.hidden = true;
    if (body) body.innerHTML = "";
    return;
  }
  btn.hidden = false;
  btn.title = `Журнал боя (${list.length})`;
  if (body) body.innerHTML = `<div class="solo-battle-log-inner">${buildSoloBattleLogHtml(list)}</div>`;
}

function openBattleLogModal() {
  const modal = document.getElementById("battle-log-modal");
  if (modal) modal.style.display = "grid";
}

function closeBattleLogModal() {
  const modal = document.getElementById("battle-log-modal");
  if (modal) modal.style.display = "none";
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

function flashSoloHitFeedback(payload) {
  const visual = document.getElementById("monster-visual");
  if (!visual) return;
  if (payload?.monster_dodged || payload?.solo_shock_skip) return;
  visual.classList.remove("solo-hit-flash");
  void visual.offsetWidth;
  visual.classList.add("solo-hit-flash");
  const dmg = payload?.damage;
  if (typeof dmg === "number" && dmg > 0) {
    const floater = document.createElement("span");
    floater.className = "solo-damage-float" + (payload.is_crit ? " solo-damage-float--crit" : "");
    floater.textContent = `-${dmg}`;
    visual.appendChild(floater);
    setTimeout(() => floater.remove(), 900);
  }
}

/**
 * Apply battle SSE payload to HP bars immediately (no API round-trip).
 * Returns true if solo-active UI was updated.
 */
function applySoloBattleSsePayload(payload) {
  if (!payload || typeof payload !== "object") return false;
  if (!canUpdateSoloBattleHp()) return false;

  const snap = soloActiveSnapshot || {};
  const hpMax = Math.max(
    1,
    safeNumber(payload.monster_max_hp ?? snap.monster_max_hp ?? snap.monster?.max_hp, 1)
  );
  const hpCur =
    payload.monster_hp != null
      ? safeNumber(payload.monster_hp, 0)
      : safeNumber(snap.monster_current_hp ?? snap.monster?.current_hp, 0);

  const waifuMax = Math.max(
    1,
    safeNumber(payload.waifu_max_hp ?? snap.waifu_max_hp ?? snap.waifu?.max_hp, 1)
  );
  let waifuCur =
    payload.waifu_current_hp != null
      ? safeNumber(payload.waifu_current_hp, 0)
      : safeNumber(snap.waifu_current_hp ?? snap.waifu?.current_hp, 0);
  if (payload.reflect_damage_taken > 0 && payload.waifu_current_hp == null && snap.waifu) {
    waifuCur = Math.max(0, safeNumber(snap.waifu.current_hp, 0) - safeNumber(payload.reflect_damage_taken, 0));
  }

  const damage = payload.damage != null ? safeNumber(payload.damage, null) : null;
  const isCrit = payload.is_crit === true;
  if (damage != null) {
    window._lastSoloDamage = damage;
    window._lastSoloCrit = isCrit;
    const dealtFromHp = Math.max(0, hpMax - hpCur);
    window._lastSoloDealt =
      dealtFromHp > 0
        ? dealtFromHp
        : damage > 0
          ? safeNumber(snap.damage_done ?? window._lastSoloDealt ?? 0, 0) + damage
          : safeNumber(snap.damage_done ?? window._lastSoloDealt ?? 0, 0);
  }

  const monster = {
    ...(snap.monster || {}),
    current_hp: hpCur,
    max_hp: hpMax,
    hp_known: snap.monster?.hp_known !== false,
    name_known: snap.monster?.name_known !== false,
    type_known: snap.monster?.type_known !== false,
  };
  const waifu = {
    ...(snap.waifu || { name: "—" }),
    current_hp: waifuCur,
    max_hp: waifuMax,
  };
  const dungeon = snap.dungeon || { name: "", total_rooms: 0, current_room: 1 };

  soloActiveSnapshot = {
    ...snap,
    monster,
    waifu,
    dungeon,
    monster_current_hp: hpCur,
    monster_max_hp: hpMax,
    waifu_current_hp: waifuCur,
    waifu_max_hp: waifuMax,
    damage_done: window._lastSoloDealt,
  };

  ensureCombatIslandMounted();
  window.WaifuCombatIsland?.applyPayload?.(payload);

  const host = document.getElementById("solo-active");
  const content = document.getElementById("solo-active-content");
  if (
    host &&
    host.style.display !== "none" &&
    (!content || content.style.display !== "none")
  ) {
    renderSoloBattleCard(monster, dungeon, waifu);
    flashSoloHitFeedback(payload);
  }
  return true;
}

function ensureCombatIslandMounted() {
  if (window._combatIslandMounted) return;
  if (typeof window.WaifuCombatIslandMount === "function") {
    const host = document.getElementById("solo-combat-island");
    if (host) {
      window.WaifuCombatIslandMount(host);
      window._combatIslandMounted = true;
    }
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
  const progressText = total > 0 ? `🚪 ${current}/${total}` : "";
  const progressEl = document.getElementById("solo-dungeon-progress-ov");
  if (progressEl) progressEl.textContent = progressText;

  const nameKnown = monster.name_known !== false;
  const typeKnown = monster.type_known !== false;

  const visual = document.getElementById("monster-visual");
  if (visual) {
    visual.className = "monster-visual";
    if (monster.is_boss) visual.classList.add("boss");
    else if (monster.is_elite) {
      const glow = monster.affix_count >= 4 ? "elite-red" : monster.affix_count >= 3 ? "elite-gold" : "elite-blue";
      visual.classList.add(glow);
    }
    // The monster is in front of the player, so always show its real art;
    // only the name/HP/type text is redacted until the relevant kill-tier.
    // Open this monster's bestiary page when tapping the card.
    visual.style.cursor = "pointer";
    visual.title = "Открыть в библиотеке";
    visual.onclick = () => {
      if (monster.template_id != null && window.WaifuApp?.openLibrary) {
        window.WaifuApp.openLibrary({ tab: "bestiary", templateId: monster.template_id });
      }
    };
  }

  setText("monster-name-text", nameKnown ? (monster.name ?? "—") : (monster.display_name || "Неизвестный монстр"));
  setText("monster-name-level", `Ур. ${monster.level ?? "—"}`);

  const typeEl = document.getElementById("monster-name-type");
  const typeLabel = typeKnown ? formatMonsterTypeLabelRu(monster.monster_type) : "";
  if (typeEl) {
    typeEl.textContent = typeLabel;
    typeEl.style.display = typeLabel ? "block" : "none";
  }

  const emojiEl = document.getElementById("monster-emoji");
  if (emojiEl) emojiEl.textContent = monster.emoji ?? "👾";
  const placeholderLabel = document.getElementById("monster-placeholder-label");
  if (placeholderLabel) placeholderLabel.textContent = typeKnown ? (monster.family ?? "") : "";

  const img = document.getElementById("monster-img");
  const placeholder = document.getElementById("monster-placeholder");
  if (img) img.classList.add("fading");
  const monsterArtVersionStr = monsterArtCacheBust(
    monster.template_id,
    monster.image_updated_at
  );
  const artKey = `${monster.family || "unknown"}|${monster.slug || "unknown"}|${monster.tier ?? 1}|${monsterArtVersionStr || ""}`;
  const family = monster.family || "unknown";
  const slug = monster.slug || "unknown";
  const tier = monster.tier ?? 1;
  const imageOverride = monster.image_override ?? null;
  if (visual && visual.dataset.monsterArtKey !== artKey) {
    visual.dataset.monsterArtKey = artKey;
    setTimeout(() => {
      loadMonsterImage(family, slug, tier, imageOverride, monsterArtVersionStr);
    }, 150);
  } else if (img && img.complete && img.naturalWidth > 0) {
    onMonsterImageLoad(img);
  } else if (placeholder?.classList.contains("visible") && img) {
    loadMonsterImage(family, slug, tier, imageOverride, monsterArtVersionStr);
  }

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
    soloActiveStoryBossId = null;
    soloActiveSnapshot = null;
    host.style.display = "none";
    list.style.display = "";
    setSoloExitBtnVisible(false);
    return;
  }

  soloActiveMonsterTemplateId =
    active.monster_template_id != null ? Number(active.monster_template_id) : null;
  soloActiveStoryBossId =
    active.is_story_boss && active.story_boss?.id != null
      ? Number(active.story_boss.id)
      : active.story_boss_definition_id != null
        ? Number(active.story_boss_definition_id)
        : null;

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

  const storyBossImg = active.story_boss?.image_webp_path || null;
  const monster = {
    name: active.monster_name,
    level: active.monster_level,
    current_hp: hpCur,
    max_hp: hpMax,
    family: active.monster_family || "unknown",
    slug: active.monster_slug || "unknown",
    tier: active.monster_tier ?? 1,
    template_id: active.monster_template_id ?? null,
    has_image: active.monster_has_image === true,
    image_updated_at: active.monster_image_updated_at || null,
    image_override: active.monster_image_override || storyBossImg || null,
    emoji: active.monster_emoji || "👾",
    is_boss: active.is_boss === true,
    is_elite: active.is_elite === true,
    affix_count: active.affix_count ?? 0,
    affixes: Array.isArray(active.affixes) ? active.affixes : [],
    monster_type: active.monster_type || active.monster_family || "",
    codex_tier: active.monster_codex_tier ?? 0,
    name_known: active.monster_name_known !== false,
    hp_known: active.monster_hp_known !== false,
    type_known: active.monster_type_known !== false,
    display_name: active.monster_display_name || active.monster_name,
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
  soloActiveSnapshot = {
    monster,
    waifu,
    dungeon,
    monster_current_hp: hpCur,
    monster_max_hp: hpMax,
    waifu_current_hp: waifu.current_hp,
    waifu_max_hp: waifu.max_hp,
    damage_done: dealt,
  };
  ensureCombatIslandMounted();
  renderSoloBattleCard(monster, dungeon, waifu);
  window.WaifuCombatIsland?.setBaseline?.({ monster, waifu });
  const logEntries = active.battle_log_entries;
  if (Array.isArray(logEntries) && logEntries.length) {
    mountSoloBattleLog(logEntries);
  }
  setSoloExitBtnVisible(true);
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
  setSoloExitBtnVisible(true);
}

async function refreshSoloActive(options = {}) {
  const includeLog = options.includeLog !== false;
  if (!dungeonsFinishBlockedMsg) showDungeonsError("");
  try {
    const active = await fetchActiveDungeon({ includeLog, force: true });
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

async function ensureSoloTabBootstrapped(profile) {
  if (soloTabBootstrapped) return;
  soloTabBootstrapped = true;
  const p = profile || window.__lastProfileForDungeons || (await loadProfile({ lite: true }));
  window.__lastProfileForDungeons = p;
  try {
    const st = await apiFetch("/dungeons/plus/status");
    const byId = window.dungeonPlusStatusById;
    for (const k of Object.keys(byId)) delete byId[k];
    for (const r of st?.status || []) {
      byId[Number(r.dungeon_id)] = r;
    }
    initPlusSelect(Boolean(st?.global_unlocked), byId);
  } catch {
    initPlusSelect(false, {});
  }
  await renderSoloDungeonsForAct(p);
  try {
    const active = await fetchActiveDungeon({ includeLog: true, force: true });
    renderAtticDungeon(active);
    renderSoloActiveProgress(active);
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    renderSoloActiveProgress({ active: false });
    showDungeonsError(`Не удалось проверить активный данж: ${detail || "ошибка"}`);
  }
}

async function populateDungeonsPage(profile) {
  ensureCombatIslandMounted();
  const p = profile || (await loadProfile({ lite: true }));
  // attic: show act in compact header
  if (p?.act != null) setText("badge-act", p.act);
  showDungeonsError("");

  // Page-scoped SSE handler: instant HP from payload; debounced API fallback for reliability.
  let logSyncTimer;
  window.WaifuApp.refreshBattleState = () =>
    refreshSoloActive({ includeLog: false }).catch(() => {});
  window.WaifuApp.onSseEvent = (evt) => {
    if (evt && evt.type === "gd") {
      clearTimeout(logSyncTimer);
      logSyncTimer = setTimeout(() => {
        loadActiveGdDungeons().catch?.(() => {});
        updateGdSessionUI().catch?.(() => {});
      }, 150);
      return;
    }
    if (!evt || evt.type !== "battle") return;
    const payload = evt.payload || {};
    if (payload.dungeon_failed || payload.waifu_died) {
      dungeonsFinishBlockedMsg = null;
      const penalty = payload.gold_penalty_pct ?? 50;
      const gold = payload.gold_gained ?? payload.total_gold_gained ?? 0;
      const exp = payload.experience_gained ?? payload.total_experience_gained ?? 0;
      const msg =
        payload.message ||
        `Подземелье провалено. Штраф к золоту: −${penalty}% от накопленного. Получено: ${gold} золота, ${exp} опыта.`;
      applySoloBattleSsePayload(payload);
      showDungeonsError(msg, "danger");
      setTimeout(() => {
        window.location.href = "./dungeons.html";
      }, 2200);
      return;
    }
    if (payload.finish_blocked) {
      const msg = payload.message || "Не хватает здоровья для победы.";
      dungeonsFinishBlockedMsg = msg;
      const applied = applySoloBattleSsePayload(payload);
      if (!applied) scheduleSoloHpRefetch();
      showDungeonsError(msg, "danger");
      return;
    }
    const applied = applySoloBattleSsePayload(payload);
    if (dungeonsFinishBlockedMsg && (payload.damage != null || payload.monster_defeated || payload.dungeon_completed)) {
      dungeonsFinishBlockedMsg = null;
      showDungeonsError("");
    }
    clearTimeout(logSyncTimer);
    if (payload.dungeon_completed || payload.monster_defeated) {
      clearTimeout(soloHpRefetchTimer);
      soloHpRefetchTimer = null;
      refreshSoloActive({ includeLog: true }).catch?.(() => {});
      if (payload.dungeon_completed) {
        dungeonsFinishBlockedMsg = null;
        openRewardModal(payload);
      }
      return;
    }
    if (!applied) {
      scheduleSoloHpRefetch();
    } else if (payload.damage != null || payload.monster_hp != null || payload.waifu_current_hp != null) {
      scheduleSoloHpRefetch();
    }
    if (payload.damage_breakdown?.length || payload.summary_ru) {
      logSyncTimer = setTimeout(() => {
        refreshSoloActive({ includeLog: true }).catch?.(() => {});
      }, 800);
    }
  };

  const tabParam = new URLSearchParams(window.location.search).get("tab");
  const skipSoloBootstrap =
    tabParam === "expedition" || tabParam === "group" || tabParam === "abyss";

  if (!skipSoloBootstrap) {
    await ensureSoloTabBootstrapped(p);
  } else {
    window.__lastProfileForDungeons = p;
  }

  if (tabParam === "solo" || tabParam === "expedition" || tabParam === "group" || tabParam === "abyss") {
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
    if (raw.includes("abyss_session_active") || detail.includes("abyss_session_active")) {
      showDungeonsError("Сначала выйдите из Бездны.");
      showTab("abyss");
      return;
    }
    if (raw.includes("dungeon_already_active") || detail.includes("dungeon_already_active")) {
      // ensure solo tab visible
      showTab("solo");
      try {
        const active = await fetchActiveDungeon({ includeLog: true, force: true });
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
    const active = await fetchActiveDungeon({ includeLog: true, force: true });
    renderSoloActiveProgress(active);
  } catch {
    // ignore
  }
  showDungeonsError("");
}

async function loadActiveDungeon() {
  const data = await fetchActiveDungeon({ includeLog: true, force: true });

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
  invalidateActiveDungeonCache();
  const profile = await loadProfile({ lite: true }).catch(() => null);
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
  const data = await fetchActiveDungeon({ includeLog: true, force: true });

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
    if (res?.waifu_died || res?.dungeon_failed) {
      const penalty = res.gold_penalty_pct ?? 50;
      const gold = res.gold_gained ?? res.total_gold_gained ?? 0;
      const exp = res.experience_gained ?? res.total_experience_gained ?? 0;
      appendBattleLog(
        `💀 Вайфу погибла! Штраф к золоту: −${penalty}% от накопленного. Получено: ${gold} 🪙, ${exp} ✨`
      );
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
      <div class="empty-state gd-empty-state">
        <button type="button" class="gd-help-btn exp-help-btn" onclick="WaifuApp.openGdHelp()" aria-label="Справка" title="Справка">?</button>
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

function gdHelpHtml() {
  return `
    <p>
      <strong>GD v1</strong> — общий поход для чата: сначала волна обычных врагов, затем босс. Название и антураж подземелья задаются шаблоном из игры (список в БД может меняться).
    </p>
    <ul class="gd-info-list">
      <li>Сообщения и медиа в группе в ходе раунда попадают в <strong>буфер</strong>; урон и навыки считаются при <strong>закрытии раунда</strong> (таймер ~30 мин или обработка в боте), а не «каждое сообщение = удар», как в соло.</li>
      <li>При «вайпе» отряда раунд может завершиться с ослаблением стороны игроков и продолжением похода — жёсткого геймовера нет.</li>
      <li>Награды (опыт, золото, дроп) в конце похода — в личку бота, пропорционально вкладу.</li>
    </ul>
    <p class="gd-info-how"><strong>Как играть:</strong> в группе — <code>/gd_join</code> на время регистрации. Вне активного GD v1 сообщения в группе могут давать соло-урон. Чтобы видеть статус этого чата здесь, откройте страницу с <code>?chat_id=ID_ЧАТА</code> (числовой id супергруппы Telegram).</p>
    <p class="gd-info-note muted">Запись в поход и бой — в Telegram; веб-приложение показывает список ваших циклов и опционально снимок по <code>chat_id</code>.</p>
  `;
}

function openGdHelp() {
  const body = document.getElementById("gd-help-body");
  if (body) body.innerHTML = gdHelpHtml();
  expOpenOverlay("gd-help-modal");
}

function closeGdHelp() {
  expCloseOverlay("gd-help-modal");
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
        <div class="hp-fill hp-fill-monster" style="width: ${hpBarWidth}"></div>
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
              <div class="hp-fill hp-fill-monster" style="width: ${dungeon.hp_percent || 0}%"></div>
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
  if (!card) return;
  if (chatId === null) {
    card.style.display = "none";
    return;
  }
  try {
    const v1 = await apiFetch(`/gd/cycle/${chatId}`).catch(() => ({ v1: false }));
    if (v1 && v1.v1) {
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
          ? `<div class="gd-session-meta muted tiny">Волна: ${escapeHtml(gdV1WaveLabelRu(v1.wave))}</div>`
          : "";
      const deadlineLine =
        deadline != null
          ? `<div class="gd-session-meta muted tiny">Дедлайн сбора раунда: ${escapeHtml(deadline)}</div>`
          : "";
      const hpBlock =
        v1.status === "active"
          ? `<div class="gd-session-hp-block">
          <div class="gd-session-monster">
          <span id="gd-session-monster-name">${escapeHtml(v1.monster_name || "—")}</span>
          <span id="gd-session-hp">${Number(v1.hp_current || 0).toLocaleString()} / ${Number(v1.hp_max || 0).toLocaleString()}</span>
        </div>
        <div class="gd-session-hp-bar"><div id="gd-session-hp-fill" class="gd-hp-fill hp-fill-monster" style="width:${hpPct}%"></div></div>
        </div>`
          : "";
      card.innerHTML = `
        <div class="gd-session-head">
          <h3 class="gd-session-title" id="gd-session-dungeon-name">${title}</h3>
          <div class="gd-session-meta muted tiny">${escapeHtml(st)}</div>
          <div class="gd-session-meta muted tiny">Регистрация до: ${escapeHtml(closes)}</div>
        </div>
        <div class="gd-session-body">
        ${
          v1.status === "active"
            ? `<div class="gd-session-meta gd-session-meta--spaced muted tiny">В журнале записан раунд: <strong>${lastR}</strong> · сбор на раунд: <strong>${coll}</strong></div>
        ${waveLine}
        ${deadlineLine}
        ${hpBlock}`
            : ""
        }
        </div>
        <p class="gd-session-foot muted tiny">Команды в чате: <code>/gd_join</code>, <code>/gd_party</code>. Сообщения в чат попадают в буфер текущего раунда; закрытие по таймеру (~15 мин) или админ-команде.</p>
      `;
      return;
    }
    card.style.display = "none";
  } catch {
    card.style.display = "none";
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

let expeditionTabDataLoaded = false;
let expeditionRosterLoaded = false;
let expeditionRosterInflight = null;
let soloTabBootstrapped = false;
let expSendLoadingInterval = null;
let expeditionSendInFlight = false;

const EXP_SEND_LOADING_PCTS = [12, 24, 36, 48, 60, 72, 84, 92];

const EXP_SEND_LOADING_MESSAGES = [
  "Красят губки...",
  "Выбирают, что надеть...",
  "Делают мейк-ап...",
  "Заплетают косички...",
  "Ищут второй носок...",
  "Пакуют зелья в рюкзак...",
  "Прощаются с котом...",
  "Спорят, кто идёт первой...",
  "Подбирают серьги к доспехам...",
  "Расчёсывают хвосты и косы...",
  "Спорят, какой плащ «более героический»...",
  "Намазывают крем от солнца и от драконов...",
  "Проверяют, не торчит ли лента из шлема...",
  "Делают селфи «на память перед боем»...",
  "Ищут заколку, которая не слетит в бою...",
  "Сверяют оттенок помады с цветом знамени...",
  "Уговаривают одну не опаздывать...",
  "Завязывают шнурки на сапогах (в третий раз)...",
  "Прячут сладости от строгой целительницы...",
  "Наносят боевой макияж — буквально...",
  "Распределяют, кто несёт зеркальце...",
  "Пытаются втиснуть ещё один флакон в сумку...",
  "Поправляют чёлки под забралами...",
  "Шепчут заклинание от статики в волосах...",
  "Выбирают аромат «лес после дождя»...",
  "Считают, хватит ли заколок на весь отряд...",
  "Уговаривают кота отпустить лучший плащ...",
  "Листают модный журнал «Доспехи осени»...",
  "Проверяют маникюр на прочность хвата...",
  "Договариваются, кто сегодня «лицо отряда»...",
  "Запасают платочки «на всякий случай»...",
  "Примеряют перчатки без пальцев — модно же...",
  "Ищут блестки, которые не шумят в засаде...",
  "Сверяют тональник с цветом заката в походе...",
  "Прощаются с подушкой — «вернёмся красивыми»...",
];

function shuffleExpSendLoadingMessages(messages) {
  const arr = messages.slice();
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

function buildExpSendLoadingSteps() {
  const picked = shuffleExpSendLoadingMessages(EXP_SEND_LOADING_MESSAGES).slice(
    0,
    EXP_SEND_LOADING_PCTS.length,
  );
  return EXP_SEND_LOADING_PCTS.map((pct, idx) => [pct, picked[idx]]);
}

function openExpeditionSendLoading() {
  const modal = document.getElementById("exp-send-loading-modal");
  const fill = document.getElementById("exp-send-loading-fill");
  const sub = document.getElementById("exp-send-loading-sub");
  if (!modal) return;
  if (expSendLoadingInterval) {
    clearInterval(expSendLoadingInterval);
    expSendLoadingInterval = null;
  }
  const steps = buildExpSendLoadingSteps();
  modal.style.display = "flex";
  modal.setAttribute("aria-busy", "true");
  document.body.style.overflow = "hidden";
  if (fill) {
    fill.style.width = "0%";
    fill.classList.remove("is-indeterminate");
  }
  if (sub) sub.textContent = steps[0][1];
  let stepIdx = 0;
  expSendLoadingInterval = setInterval(() => {
    if (stepIdx < steps.length && fill && sub) {
      const [pct, text] = steps[stepIdx++];
      fill.style.width = pct + "%";
      sub.textContent = text;
    }
  }, 600);
}

function closeExpeditionSendLoading() {
  if (expSendLoadingInterval) {
    clearInterval(expSendLoadingInterval);
    expSendLoadingInterval = null;
  }
  const modal = document.getElementById("exp-send-loading-modal");
  if (modal) {
    modal.style.display = "none";
    modal.setAttribute("aria-busy", "false");
  }
  document.body.style.overflow = "";
}

async function ensureExpeditionRoster(opts = {}) {
  const force = Boolean(opts && opts.force);
  if (expeditionRosterLoaded && !force) return expeditionState.roster || [];
  if (expeditionRosterInflight) return expeditionRosterInflight;
  expeditionRosterInflight = apiFetch("/expeditions/roster")
    .then((res) => {
      expeditionState.roster = Array.isArray(res?.waifus) ? res.waifus : [];
      expeditionRosterLoaded = true;
      return expeditionState.roster;
    })
    .catch(() => {
      expeditionState.roster = [];
      expeditionRosterLoaded = true;
      return [];
    })
    .finally(() => {
      expeditionRosterInflight = null;
    });
  return expeditionRosterInflight;
}

async function loadExpeditionTab(opts = {}) {
  const force = Boolean(opts && opts.force);
  if (force) expeditionRosterLoaded = false;
  showExpeditionError("");
  try {
    if (!expeditionTabDataLoaded || force) {
      if (!expeditionTabDataLoaded) expeditionTabDataLoaded = true;
      const [catalogRes, activeRes] = await Promise.all([
        apiFetch("/expeditions/catalog").catch(() => ({ reward_types: [], depth_tiers: [] })),
        apiFetch("/expeditions/active"),
      ]);
      expeditionState.catalog = {
        reward_types: Array.isArray(catalogRes?.reward_types) ? catalogRes.reward_types : [],
        depth_tiers: Array.isArray(catalogRes?.depth_tiers) ? catalogRes.depth_tiers : [],
        max_concurrent: Number(catalogRes?.max_concurrent) || 3,
      };
      expeditionState.active = Array.isArray(activeRes?.active) ? activeRes.active : [];
      expeditionUiCache.activeById = {};
      (expeditionState.active || []).forEach((a) => {
        expeditionUiCache.activeById[a.id] = a;
      });
    }
    renderExpeditionGrids();
    wireExpeditionTabTimers();
    refreshAtticChips({ skipDungeon: true });
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    showExpeditionError(detail || "Ошибка загрузки экспедиций");
  }
}

function formatExpeditionTime(seconds) {
  if (seconds == null || seconds <= 0) return "—";
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  if (h > 0) return `${pad(h)}:${pad(m)}:${pad(ss)}`;
  return `${m}:${pad(ss)}`;
}

function formatExpeditionDurationShort(minutes) {
  const m = Number(minutes) || 0;
  if (m <= 0) return "—";
  if (m < 60) return `${m} мин`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}ч ${rem}м` : `${h} ч`;
}

function powerThresholdClass(sqPower, recommended) {
  const sq = Number(sqPower) || 0;
  const need = Number(recommended) || 0;
  if (!need) return "exp-power-ok";
  if (sq >= need) return "exp-power-ok";
  if (sq >= Math.round(need * 0.7)) return "exp-power-low";
  return "exp-power-bad";
}

function healForecastMinutes(hpCurrent, hpMax) {
  const hpM = Number(hpMax) || 1;
  const hpC = Math.max(0, Number(hpCurrent) || 0);
  if (hpC >= hpM) return 0;
  const lostPct = Math.max(0, (hpM - hpC) / hpM) * 100;
  // 0.8 мин за 1% потерянного HP; ×1.5 если HP=0
  const mins = lostPct * 0.8 * (hpC <= 0 ? 1.5 : 1);
  return Math.round(mins);
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

const EXPEDITION_ARCHETYPE_ART = new Set([
  "arctic",
  "bridge_town",
  "carnival",
  "city",
  "factory",
  "fae_realm",
  "hospital",
  "jungle",
  "library",
  "market",
  "night_club",
  "observatory",
  "sewer",
  "slums",
  "theater",
  "train_station",
  "university",
]);
const EXPEDITION_BIOME_ART = new Set([
  "abyss",
  "cave",
  "coast",
  "crypt",
  "dark_temple",
  "default",
  "desert",
  "dungeon",
  "forest",
  "fortress",
  "mountain",
  "ruins",
  "sea_depth",
  "sky",
  "swamp",
  "temple",
  "tundra",
  "volcano",
]);

function biomeImageUrls(tag, archetypeId) {
  const urls = [];
  const archKey = String(archetypeId || "")
    .trim()
    .toLowerCase()
    .replace(/ /g, "_")
    .replace(/-/g, "_");
  const archetypesBase = window.EXPEDITION_ARCHETYPES_BASE || "/static/game/expeditions/archetypes";
  const biomesBase = window.EXPEDITION_BIOMES_BASE || "/static/game/expeditions/biomes";
  if (archKey && EXPEDITION_ARCHETYPE_ART.has(archKey)) {
    const v = (window.expeditionArchetypeArtVersion || {})[archKey];
    const q = v ? `?v=${encodeURIComponent(v)}` : "";
    urls.push(`${archetypesBase}/${encodeURIComponent(archKey)}.webp${q}`);
  }
  const key = normalizeBiomeTag(tag);
  if (key && EXPEDITION_BIOME_ART.has(key)) urls.push(`${biomesBase}/${encodeURIComponent(key)}.webp`);
  urls.push(`${biomesBase}/default.webp`);
  return urls;
}

/** Кэш успешных URL фонов биомов экспедиций (tag|archetypeId → url). */
const expeditionBiomeUrlCache = new Map();
/** In-flight probes: cacheKey → Promise<url|null> */
const expeditionBiomeProbeInflight = new Map();

function applyExpeditionBiomeToElement(el, tag, emojiEl, archetypeId, url) {
  const fallback = biomeBg(tag);
  const isModal = el.classList.contains("exp-modal-img");
  const biomeCls = isModal ? "exp-modal-img--biome" : "exp-card-img--biome";
  el.classList.remove("exp-modal-img--biome", "exp-card-img--biome");
  el.style.background = fallback;
  el.style.backgroundImage = `url("${url}")`;
  el.style.backgroundSize = "cover";
  el.style.backgroundPosition = "center";
  el.classList.add(biomeCls);
  if (emojiEl) emojiEl.style.display = "none";
}

function probeExpeditionBiomeUrl(tag, archetypeId) {
  const cacheKey = `${String(tag || "").trim()}|${String(archetypeId || "").trim()}`;
  const cachedUrl = expeditionBiomeUrlCache.get(cacheKey);
  if (cachedUrl) return Promise.resolve(cachedUrl);
  const inflight = expeditionBiomeProbeInflight.get(cacheKey);
  if (inflight) return inflight;
  const urls = biomeImageUrls(tag, archetypeId);
  const promise = new Promise((resolve) => {
    let i = 0;
    function tryNext() {
      if (i >= urls.length) {
        resolve(null);
        return;
      }
      const url = urls[i++];
      const probe = new Image();
      probe.onload = () => {
        expeditionBiomeUrlCache.set(cacheKey, url);
        resolve(url);
      };
      probe.onerror = tryNext;
      probe.src = url;
    }
    tryNext();
  }).finally(() => {
    expeditionBiomeProbeInflight.delete(cacheKey);
  });
  expeditionBiomeProbeInflight.set(cacheKey, promise);
  return promise;
}

function applyExpeditionBiomeBackground(el, tag, emojiEl, archetypeId) {
  if (!el) return;
  const fallback = biomeBg(tag);
  el.classList.remove("exp-modal-img--biome", "exp-card-img--biome");
  el.style.backgroundImage = "";
  el.style.background = fallback;
  if (emojiEl) emojiEl.style.display = "";
  const cacheKey = `${String(tag || "").trim()}|${String(archetypeId || "").trim()}`;
  const cachedUrl = expeditionBiomeUrlCache.get(cacheKey);
  if (cachedUrl) {
    applyExpeditionBiomeToElement(el, tag, emojiEl, archetypeId, cachedUrl);
    return;
  }
  probeExpeditionBiomeUrl(tag, archetypeId).then((url) => {
    if (!url || !el.isConnected) return;
    applyExpeditionBiomeToElement(el, tag, emojiEl, archetypeId, url);
  });
}

function wireExpeditionCardBiomes(root) {
  (root || document).querySelectorAll(".exp-card-img[data-biome-tag]").forEach((imgEl) => {
    const tag = imgEl.getAttribute("data-biome-tag") || "";
    const archetypeId = imgEl.getAttribute("data-archetype-id") || "";
    const emojiEl = imgEl.querySelector(".exp-card-emoji");
    applyExpeditionBiomeBackground(imgEl, tag, emojiEl, archetypeId);
  });
}

function expeditionCardGenArtButton(kind, item) {
  const archId = String(item?.location_archetype_id || "").trim();
  if (!archId) return "";
  const expId = Number(item?.id);
  if (!Number.isFinite(expId)) return "";
  const kindAttr = kind === "active" ? "active" : "daily";
  return `<button type="button" class="exp-card-gen-art admin-only" style="display:none"
    data-exp-kind="${kindAttr}" data-exp-id="${expId}" data-archetype-id="${escapeHtml(archId)}"
    onclick="event.stopPropagation(); WaifuApp.adminGenerateExpeditionArt(this)"
    title="Сгенерировать акварельный арт" aria-label="Сгенерировать акварельный арт">🎨</button>`;
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
        ? "Тип закрыт перком отряда (снижение урона)"
        : "Активный тип сложности — нужен подходящий перк";
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
      title: `${race?.name || "Раса"} · ${hit.join(", ")} · бонус −10% к событиям (не закрывает тег)`,
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
      title: `${cls?.name || "Класс"} · ${hit.join(", ")} · бонус −10% к событиям (не закрывает тег)`,
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
  const forecastEl = expG("esm-forecast");
  const warnEl = expG("esm-send-warnings");
  const unitIds = expeditionSend.squadSlots.filter(Boolean).map((u) => u.id);
  updateExpeditionSquadPowerLabel();
  if (!unitIds.length) {
    if (forecastEl) {
      forecastEl.classList.remove("exp-forecast--visible");
      forecastEl.innerHTML = "";
    }
    if (warnEl) warnEl.textContent = "";
    updateExpConfirmPanel(null);
    return;
  }
  try {
    const prev = await apiFetch("/expeditions/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        unit_ids: unitIds,
        reward_type: expeditionSend.rewardType,
        depth_tier: expeditionSend.depthTier,
      }),
    });
    // HP-прогноз по базовому урону тира (теги/твисты неизвестны до старта).
    if (forecastEl) {
      const dmgPct = prev.damage_per_event_pct != null ? Number(prev.damage_per_event_pct) : null;
      const hpPct = prev.hp_forecast_pct != null ? Number(prev.hp_forecast_pct) : null;
      const ev = prev.events_count || "?";
      const tierName = prev.depth_name || `Тир ${prev.depth_tier || expeditionSend.depthTier}`;
      if (hpPct != null && dmgPct != null) {
        const hpCls = hpPct >= 52 ? "exp-forecast-hp-good" : hpPct >= 12 ? "exp-forecast-hp-mid" : "exp-forecast-hp-bad";
        const outcome = hpPct >= 52 ? "Успех" : hpPct >= 12 ? "Частичный" : "Провал";
        forecastEl.innerHTML = `<div class="exp-forecast-main">HP ~<strong class="${hpCls}">${Math.round(hpPct)}%</strong> · ${outcome} · ~${dmgPct}%/тик × ${ev}</div>`;
        forecastEl.classList.add("exp-forecast--visible", "exp-forecast--compact");
      } else {
        forecastEl.classList.remove("exp-forecast--visible");
        forecastEl.innerHTML = "";
      }
    }
    if (warnEl) {
      if (prev.power_ok === false) {
        warnEl.textContent = `Недостаточно мощи: ${prev.squad_power || 0} / ${prev.min_squad_power || 0}`;
      } else {
        warnEl.textContent = "";
      }
    }
    updateExpConfirmPanel(prev);
  } catch (_) {
    if (forecastEl) {
      forecastEl.classList.remove("exp-forecast--visible");
      forecastEl.innerHTML = "";
    }
    updateExpConfirmPanel(null);
  }
}

function updateExpConfirmPanel(prev) {
  const powerEl = expG("esm-confirm-power");
  const hpEl = expG("esm-confirm-hp");
  const durEl = expG("esm-confirm-dur");
  const rewardEl = expG("esm-confirm-reward");
  const sq = expeditionSquadPowerTotal();
  const tier = (expeditionState.catalog?.depth_tiers || []).find((t) => t.tier === expeditionSend.depthTier);
  const dur = tier ? formatExpeditionDurationShort(tier.duration_minutes) : "—";
  const hp = prev?.hp_forecast_pct != null ? `${Math.round(prev.hp_forecast_pct)}%` : "—";
  const rewardIcon = REWARD_ICONS[expeditionSend.rewardType] || "🎁";
  const rewardName = REWARD_SHORT_NAMES[expeditionSend.rewardType] || "—";
  if (powerEl) powerEl.innerHTML = `⚔ <strong>${sq}</strong>`;
  if (hpEl) hpEl.innerHTML = `❤ <strong>${escapeHtml(hp)}</strong>`;
  if (durEl) durEl.innerHTML = `⏱ <strong>${escapeHtml(dur)}</strong>`;
  if (rewardEl) rewardEl.innerHTML = `${rewardIcon} <strong>${escapeHtml(rewardName)}</strong>`;
}

function expeditionCardArchetypeChip(item) {
  const arch = String(item?.location_archetype_name || item?.base_location || "").trim();
  if (!arch) return "";
  return `<div class="exp-narr-meta exp-narr-meta--card"><span class="exp-narr-chip exp-narr-arch">${escapeHtml(arch)}</span></div>`;
}

function expeditionCardTitleOverlay(title) {
  const t = String(title || "").trim();
  if (!t) return "";
  return `<div class="exp-card-title-overlay">${escapeHtml(t)}</div>`;
}

function expeditionSendModalTitle(slot) {
  const mode = slot?.expedition_mode_name;
  const arch = slot?.location_archetype_name;
  if (mode && arch) return `${mode} · ${arch}`;
  return slot?.name || slot?.base_location || "—";
}

function expeditionNarrativeMetaHtml(item) {
  const mode = item?.expedition_mode_name;
  const arch = item?.location_archetype_name;
  if (!mode && !arch) return "";
  const parts = [];
  if (mode) parts.push(`<span class="exp-narr-chip exp-narr-mode">${escapeHtml(mode)}</span>`);
  if (arch) parts.push(`<span class="exp-narr-chip exp-narr-arch">${escapeHtml(arch)}</span>`);
  return `<div class="exp-narr-meta">${parts.join("")}</div>`;
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

function expeditionDiffCountClass(item) {
  // Цветная рамка по количеству «сложностей» (от зелёной до фиолетовой).
  let count = Array.isArray(item?.affixes) ? item.affixes.length : 0;
  if (!count && Array.isArray(item?.difficulty_tags)) count = item.difficulty_tags.length;
  count = Math.max(1, Math.min(5, count || 1));
  return `exp-diff-count-${count}`;
}

function renderExpeditionGrids() {
  const activeSection = document.getElementById("exp-active-section");
  const activeGrid = document.getElementById("exp-active-grid");
  if (!activeGrid) return;

  const actives = expeditionState.active || [];
  const maxConcurrent = Number(expeditionState.catalog?.max_concurrent) || 3;
  if (activeSection) {
    if (actives.length) {
      activeSection.style.display = "";
      activeGrid.innerHTML = actives
        .map((a) => {
          const titleOverlay = expeditionCardTitleOverlay(a.narrative_title);
          const archetypeChip = expeditionCardArchetypeChip(a);
          const affixIcos = (a.affixes || [])
            .slice(0, 4)
            .map((x) => `<div class="exp-affix-ico">${x.icon || "✦"}</div>`)
            .join("");
          const prog = a.progress_pct != null ? Math.min(100, Number(a.progress_pct)) : 0;
          const sec = a.seconds_left != null ? a.seconds_left : 0;
          const timeStr = a.can_claim ? "—" : formatExpeditionTime(sec);
          const emoji = a.biome_emoji || "🗺";
          const biomeTag = escapeHtml(a.biome_tag || "");
          const archId = escapeHtml(a.location_archetype_id || "");
          const genBtn = expeditionCardGenArtButton("active", a);
          const diffCls = expeditionDiffCountClass(a);
          const statusCls = a.outcome === "cancelled" ? "exp-is-cancelled" : a.can_claim ? "exp-is-ready" : "";
          const statusBadge = a.outcome === "cancelled"
            ? '<span class="exp-status-cancelled">⚫ Отменена</span>'
            : a.can_claim
              ? '<span class="exp-status-ready">● Готово</span>'
              : '<span class="exp-status-active">● В пути</span>';
          const metaHtml = expActiveCardMetaHtml(a);
          return `<div class="exp-card-item exp-is-active ${diffCls} ${statusCls}" data-exp-kind="active" data-exp-id="${a.id}">
            <div class="exp-card-img" data-biome-tag="${biomeTag}" data-archetype-id="${archId}">
              <div class="exp-card-emoji">${emoji}</div>
              <div class="exp-card-affix-col">
                <div class="exp-card-affix-icons">${affixIcos}</div>
                ${genBtn}
              </div>
              ${archetypeChip}
              ${titleOverlay}
            </div>
            <div class="exp-card-progbar"><div class="exp-card-progfill" style="width:${prog}%"></div></div>
            <div class="exp-card-foot">${statusBadge}<span class="exp-foot-timer">${timeStr}</span></div>
            ${metaHtml}
          </div>`;
        })
        .join("");
    } else {
      activeSection.style.display = "none";
      activeGrid.innerHTML = "";
    }
  }

  wireExpeditionCardBiomes(activeGrid);
  renderExpSlotsIndicator(actives.length, maxConcurrent);
  renderExpBottomZone(actives.length, maxConcurrent);
  window.WaifuApp?.renderAtticExpeditions?.(actives, maxConcurrent);

  document.querySelectorAll("#exp-active-grid [data-exp-kind]").forEach((el) => {
    el.addEventListener("click", () => {
      const kind = el.getAttribute("data-exp-kind");
      const id = Number(el.getAttribute("data-exp-id"));
      expOpenCard(kind, id);
    });
  });
}

function expActiveCardMetaHtml(a) {
  const tierName = a.depth_name || (a.depth_tier ? `Тир ${a.depth_tier}` : null);
  const tierRoman = a.depth_tier ? (["I", "II", "III", "IV", "V"][(a.depth_tier | 0) - 1] || "") : "";
  const dur = a.duration_minutes ? formatExpeditionDurationShort(a.duration_minutes) : null;
  const sqPower = a.squad_power != null ? a.squad_power : null;
  const recPower = a.recommended_power != null ? a.recommended_power : null;
  const hpPct = a.squad_hp_pct != null ? a.squad_hp_pct : null;
  const reward = a.reward_preview || null;

  const tierParts = [];
  if (tierRoman) tierParts.push(`<span class="exp-card-tier">${tierRoman}${tierName ? ` · ${escapeHtml(tierName)}` : ""}</span>`);
  if (dur) tierParts.push(`<span class="muted">${escapeHtml(dur)}</span>`);
  const tierRow = tierParts.length ? `<div class="exp-card-meta-row">${tierParts.join("")}</div>` : "";

  const statParts = [];
  if (sqPower != null) {
    const cls = powerThresholdClass(sqPower, recPower);
    const recTxt = recPower != null ? ` / рек. ${recPower}` : "";
    statParts.push(`<span class="exp-card-power">⚔ <span class="${cls}">${sqPower}${recTxt}</span></span>`);
  }
  if (hpPct != null) {
    statParts.push(`<span class="exp-card-hp">❤ ${Math.round(hpPct)}%</span>`);
  }
  const statRow = statParts.length ? `<div class="exp-card-meta-row">${statParts.join("")}</div>` : "";

  const rewardRow = reward ? `<div class="exp-card-meta-row"><span class="exp-card-reward">${escapeHtml(reward)}</span></div>` : "";

  const meta = tierRow + statRow + rewardRow;
  return meta ? `<div class="exp-card-meta">${meta}</div>` : "";
}

function renderExpSlotsIndicator(activeCount, maxConcurrent) {
  const el = document.getElementById("exp-slots-indicator");
  if (!el) return;
  const full = activeCount >= maxConcurrent;
  el.textContent = `${activeCount}/${maxConcurrent} занято`;
  el.classList.toggle("exp-slots-full", full);
  el.style.display = activeCount > 0 ? "" : "none";
}

function renderExpBottomZone(activeCount, maxConcurrent) {
  const freeWrap = document.getElementById("exp-free-slots");
  const lastLootWrap = document.getElementById("exp-last-loot");

  // Свободные слоты (включая случай 0 активных — это основной способ запустить экспедицию)
  if (freeWrap) {
    if (activeCount < maxConcurrent) {
      const free = maxConcurrent - activeCount;
      const slots = [];
      for (let i = 0; i < free; i++) {
        slots.push(`<div class="exp-free-slot" onclick="WaifuApp.openSendExpModal()"><span class="exp-free-slot-ico">＋</span><span>Отправить<br>экспедицию</span></div>`);
      }
      freeWrap.innerHTML = slots.join("");
      freeWrap.style.display = "";
    } else {
      freeWrap.innerHTML = "";
      freeWrap.style.display = "none";
    }
  }

  // Последняя добыча — пока источник не подключён; скрываем
  if (lastLootWrap) {
    lastLootWrap.style.display = "none";
  }
}

function expTierCheatsheetHtml(tiers) {
  const rows = tiers.map((dt) => {
    const roman = ["I", "II", "III", "IV", "V"][(dt.tier | 0) - 1] || `Тир ${dt.tier}`;
    const name = escapeHtml(dt.name_ru || dt.name || "—");
    const dur = formatExpeditionDurationShort(dt.duration_minutes);
    const ev = dt.events_count || "—";
    const power = dt.min_squad_power || 0;
    const dmgMap = { 1: "6%", 2: "10%", 3: "15%", 4: "20%", 5: "28%" };
    const dmg = dmgMap[dt.difficulty_level || dt.tier] || "—";
    return `<tr><td><strong>${roman}</strong></td><td>${name}</td><td>${dur}</td><td>${ev}</td><td>⚔${power}</td><td>${dmg}/тик</td></tr>`;
  });
  return `<table class="exp-tier-cheatsheet-table"><thead><tr><th>Тир</th><th>Название</th><th>Длит.</th><th>Событий</th><th>Мощь</th><th>Урон</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

let expeditionTimerId = null;
let expeditionActivePollId = null;
let expActiveModalTimer = null;

function updateExpeditionActiveCardsOnly() {
  const active = expeditionState.active || [];
  let anyRunning = false;
  active.forEach((a) => {
    const card = document.querySelector(`.exp-card-item[data-exp-kind="active"][data-exp-id="${a.id}"]`);
    if (!card) return;
    const sec = a.remaining_seconds;
    if (!a.can_claim && sec != null && sec > 0) {
      anyRunning = true;
      a.remaining_seconds = Math.max(0, sec - 1);
    }
    const timerEl = card.querySelector(".exp-foot-timer");
    if (timerEl) timerEl.textContent = a.can_claim ? "—" : formatExpeditionTime(a.remaining_seconds);
    const progEl = card.querySelector(".exp-card-progfill");
    if (progEl && a.progress_pct != null) progEl.style.width = `${a.progress_pct}%`;
  });
  return anyRunning;
}

async function pollExpeditionActiveLight() {
  try {
    const activeRes = await apiFetch("/expeditions/active");
    expeditionState.active = Array.isArray(activeRes?.active) ? activeRes.active : [];
    expeditionUiCache.activeById = {};
    (expeditionState.active || []).forEach((a) => {
      expeditionUiCache.activeById[a.id] = a;
    });
    const grid = document.getElementById("exp-active-grid");
    const needsFullRender = (expeditionState.active || []).some((a) => {
      const card = document.querySelector(`.exp-card-item[data-exp-kind="active"][data-exp-id="${a.id}"]`);
      return !card;
    });
    if (needsFullRender) {
      renderExpeditionGrids();
    } else {
      updateExpeditionActiveCardsOnly();
    }
    wireExpeditionTabTimers();
    refreshAtticChips({ skipDungeon: true });
  } catch {
    // ignore light poll errors
  }
}

function wireExpeditionTabTimers() {
  const hasRunning = (expeditionState.active || []).some((a) => !a.can_claim);
  if (hasRunning && !expeditionTimerId) {
    expeditionTimerId = setInterval(() => {
      if (document.getElementById("tab-expedition")?.style.display === "none") return;
      const still = updateExpeditionActiveCardsOnly();
      if (!still) {
        pollExpeditionActiveLight().catch(() => {});
      }
    }, 1000);
  } else if (!hasRunning && expeditionTimerId) {
    clearInterval(expeditionTimerId);
    expeditionTimerId = null;
  }
  if (hasRunning && !expeditionActivePollId) {
    expeditionActivePollId = setInterval(() => {
      if (document.getElementById("tab-expedition")?.style.display === "none") return;
      pollExpeditionActiveLight().catch(() => {});
    }, 15000);
  } else if (!hasRunning && expeditionActivePollId) {
    clearInterval(expeditionActivePollId);
    expeditionActivePollId = null;
  }
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

let expeditionClaimInFlight = false;

function expOpenCard(kind, id) {
  if (kind === "active") {
    const raw = expeditionUiCache.activeById[id];
    if (!raw) return;
    if (raw.can_claim) {
      claimAndShowExpeditionResult(raw.id, raw.result_ready);
      return;
    }
    openActiveExpModal(raw);
  }
}

function expeditionSquadPowerTotal() {
  return expeditionSend.squadSlots.filter(Boolean).reduce((sum, u) => sum + (Number(u.power) || 0), 0);
}

const REWARD_ICONS = {
  gold: "🪙", waifu_exp: "⭐", items: "🗡", enchant: "💎", merc_exp: "✨", mixed: "🎁",
};
const REWARD_SHORT_NAMES = {
  gold: "Золото", waifu_exp: "Опыт ОВ", items: "Снаряжение",
  enchant: "Заточка", merc_exp: "Опыт наёмниц", mixed: "Смешанная",
};

function renderExpRewardSelect() {
  const sel = expG("esm-reward-select");
  if (!sel) return;
  const types = expeditionState.catalog?.reward_types || [];
  sel.innerHTML =
    types
      .map((rt) => {
        const icon = REWARD_ICONS[rt.id] || "🎁";
        const name = REWARD_SHORT_NAMES[rt.id] || rt.name || rt.id;
        const selected = expeditionSend.rewardType === rt.id ? " selected" : "";
        return `<option value="${escapeHtml(rt.id)}"${selected}>${icon} ${escapeHtml(name)}</option>`;
      })
      .join("") || '<option value="">Загрузка…</option>';
  if (types.length && !types.some((t) => t.id === expeditionSend.rewardType)) {
    expeditionSend.rewardType = types[0].id;
  }
  sel.value = expeditionSend.rewardType || "";
  if (!sel.dataset.wired) {
    sel.dataset.wired = "1";
    sel.addEventListener("change", () => {
      expeditionSend.rewardType = sel.value;
      refreshExpeditionTagPreview();
    });
  }
}

const TIER_SHORT_NAMES = { 1: "Разведка", 2: "Патруль", 3: "Поход", 4: "Рейд", 5: "В глубину" };
const TIER_ROMAN = ["I", "II", "III", "IV", "V"];

function renderExpTierSelect() {
  const sel = expG("esm-tier-select");
  if (!sel) return;
  const tiers = expeditionState.catalog?.depth_tiers || [];
  const sqPower = expeditionSquadPowerTotal();
  const current = tiers.find((t) => t.tier === expeditionSend.depthTier);
  if (current && sqPower < (current.min_squad_power || 0)) {
    const unlocked = tiers.filter((t) => sqPower >= (t.min_squad_power || 0));
    if (unlocked.length) expeditionSend.depthTier = unlocked[unlocked.length - 1].tier;
  }
  sel.innerHTML =
    tiers
      .map((dt) => {
        const locked = sqPower < (dt.min_squad_power || 0);
        const roman = TIER_ROMAN[(dt.tier || 1) - 1] || String(dt.tier);
        const name = TIER_SHORT_NAMES[dt.tier] || dt.name_ru || dt.name || `Тир ${dt.tier}`;
        const power = dt.min_squad_power || 0;
        const dur = formatExpeditionDurationShort(dt.duration_minutes);
        const ev = dt.events_count || "—";
        const label = `${roman} · ${name} · ⚔${power} · ${dur} · ${ev} соб.`;
        const selected = expeditionSend.depthTier === dt.tier ? " selected" : "";
        return `<option value="${dt.tier}"${locked ? " disabled" : ""}${selected}>${escapeHtml(label)}</option>`;
      })
      .join("") || '<option value="">Загрузка…</option>';
  sel.value = String(expeditionSend.depthTier || "");
  if (!sel.dataset.wired) {
    sel.dataset.wired = "1";
    sel.addEventListener("change", () => {
      expeditionSend.depthTier = Number(sel.value);
      renderExpTierSelect();
      updateExpeditionSquadPowerLabel();
      refreshExpeditionTagPreview();
    });
  }
}

function updateExpeditionSquadPowerLabel() {
  const el = expG("esm-squad-power");
  if (!el) return;
  const sq = expeditionSquadPowerTotal();
  const tier = (expeditionState.catalog?.depth_tiers || []).find((t) => t.tier === expeditionSend.depthTier);
  const need = tier ? tier.min_squad_power || 0 : 0;
  el.textContent = `Мощь отряда: ${sq}${need ? ` / нужно ${need}` : ""}`;
  renderExpTierSelect();
}

function expToggleSquadUnit(id) {
  const units = getAvailableUnits();
  const unit = units.find((u) => u.id === id);
  if (!unit || unit.expedition_id || unit.healing || unit.eligible === false) return;
  const idx = expeditionSend.squadSlots.findIndex((u) => u && u.id === id);
  if (idx >= 0) {
    expeditionSend.squadSlots[idx] = null;
  } else {
    const empty = expeditionSend.squadSlots.findIndex((u) => !u);
    if (empty < 0) return;
    expeditionSend.squadSlots[empty] = unit;
  }
  renderExpeditionSquadSlots();
  renderExpRosterPicker();
  updateExpeditionSquadPowerLabel();
  refreshExpeditionTagPreview();
}

function renderExpRosterPicker() {
  const list = expG("esm-unit-picker");
  if (!list) return;
  expPickerFilterState();
  renderExpPickerFilters();
  wireExpPickerTools();
  const search = expG("esm-picker-search");
  if (search && expeditionSend.pickerSearch != null && search.value !== expeditionSend.pickerSearch) {
    search.value = expeditionSend.pickerSearch;
  }
  const sortSel = expG("esm-picker-sort");
  if (sortSel && expeditionSend.pickerSort) sortSel.value = expeditionSend.pickerSort;

  const selectedIds = new Set(expeditionSend.squadSlots.filter(Boolean).map((u) => u.id));
  const allUnits = getAvailableUnits();
  const filter = expeditionSend.pickerFilter || "all";
  const q = (expeditionSend.pickerSearch || "").trim().toLowerCase();
  let units = allUnits;
  if (filter !== "all") {
    units = units.filter((u) => expPickerUnitStatus(u) === filter);
  }
  if (q) {
    units = units.filter((u) => String(u.name || "").toLowerCase().includes(q));
  }
  const selectedUnits = allUnits.filter((u) => selectedIds.has(u.id));
  const visibleSet = new Set(units.map((u) => u.id));
  const extraSelected = selectedUnits.filter((u) => !visibleSet.has(u.id));
  const ordered = expPickerSortUnits(units);
  extraSelected.forEach((u) => ordered.unshift(u));
  list.innerHTML =
    ordered
      .map((u) => {
        const inExp = u.expedition_id != null;
        const healing = Boolean(u.healing);
        const lowHp = u.eligible === false;
        const disabled = inExp || healing || lowHp;
        const selected = selectedIds.has(u.id);
        const hpM = u.hp_max ?? u.max_hp ?? 1;
        const hpC = u.current_hp ?? u.hp_current ?? hpM;
        const power = u.power != null ? u.power : "—";
        let note = inExp ? "🔒 В экспедиции" : healing ? "💊 Лечение" : lowHp ? "❤ Мало HP" : "Готова";
        if (healing && u.heal_complete_at) {
          note += ` · до ${new Date(u.heal_complete_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
        }
        const cid = Number(u.class ?? u.class_);
        const rid = Number(u.race);
        const cls = WAIFU_CLASSES.find((c) => c.id === cid);
        const race = WAIFU_RACES.find((r) => r.id === rid);
        const className = cls?.name || "—";
        const raceName = race?.name || "—";
        const cardCls = `exp-pick-card exp-pick-card--compact${disabled ? " exp-pick-card--disabled" : ""}${selected ? " exp-pick-card--match" : ""}`;
        const clickAttr = disabled ? "" : ` onclick="WaifuApp.expToggleSquadUnit(${u.id})"`;
        return `<div class="${cardCls}"${clickAttr}>
          <div class="exp-pick-compact-row">
            <div class="exp-pick-name">${escapeHtml(u.name || "")}${selected ? " ✓" : ""}</div>
            <div class="exp-pick-sub">${escapeHtml(note)}</div>
          </div>
          <div class="exp-pick-stats exp-pick-stats--compact">
            <span class="exp-pick-stat">⚔ ${power}</span>
            <span class="exp-pick-stat">❤ ${hpC}/${hpM}</span>
            <span class="exp-pick-stat">${escapeHtml(raceName)}</span>
            <span class="exp-pick-stat">${escapeHtml(className)}</span>
          </div>
        </div>`;
      })
      .join("") || '<div class="placeholder muted tiny">Нет наёмниц по фильтру</div>';
}

const EXP_PICKER_FILTERS = [
  { id: "all", label: "Все" },
  { id: "ready", label: "Готовы" },
  { id: "expedition", label: "В экспедиции" },
  { id: "healing", label: "Лечение" },
];

function expPickerFilterState() {
  if (!expeditionSend.pickerFilter) expeditionSend.pickerFilter = "all";
  if (!expeditionSend.pickerSort) expeditionSend.pickerSort = "level";
  if (expeditionSend.pickerSearch == null) expeditionSend.pickerSearch = "";
  return expeditionSend;
}

function renderExpPickerFilters() {
  const wrap = expG("esm-picker-filters");
  if (!wrap) return;
  const st = expPickerFilterState();
  wrap.innerHTML = EXP_PICKER_FILTERS.map(
    (f) => `<button type="button" class="exp-picker-filter-btn${st.pickerFilter === f.id ? " active" : ""}" data-picker-filter="${f.id}">${escapeHtml(f.label)}</button>`
  ).join("");
  wrap.querySelectorAll("[data-picker-filter]").forEach((b) => {
    b.addEventListener("click", () => {
      expeditionSend.pickerFilter = b.getAttribute("data-picker-filter");
      renderExpPickerFilters();
      renderExpRosterPicker();
    });
  });
}

function wireExpPickerTools() {
  const search = expG("esm-picker-search");
  const sort = expG("esm-picker-sort");
  if (search && !search.dataset.wired) {
    search.dataset.wired = "1";
    search.addEventListener("input", () => {
      expeditionSend.pickerSearch = search.value || "";
      renderExpRosterPicker();
    });
  }
  if (sort && !sort.dataset.wired) {
    sort.dataset.wired = "1";
    sort.value = expeditionSend.pickerSort || "level";
    sort.addEventListener("change", () => {
      expeditionSend.pickerSort = sort.value;
      renderExpRosterPicker();
    });
  }
}

function expPickerUnitStatus(u) {
  if (u.expedition_id != null) return "expedition";
  if (u.healing) return "healing";
  if (u.eligible === false) return "healing";
  return "ready";
}

function expPickerSortUnits(units) {
  const sortKey = expeditionSend.pickerSort || "level";
  const arr = units.slice();
  arr.sort((a, b) => {
    if (sortKey === "power") return (Number(b.power) || 0) - (Number(a.power) || 0);
    if (sortKey === "rarity") return (Number(b.rarity) || 0) - (Number(a.rarity) || 0);
    if (sortKey === "role") {
      const ar = String(a.class ?? a.class_ ?? "");
      const br = String(b.class ?? b.class_ ?? "");
      return ar.localeCompare(br);
    }
    return (Number(b.level) || 0) - (Number(a.level) || 0);
  });
  return arr;
}

function openActiveExpModal(raw) {
  expeditionUiCache._activeRaw = raw;
  expG("eam-title").textContent = raw.narrative_title || "—";
  const eamNarr = expG("eam-narrative-meta");
  if (eamNarr) eamNarr.innerHTML = expeditionNarrativeMetaHtml(raw);
  const affHtml = expeditionAffixChipsHtml(raw.affixes || [], raw.affix_level, true);
  expG("eam-affixes").innerHTML = affHtml;
  const img = expG("eam-img");
  const emo = expG("eam-emoji");
  if (emo) emo.textContent = raw.biome_emoji || "🗺";
  applyExpeditionBiomeBackground(img, raw.biome_tag, emo, raw.location_archetype_id);

  tickActiveModal();
  if (expActiveModalTimer) clearInterval(expActiveModalTimer);
  expActiveModalTimer = setInterval(tickActiveModal, 1000);

  const squad = raw.squad_snapshot || [];
  expG("eam-squad").innerHTML = squad.map(expeditionActiveUnitRow).join("");

  window._activeExpId = raw.id;
  const claimBtn = expG("eam-claim-btn");
  if (claimBtn) claimBtn.style.display = "none";
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
  if (claimBtn) claimBtn.style.display = canClaim ? "block" : "none";
}

function closeActiveExpModal() {
  if (expActiveModalTimer) {
    clearInterval(expActiveModalTimer);
    expActiveModalTimer = null;
  }
  expeditionUiCache._activeRaw = null;
  expCloseOverlay("exp-active-modal");
}

function openSendExpModal() {
  expeditionSend.rewardType = expeditionSend.rewardType || "gold";
  expeditionSend.depthTier = expeditionSend.depthTier || 1;
  expeditionSend.squadSlots = [null, null, null];
  renderExpRewardSelect();
  renderExpTierSelect();
  updateExpeditionSquadPowerLabel();
  const forecastEl = expG("esm-forecast");
  if (forecastEl) {
    forecastEl.classList.remove("exp-forecast--visible");
    forecastEl.innerHTML = "";
  }
  const warnEl = expG("esm-send-warnings");
  if (warnEl) warnEl.textContent = "";
  renderExpeditionSquadSlots();
  updateExpConfirmPanel(null);
  expOpenOverlay("exp-send-modal");
}

function openExpRosterModal() {
  expOpenOverlay("exp-roster-modal");
  ensureExpeditionRoster()
    .then(() => renderExpRosterPicker())
    .catch(() => renderExpRosterPicker());
}

function closeExpRosterModal() {
  expCloseOverlay("exp-roster-modal");
  renderExpeditionSquadSlots();
  updateExpeditionSquadPowerLabel();
  refreshExpeditionTagPreview();
}

function closeSendExpModal() {
  if (expeditionSendInFlight) return;
  closeExpRosterModal();
  expCloseOverlay("exp-send-modal");
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
      slot.onclick = () => expToggleSquadUnit(unit.id);
    } else {
      slot.className = "exp-squad-slot";
      slot.innerHTML = '<span class="exp-squad-empty">＋</span>';
      slot.onclick = () => openExpRosterModal();
    }
  }
  const btn = expG("exp-send-btn");
  const tier = (expeditionState.catalog?.depth_tiers || []).find((t) => t.tier === expeditionSend.depthTier);
  const sqPower = expeditionSquadPowerTotal();
  const powerOk = !tier || sqPower >= (tier.min_squad_power || 0);
  const hasSquad = expeditionSend.squadSlots.some((s) => s);
  if (btn) btn.disabled = !hasSquad || !powerOk;
  refreshExpeditionTagPreview();
}

async function submitExpeditionStart() {
  if (expeditionSendInFlight) return;
  const unitIds = expeditionSend.squadSlots.filter(Boolean).map((u) => u.id);
  if (!unitIds.length) {
    showExpeditionError("Выберите отряд (1–3 наёмницы).");
    return;
  }
  const savedReward = expeditionSend.rewardType;
  const savedTier = expeditionSend.depthTier;
  const savedSquad = expeditionSend.squadSlots.slice();
  const sendBtn = expG("exp-send-btn");
  closeSendExpModal();
  expeditionSendInFlight = true;
  if (sendBtn) {
    sendBtn.disabled = true;
    sendBtn.setAttribute("aria-busy", "true");
  }
  openExpeditionSendLoading();
  try {
    await apiFetch("/expeditions/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        unit_ids: unitIds,
        reward_type: expeditionSend.rewardType,
        depth_tier: expeditionSend.depthTier,
      }),
    });
    if (expSendLoadingInterval) {
      clearInterval(expSendLoadingInterval);
      expSendLoadingInterval = null;
    }
    const fill = document.getElementById("exp-send-loading-fill");
    const sub = document.getElementById("exp-send-loading-sub");
    if (fill) fill.style.width = "100%";
    if (sub) sub.textContent = "Отряд вышел в поход!";
    await new Promise((r) => setTimeout(r, 300));
    closeExpeditionSendLoading();
    showExpeditionError("");
    await loadExpeditionTab({ force: true });
    document.getElementById("exp-active-section")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) {
    closeExpeditionSendLoading();
    const { detail } = parseHttpErrorDetail(e);
    showExpeditionError(detail || "Ошибка запуска экспедиции");
    openSendExpModal();
    expeditionSend.rewardType = savedReward;
    expeditionSend.depthTier = savedTier;
    expeditionSend.squadSlots = savedSquad;
    renderExpRewardSelect();
    renderExpTierSelect();
    renderExpeditionSquadSlots();
  } finally {
    expeditionSendInFlight = false;
    if (sendBtn) sendBtn.removeAttribute("aria-busy");
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

  // Таблица тиров I–V: из каталога, со статичным fallback
  const tiers = expeditionState.catalog?.depth_tiers || [];
  const tierTableHtml = tiers.length
    ? expTierCheatsheetHtml(tiers)
    : `<table class="exp-tier-cheatsheet-table"><thead><tr><th>Тир</th><th>Название</th><th>Длит.</th><th>Событий</th><th>Мощь</th><th>Урон</th></tr></thead><tbody>
      <tr><td><strong>I</strong></td><td>Разведка</td><td>60 мин</td><td>2</td><td>⚔0</td><td>6%/тик</td></tr>
      <tr><td><strong>II</strong></td><td>Патруль</td><td>90 мин</td><td>3</td><td>⚔80</td><td>10%/тик</td></tr>
      <tr><td><strong>III</strong></td><td>Поход</td><td>120 мин</td><td>4</td><td>⚔150</td><td>15%/тик</td></tr>
      <tr><td><strong>IV</strong></td><td>Рейд</td><td>180 мин</td><td>6</td><td>⚔220</td><td>20%/тик</td></tr>
      <tr><td><strong>V</strong></td><td>В глубину</td><td>240 мин</td><td>8</td><td>⚔300</td><td>28%/тик</td></tr>
      </tbody></table>`;

  return `
    <p><strong>Слоты.</strong> До 3 параллельных экспедиций одновременно. Состав — 1–3 наёмницы, HP ≥ 25% для участия.</p>
    <p><strong>Тиры глубины I–V.</strong> Определяют длительность, число событий, рекоменд. мощность и урон за тик. Недостаточная мощность блокирует выбор тира.</p>
    ${tierTableHtml}
    <p><strong>Тики.</strong> События равномерно распределены по длительности (≈30 мин на событие). Больше событий — выше риск по HP, но больше награда.</p>
    <p><strong>Исход.</strong> Считается по остатку HP отряда после всех тиков (не предролл-шанс): &lt;12% — <span style="color:#f87171">провал</span>, ≥52% — <span style="color:#4ade80">успех</span>, иначе — <span style="color:#fbbf24">частичный</span> (награда ×0.7).</p>
    <p><strong>Теги/аффиксы сложности (8).</strong> Генерируются <em>случайно после старта</em> экспедиции — на этапе формирования игроку неизвестны. Покрытие тегов отрядом (раса/класс/перк) снижает урон. Влияние каждого тега раскрывается в логе результата.</p>
    <p><strong>Твисты (~10%).</strong> Случайные события: treasure (награда), rest (восстановление HP), skip damage (пропуск урона) и др.</p>
    <p><strong>Типы наград (6).</strong> 💰 Золото · ✨ Опыт вайфу · ⚔ Снаряжение · 🔮 Камни заточки · 📖 Опыт наёмниц · 🎁 Смешанная.</p>
    <p><strong>Мощность наёмницы.</strong> <code>RARITY_BASE + (level−1)×3</code> (Common 40 → Legendary 120). Рекоменд. пороги: 0 / 80 / 150 / 220 / 300.</p>
    <p><strong>Лечение.</strong> После экспедиции раненые наёмницы лечатся автоматически: 0.8 мин за 1% потерянного HP (×1.5 при HP=0).</p>
    <p><strong>Перки.</strong> Прокачка во вкладке ⬆ LVL таверны (очки за лвлап после экспедиции). Эффективность перка против уровня препятствия:</p>
    <table class="exp-help-table" aria-label="Эффективность перка">
      <thead><tr><th>Перк↓ / Ур.→</th><th>I</th><th>II</th><th>III</th><th>IV</th><th>V</th></tr></thead>
      <tbody>${effRows}</tbody>
    </table>
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

function showExpeditionResultModal(opts = {}) {
  const showLoading = Boolean(opts.loading);
  const showContent = Boolean(opts.content);
  const modal = document.getElementById("expedition-result-modal");
  const loading = document.getElementById("exp-result-loading");
  const content = document.getElementById("exp-result-content");
  if (!modal || !loading || !content) return false;
  modal.style.display = "flex";
  loading.style.display = showLoading ? "flex" : "none";
  content.style.display = showContent ? "block" : "none";
  return true;
}

async function claimAndShowExpeditionResult(expeditionId, resultReady) {
  if (expeditionClaimInFlight) return;
  expeditionClaimInFlight = true;
  showExpeditionResultModal({ loading: !resultReady });
  try {
    const result = await apiFetch(`/expeditions/${expeditionId}/claim`, { method: "POST" });
    fillExpeditionResult(result);
    showExpeditionResultModal({ content: true });
    await loadExpeditionTab({ force: true });
    loadProfile().catch(() => {});
  } catch (e) {
    const modal = document.getElementById("expedition-result-modal");
    if (modal) modal.style.display = "none";
    const { detail } = parseHttpErrorDetail(e);
    showToast(detail || e?.message || "Ошибка получения наград", "error");
    loadExpeditionTab({ force: true }).catch(() => {});
  } finally {
    expeditionClaimInFlight = false;
  }
}

async function openExpeditionResult(expeditionId) {
  await claimAndShowExpeditionResult(expeditionId, false);
}

function expGateLogEntryHtml(g) {
  const idx = g.index != null ? `#${g.index}` : "";
  const cat = escapeHtml(g.category_label || g.category || "—");
  const dmg = Number(g.damage) || 0;
  const dmgCls = dmg > 0 ? "exp-gate-log-dmg" : "exp-gate-log-dmg exp-gate-log-dmg--zero";
  const dmgTxt = dmg > 0 ? `−${dmg} HP` : "0 HP";
  const statusTxt = g.covered ? "пройдено" : "урон";
  const head = `<div class="exp-gate-log-head"><span><span class="exp-gate-log-cat">${idx} ${cat}</span> · ${escapeHtml(statusTxt)}</span><span class="${dmgCls}">${dmgTxt}</span></div>`;
  const mathParts = [];
  if (g.base_pct != null) mathParts.push(`<span>база ${g.base_pct}%</span>`);
  if (g.coverage != null) {
    const covPct = Math.round((Number(g.coverage) || 0) * 100);
    mathParts.push(`<span>покрытие ${covPct}%</span>`);
  }
  if (g.tag_mult != null) mathParts.push(`<span>теги ×${g.tag_mult}</span>`);
  if (g.challenge_adj != null) {
    const sign = g.challenge_adj > 0 ? "+" : "";
    mathParts.push(`<span>вызов ${sign}${Math.round((g.challenge_adj) * 100)}%</span>`);
  }
  if (g.variance != null) mathParts.push(`<span>разброс ×${g.variance}</span>`);
  // Итоговый множитель урона
  const tagM = Number(g.tag_mult) || null;
  const chAdj = Number(g.challenge_adj) || 0;
  const vari = Number(g.variance) || null;
  if (tagM != null && vari != null) {
    const total = tagM * (1 + chAdj) * vari;
    mathParts.push(`<span style="color:#e8b84b">→ итог ×${total.toFixed(2)}</span>`);
  }
  if (g.twist) mathParts.push(`<span class="exp-gate-log-twist">★ ${escapeHtml(g.twist)}</span>`);
  const mathHtml = mathParts.length ? `<div class="exp-gate-log-math">${mathParts.join("")}</div>` : "";
  const tagsArr = Array.isArray(g.active_tags) ? g.active_tags : [];
  const covArr = Array.isArray(g.covered_tags) ? g.covered_tags : [];
  let tagsHtml = "";
  if (tagsArr.length) {
    const covSet = new Set(covArr.map((t) => String(t)));
    const TAG_LABEL_RU = {
      cursed: "Проклятия", undead: "Нежить", beasts: "Звери", constructs: "Конструкты",
      hazard: "Опасности", arcane: "Магия", poison: "Яды", terrain: "Местность",
    };
    const chips = tagsArr.map((t) => {
      const label = escapeHtml(TAG_LABEL_RU[t] || t);
      const ok = covSet.has(String(t));
      return `<span style="color:${ok ? "#4ade80" : "#f87171"}">${ok ? "✓" : "✗"}${label}</span>`;
    });
    tagsHtml = `<div class="exp-gate-log-tags">Сложности: ${chips.join(" · ")}</div>`;
  }
  return `<li>${head}${tagsHtml}${mathHtml}</li>`;
}

function expGateLogSummaryHtml(result, gateLog) {
  // Итоговый HP-остаток и порог исхода
  const totalDmg = gateLog.reduce((s, g) => s + (Number(g.damage) || 0), 0);
  const outcome = result.outcome || "failure";
  const outcomeTxt = outcome === "success" ? "Успех (HP ≥ 52%)" : outcome === "partial_success" ? "Частичный (HP 12–52%)" : "Провал (HP < 12%)";
  const outcomeColor = outcome === "success" ? "#4ade80" : outcome === "partial_success" ? "#fbbf24" : "#f87171";
  const squad = Array.isArray(result.squad_state) ? result.squad_state : [];
  const totalMax = squad.reduce((s, u) => s + (Number(u.hp_max) || 0), 0);
  const totalCur = squad.reduce((s, u) => s + (Number(u.hp_current) || 0), 0);
  const hpPct = totalMax > 0 ? Math.round((totalCur / totalMax) * 100) : null;
  const hpLine = hpPct != null ? `Остаток HP отряда: <strong style="color:${outcomeColor}">${hpPct}%</strong> → ${escapeHtml(outcomeTxt)}` : escapeHtml(outcomeTxt);
  return `<li class="exp-gate-log-summary">Суммарный урон: <strong>−${totalDmg} HP</strong>. ${hpLine}.</li>`;
}

let expResultSquadState = [];

function expResultRewardRow(label, valueHtml, mult) {
  const multHtml = mult ? `<span class="exp-result-reward-mult">${mult}</span>` : "";
  return `<div class="exp-result-reward-row">
    <span class="exp-result-reward-label">${escapeHtml(label)}</span>
    <span class="exp-result-reward-inline">${valueHtml}${multHtml}</span>
  </div>`;
}

function expResultItemThumbHtml(item) {
  if (typeof itemArtHtml === "function") {
    return itemArtHtml(item, { lazy: true });
  }
  if (typeof itemIconForSlotType === "function") {
    return itemIconForSlotType(item.slot_type) || "🎁";
  }
  return "🎁";
}

function expResultItemRewardRow(item) {
  const invId = item.inventory_item_id ?? item.id ?? null;
  const name = item.display_name || item.name || "—";
  const thumb = expResultItemThumbHtml(item);
  const rc = typeof rarityClass === "function" ? rarityClass(item.rarity) : "";
  const clickAttr = invId
    ? `role="button" tabindex="0" data-exp-result-item-id="${invId}" onclick="event.stopPropagation();WaifuApp.viewRewardItem(${invId})"`
    : "";
  return `<div class="exp-result-reward-row exp-result-reward-row--item ${rc}" ${clickAttr}>
    <span class="exp-result-reward-label">Предмет</span>
    <span class="exp-result-reward-inline exp-result-reward-item-inline">
      <span class="exp-result-item-thumb">${thumb}</span>
      <span class="exp-result-item-name">${escapeHtml(name)}</span>
    </span>
  </div>`;
}

async function hydrateExpResultItemThumbs(items) {
  const needsFetch = (items || []).filter(
    (it) => (it.inventory_item_id ?? it.id) && !it.art_key && !it.image_key
  );
  if (!needsFetch.length) return;
  await Promise.all(
    needsFetch.map(async (it) => {
      const invId = it.inventory_item_id ?? it.id;
      try {
        const full = await apiFetch(`/inventory/${invId}`);
        Object.assign(it, {
          slot_type: full.slot_type,
          art_key: full.art_key,
          image_key: full.image_key,
          tier: full.tier,
          display_name: full.display_name || full.name,
          rarity: full.rarity,
        });
        const row = document.querySelector(`[data-exp-result-item-id="${invId}"] .exp-result-item-thumb`);
        if (row) row.innerHTML = expResultItemThumbHtml(it);
      } catch {
        /* ignore */
      }
    })
  );
}

function renderExpResultSquad(squadState) {
  const squadEl = document.getElementById("exp-result-squad");
  if (!squadEl) return;
  squadEl.innerHTML = (squadState || [])
    .map((u) => {
      const hpPct = u.hp_max ? Math.round((u.hp_current / u.hp_max) * 100) : 100;
      const needsHeal = u.hp_current < u.hp_max && !u.healing;
      let healTxt = " · ✓ Здорова";
      if (u.healing) {
        const mins = u.heal_minutes ?? u.heal_forecast_minutes;
        healTxt = mins != null
          ? ` · <span style="color:#60a5fa">💊 На лечении ~${mins} мин</span>`
          : ' · <span style="color:#60a5fa">💊 На лечении</span>';
      } else if (needsHeal && u.heal_forecast_minutes != null) {
        healTxt = ` · <span style="color:#60a5fa">💊 Лечение ~${u.heal_forecast_minutes} мин</span>`;
      } else if (needsHeal) {
        healTxt = ' · <span style="color:#f87171">Нужно лечение</span>';
      }
      return `
          <div class="exp-result-unit">
            <div class="exp-result-unit-info">
              <div class="exp-result-unit-name">${escapeHtml(u.name || "—")}</div>
              <div class="exp-result-unit-stats">
                ❤ ${u.hp_current}/${u.hp_max}${healTxt}
                ${u.leveled_up ? ' · <span style="color:#4ade80">⭐ Новый уровень!</span>' : ""}
              </div>
            </div>
            <div class="exp-result-unit-bar">
              <div class="exp-result-unit-bar-fill" style="width:${hpPct}%"></div>
            </div>
          </div>`;
    })
    .join("");

  const healBtn = document.getElementById("exp-result-heal-btn");
  if (healBtn) {
    const hasWounded = (squadState || []).some((u) => u.hp_current < u.hp_max && u.hired_waifu_id && !u.healing);
    healBtn.style.display = hasWounded ? "" : "none";
    healBtn.disabled = false;
    healBtn.textContent = "💊 Отправить на лечение";
    healBtn.onclick = (ev) => {
      ev?.stopPropagation?.();
      healExpeditionSquad(expResultSquadState);
    };
  }
}

function fillExpeditionResult(result) {
  const OUTCOME_CONFIG = {
    success: { icon: "✅", title: "Успешно завершена!", color: "#4ade80", mult: "×1.0", cls: "exp-result-sheet--success" },
    partial_success: { icon: "⚠️", title: "Завершена с потерями", color: "#facc15", mult: "×0.7", cls: "exp-result-sheet--partial" },
    failure: { icon: "❌", title: "Провал", color: "#f87171", mult: "×0.4", cls: "exp-result-sheet--failure" },
  };
  const cfg = OUTCOME_CONFIG[result.outcome] || OUTCOME_CONFIG.partial_success;

  // Цветная рамка модалки по исходу (вместо крупного баннера)
  const sheet = document.querySelector("#expedition-result-modal .exp-result-sheet");
  if (sheet) {
    sheet.classList.remove("exp-result-sheet--success", "exp-result-sheet--partial", "exp-result-sheet--failure");
    sheet.classList.add(cfg.cls);
  }

  const gateWrap = document.getElementById("exp-result-gate-log-wrap");
  const gateList = document.getElementById("exp-result-gate-log");
  const gateLog = Array.isArray(result.gate_log) ? result.gate_log : [];
  if (gateWrap && gateList) {
    if (gateLog.length) {
      gateList.innerHTML = gateLog.map((g) => expGateLogEntryHtml(g)).join("") + expGateLogSummaryHtml(result, gateLog);
      gateWrap.style.display = "";
      const sum = gateWrap.querySelector("summary");
      if (sum) sum.textContent = "Лог препятствий — влияние сложностей на математику";
    } else {
      gateWrap.style.display = "none";
      gateList.innerHTML = "";
    }
  }

  // Вся награда (включая предметы) — в едином поле «Награда»
  const rewardsEl = document.getElementById("exp-result-rewards");
  if (rewardsEl) {
    const rt = result.reward_type || "gold";
    const rows = [];
    if (result.gold_earned > 0 || rt === "gold" || rt === "mixed") {
      rows.push(expResultRewardRow("Золото", `🪙 ${result.gold_earned ?? 0}`, cfg.mult));
    }
    if (result.exp_earned > 0 || rt === "merc_exp" || rt === "mixed") {
      rows.push(expResultRewardRow("Опыт наёмниц", `✨ ${result.exp_earned ?? 0}`, cfg.mult));
    }
    if (result.waifu_exp_gained > 0 || rt === "waifu_exp") {
      rows.push(expResultRewardRow("Опыт основной вайфу", `⭐ ${result.waifu_exp_gained ?? 0}`));
    }
    if (result.enchant_stones > 0 || rt === "enchant") {
      rows.push(expResultRewardRow("Камни заточки", `💎 ${result.enchant_stones ?? 0}`));
    }
    const items = Array.isArray(result.items_earned) ? result.items_earned : [];
    for (const item of items) {
      rows.push(expResultItemRewardRow(item));
    }
    if (!rows.length) {
      if (rt === "items") {
        rows.push(expResultRewardRow("Награда", `<span class="muted">Предметы не выпали</span>`));
      } else {
        rows.push(expResultRewardRow("Награда", `<span class="muted">—</span>`));
      }
    }
    rewardsEl.innerHTML = rows.join("");
    hydrateExpResultItemThumbs(items).catch(() => {});
  }

  expResultSquadState = Array.isArray(result.squad_state) ? result.squad_state.map((u) => ({ ...u })) : [];
  renderExpResultSquad(expResultSquadState);
}

async function healExpeditionSquad(squadState) {
  const wounded = (squadState || []).filter(
    (u) => u.hp_current < u.hp_max && u.hired_waifu_id && !u.healing
  );
  if (!wounded.length) {
    showToast?.("Лечение не требуется", "info");
    return;
  }

  const modal = document.getElementById("expedition-result-modal");
  const btn = document.getElementById("exp-result-heal-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Лечение...";
  }
  const errors = [];
  for (const u of wounded) {
    try {
      const res = await apiFetch(`/tavern/heal?hired_waifu_id=${u.hired_waifu_id}`, { method: "POST" });
      if (res?.error) {
        errors.push(`${u.name}: ${res.error}`);
      } else {
        u.healing = true;
        u.heal_minutes = res?.heal_minutes ?? u.heal_forecast_minutes;
      }
    } catch (e) {
      const { detail } = parseHttpErrorDetail(e);
      errors.push(`${u.name}: ${detail || "ошибка"}`);
    }
  }
  expResultSquadState = squadState;
  renderExpResultSquad(expResultSquadState);
  if (modal) modal.style.display = "flex";

  if (errors.length) {
    showToast?.(`Часть не вылечена: ${errors.join("; ")}`, "danger");
  }
  await loadExpeditionTab({ force: true }).catch(() => {});
  if (typeof loadProfile === "function") await loadProfile().catch(() => {});
  if (modal) modal.style.display = "flex";
}

function closeExpeditionResult() {
  const modal = document.getElementById("expedition-result-modal");
  if (modal) modal.style.display = "none";
  loadExpeditionTab({ force: true }).catch(() => {});
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

async function adminGenerateExpeditionArt(btn) {
  if (!isAdminUser() || !btn) return;
  const kind = btn.getAttribute("data-exp-kind") || "daily";
  const expId = btn.getAttribute("data-exp-id");
  const archetypeId = btn.getAttribute("data-archetype-id") || "";
  if (!expId) return;
  const prev = btn.textContent;
  btn.disabled = true;
  btn.textContent = "⏳";
  try {
    const qs =
      kind === "active"
        ? `active_id=${encodeURIComponent(expId)}&archetype_id=${encodeURIComponent(archetypeId)}`
        : `slot_id=${encodeURIComponent(expId)}&archetype_id=${encodeURIComponent(archetypeId)}`;
    const payload = await apiFetch(`/admin/expedition-art/generate?${qs}`, { method: "POST" });
    const arch = String(payload?.archetype_id || archetypeId || "")
      .trim()
      .toLowerCase();
    if (arch) {
      const cache = window.expeditionArchetypeArtVersion || (window.expeditionArchetypeArtVersion = {});
      cache[arch] = Date.now();
    }
    wireExpeditionCardBiomes(document.getElementById("exp-active-grid"));
    const openActive = expeditionUiCache._activeRaw;
    if (openActive && String(openActive.location_archetype_id || "").toLowerCase() === arch) {
      applyExpeditionBiomeBackground(
        expG("eam-img"),
        openActive.biome_tag,
        expG("eam-emoji"),
        openActive.location_archetype_id,
      );
    }
    showToast("Арт экспедиции сгенерирован", "success");
  } catch (e) {
    const msg = (e && e.message) || parseHttpErrorDetail(e).detail || "Ошибка генерации арта";
    showToast(msg, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = prev || "🎨";
  }
}

// ===========================================================================
// Бездна (Abyss)
// ===========================================================================

let abyssRefreshTimer = null;
let abyssState = null;
let abyssCheckpointShown = false;

const ABYSS_MODIFIER_BADGE = {
  BLESSED: { icon: "✨", cls: "abyss-mod-blessed" },
  CURSED: { icon: "💀", cls: "abyss-mod-cursed" },
  RAGE: { icon: "🔥", cls: "abyss-mod-rage" },
  DARK: { icon: "🌑", cls: "abyss-mod-dark" },
  ECHO: { icon: "👻", cls: "abyss-mod-echo" },
};

async function loadAbyssTab() {
  const root = document.getElementById("abyss-root");
  if (!root) return;
  try {
    const st = await apiFetch("/abyss/status");
    const prev = abyssState;
    abyssState = st;
    renderAbyss(st);
    if (st.pending_grace_choices && st.pending_grace_choices.length) {
      openAbyssGraceModal(st.pending_grace_choices);
    }
    // Reflect Abyss session in the shared header chip (mutually exclusive with solo).
    if (typeof renderAtticDungeon === "function" && st.session_active) {
      const m = st.current_monster || {};
      renderAtticDungeon({
        abyss_active: true,
        abyss_floor: st.current_floor,
        monster_current_hp: Number(m.hp_current || 0),
        monster_max_hp: Number(m.hp_max || 1),
      });
    }
    // Celebrate a freshly cleared checkpoint once.
    if (prev && Number(st.current_checkpoint || 0) > Number(prev.current_checkpoint || 0)) {
      openAbyssCheckpointModal(Number(st.current_checkpoint || 0));
    }
  } catch (e) {
    const { detail } = parseHttpErrorDetail(e);
    root.innerHTML = `<div class="banner">Не удалось загрузить Бездну: ${escapeHtml(detail || String(e?.message || e))}</div>`;
  }
}

function abyssHpBar(cur, max, fillClass) {
  const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((cur / max) * 100))) : 0;
  return `
    <div class="hp-bar-wrap abyss-hpbar-labeled">
      <div class="hp-bar-labels">
        <span class="hp-bar-label-value">${Math.max(0, cur)} / ${max}</span>
      </div>
      <div class="hp-bar">
        <div class="hp-fill ${fillClass}" style="width:${pct}%"></div>
      </div>
    </div>`;
}

function abyssAffixColorClass(monster) {
  const n = Number(monster.affix_count) || (monster.affixes || []).length;
  if (n >= 4) return "red";
  if (n >= 3) return "gold";
  return monster.is_elite ? "gold" : "blue";
}

function abyssModifierBadge(modifier, label, desc) {
  if (!modifier) return "";
  const b = ABYSS_MODIFIER_BADGE[modifier] || { icon: "", cls: "" };
  return `<div class="abyss-modifier-badge ${b.cls}" title="${escapeHtml(desc || "")}">${b.icon} ${escapeHtml(label || modifier)}</div>`;
}

function renderAbyss(st) {
  const root = document.getElementById("abyss-root");
  if (!root) return;

  if (!st.is_available) {
    root.innerHTML = `
      <div class="card card--locked">
        <div class="abyss-hero-icon">🕳️</div>
        <h3>Бездна закрыта</h3>
        <p class="muted">${escapeHtml(st.unavailable_reason || "Недоступно")}</p>
      </div>`;
    return;
  }

  if (!st.session_active) {
    root.innerHTML = abyssLobbyHtml(st);
    return;
  }

  root.innerHTML = abyssBattleHtml(st);
}

function abyssLobbyHtml(st) {
  const record = Number(st.max_floor_reached || 0);
  const checkpoint = Number(st.current_checkpoint || 0);
  const resumeFloor = checkpoint > 0 ? checkpoint + 1 : 1;
  const btnLabel = checkpoint > 0 ? `Продолжить (этаж ${resumeFloor})` : "Начать спуск";
  const limitUsed = Number(st.checkpoints_today || 0);
  const limit = Number(st.daily_limit || 0);
  const shards = Number(st.abyss_shards || 0);
  return `
    <div class="card">
      <div class="abyss-lobby-head">
        <div class="abyss-lobby-icon">🕳️</div>
        <div>
          <h3>Бездна</h3>
          <div class="muted tiny">Бесконечный спуск. Каждое сообщение в чате — удар.</div>
        </div>
      </div>
      <div class="abyss-stats-grid">
        <div class="abyss-stat"><div class="muted tiny">Рекорд</div><div class="abyss-stat-value">🏆 ${record}</div></div>
        <div class="abyss-stat"><div class="muted tiny">Последний чекпоинт</div><div class="abyss-stat-value">🏛 ${checkpoint}</div></div>
        <div class="abyss-stat"><div class="muted tiny">Осколки Бездны</div><div class="abyss-stat-value">🔮 ${shards}</div></div>
        <div class="abyss-stat"><div class="muted tiny">Чекпоинты сегодня</div><div class="abyss-stat-value">${limitUsed} / ${limit}</div></div>
      </div>
      <button class="primary btn-block" onclick="WaifuApp.abyssEnter()">${escapeHtml(btnLabel)}</button>
      <div class="abyss-actions-row">
        <button class="secondary" onclick="WaifuApp.openAbyssLeaderboard()">🏆 Топ недели</button>
        <button class="secondary" onclick="WaifuApp.openAbyssShop()">🔮 Магазин</button>
      </div>
    </div>`;
}

function abyssBattleHtml(st) {
  const m = st.current_monster || {};
  const floor = Number(st.current_floor || 0);
  const badges = [];
  if (m.is_boss) badges.push(`<span class="badge abyss-badge-boss">👑 Босс</span>`);
  if (m.is_elite) badges.push(`<span class="badge abyss-badge-elite">⭐ Элита</span>`);
  const affixColor = abyssAffixColorClass(m);
  const affixChips = (m.affixes || [])
    .map((a) => `<span class="affix-chip ${affixColor}">${escapeHtml(a.name)}</span>`)
    .join("");
  const grace = st.active_grace;
  const graceHtml = grace
    ? `<div class="abyss-grace-active">${escapeHtml(grace.icon || "✨")} <b>${escapeHtml(grace.name)}</b> — ${escapeHtml(grace.effect_label || grace.description || "")}</div>`
    : "";
  const modifierHtml = st.current_floor_modifier
    ? abyssModifierBadge(st.current_floor_modifier, st.modifier_label, st.modifier_description)
    : "";
  const warning = m.warning_text
    ? `<div class="banner banner--warning">⚠️ ${escapeHtml(m.warning_text)}</div>`
    : "";
  const unconscious = st.waifu_unconscious;
  const reviveBtn = unconscious
    ? `<button type="button" class="primary btn-block abyss-revive-btn" onclick="WaifuApp.abyssRevive()">🔮 Воскресить за Осколки</button>`
    : "";
  const unconsciousBanner = unconscious
    ? `<div class="banner banner--danger">😵 ОВ без сознания. HP восстанавливается со временем — атаки возобновятся автоматически.</div>`
    : "";

  return `
    <div class="card">
      <div class="abyss-battle-head">
        <div><span class="muted tiny">Этаж</span> <span class="abyss-floor-num">${floor}</span></div>
        <button class="dungeon-tab-sm" title="Покинуть Бездну" onclick="WaifuApp.openAbyssExitModal()">🏳️</button>
      </div>
      <div class="abyss-modifiers">${modifierHtml}</div>
      ${graceHtml}
      ${warning}
      ${unconsciousBanner}
      <div class="abyss-monster">
        <div class="abyss-monster-head">
          <div class="abyss-monster-name">${escapeHtml(m.name || "Монстр")} ${badges.join(" ")}</div>
          <div class="muted tiny">ур. ${Number(m.level || 1)}</div>
        </div>
        <div class="abyss-affixes">${affixChips}</div>
        ${abyssHpBar(Number(m.hp_current || 0), Number(m.hp_max || 1), "hp-fill-monster")}
      </div>
      <div class="abyss-waifu">
        <div class="muted tiny">Ваша ОВ</div>
        ${abyssHpBar(Number(st.waifu_hp || 0), Number(st.waifu_max_hp || 1), "hp-fill-waifu")}
      </div>
      ${reviveBtn}
      <p class="muted tiny abyss-hint">✍️ Пишите в групповой чат — каждое сообщение наносит урон.</p>
    </div>`;
}

async function abyssEnter() {
  try {
    const res = await apiFetch("/abyss/enter", { method: "POST" });
    if (!res.success) {
      showToast(res.reason || "Не удалось войти в Бездну", "error");
    }
  } catch (e) {
    showToast("Ошибка входа: " + (e?.message || e), "error");
  }
  abyssCheckpointShown = false;
  await loadAbyssTab();
}

function openAbyssExitModal() {
  const modal = document.getElementById("abyss-exit-modal");
  const txt = document.getElementById("abyss-exit-text");
  if (txt && abyssState) {
    const lost = Math.max(0, Number(abyssState.current_floor || 0) - Number(abyssState.current_checkpoint || 0));
    txt.textContent = `Прогресс текущего блока (${lost} эт.) сбросится до чекпоинта ${Number(abyssState.current_checkpoint || 0)}. Осколки и опыт остаются с вами.`;
  }
  if (modal) modal.style.display = "flex";
}

function closeAbyssExitModal() {
  const modal = document.getElementById("abyss-exit-modal");
  if (modal) modal.style.display = "none";
}

async function confirmAbyssExit() {
  closeAbyssExitModal();
  try {
    await apiFetch("/abyss/exit", { method: "POST" });
  } catch (e) {
    showToast("Ошибка выхода: " + (e?.message || e), "error");
  }
  await loadAbyssTab();
}

function openAbyssGraceModal(choices) {
  const modal = document.getElementById("abyss-grace-modal");
  const wrap = document.getElementById("abyss-grace-options");
  if (!modal || !wrap) return;
  wrap.innerHTML = (choices || []).map((g) => `
    <button type="button" class="abyss-grace-option" onclick="WaifuApp.chooseAbyssGrace(${Number(g.id)})">
      <div class="abyss-grace-option-title">${escapeHtml(g.icon || "✨")} ${escapeHtml(g.name)}</div>
      <div class="muted tiny abyss-grace-option-desc">${escapeHtml(g.effect_label || g.description || "")}</div>
    </button>`).join("");
  modal.style.display = "flex";
}

function closeAbyssGraceModal() {
  const modal = document.getElementById("abyss-grace-modal");
  if (modal) modal.style.display = "none";
}

async function chooseAbyssGrace(graceId) {
  try {
    const res = await apiFetch("/abyss/grace/choose", {
      method: "POST",
      body: JSON.stringify({ grace_id: Number(graceId) }),
    });
    if (!res.success) {
      showToast(res.error || "Не удалось выбрать Благодать", "error");
      return;
    }
    closeAbyssGraceModal();
  } catch (e) {
    showToast("Ошибка выбора: " + (e?.message || e), "error");
  }
  await loadAbyssTab();
}

function openAbyssCheckpointModal(floor) {
  const modal = document.getElementById("abyss-checkpoint-modal");
  const title = document.getElementById("abyss-checkpoint-title");
  const body = document.getElementById("abyss-checkpoint-body");
  if (!modal || !body) return;
  if (title) title.textContent = `🏛 Чекпоинт ${floor} пройден!`;
  body.innerHTML = `
    <p class="abyss-checkpoint-lead">Босс повержен, прогресс сохранён.</p>
    <p class="muted tiny abyss-checkpoint-note">Награды (осколки и предмет) начислены — подробности в личке бота.
    Выберите Благодать, чтобы продолжить спуск.</p>`;
  modal.style.display = "flex";
}

function closeAbyssCheckpointModal() {
  const modal = document.getElementById("abyss-checkpoint-modal");
  if (modal) modal.style.display = "none";
}

async function abyssRevive() {
  try {
    const res = await apiFetch("/abyss/revive", { method: "POST" });
    if (!res.success) {
      const labels = {
        INSUFFICIENT_SHARDS: "Недостаточно осколков",
        LIMIT_REACHED: "Лимит свитков на блок исчерпан",
        NOT_UNCONSCIOUS: "ОВ не без сознания",
      };
      showToast(labels[res.error] || res.error || "Не удалось воскресить", "error");
    } else {
      showToast("ОВ воскрешена!", "success");
    }
  } catch (e) {
    showToast("Ошибка: " + (e?.message || e), "error");
  }
  await loadAbyssTab();
}

async function openAbyssLeaderboard() {
  try {
    const data = await apiFetch("/abyss/leaderboard?limit=50");
    const rows = (data.entries || []).map((e) => `
      <div class="abyss-list-row${e.is_me ? " abyss-list-row--me" : ""}">
        <span>${e.rank}. ${escapeHtml(e.name)}</span>
        <span class="abyss-list-row-floor">🕳️ ${e.max_floor}</span>
      </div>`).join("") || `<div class="muted abyss-list-empty">Пока пусто</div>`;
    const myRank = data.my_rank ? `<p class="muted tiny">Ваше место: ${data.my_rank}</p>` : "";
    showAbyssBottomSheet("🏆 Лидерборд недели", rows + myRank);
  } catch (e) {
    showToast("Не удалось загрузить лидерборд: " + (e?.message || e), "error");
  }
}

async function openAbyssShop() {
  try {
    const data = await apiFetch("/abyss/shop");
    const items = (data.items || []).map((it) => `
      <div class="abyss-list-row abyss-shop-row">
        <div>
          <div class="abyss-shop-name">${escapeHtml(it.icon || "")} ${escapeHtml(it.name)}</div>
          <div class="muted tiny">${escapeHtml(it.description || "")}</div>
        </div>
        <button type="button" class="secondary" ${it.affordable ? "" : "disabled"} onclick="WaifuApp.abyssBuy(${it.id})">🔮 ${it.cost_shards}</button>
      </div>`).join("") || `<div class="muted abyss-list-empty">Магазин пуст</div>`;
    showAbyssBottomSheet(`🔮 Магазин Осколков (${data.abyss_shards})`, items);
  } catch (e) {
    showToast("Не удалось загрузить магазин: " + (e?.message || e), "error");
  }
}

async function abyssBuy(itemId) {
  try {
    const res = await apiFetch("/abyss/shop/buy", {
      method: "POST",
      body: JSON.stringify({ item_id: Number(itemId) }),
    });
    if (res.success) {
      showToast("Покупка совершена!", "success");
      openAbyssShop();
    } else {
      showToast(res.error || "Не удалось купить", "error");
    }
  } catch (e) {
    showToast("Ошибка покупки: " + (e?.message || e), "error");
  }
}

function showAbyssBottomSheet(title, innerHtml) {
  let sheet = document.getElementById("abyss-bottomsheet");
  if (!sheet) {
    sheet = document.createElement("div");
    sheet.id = "abyss-bottomsheet";
    sheet.className = "modal abyss-bottomsheet-modal";
    sheet.style.display = "none";
    sheet.innerHTML = `
      <div class="modal-content abyss-modal-content">
        <div class="modal-head">
          <div class="modal-title" id="abyss-bs-title"></div>
          <button type="button" class="secondary" onclick="document.getElementById('abyss-bottomsheet').style.display='none'">✖</button>
        </div>
        <div class="modal-body" id="abyss-bs-body"></div>
      </div>`;
    document.body.appendChild(sheet);
  }
  document.getElementById("abyss-bs-title").textContent = title;
  document.getElementById("abyss-bs-body").innerHTML = innerHtml;
  sheet.style.display = "flex";
}

function showTab(name) {
  const tabs = document.getElementById("dungeon-tabs");
  if (!tabs) return;
  tabs.querySelectorAll(".tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === name));
  ["solo", "expedition", "group", "abyss"].forEach((t) => {
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
  if (name === "solo") {
    const wasSoloBootstrapped = soloTabBootstrapped;
    ensureSoloTabBootstrapped(window.__lastProfileForDungeons).catch(() => {});
    apiFetch("/abyss/status")
      .then((st) => {
        abyssState = st;
        if (wasSoloBootstrapped) {
          const profile = window.__lastProfileForDungeons;
          if (profile) renderSoloDungeonsForAct(profile).catch(() => {});
        }
      })
      .catch(() => {});
  }
  if (name === "abyss") {
    loadAbyssTab().catch(() => {});
    if (abyssRefreshTimer) clearInterval(abyssRefreshTimer);
    abyssRefreshTimer = setInterval(() => {
      if (document.getElementById("tab-abyss")?.style.display !== "none") {
        loadAbyssTab().catch(() => {});
      }
    }, 6000);
  } else {
    if (abyssRefreshTimer) {
      clearInterval(abyssRefreshTimer);
      abyssRefreshTimer = null;
    }
  }
}


Object.assign(window.WaifuApp, {
  loadMonsterImage,
  buildMonsterImageUrls,
  monsterArtCacheBust,
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
  openBattleLogModal,
  closeBattleLogModal,
  adminExitDungeon,
  loadBattle,
  continueBattle,
  exitBattle,
  showTab,
  populateDungeonsPage,
  refreshSoloActive,
  refreshBattleState: () => refreshSoloActive({ includeLog: false }).catch(() => {}),
  applySoloBattleSsePayload,
  loadExpeditionTab,
  submitExpeditionStart,
  expToggleSquadUnit,
  openSendExpModal,
  closeSendExpModal,
  openExpRosterModal,
  closeExpRosterModal,
  closeActiveExpModal,
  healExpeditionSquad,
  getAvailableUnits,
  claimExpedition,
  openExpeditionResult,
  closeExpeditionResult,
  viewRewardItem,
  adminRefreshExpeditions,
  adminGenerateExpeditionArt,
  openExpeditionHelp,
  closeExpeditionHelp,
  openGdHelp,
  closeGdHelp,
  loadAbyssTab,
  abyssEnter,
  openAbyssExitModal,
  closeAbyssExitModal,
  confirmAbyssExit,
  openAbyssGraceModal,
  closeAbyssGraceModal,
  chooseAbyssGrace,
  closeAbyssCheckpointModal,
  abyssRevive,
  openAbyssLeaderboard,
  openAbyssShop,
  abyssBuy,
});
