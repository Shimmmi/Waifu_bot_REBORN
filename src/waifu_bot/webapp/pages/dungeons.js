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

// Cache-bust version for a monster's generated art: prefer the freshest of the
// session-generated timestamp and the API's image_updated_at.
function monsterArtCacheBust(templateId, imageUpdatedAt) {
  let v = 0;
  try {
    const sess = templateId != null ? monsterArtVersion[templateId] : 0;
    if (sess) v = Math.max(v, Number(sess) || 0);
  } catch (e) {
    /* monsterArtVersion may be undefined in isolation; ignore */
  }
  if (imageUpdatedAt) {
    const t = Date.parse(imageUpdatedAt);
    if (!Number.isNaN(t)) v = Math.max(v, t);
  }
  return v > 0 ? String(v) : null;
}

function buildMonsterImageUrls(family, slug, tier, imageOverride, version) {
  if (imageOverride) return [imageOverride, `${MONSTER_STATIC_BASE}/_unknown.webp`];
  const q = version ? `?v=${encodeURIComponent(version)}` : "";
  return [
    `${MONSTER_STATIC_BASE}/${family}/${slug}.webp${q}`,
    `${MONSTER_STATIC_BASE}/${family}/_family_t${tier}.webp`,
    `${MONSTER_STATIC_BASE}/${family}/_family.webp`,
    `${MONSTER_STATIC_BASE}/_unknown.webp`,
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
  // If the same URL is already loaded, onload may not refire — reveal it manually
  // so the emoji overlay does not stay stuck over a valid image.
  if (img.getAttribute("src") === urls[0] && img.complete && img.naturalWidth > 0) {
    onMonsterImageLoad(img);
    return;
  }
  img.src = urls[0];
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
  host.innerHTML = `<details class="solo-battle-log-root"><summary class="solo-battle-log-root-sum">Журнал боя (${list.length})</summary><div class="solo-battle-log-inner">${buildSoloBattleLogHtml(list)}</div></details>`;
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

  const nameKnown = monster.name_known !== false;
  const hpKnown = monster.hp_known !== false;
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
  if (img) img.classList.add("fading");
  const monsterArtVersionStr = monster.has_image
    ? monsterArtCacheBust(monster.template_id, monster.image_updated_at)
    : null;
  setTimeout(() => {
    loadMonsterImage(
      monster.family || "unknown",
      monster.slug || "unknown",
      monster.tier ?? 1,
      monster.image_override ?? null,
      monsterArtVersionStr
    );
  }, 150);

  const monsterPct = monster.max_hp > 0 ? Math.max(0, Math.min(100, (monster.current_hp / monster.max_hp) * 100)) : 0;
  setText("monster-hp-text", hpKnown ? `${monster.current_hp} / ${monster.max_hp}` : "??? / ???");
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
    soloActiveStoryBossId = null;
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
  renderSoloBattleCard(monster, dungeon, waifu);
  mountSoloBattleLog(active.battle_log_entries || []);
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

async function refreshSoloActive() {
  if (!dungeonsFinishBlockedMsg) showDungeonsError("");
  try {
    const active = await fetchActiveDungeon({ includeLog: true, force: true });
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
  const p = profile || (await loadProfile({ lite: true }));
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
    const active = await fetchActiveDungeon({ includeLog: true, force: true });
    renderAtticDungeon(active);
    renderSoloActiveProgress(active);
  } catch (e) {
    // Don't break page if active endpoint fails.
    const { detail } = parseHttpErrorDetail(e);
    renderSoloActiveProgress({ active: false });
    showDungeonsError(`Не удалось проверить активный данж: ${detail || "ошибка"}`);
  }

  // Open tab from URL (e.g. from ОЧ chip click)
  const tabParam = new URLSearchParams(window.location.search).get("tab");
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

function biomeImageUrls(tag, archetypeId) {
  const urls = [];
  const archKey = String(archetypeId || "")
    .trim()
    .toLowerCase()
    .replace(/ /g, "_")
    .replace(/-/g, "_");
  if (archKey) {
    const v = expeditionArchetypeArtVersion[archKey];
    const q = v ? `?v=${encodeURIComponent(v)}` : "";
    urls.push(`${EXPEDITION_ARCHETYPES_BASE}/${encodeURIComponent(archKey)}.webp${q}`);
  }
  const key = normalizeBiomeTag(tag);
  if (key) urls.push(`${EXPEDITION_BIOMES_BASE}/${encodeURIComponent(key)}.webp`);
  urls.push(`${EXPEDITION_BIOMES_BASE}/default.webp`);
  return urls;
}

function applyExpeditionBiomeBackground(el, tag, emojiEl, archetypeId) {
  if (!el) return;
  const fallback = biomeBg(tag);
  const isModal = el.classList.contains("exp-modal-img");
  const biomeCls = isModal ? "exp-modal-img--biome" : "exp-card-img--biome";
  el.classList.remove("exp-modal-img--biome", "exp-card-img--biome");
  el.style.backgroundImage = "";
  el.style.background = fallback;
  if (emojiEl) emojiEl.style.display = "";
  const urls = biomeImageUrls(tag, archetypeId);
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
  const dailyGrid = document.getElementById("exp-daily-grid");
  if (!activeGrid || !dailyGrid) return;

  const actives = expeditionState.active || [];
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
          return `<div class="exp-card-item exp-is-active ${diffCls}" data-exp-kind="active" data-exp-id="${a.id}">
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
        const archetypeChip = expeditionCardArchetypeChip(s);
        const affixIcos = (s.affixes || [])
          .slice(0, 4)
          .map((x) => `<div class="exp-affix-ico">${x.icon || "✦"}</div>`)
          .join("");
        const emoji = s.biome_emoji || "🗺";
        const biomeTag = escapeHtml(s.biome_tag || "");
        const archId = escapeHtml(s.location_archetype_id || "");
        const genBtn = expeditionCardGenArtButton("daily", s);
        const cls = used ? " exp-card-used" : "";
        const diffCls = expeditionDiffCountClass(s);
        const foot = used
          ? `<div class="exp-card-foot"><span class="exp-foot-muted">● Отправлена</span></div>`
          : `<div class="exp-card-foot"><span class="exp-foot-ready">● Доступна</span></div>`;
        return `<div class="exp-card-item${cls} ${diffCls}" data-exp-kind="daily" data-exp-id="${s.id}" data-exp-used="${used ? "1" : "0"}">
            <div class="exp-card-img" data-biome-tag="${biomeTag}" data-archetype-id="${archId}">
              <div class="exp-card-emoji">${emoji}</div>
              <div class="exp-card-affix-col">
                <div class="exp-card-affix-icons">${affixIcos}</div>
                ${genBtn}
              </div>
              ${archetypeChip}
            </div>
            ${foot}
          </div>`;
      })
      .join("");
  }

  wireExpeditionCardBiomes(activeGrid);
  wireExpeditionCardBiomes(dailyGrid);

  const adminUiOn = typeof isAdminUiEnabled === "function"
    ? isAdminUiEnabled()
    : Boolean(window.WaifuApp?.isAdminUiEnabled?.());
  if (adminUiOn) {
    document.querySelectorAll("#exp-active-grid .admin-only, #exp-daily-grid .admin-only").forEach((el) => {
      el.style.display = "";
    });
  }

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
  expG("esm-title").textContent = expeditionSendModalTitle(slot);
  const esmNarr = expG("esm-narrative-meta");
  if (esmNarr) esmNarr.innerHTML = expeditionNarrativeMetaHtml(slot);
  updateExpeditionSendAffixes();
  const tagsEl = expG("esm-difficulty-tags");
  if (tagsEl) updateExpeditionSendTags([]);
  updateExpeditionObstacleLevel();
  const effEl = expG("esm-tag-effectiveness");
  if (effEl) effEl.textContent = "Снижение сложности: ~100% (выберите отряд)";
  const img = expG("esm-img");
  const emo = expG("esm-emoji");
  if (emo) emo.textContent = slot.biome_emoji || "🗺";
  applyExpeditionBiomeBackground(img, slot.biome_tag, emo, slot.location_archetype_id);

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
      expeditionArchetypeArtVersion[arch] = Date.now();
    }
    wireExpeditionCardBiomes(document.getElementById("exp-active-grid"));
    wireExpeditionCardBiomes(document.getElementById("exp-daily-grid"));
    const openActive = expeditionUiCache._activeRaw;
    if (openActive && String(openActive.location_archetype_id || "").toLowerCase() === arch) {
      applyExpeditionBiomeBackground(
        expG("eam-img"),
        openActive.biome_tag,
        expG("eam-emoji"),
        openActive.location_archetype_id,
      );
    }
    const openSlot = expeditionSend.currentSlot;
    if (openSlot && String(openSlot.location_archetype_id || "").toLowerCase() === arch) {
      applyExpeditionBiomeBackground(
        expG("esm-img"),
        openSlot.biome_tag,
        expG("esm-emoji"),
        openSlot.location_archetype_id,
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

function abyssHpBar(cur, max, color) {
  const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((cur / max) * 100))) : 0;
  return `
    <div class="abyss-hpbar" style="background:#2a2030;border-radius:8px;overflow:hidden;height:18px;position:relative;">
      <div style="width:${pct}%;height:100%;background:${color};transition:width .3s;"></div>
      <span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff;text-shadow:0 1px 2px #000;">${Math.max(0, cur)} / ${max}</span>
    </div>`;
}

function abyssModifierBadge(modifier, label, desc) {
  if (!modifier) return "";
  const b = ABYSS_MODIFIER_BADGE[modifier] || { icon: "", cls: "" };
  return `<div class="abyss-modifier-badge ${b.cls}" title="${escapeHtml(desc || "")}" style="display:inline-block;padding:4px 10px;border-radius:14px;background:#3a2a4a;border:1px solid #5a3a6a;font-size:12px;margin:2px;">${b.icon} ${escapeHtml(label || modifier)}</div>`;
}

function renderAbyss(st) {
  const root = document.getElementById("abyss-root");
  if (!root) return;

  if (!st.is_available) {
    root.innerHTML = `
      <div class="card" style="text-align:center;padding:24px;">
        <div style="font-size:42px;">🕳️</div>
        <h3 style="margin:8px 0;">Бездна закрыта</h3>
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
    <div class="card" style="padding:18px;">
      <div style="display:flex;align-items:center;gap:10px;">
        <div style="font-size:36px;">🕳️</div>
        <div>
          <h3 style="margin:0;">Бездна</h3>
          <div class="muted tiny">Бесконечный спуск. Каждое сообщение в чате — удар.</div>
        </div>
      </div>
      <div class="abyss-stats-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0;">
        <div class="abyss-stat"><div class="muted tiny">Рекорд</div><div style="font-size:20px;font-weight:700;">🏆 ${record}</div></div>
        <div class="abyss-stat"><div class="muted tiny">Последний чекпоинт</div><div style="font-size:20px;font-weight:700;">🏛 ${checkpoint}</div></div>
        <div class="abyss-stat"><div class="muted tiny">Осколки Бездны</div><div style="font-size:20px;font-weight:700;">🔮 ${shards}</div></div>
        <div class="abyss-stat"><div class="muted tiny">Чекпоинты сегодня</div><div style="font-size:20px;font-weight:700;">${limitUsed} / ${limit}</div></div>
      </div>
      <button class="primary" style="width:100%;" onclick="WaifuApp.abyssEnter()">${escapeHtml(btnLabel)}</button>
      <div style="display:flex;gap:8px;margin-top:10px;">
        <button class="secondary" style="flex:1;" onclick="WaifuApp.openAbyssLeaderboard()">🏆 Топ недели</button>
        <button class="secondary" style="flex:1;" onclick="WaifuApp.openAbyssShop()">🔮 Магазин</button>
      </div>
    </div>`;
}

function abyssBattleHtml(st) {
  const m = st.current_monster || {};
  const floor = Number(st.current_floor || 0);
  const badges = [];
  if (m.is_boss) badges.push(`<span class="badge" style="background:#7a2a2a;padding:2px 8px;border-radius:10px;font-size:11px;">👑 Босс</span>`);
  if (m.is_elite) badges.push(`<span class="badge" style="background:#2a4a7a;padding:2px 8px;border-radius:10px;font-size:11px;">⭐ Элита</span>`);
  const affixChips = (m.affixes || []).map((a) => `<span class="affix-chip" style="display:inline-block;background:#33304a;padding:2px 7px;border-radius:8px;font-size:10px;margin:1px;">${escapeHtml(a.name)}</span>`).join("");
  const grace = st.active_grace;
  const graceHtml = grace
    ? `<div class="abyss-grace-active" style="background:#243a24;border:1px solid #3a6a3a;border-radius:10px;padding:8px 10px;margin:8px 0;font-size:12px;">${escapeHtml(grace.icon || "✨")} <b>${escapeHtml(grace.name)}</b> — ${escapeHtml(grace.effect_label || grace.description || "")}</div>`
    : "";
  const modifierHtml = st.current_floor_modifier
    ? abyssModifierBadge(st.current_floor_modifier, st.modifier_label, st.modifier_description)
    : "";
  const warning = m.warning_text
    ? `<div class="banner" style="background:#4a2a1a;border-color:#7a4a2a;">⚠️ ${escapeHtml(m.warning_text)}</div>`
    : "";
  const unconscious = st.waifu_unconscious;
  const reviveBtn = unconscious
    ? `<button class="primary" style="width:100%;margin-top:8px;" onclick="WaifuApp.abyssRevive()">🔮 Воскресить за Осколки</button>`
    : "";
  const unconsciousBanner = unconscious
    ? `<div class="banner" style="background:#3a1a1a;border-color:#7a2a2a;">😵 ОВ без сознания. HP восстанавливается со временем — атаки возобновятся автоматически.</div>`
    : "";

  return `
    <div class="card" style="padding:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div><span style="font-size:13px;" class="muted">Этаж</span> <span style="font-size:24px;font-weight:800;">${floor}</span></div>
        <button class="dungeon-tab-sm" title="Покинуть Бездну" onclick="WaifuApp.openAbyssExitModal()">🏳️</button>
      </div>
      <div style="margin:6px 0;">${modifierHtml}</div>
      ${graceHtml}
      ${warning}
      ${unconsciousBanner}
      <div class="abyss-monster" style="margin-top:10px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;">
          <div style="font-weight:700;">${escapeHtml(m.name || "Монстр")} ${badges.join(" ")}</div>
          <div class="muted tiny">ур. ${Number(m.level || 1)}</div>
        </div>
        <div style="margin:6px 0;">${affixChips}</div>
        ${abyssHpBar(Number(m.hp_current || 0), Number(m.hp_max || 1), "linear-gradient(90deg,#c0392b,#e74c3c)")}
      </div>
      <div class="abyss-waifu" style="margin-top:14px;">
        <div class="muted tiny">Ваша ОВ</div>
        ${abyssHpBar(Number(st.waifu_hp || 0), Number(st.waifu_max_hp || 1), "linear-gradient(90deg,#27ae60,#2ecc71)")}
      </div>
      ${reviveBtn}
      <p class="muted tiny" style="text-align:center;margin:12px 0 0;">✍️ Пишите в групповой чат — каждое сообщение наносит урон.</p>
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
    <button class="abyss-grace-option" onclick="WaifuApp.chooseAbyssGrace(${Number(g.id)})"
      style="display:block;width:100%;text-align:left;background:#2a2438;border:1px solid #4a3a5a;border-radius:12px;padding:12px;margin:6px 0;cursor:pointer;">
      <div style="font-weight:700;">${escapeHtml(g.icon || "✨")} ${escapeHtml(g.name)}</div>
      <div class="muted tiny" style="margin-top:4px;">${escapeHtml(g.effect_label || g.description || "")}</div>
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
    <p style="text-align:center;font-size:14px;">Босс повержен, прогресс сохранён.</p>
    <p class="muted tiny" style="text-align:center;">Награды (осколки и предмет) начислены — подробности в личке бота.
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
      <div style="display:flex;justify-content:space-between;padding:6px 4px;border-bottom:1px solid #2a2438;${e.is_me ? "background:#243a24;border-radius:6px;" : ""}">
        <span>${e.rank}. ${escapeHtml(e.name)}</span>
        <span style="font-weight:700;">🕳️ ${e.max_floor}</span>
      </div>`).join("") || `<div class="muted" style="padding:12px;text-align:center;">Пока пусто</div>`;
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
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px;border-bottom:1px solid #2a2438;">
        <div>
          <div style="font-weight:700;">${escapeHtml(it.icon || "")} ${escapeHtml(it.name)}</div>
          <div class="muted tiny">${escapeHtml(it.description || "")}</div>
        </div>
        <button class="secondary" ${it.affordable ? "" : "disabled"} onclick="WaifuApp.abyssBuy(${it.id})">🔮 ${it.cost_shards}</button>
      </div>`).join("") || `<div class="muted" style="padding:12px;text-align:center;">Магазин пуст</div>`;
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
    sheet.className = "modal";
    sheet.style.display = "none";
    sheet.innerHTML = `
      <div class="modal-content">
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
  showTab,
  populateDungeonsPage,
  refreshSoloActive,
  loadExpeditionTab,
  submitExpeditionStart,
  expSelDiff,
  expSelDur,
  expPickUnit,
  expClosePicker,
  closeRewardModal,
  viewRewardItem,
  closeActiveExpModal,
  closeSendExpModal,
  abortExpedition,
  getAvailableUnits,
  claimExpedition,
  openExpeditionResult,
  closeExpeditionResult,
  cancelExpedition,
  adminRefreshExpeditions,
  adminGenerateExpeditionArt,
  openExpeditionHelp,
  closeExpeditionHelp,
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
