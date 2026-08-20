/** Delve column — camp + shaft in #tab-expedition. */
(function (global) {
  "use strict";

  const DELVE_STATIC = "/static/game/delve";
  const LINE_MS = 30000;
  const BRANCH_UI_MS = 15000;
  const LANDMARKS = [7, 13, 23, 37, 47, 67, 83, 97];
  const PLACE_RU = {
    mushrooms: "грибной ход",
    crystal: "кристальный ход",
    coal: "угольный ход",
    wet: "мокрый камень",
    ash: "пепельный ход",
    limestone: "известняк",
  };
  const KICKER_NODE = {
    TRAVERSE: "Спуск · {place}",
    COMBAT: "Бой · {place}",
    BOSS: "Босс · {place}",
    BRANCH: "Вилка · {place}",
    LANDMARK: "Метка · {place}",
    REST: "Привал · {place}",
    SHOP: "Лавка · {place}",
    SURFACE: "Лагерь",
  };
  let state = null;
  let tickTimer = null;
  let lineTimer = null;
  let forkHideTimer = null;
  let forkUi = { depth: null, hideAt: 0, dismissed: false };
  let wizard = { step: 0, size: 1, companions: [] };
  let statusEscHandler = null;

  const SPECIAL_NODE_RU = {
    SURFACE: "Лагерь",
    BOSS: "Босс",
    BRANCH: "Вилка",
    LANDMARK: "Метка",
    REST: "Костёр",
    SHOP: "Лавка",
  };

  function esc(s) {
    return (global.escapeHtml || ((x) => String(x)))(s == null ? "" : String(s));
  }

  function apiFetch(path, opts) {
    if (global.apiFetch) return global.apiFetch(path, opts);
    return fetch("/api" + path, opts).then((r) => r.json());
  }

  function showToast(msg, kind) {
    if (global.showToast) global.showToast(msg, kind);
  }

  function copy(key, fallback) {
    const c = (state && state.copy) || {};
    return c[key] || fallback || key;
  }

  function paletteById(id) {
    const list = (state && state.palettes) || [];
    return list.find((p) => p.id === id) || list[0] || { id: "ash", label: "Пепел", shaft: "#2a2420", accent: "#c8c2b4" };
  }

  function faceSrc(c) {
    if (!c) return "";
    return String(c.image_url || c.portrait_url || "").trim();
  }

  function fmtNum(n) {
    const v = Number(n || 0);
    if (!Number.isFinite(v)) return "0";
    return v.toLocaleString("ru-RU");
  }

  function daysLabel(days) {
    const n = Math.max(0, Number(days) || 0);
    if (n <= 0) return "сегодня";
    return n + " дн.";
  }

  function hudRecord(frame) {
    const pb = Number((state && state.pb_depth) || 0);
    const rec = Number((frame && frame.record) || 0);
    const d = Number((frame && frame.d) || 0);
    return Math.max(pb, rec, Math.floor(d));
  }

  function tabOpen() {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return false;
    const panel = document.getElementById("tab-expedition");
    if (!panel) return true;
    return panel.style.display !== "none";
  }

  function emptyCompanion(slot) {
    const names = (state && state.name_suggestions) || ["Ирида", "Сера", "Кайра"];
    const stances = ["scout", "shield", "guide"];
    const tempers = ["curiosity", "temper", "stay"];
    return {
      slot,
      name: names[(slot - 1) % names.length] || "Спутница",
      stance: stances[(slot - 1) % 3],
      temper: tempers[(slot - 1) % 3],
      cloak_color: "ash",
      image_url: `${DELVE_STATIC}/templates/${stances[(slot - 1) % 3]}.webp`,
      keep_portrait: false,
    };
  }

  function ensureWizardCompanions() {
    const size = wizard.size;
    while (wizard.companions.length < size) {
      wizard.companions.push(emptyCompanion(wizard.companions.length + 1));
    }
    wizard.companions = wizard.companions.slice(0, size).map((c, i) => ({ ...c, slot: i + 1 }));
  }

  function clientFrame(nowMs) {
    if (!state || !state.started || !state.t_origin) return state && state.frame;
    const k = (state.constants) || {};
    const D0 = Number(k.D0) || 24;
    const alpha = Number(k.alpha) || 0.42;
    const t0 = Number(k.t0) || 720;
    const tUp = Number(k.t_up) || 6;
    const depthExp = Number(k.depth_exp) || 1.15;
    const origin = Date.parse(state.t_origin);
    if (!Number.isFinite(origin)) return state.frame;
    const elapsed = Math.max(0, (nowMs - origin) / 1000);
    const hours = elapsed / 3600;
    const ov = Number(state.ov_level || 1);
    const ceil = D0 * (1 + alpha * Math.log(1 + hours)) * (1 + 0.03 * Math.sqrt(Math.max(1, ov)));
    const tDown = t0 * Math.log(1 + ceil);
    const tRest = 50 + 10 * Math.log(1 + ceil);
    const period = tDown + tUp + tRest;
    const phase = period > 0 ? elapsed % period : 0;
    let depth = 0;
    let status = copy("camp", "Лагерь · сами пойдут");
    let st = "SURFACE_REST";
    if (phase < tDown) {
      const u = tDown > 0 ? phase / tDown : 1;
      depth = 1 + (ceil - 1) * Math.pow(u, depthExp);
      st = "DESCENDING";
      status = u < 0.35 ? "Спуск · несут" : u < 0.75 ? "Спуск · вровень" : "Спуск · тяжело";
    } else if (phase < tDown + tUp) {
      const v = (phase - tDown) / tUp;
      depth = ceil * (1 - v);
      st = "ASCENDING";
      status = "Наверх";
    }
    const d = Math.max(0, Math.floor(depth));
    const server = state.frame || {};
    const rec = Math.max(Number(server.record || 0), Number(state.pb_depth || 0), d);
    const node = spineType(d, ceil);
    const on_branch = node === "BRANCH" && st === "DESCENDING";
    let boss_in = null;
    if (st === "DESCENDING" && node !== "BOSS") {
      boss_in = Math.max(0, (Math.floor(d / 10) + 1) * 10 - d);
    }
    return Object.assign({}, server, {
      depth,
      d,
      state: st,
      status,
      d_ceiling: ceil,
      record: rec,
      node,
      on_branch,
      boss_in,
      kicker: kickerFor(node, server.palette_id),
    });
  }

  function isLandmark(d) {
    const n = Math.floor(Number(d) || 0);
    if (n <= 0) return false;
    return LANDMARKS.indexOf(n % 100) >= 0;
  }

  function spineType(d, ceil) {
    const n = Math.floor(Number(d) || 0);
    if (n <= 0) return "SURFACE";
    if (n % 10 === 0) return "BOSS";
    if (n % 5 === 0) return "BRANCH";
    if (isLandmark(n)) return "LANDMARK";
    if (n % 8 === 6) return "REST";
    if (n % 12 === 4) return "SHOP";
    if (ceil > 0 && n < 0.35 * ceil) return "TRAVERSE";
    return "COMBAT";
  }

  function kickerFor(node, paletteId) {
    const place = PLACE_RU[paletteId] || "камне";
    const tmpl = KICKER_NODE[node] || "Идут по {place}";
    return tmpl.indexOf("{place}") >= 0 ? tmpl.replace("{place}", place) : tmpl;
  }

  function showForkChrome(node, st, d) {
    const on = node === "BRANCH" && st === "DESCENDING";
    const now = Date.now();
    if (!on) {
      forkUi = { depth: null, hideAt: 0, dismissed: false };
      if (forkHideTimer) {
        clearTimeout(forkHideTimer);
        forkHideTimer = null;
      }
      return false;
    }
    if (!tabOpen()) {
      if (forkUi.depth != null) forkUi.dismissed = true;
      if (forkHideTimer) {
        clearTimeout(forkHideTimer);
        forkHideTimer = null;
      }
      return false;
    }
    const depth = Math.floor(Number(d) || 0);
    if (forkUi.depth !== depth) {
      forkUi = { depth, hideAt: now + BRANCH_UI_MS, dismissed: false };
      if (forkHideTimer) clearTimeout(forkHideTimer);
      forkHideTimer = setTimeout(() => {
        forkHideTimer = null;
        forkUi.dismissed = true;
        paintFrameCard();
      }, BRANCH_UI_MS);
    }
    if (now >= forkUi.hideAt) forkUi.dismissed = true;
    return !forkUi.dismissed;
  }

  function nodeGlyph(type) {
    const map = {
      SURFACE: "△",
      BOSS: "●",
      BRANCH: "Y",
      LANDMARK: "◆",
      REST: "▲",
      SHOP: "□",
      TRAVERSE: "·",
      COMBAT: "✕",
    };
    return map[type] || "·";
  }

  function shaftBand(d) {
    let n = Math.floor(Number(d) || 0);
    if (n <= 0) n = 1;
    return Math.min(100, Math.max(10, (Math.floor((n - 1) / 10) + 1) * 10));
  }

  function shaftUrlForDepth(d) {
    const biomes = (state && state.shaft_biomes) || [];
    const band = shaftBand(d);
    const row = biomes.find((b) => Number(b.band) === band);
    if (row && row.url) return row.url;
    if (band <= 10) return `${DELVE_STATIC}/shaft.webp`;
    return `${DELVE_STATIC}/shaft_${band}.webp`;
  }

  function nodeCaption(n, hereD) {
    const here = Number(n.d) === hereD;
    const special = SPECIAL_NODE_RU[n.type] || "";
    if (here && special) return `${hereD} · ${special}`;
    if (here) return String(hereD);
    return special;
  }

  function hudLine(frame) {
    const rec = hudRecord(frame);
    const status = (frame && frame.status) || copy("camp", "Лагерь · сами пойдут");
    const d = Number((frame && frame.d) || 0);
    return `${status} · глубина ${d} · рекорд ${rec}`;
  }

  function bandNodesFor(frame, d) {
    const band = shaftBand(d);
    const start = band - 9;
    const lookup = {};
    []
      .concat((frame && frame.band_nodes) || [])
      .concat((frame && frame.nodes) || [])
      .forEach((n) => {
        lookup[Number(n.d)] = n.type;
      });
    const list = [];
    for (let i = 0; i < 10; i += 1) {
      const nd = start + i;
      list.push({ d: nd, type: lookup[nd] || "TRAVERSE" });
    }
    return list;
  }

  function phraseHtml(text) {
    let s = esc(text || "");
    const names = ((state && state.companions) || [])
      .map((c) => String(c.name || "").trim())
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);
    for (const n of names) {
      const needle = esc(n);
      if (!needle) continue;
      s = s.split(needle).join(`<strong>${needle}</strong>`);
    }
    return s;
  }

  function renderShaft(frame) {
    const pal = paletteById(frame && frame.palette_id);
    const rec = hudRecord(frame);
    const cur = Number((frame && frame.d) || 0);
    const hereD = cur <= 0 ? 1 : cur;
    const tokenN = Number((frame && frame.token_n) || (state && state.companions && state.companions.length) || 1);
    const faces = ((state && state.companions) || []).slice(0, tokenN);
    const tokenHtml = faces
      .map(
        (c) =>
          `<img class="delve-token-face" src="${esc(faceSrc(c))}" alt="${esc(c.name || "")}" width="28" height="28" />`
      )
      .join("");
    const nodes = bandNodesFor(frame, hereD);
    const list = nodes
      .map((n) => {
        const here = Number(n.d) === hereD;
        const seen = Number(n.d) <= rec;
        const loc = nodeCaption(n, hereD);
        const locHtml = loc ? `<span class="delve-node-loc">${esc(loc)}</span>` : "";
        const token = here
          ? `<div class="delve-token delve-token--${tokenN}">${tokenHtml || "△"}</div>`
          : "";
        return `<div class="delve-node${here ? " is-here" : ""}${seen ? " is-seen" : ""}" data-d="${n.d}" title="${esc(String(n.d))}">
          ${locHtml}
          <span class="delve-node-g">${nodeGlyph(n.type)}</span>
          ${token}
        </div>`;
      })
      .join("");
    return `<div class="delve-shaft" style="--shaft:${esc(pal.shaft)};--accent:${esc(pal.accent)};--shaft-art:url('${esc(shaftUrlForDepth(cur))}')">
      <div class="delve-nodes">${list}</div>
    </div>`;
  }

  function renderFrameCard(frame) {
    if (!frame) return "";
    const pal = paletteById(frame.palette_id);
    const showFork = showForkChrome(frame.node, frame.state, frame.d) && Array.isArray(frame.sleeves);
    if (frame.node === "BRANCH" && frame.state === "DESCENDING" && !showFork) {
      return "";
    }
    let branch = "";
    if (showFork) {
      branch = `<div class="delve-sleeves"><p class="delve-hint">${esc(copy("tint_hint", "Можно подкрасить. Они уже идут."))}</p>${frame.sleeves
        .map((s) => {
          const p = paletteById(s.id);
          return `<button type="button" class="delve-sleeve${s.instinct ? " is-instinct" : ""}" data-palette="${esc(s.id)}" style="--accent:${esc(p.accent)}">${esc(p.label)}${s.instinct ? " · уже" : ""}</button>`;
        })
        .join("")}</div>`;
    }
    const kickerNode = showFork ? "BRANCH" : frame.node === "BRANCH" ? "TRAVERSE" : frame.node;
    const kicker = kickerFor(kickerNode, frame.palette_id) || frame.kicker || pal.label || "";
    const boss =
      frame.boss_in != null
        ? `<div class="delve-meta">${esc(copy("boss_in", "До босса"))}: ${esc(String(frame.boss_in))}</div>`
        : "";
    return `<div class="delve-card">
      <div class="delve-card-kicker">${esc(kicker)}</div>
      <div class="delve-card-phrase">${phraseHtml(frame.phrase || "")}</div>
      ${boss}
      ${branch}
    </div>`;
  }

  function stampLabel(j) {
    const pal = paletteById(j.palette);
    const d = Number(j.d || 0);
    if (j.kind === "shop") return `Лавка на ${d}`;
    if (j.kind === "landmark") return `Метка на ${d}`;
    if (j.kind === "sryv") return `Срыв на ${d}`;
    if (j.kind === "palette") return pal.label || "Палитра";
    return String(j.kind || "");
  }

  function renderSheet() {
    if (!state) return "";
    const comps = Array.isArray(state.companions) ? state.companions : [];
    const faces = comps
      .map((c) => {
        const src = faceSrc(c);
        return `<div class="delve-sheet-face">
          <img class="delve-bust" src="${esc(src)}" alt="${esc(c.name || "")}" width="56" height="56" />
          <div>
            <strong title="${esc(c.name || "")}">${esc(c.name || "")}</strong>
            <div class="muted tiny">${esc(fmtNum(c.gold_earned))} зол. · ${esc(fmtNum(c.xp_earned))} опыта · ${esc(daysLabel(c.days))}</div>
          </div>
        </div>`;
      })
      .join("");
    const journal = Array.isArray(state.journal) ? state.journal : [];
    const stamps = journal
      .slice(0, 40)
      .map((j) => {
        const p = paletteById(j.palette);
        const label = stampLabel(j);
        return `<span class="delve-stamp" title="${esc(label)}" style="--accent:${esc(p.accent)}">${esc(label)}</span>`;
      })
      .join("");
    return `<div class="delve-sheet">
      <div class="delve-sheet-stats">
        <div>${esc(copy("gold_today", "Сегодня золота"))}: ${esc(fmtNum(state.gold_today))} / ${esc(fmtNum(state.gold_cap_day))} (${esc(String(state.floor_gold_pct || 0))}%)</div>
        <div>${esc(copy("xp_today", "Сегодня опыта"))}: ${esc(fmtNum(state.xp_today))} / ${esc(fmtNum(state.xp_cap_day))} (${esc(String(state.floor_xp_pct || 0))}%)</div>
        <div>${esc(copy("gold_party", "Золото отряда"))}: ${esc(fmtNum(state.gold_granted_total))}</div>
        <div>${esc(copy("xp_party", "Опыт отряда"))}: ${esc(fmtNum(state.xp_granted_total))}</div>
      </div>
      <div class="delve-sheet-faces">${faces}</div>
      <div class="delve-stamps">${stamps || "Пока пусто."}</div>
    </div>`;
  }

  function renderEmpty() {
    const root = document.getElementById("delve-root") || document.getElementById("chronicle-root");
    if (!root) return;
    stop();
    const hasMain = !!(state && state.has_main_waifu);
    const unlocked = !!(state && state.unlocked);
    let body = `<p class="delve-copy">${esc(copy("onboard_1"))}</p>`;
    if (!hasMain) body += `<p class="muted tiny">${esc(copy("need_waifu"))}</p>`;
    else if (!unlocked) body += `<p class="muted tiny">${esc(copy("locked"))}</p>`;
    else body += `<button type="button" class="delve-cta" id="delve-start-cta">${esc(copy("start_cta"))}</button>`;
    if (state && state.migration_from_chronicle && !state.legacy_seen) {
      body = `<p class="delve-copy">${esc(copy("legacy"))}</p>` + body;
    }
    root.innerHTML = `<div class="delve-camp delve-camp--empty">${body}</div>`;
    const btn = document.getElementById("delve-start-cta");
    if (btn) btn.addEventListener("click", () => openWizard());
  }

  function remainingSprites() {
    if (!state) return 3;
    return Math.max(0, Number(state.sprite_cap || 9) - Number(state.sprite_count || 0));
  }

  function openWizard(reform) {
    const remain = reform ? remainingSprites() : 3;
    wizard = { step: 1, size: Math.min(1, remain) || 1, companions: [], reform: !!reform, maxSize: Math.min(3, remain || 3) };
    if (!reform) wizard.maxSize = 3;
    ensureWizardCompanions();
    renderWizard();
  }

  function renderWizard() {
    const root = document.getElementById("delve-root") || document.getElementById("chronicle-root");
    if (!root) return;
    stop();
    ensureWizardCompanions();
    if (wizard.step === 1) {
      root.innerHTML = `
        <div class="delve-camp delve-wizard">
          <p class="delve-copy">${esc(copy("onboard_1"))}</p>
          <div class="delve-size">
            ${[1, 2, 3]
              .filter((n) => n <= wizard.maxSize)
              .map(
                (n) =>
                  `<button type="button" class="delve-size-btn${wizard.size === n ? " active" : ""}" data-size="${n}">${n}</button>`
              )
              .join("")}
          </div>
          <p class="muted tiny">${esc(copy("onboard_2"))}</p>
          <div class="delve-faces">
            ${wizard.companions
              .map(
                (c) => `
              <div class="delve-face" data-slot="${c.slot}">
                <img class="delve-bust" src="${esc(c.image_url)}" alt="${esc(c.name || "")}" width="72" height="72" />
                <input type="text" maxlength="48" value="${esc(c.name)}" data-name="${c.slot}" title="${esc(c.name)}" />
                <button type="button" class="delve-gen" data-slot="${c.slot}">Портрет</button>
              </div>`
              )
              .join("")}
          </div>
          <button type="button" class="delve-cta" id="delve-wiz-next">${esc(copy("faces_next"))}</button>
        </div>`;
      root.querySelectorAll(".delve-size-btn").forEach((b) =>
        b.addEventListener("click", () => {
          wizard.size = Number(b.getAttribute("data-size"));
          ensureWizardCompanions();
          renderWizard();
        })
      );
      root.querySelectorAll("[data-name]").forEach((inp) => {
        inp.addEventListener("input", () => {
          const slot = Number(inp.getAttribute("data-name"));
          const row = wizard.companions.find((c) => c.slot === slot);
          if (row) row.name = inp.value;
        });
      });
      root.querySelectorAll(".delve-gen").forEach((b) => b.addEventListener("click", () => generatePortrait(Number(b.getAttribute("data-slot")))));
      document.getElementById("delve-wiz-next").addEventListener("click", () => {
        wizard.step = 2;
        renderWizard();
      });
      return;
    }
    const stances = (state && state.stances) || [];
    const tempers = (state && state.tempers) || [];
    root.innerHTML = `
      <div class="delve-camp delve-wizard">
        <p class="delve-copy">${esc(copy("onboard_2"))}</p>
        <div class="delve-roles">
          ${wizard.companions
            .map(
              (c) => `
            <div class="delve-role-row" data-slot="${c.slot}">
              <strong title="${esc(c.name)}">${esc(c.name)}</strong>
              <select data-stance="${c.slot}">${stances
                .map((s) => `<option value="${esc(s.id)}" ${c.stance === s.id ? "selected" : ""}>${esc(s.label)}</option>`)
                .join("")}</select>
              <select data-temper="${c.slot}">${tempers
                .map((s) => `<option value="${esc(s.id)}" ${c.temper === s.id ? "selected" : ""}>${esc(s.label)}</option>`)
                .join("")}</select>
            </div>`
            )
            .join("")}
        </div>
        <button type="button" class="delve-cta" id="delve-begin">${wizard.reform ? esc(copy("reform")) : esc(copy("go_down"))}</button>
        <button type="button" class="delve-link" id="delve-wiz-back">Назад</button>
      </div>`;
    root.querySelectorAll("[data-stance]").forEach((el) => {
      el.addEventListener("change", () => {
        const row = wizard.companions.find((c) => c.slot === Number(el.getAttribute("data-stance")));
        if (row) row.stance = el.value;
      });
    });
    root.querySelectorAll("[data-temper]").forEach((el) => {
      el.addEventListener("change", () => {
        const row = wizard.companions.find((c) => c.slot === Number(el.getAttribute("data-temper")));
        if (row) row.temper = el.value;
      });
    });
    document.getElementById("delve-wiz-back").addEventListener("click", () => {
      wizard.step = 1;
      renderWizard();
    });
    document.getElementById("delve-begin").addEventListener("click", submitStart);
  }

  async function generatePortrait(slot) {
    const row = wizard.companions.find((c) => c.slot === slot);
    if (!row) return;
    try {
      const res = await apiFetch("/delve/portrait/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slot,
          name: row.name,
          stance: row.stance,
          temper: row.temper,
          cloak_color: row.cloak_color,
        }),
      });
      if (res && res.image_url) {
        row.image_url = res.image_url + "?t=" + Date.now();
        row.keep_portrait = true;
        renderWizard();
      }
    } catch (e) {
      showToast("Портрет не вышел — будет шаблон", "error");
    }
  }

  async function submitStart() {
    const path = wizard.reform ? "/delve/reform" : "/delve/start";
    try {
      const payload = await apiFetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          size: wizard.size,
          companions: wizard.companions.map((c) => ({
            name: c.name,
            stance: c.stance,
            temper: c.temper,
            cloak_color: c.cloak_color,
            keep_portrait: Boolean(c.keep_portrait) || String(c.image_url || "").includes("/portraits/"),
          })),
        }),
      });
      state = payload;
      wizard.step = 0;
      render();
    } catch (e) {
      showToast("Не вышло собрать отряд", "error");
    }
  }

  function closeStatusModal() {
    const el = document.getElementById("delve-status-modal");
    if (el) el.remove();
    if (statusEscHandler) {
      document.removeEventListener("keydown", statusEscHandler);
      statusEscHandler = null;
    }
  }

  function openStatusModal() {
    closeStatusModal();
    if (!state) return;
    const wrap = document.createElement("div");
    wrap.id = "delve-status-modal";
    wrap.className = "delve-status-modal";
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-modal", "true");
    wrap.setAttribute("aria-label", copy("sheet", "Статус"));
    wrap.innerHTML = `
      <div class="delve-status-modal-card">
        <div class="delve-status-modal-head">
          <div class="delve-status-modal-title">${esc(copy("sheet", "Статус"))}</div>
          <button type="button" class="delve-status-modal-close" aria-label="Закрыть">×</button>
        </div>
        <div class="delve-status-modal-body">${renderSheet()}</div>
      </div>`;
    wrap.addEventListener("click", (e) => {
      if (e.target === wrap) closeStatusModal();
    });
    const closeBtn = wrap.querySelector(".delve-status-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closeStatusModal);
    document.body.appendChild(wrap);
    statusEscHandler = (e) => {
      if (e.key === "Escape") closeStatusModal();
    };
    document.addEventListener("keydown", statusEscHandler);
  }

  function startLocalTick() {
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = setInterval(() => {
      if (!state || !state.started) return;
      const frame = clientFrame(Date.now());
      const hudEl = document.getElementById("delve-hud-line");
      if (hudEl && frame) hudEl.textContent = hudLine(frame);
      const shaft = document.getElementById("delve-shaft-host");
      if (shaft && frame) shaft.innerHTML = renderShaft(frame);
      paintFrameCard();
    }, 1000);
  }

  async function fetchLine() {
    if (!state || !state.started || !tabOpen()) return;
    try {
      const res = await apiFetch("/delve/line", { method: "POST" });
      if (res && res.phrase) {
        if (state.frame) state.frame.phrase = res.phrase;
        const el = document.querySelector(".delve-card-phrase");
        if (el) el.innerHTML = phraseHtml(res.phrase);
      }
    } catch (e) {
      /* template line already on screen */
    }
  }

  function startLinePoll() {
    if (lineTimer) clearInterval(lineTimer);
    fetchLine();
    lineTimer = setInterval(fetchLine, LINE_MS);
  }

  function stop() {
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
    if (lineTimer) {
      clearInterval(lineTimer);
      lineTimer = null;
    }
    if (forkHideTimer) {
      clearTimeout(forkHideTimer);
      forkHideTimer = null;
    }
    closeStatusModal();
  }

  function dismissForkChrome() {
    forkUi.dismissed = true;
    forkUi.hideAt = Date.now();
    if (forkHideTimer) {
      clearTimeout(forkHideTimer);
      forkHideTimer = null;
    }
  }

  let lastFrameHtml = "";

  function bindSleeves(root) {
    (root || document).querySelectorAll(".delve-sleeve").forEach((b) => {
      b.addEventListener("click", async () => {
        try {
          const payload = await apiFetch("/delve/tint", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ palette_id: b.getAttribute("data-palette") }),
          });
          dismissForkChrome();
          state = payload;
          render();
        } catch (e) {
          /* already gone */
        }
      });
    });
  }

  function paintFrameCard() {
    const host = document.getElementById("delve-frame-host");
    if (!host || !state) return;
    const frame = clientFrame(Date.now()) || state.frame || {};
    const html = renderFrameCard(frame);
    if (html === lastFrameHtml) return;
    lastFrameHtml = html;
    host.innerHTML = html;
    bindSleeves(host);
  }

  function renderColumn() {
    const root = document.getElementById("delve-root") || document.getElementById("chronicle-root");
    if (!root) return;
    const frame = clientFrame(Date.now()) || state.frame || {};
    const reform =
      state.reform_ready
        ? `<button type="button" class="delve-link" id="delve-reform">${esc(copy("reform"))}</button>`
        : "";
    const legacy =
      state.migration_from_chronicle && !state.legacy_seen
        ? `<div class="delve-legacy">${esc(copy("legacy"))}</div>`
        : "";
    lastFrameHtml = "";
    root.innerHTML = `
      <div class="delve-camp">
        ${legacy}
        <div class="delve-stage">
          <div class="delve-shaft-wrap">
            <div id="delve-shaft-host">${renderShaft(frame)}</div>
            <div class="delve-shaft-overlay">
              <div id="delve-hud-line" class="delve-shaft-status">${esc(hudLine(frame))}</div>
              <button type="button" id="delve-sheet-btn" class="delve-status-btn">${esc(copy("sheet", "Статус"))}</button>
            </div>
          </div>
          <div id="delve-frame-host">${renderFrameCard(frame)}</div>
        </div>
        ${reform}
      </div>`;
    lastFrameHtml = document.getElementById("delve-frame-host")?.innerHTML || "";
    const sheetBtn = document.getElementById("delve-sheet-btn");
    if (sheetBtn) sheetBtn.addEventListener("click", openStatusModal);
    const reformBtn = document.getElementById("delve-reform");
    if (reformBtn) reformBtn.addEventListener("click", () => openWizard(true));
    bindSleeves(root);
    startLocalTick();
    startLinePoll();
  }

  function render() {
    const root = document.getElementById("delve-root") || document.getElementById("chronicle-root");
    if (!root) return;
    if (!state || !state.started) {
      renderEmpty();
      return;
    }
    renderColumn();
  }

  async function load() {
    const root = document.getElementById("delve-root") || document.getElementById("chronicle-root");
    if (!root) return;
    try {
      const payload = await apiFetch("/delve/sync?tab=true");
      state = payload;
      render();
    } catch (e) {
      stop();
      root.innerHTML = `<div class="delve-camp"><p class="delve-copy">${esc(copy("unavailable"))}</p></div>`;
    }
  }

  global.DelveColumn = { load, render, stop, state: () => state };
  global.ChronicleScriptorium = global.DelveColumn;
})(typeof window !== "undefined" ? window : globalThis);
