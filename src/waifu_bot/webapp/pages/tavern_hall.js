/** Living tavern hall. Arena / hire / bench stay dead. BGM tab still uses the old bootstrap. */

(function livingTavernHall() {
  const VERSION = "v114";
  let hall = null;
  let openCardId = null;
  let seenOnce = false;
  let hireBusy = false;
  let artPoll = null;
  const chatMemory = new Map();

  function qsTab() {
    try {
      return new URLSearchParams(window.location.search).get("tab") || "";
    } catch {
      return "";
    }
  }

  function copy() {
    return hall?.copy || {};
  }

  function esc(s) {
    return (typeof escapeHtml === "function" ? escapeHtml : (x) => String(x))(s == null ? "" : String(s));
  }

  function portrait(card, kind) {
    if (!card) return "";
    if (kind === "anime") return card.portrait_anime || card.portrait_pixel || "";
    return card.portrait_pixel || card.portrait_anime || "";
  }

  function loyaltyHeart(card) {
    if (!card) return "";
    const url = String(card.loyalty_heart || "");
    if (!url) return "";
    const n = card.loyalty == null ? 50 : card.loyalty;
    return `<img class="living-loyalty" src="${esc(url)}?v=${VERSION}" alt="Лояльность ${esc(n)}" title="Лояльность ${n}">`;
  }

  function hireCostLabel() {
    const n = Number(hall?.hire_cost);
    if (!Number.isFinite(n) || n <= 0) return "Бесплатно";
    return `🪙 ${n.toLocaleString("ru-RU")}`;
  }

  function renderColumns() {
    const cols = hall?.columns || [];
    const c = copy();
    return `<div class="tavern-living-cols">${cols
      .map((col) => {
        const kind = col.kind;
        const card = col.card;
        if (kind === "living" && card) {
          const waiting = !card.portrait_anime;
          return `<button type="button" class="living-col${card.scar_frame ? " scar" : ""}" data-kind="living" data-id="${card.id}">
            <div class="living-frame${waiting ? " art-wait" : ""}">${card.portrait_anime || card.portrait_pixel ? `<img src="${esc(portrait(card, "anime"))}" alt="">` : ""}</div>
            <div class="living-hood-row">
              <div class="living-hood">${portrait(card, "pixel") ? `<img src="${esc(portrait(card, "pixel"))}" alt="">` : ""}</div>
              ${loyaltyHeart(card)}
            </div>
            <div class="name">${esc(card.name)}</div>
            <div class="meta">${esc(card.lineage || [card.race_ru, card.class_ru].filter(Boolean).join(" · ") || `${card.stance_label || ""} · ${card.temper_label || ""}`)}</div>
            <div class="who-sub">${esc(card.stance_label || "")} · ${esc(card.temper_label || "")}</div>
          </button>`;
        }
        if (kind === "rain" && card) {
          return `<div class="living-col" data-kind="rain" data-id="${card.id}">
            <div class="living-frame hood">капюшон</div>
            <div class="living-hood-row"><div class="living-hood"></div></div>
            <div class="name">${esc(c.rain || "Вошла с дождя")}</div>
            <button type="button" class="living-cta" data-rain="accept">${esc(c.rain || "Вошла с дождя")}</button>
            <button type="button" class="living-refuse" data-rain="refuse">Не пускать</button>
          </div>`;
        }
        return `<button type="button" class="living-col living-col-hire" data-kind="hire" data-slot="${col.slot}">
          <div class="living-frame hire-plus" aria-hidden="true">+</div>
          <div class="name">${esc(c.hire || "Нанять")}</div>
          <div class="meta hire-cost">${esc(hireCostLabel())}</div>
        </button>`;
      })
      .join("")}</div>`;
  }

  function renderHall() {
    const root = document.getElementById("tavern-living-root");
    if (!root || !hall) return;
    const c = copy();
    root.innerHTML = `<div class="tavern-living-head"><h1>${esc(c.title || "Таверна")}</h1><span class="sub">${esc(c.sub || "")}</span></div>
      ${renderColumns()}`;
  }

  async function onHire(slot) {
    if (hireBusy) return;
    hireBusy = true;
    try {
      await apiFetch("/tavern/living/hire", {
        method: "POST",
        body: JSON.stringify({ slot: Number(slot) }),
      });
      await refreshHall();
      try {
        if (typeof loadProfile === "function") await loadProfile({ lite: true });
      } catch (_) {}
      kickArt();
    } finally {
      hireBusy = false;
    }
  }

  function kickArt() {
    apiFetch("/tavern/living/art", { method: "POST" }).catch(() => {});
    if (artPoll) return;
    artPoll = (async () => {
      const until = Date.now() + 180000;
      while (Date.now() < until) {
        await new Promise((r) => setTimeout(r, 5000));
        try {
          await refreshHall();
        } catch {
          break;
        }
        if (!hall?.needs_art?.length) break;
        apiFetch("/tavern/living/art", { method: "POST" }).catch(() => {});
      }
    })().finally(() => {
      artPoll = null;
    });
  }

  async function closeLivingModal(opts) {
    const skipTick = Boolean(opts && opts.skipTick);
    const id = openCardId;
    const turns = id != null ? chatMemory.get(id) || [] : [];
    const modal = document.getElementById("tavern-living-modal");
    if (modal) modal.classList.remove("open");
    closePop();
    openCardId = null;
    if (id != null) chatMemory.delete(id);
    if (id == null || skipTick) return;
    try {
      const out = await apiFetch(`/tavern/living/cards/${id}/loyalty-tick`, {
        method: "POST",
        body: JSON.stringify({
          history: turns.map((t) => ({ role: t.role, text: t.text })),
        }),
      });
      if (out && out.left) {
        showToast(`${out.name || "Она"} ушла сама.`, "info");
        await refreshHall();
      }
    } catch (_) {}
  }

  function closeModal() {
    closeLivingModal().catch(() => {});
  }

  function bodyMark() {
    return `<svg class="living-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12.1 21.3S3 15.2 3 9.4C3 6.4 5.4 4 8.4 4c1.7 0 3.2.8 4.1 2.1C13.4 4.8 14.9 4 16.6 4 19.6 4 22 6.4 22 9.4c0 5.8-9.1 11.9-9.9 11.9z"/></svg>`;
  }

  function mindMark() {
    return `<svg class="living-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 5c5.2 0 9.4 4.2 10.5 7-1.1 2.8-5.3 7-10.5 7S2.6 14.8 1.5 12C2.6 9.2 6.8 5 12 5zm0 3.2A3.8 3.8 0 1 0 12 16a3.8 3.8 0 0 0 0-7.8zm0 2.1a1.7 1.7 0 1 1 0 3.4 1.7 1.7 0 0 1 0-3.4z"/></svg>`;
  }

  function toneOf(value, fallback) {
    if (fallback === "ok" || fallback === "warn" || fallback === "bad") return fallback;
    if (value === "еле держится" || value === "пустой взгляд") return "bad";
    if (value === "побита" || String(value || "").indexOf("тень") >= 0) return "warn";
    return "ok";
  }

  function conditionItems(rows, fallback) {
    return (rows || []).map((row) => {
      const name = row.label || row.part || row.facet || fallback;
      if (row.line) return `${name}. ${row.line}`;
      return row.severity ? `${name} · ${row.severity}` : name;
    });
  }

  function listBlock(items, emptyLine) {
    if (!items.length) return `<ul><li class="ok">${esc(emptyLine)}</li></ul>`;
    return `<ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
  }

  function bodyHtml(detail) {
    return listBlock(conditionItems(detail.wounds, "рана"), "В форме, ран нет.");
  }

  function mindHtml(detail) {
    const bonds = (detail.bonds || []).filter(Boolean);
    const bits = [listBlock(conditionItems(detail.psyche, "тень"), "Ясна.")];
    if (bonds.length) {
      bits.push(`<h3>Связи</h3><ul>${bonds.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`);
    }
    return bits.join("");
  }

  function bioHtml(detail) {
    const traits = (detail.traits || []).filter(Boolean);
    const traitBlock = traits.length
      ? `<div class="living-bio-traits">${traits.map((t) => `<span class="living-trait-chip">${esc(t)}</span>`).join("")}</div>`
      : `<p class="empty">Пока без ярких черт.</p>`;
    return `<p>${esc(detail.bio || "Пока молчит.")}</p>${traitBlock}`;
  }

  function logHtml(detail, emptyLine) {
    const hist = detail.history || [];
    if (!hist.length) return `<p class="empty">${esc(emptyLine || "Пока тишина.")}</p>`;
    return `<ul class="living-log-list">${hist
      .map((h) => {
        const text = h.fact || h.line || "";
        const depth = h.depth ? ` <span class="muted">· ${esc(h.depth)}</span>` : "";
        return `<li>${esc(text)}${depth}</li>`;
      })
      .join("")}</ul>`;
  }

  function closePop() {
    const pop = document.getElementById("living-pop");
    if (pop) pop.hidden = true;
  }

  function openPop(title, bodyHtml) {
    const pop = document.getElementById("living-pop");
    const head = document.getElementById("living-pop-title");
    const body = document.getElementById("living-pop-body");
    if (!pop || !head || !body) return;
    head.textContent = title;
    body.innerHTML = bodyHtml;
    pop.hidden = false;
  }

  function paintThread(cardId) {
    const box = document.getElementById("living-thread");
    if (!box) return;
    const turns = chatMemory.get(cardId) || [];
    box.classList.toggle("is-empty", turns.length === 0);
    box.innerHTML = turns
      .map((t) => `<div class="living-bubble ${t.role === "user" ? "me" : "her"}">${esc(t.text)}</div>`)
      .join("");
    box.scrollTop = box.scrollHeight;
  }

  function renderModal(detail) {
    const modal = document.getElementById("tavern-living-modal");
    const sheet = document.getElementById("tavern-living-sheet");
    if (!modal || !sheet || !detail) return;
    const c = copy();
    const body = detail.body || "в форме";
    const mind = detail.mind || "ясна";
    const bodyTone = toneOf(body, detail.body_tone);
    const mindTone = toneOf(mind, detail.mind_tone);
    const loyalty = Math.max(0, Math.min(100, Number(detail.loyalty == null ? 50 : detail.loyalty) || 50));
    const lineage = detail.lineage || [detail.race_ru, detail.class_ru].filter(Boolean).join(" · ");
    const art = portrait(detail, "anime");
    const stance = String(detail.stance_label || "").trim();
    const temper = String(detail.temper_label || "").trim();
    const tagChips = [stance, temper]
      .filter(Boolean)
      .map((t) => `<span class="living-tag-chip">${esc(t)}</span>`)
      .join("");
    sheet.classList.toggle("scar", Boolean(detail.scar_frame));
    sheet.innerHTML = `
      <div class="living-hero">
        <div class="living-hero-rays" aria-hidden="true"></div>
        <div class="living-hero-art">${art ? `<img src="${esc(art)}" alt="">` : ""}</div>
        <div class="living-hero-top">
          <button type="button" class="living-circle-btn" id="living-log-btn" title="Журнал" aria-label="Журнал">📜</button>
          <div class="living-hero-top-right">
            <button type="button" class="living-circle-btn living-dismiss-ico" id="living-dismiss-btn" title="${esc(c.dismiss || "Уволить")}" aria-label="${esc(c.dismiss || "Уволить")}"${detail.can_dismiss ? "" : " disabled"}>🚪</button>
            <button type="button" class="living-circle-btn" id="living-close-btn" aria-label="Закрыть">✕</button>
          </div>
        </div>
        <div class="living-hero-scrim">
          <div class="living-hero-identity">
            <h2 class="${detail.can_rename ? "can-rename" : ""}" id="living-name" ${detail.can_rename ? 'title="Сменить имя (один раз)"' : ""}>${esc(detail.name)}</h2>
            ${lineage ? `<div class="living-who">${esc(lineage)}</div>` : ""}
          </div>
          <div class="living-hero-status">
            <button type="button" class="living-stat tone-${bodyTone}" data-open="body" title="${esc(body)}">${bodyMark()}<span>${esc(body)}</span></button>
            <button type="button" class="living-stat tone-${mindTone}" data-open="mind" title="${esc(mind)}">${mindMark()}<span>${esc(mind)}</span></button>
          </div>
        </div>
      </div>
      <div class="living-body">
        <div class="living-tag-row">
          <div class="living-tag-chips">${tagChips}</div>
          <button type="button" class="living-bio-btn" id="living-bio-btn">Био</button>
        </div>
        <div class="living-loyalty-row">
          <div class="living-loyalty-top">
            <span class="living-loyalty-lbl">Лояльность</span>
            <span class="living-loyalty-val">${esc(loyalty)} / 100</span>
          </div>
          <div class="living-loyalty-bar" aria-hidden="true"><i style="--pct:${loyalty}%"></i></div>
        </div>
        <div class="living-thread is-empty" id="living-thread"></div>
      </div>
      <form class="living-chat" id="living-chat-form">
        <input name="text" maxlength="400" placeholder="${esc(c.chat_ph || "Сказать ей…")}" ${detail.chat_left <= 0 ? "disabled" : ""} />
        <button type="submit"${detail.chat_left <= 0 ? " disabled" : ""}>Сказать</button>
      </form>
      <div id="living-pop" class="living-pop" hidden>
        <div class="living-pop-card">
          <div class="living-pop-head">
            <strong id="living-pop-title">Журнал</strong>
            <button type="button" class="living-pop-close" id="living-pop-close" aria-label="Закрыть">×</button>
          </div>
          <div class="living-pop-body" id="living-pop-body"></div>
        </div>
      </div>`;
    modal.classList.add("open");
    openCardId = detail.id;
    paintThread(detail.id);
    const closeModal = () => {
      closeLivingModal().catch(() => {});
    };
    sheet.querySelector("#living-close-btn")?.addEventListener("click", closeModal);
    bindDismiss(detail);
    sheet.querySelector("#living-name")?.addEventListener("click", () => onRename(detail));
    sheet.querySelector("#living-pop-close")?.addEventListener("click", closePop);
    sheet.querySelector("#living-log-btn")?.addEventListener("click", () => {
      openPop("Журнал", logHtml(detail, c.history_empty));
    });
    sheet.querySelector("#living-bio-btn")?.addEventListener("click", () => onBio(detail));
    sheet.querySelector("[data-open=body]")?.addEventListener("click", () => {
      openPop("Тело", bodyHtml(detail));
    });
    sheet.querySelector("[data-open=mind]")?.addEventListener("click", () => {
      openPop("Ум", mindHtml(detail));
    });
    sheet.querySelector("#living-pop")?.addEventListener("click", (ev) => {
      if (ev.target.id === "living-pop") closePop();
    });
    sheet.querySelector("#living-chat-form")?.addEventListener("submit", (ev) => {
      ev.preventDefault();
      onChat(detail, ev.target);
    });
  }

  function bindDismiss(detail) {
    const btn = document.getElementById("living-dismiss-btn");
    if (!btn) return;
    const label = copy().dismiss || "Уволить";
    let confirming = false;
    let resetTimer = 0;
    btn.addEventListener("click", () => {
      if (!detail?.can_dismiss) {
        showToast("Завтра.", "info");
        return;
      }
      if (!confirming) {
        confirming = true;
        btn.classList.add("confirming");
        btn.setAttribute("title", "Точно уволить?");
        btn.setAttribute("aria-label", "Точно уволить?");
        resetTimer = window.setTimeout(() => {
          confirming = false;
          btn.classList.remove("confirming");
          btn.setAttribute("title", label);
          btn.setAttribute("aria-label", label);
        }, 2500);
        return;
      }
      window.clearTimeout(resetTimer);
      onDismiss(detail);
    });
  }

  async function openCard(id) {
    if (openCardId != null && Number(openCardId) !== Number(id)) {
      await closeLivingModal();
    }
    const detail = await apiFetch(`/tavern/living/cards/${id}`);
    renderModal(detail);
  }

  async function onChat(detail, form) {
    const input = form.querySelector("input[name=text]");
    const btn = form.querySelector("button[type=submit]");
    const text = (input?.value || "").trim();
    if (!text) return;
    input.value = "";
    const prior = (chatMemory.get(detail.id) || []).slice(-16);
    const turns = chatMemory.get(detail.id) || [];
    turns.push({ role: "user", text });
    chatMemory.set(detail.id, turns);
    paintThread(detail.id);
    try {
      const out = await apiFetch(`/tavern/living/cards/${detail.id}/chat`, {
        method: "POST",
        body: JSON.stringify({ text, history: prior }),
      });
      turns.push({ role: "assistant", text: out.reply || "" });
      chatMemory.set(detail.id, turns);
      paintThread(detail.id);
      if (out.chat_left <= 0) {
        if (input) input.disabled = true;
        if (btn) btn.disabled = true;
      }
    } catch (err) {
      turns.pop();
      chatMemory.set(detail.id, turns);
      paintThread(detail.id);
      const { detail: d } = parseHttpErrorDetail(err);
      showToast(d === "chat_day_cap" ? "Хватит на сегодня." : d || "Молчит.", "error");
    }
  }

  async function onRename(detail) {
    if (!detail?.can_rename) return;
    const next = window.prompt("Имя наёмницы (сменить можно один раз)", detail.name || "");
    if (next == null) return;
    const name = String(next).trim();
    if (!name || name === detail.name) return;
    try {
      const out = await apiFetch(`/tavern/living/cards/${detail.id}/rename`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      detail.name = out.name;
      detail.can_rename = false;
      const title = document.getElementById("living-name");
      if (title) {
        title.textContent = out.name;
        title.classList.remove("can-rename");
        title.removeAttribute("title");
      }
      await refreshHall();
    } catch (err) {
      const { detail: d } = parseHttpErrorDetail(err);
      const map = {
        name_locked: "Имя уже меняли.",
        name_taken: "Такое имя уже за столом.",
        bad_name: "Имя из 2–24 букв.",
      };
      showToast(map[d] || d || "Не вышло.", "error");
    }
  }

  async function onBio(detail) {
    openPop("Био", bioHtml(detail));
    if (!detail.bio_expandable) return;
    try {
      const out = await apiFetch(`/tavern/living/cards/${detail.id}/bio`, { method: "POST" });
      if (out && out.bio) {
        detail.bio = out.bio;
        detail.bio_expandable = false;
        const body = document.getElementById("living-pop-body");
        if (body) body.innerHTML = bioHtml(detail);
      }
    } catch (_) {}
  }

  async function onDismiss(detail) {
    if (!detail?.can_dismiss) {
      showToast("Завтра.", "info");
      return;
    }
    const btn = document.getElementById("living-dismiss-btn");
    if (btn) btn.disabled = true;
    try {
      await apiFetch(`/tavern/living/cards/${detail.id}/dismiss`, { method: "POST" });
      await closeLivingModal({ skipTick: true });
      await refreshHall();
    } catch (err) {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("confirming");
        const label = copy().dismiss || "Уволить";
        btn.setAttribute("title", label);
        btn.setAttribute("aria-label", label);
      }
      const { detail: d } = parseHttpErrorDetail(err);
      showToast(d === "dismiss_day_cap" ? "Завтра." : d || "Не вышло.", "error");
    }
  }

  async function onRainAccept() {
    const c = copy();
    const ok = await confirmAction(c.confirm_rain || "Снять капюшон и посадить за стол?");
    if (!ok) return;
    await apiFetch("/tavern/living/rain/accept", { method: "POST" });
    await refreshHall();
    kickArt();
  }

  async function onRainRefuse() {
    const ok = await confirmAction("Оставить за дверью? Она не перекатится.");
    if (!ok) return;
    await apiFetch("/tavern/living/rain/refuse", { method: "POST" });
    await refreshHall();
  }

  async function refreshHall() {
    const payload = await apiFetch("/tavern/living/hall?mark_seen=0");
    seenOnce = true;
    hall = payload;
    renderHall();
  }

  function bindRoot() {
    const root = document.getElementById("tavern-living-root");
    if (!root) return;
    root.addEventListener("click", (ev) => {
      const rainBtn = ev.target.closest("[data-rain]");
      if (rainBtn) {
        ev.preventDefault();
        const act = rainBtn.getAttribute("data-rain");
        if (act === "accept") {
          onRainAccept().catch((err) => {
            const { detail: d } = parseHttpErrorDetail(err);
            showToast(d || "Дверь занята.", "error");
          });
        } else if (act === "refuse") {
          onRainRefuse().catch((err) => {
            const { detail: d } = parseHttpErrorDetail(err);
            showToast(d || "Дверь занята.", "error");
          });
        }
        return;
      }
      const col = ev.target.closest(".living-col");
      if (!col) return;
      const kind = col.getAttribute("data-kind");
      const id = col.getAttribute("data-id");
      if (kind === "hire") {
        ev.preventDefault();
        onHire(col.getAttribute("data-slot")).catch((err) => {
          const { detail: d } = parseHttpErrorDetail(err);
          showToast(d === "not_enough_gold" ? "Не хватает золота." : d || "Стул занят.", "error");
        });
        return;
      }
      if (kind === "living" && id) {
        openCard(id).catch((err) => {
          const { detail: d } = parseHttpErrorDetail(err);
          showToast(d || "Карта закрыта.", "error");
        });
      }
    });
    document.getElementById("tavern-living-modal")?.addEventListener("click", (ev) => {
      if (ev.target.id === "tavern-living-modal") closeLivingModal().catch(() => {});
    });
  }

  async function bootstrapLivingTavern() {
    if (qsTab() === "bgm") {
      if (window.WaifuApp?.bootstrapTavernPage) return window.WaifuApp.bootstrapTavernPage();
      return;
    }
    document.body.classList.add("living-hall");
    if (window.WaifuApp?.initPage) await window.WaifuApp.initPage("tavern");
    else if (typeof initPage === "function") await initPage("tavern");
    try {
      await loadProfile?.({ lite: true });
    } catch (_) {}
    document.body.classList.remove("tavern-loading");
    const layer = document.getElementById("tavern-page-loading");
    if (layer) layer.setAttribute("aria-busy", "false");
    bindRoot();
    try {
      await refreshHall();
    } catch (err) {
      const root = document.getElementById("tavern-living-root");
      const { detail: d } = parseHttpErrorDetail(err);
      if (root) root.innerHTML = `<p class="muted">${esc(d || "Таверна закрыта.")}</p>`;
    }
    try {
      if (typeof scheduleTavernBgmStart === "function") scheduleTavernBgmStart();
    } catch (_) {}
    if (hall?.needs_art?.length) kickArt();
  }

  window.WaifuApp = Object.assign(window.WaifuApp || {}, {
    bootstrapLivingTavern,
    closeLivingTavernModal: () => closeLivingModal(),
  });
  void VERSION;
})();
