/** Living tavern hall. Arena / hire / bench stay dead. BGM tab still uses the old bootstrap. */

(function livingTavernHall() {
  const VERSION = "v110";
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

  function renderBoard() {
    const c = copy();
    const rows = hall?.chalkboard || [];
    if (!rows.length) {
      return `<section class="tavern-chalk"><h2>${esc(c.board || "Вчера")}</h2><p class="empty">${esc(c.history_empty || "Пока тишина.")}</p></section>`;
    }
    return `<section class="tavern-chalk"><h2>${esc(c.board || "Вчера")}</h2><ul>${rows
      .map((row) => {
        const severe = ["death", "leave_column", "maim", "psyche", "crime", "bond_break"].includes(row.severity);
        const who = row.name ? `${row.name}: ` : "";
        return `<li class="${severe ? "severe" : ""}">${esc(who)}${esc(row.line || "")}</li>`;
      })
      .join("")}</ul></section>`;
  }

  function renderHall() {
    const root = document.getElementById("tavern-living-root");
    if (!root || !hall) return;
    const c = copy();
    root.innerHTML = `<div class="tavern-living-head"><h1>${esc(c.title || "Таверна")}</h1><span class="sub">${esc(c.sub || "")}</span></div>
      ${renderColumns()}
      ${renderBoard()}`;
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

  function conditionsHtml(detail) {
    const traits = (detail.traits || []).filter(Boolean);
    const flesh = detail.wounds || [];
    const psyche = detail.psyche || [];
    const bonds = (detail.consequences || []).filter((x) => /не смотрит|Просит не гасить/i.test(x));
    const bits = [];
    bits.push(`<h3>Черты</h3><ul>${traits.length ? traits.map((t) => `<li>${esc(t)}</li>`).join("") : "<li class='muted'>Пока без ярких черт.</li>"}</ul>`);
    bits.push(`<h3>Тело</h3><ul>${flesh.length ? flesh.map((w) => `<li>${esc(w.label || w.part || "рана")}${w.severity ? " · " + esc(w.severity) : ""}</li>`).join("") : "<li class='ok'>В форме, ран нет.</li>"}</ul>`);
    bits.push(`<h3>Ум</h3><ul>${psyche.length ? psyche.map((p) => `<li>${esc(p.label || p.facet || "тень")}${p.severity ? " · " + esc(p.severity) : ""}</li>`).join("") : "<li class='ok'>Ясна.</li>"}</ul>`);
    if (bonds.length) bits.push(`<h3>Связи</h3><ul>${bonds.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`);
    return bits.join("");
  }

  function logHtml(detail, emptyLine) {
    const hist = detail.history || [];
    if (!hist.length) return `<p class="empty">${esc(emptyLine || "Пока тишина.")}</p>`;
    return `<ul class="living-log-list">${hist.map((h) => `<li>${esc(h.line || "")}</li>`).join("")}</ul>`;
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
    const cons = (detail.consequences || []).slice(0, 3);
    const traits = (detail.traits || []).filter(Boolean);
    const body = detail.body || "в форме";
    const mind = detail.mind || "ясна";
    const bodyTone = toneOf(body, detail.body_tone);
    const mindTone = toneOf(mind, detail.mind_tone);
    sheet.innerHTML = `
      <button type="button" class="living-log-btn" id="living-log-btn" title="Журнал" aria-label="Журнал">📜</button>
      <div class="living-hero">
        <div class="portrait-23">${portrait(detail, "anime") ? `<img src="${esc(portrait(detail, "anime"))}" alt="">` : ""}</div>
        <div class="living-hero-copy">
          <h2 class="${detail.can_rename ? "can-rename" : ""}" id="living-name" ${detail.can_rename ? 'title="Сменить имя (один раз)"' : ""}>${esc(detail.name)}</h2>
          <div class="who">${esc(detail.lineage || [detail.race_ru, detail.class_ru].filter(Boolean).join(" · "))}</div>
          <div class="who-sub">${esc(detail.stance_label || "")} · ${esc(detail.temper_label || "")}</div>
          <div class="loyalty">${loyaltyHeart(detail)}<span>Лояльность ${esc(detail.loyalty == null ? 50 : detail.loyalty)}</span></div>
          ${traits.length ? `<div class="traits">${traits.map(esc).join(" · ")}</div>` : ""}
          <div class="living-stats">
            <button type="button" class="living-stat tone-${bodyTone}" data-open="conditions" title="${esc(body)}">${bodyMark()}<span>${esc(body)}</span></button>
            <button type="button" class="living-stat tone-${mindTone}" data-open="conditions" title="${esc(mind)}">${mindMark()}<span>${esc(mind)}</span></button>
            <button type="button" class="living-stat" id="living-bio-btn">Био</button>
          </div>
          ${cons.length ? `<div class="living-chips">${cons.map((x) => `<span class="living-chip">${esc(x)}</span>`).join("")}</div>` : ""}
        </div>
      </div>
      <div class="living-thread" id="living-thread"></div>
      <form class="living-chat" id="living-chat-form">
        <input name="text" maxlength="400" placeholder="${esc(c.chat_ph || "Сказать ей…")}" ${detail.chat_left <= 0 ? "disabled" : ""} />
        <button type="submit"${detail.chat_left <= 0 ? " disabled" : ""}>Сказать</button>
      </form>
      <div class="living-actions">
        <button type="button" class="danger" id="living-dismiss-btn"${detail.can_dismiss ? "" : " disabled"}>${esc(c.dismiss || "Уволить")}</button>
        <button type="button" class="ghost" id="living-close-btn">Закрыть</button>
      </div>
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
    sheet.querySelector("#living-close-btn")?.addEventListener("click", () => {
      closeLivingModal().catch(() => {});
    });
    sheet.querySelector("#living-dismiss-btn")?.addEventListener("click", () => onDismiss(detail));
    sheet.querySelector("#living-name")?.addEventListener("click", () => onRename(detail));
    sheet.querySelector("#living-pop-close")?.addEventListener("click", closePop);
    sheet.querySelector("#living-log-btn")?.addEventListener("click", () => {
      openPop("Журнал", logHtml(detail, c.history_empty));
    });
    sheet.querySelector("#living-bio-btn")?.addEventListener("click", () => onBio(detail));
    sheet.querySelectorAll("[data-open=conditions]").forEach((btn) => {
      btn.addEventListener("click", () => openPop("Состояния", conditionsHtml(detail)));
    });
    sheet.querySelector("#living-pop")?.addEventListener("click", (ev) => {
      if (ev.target.id === "living-pop") closePop();
    });
    sheet.querySelector("#living-chat-form")?.addEventListener("submit", (ev) => {
      ev.preventDefault();
      onChat(detail, ev.target);
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
    openPop("Био", `<p>${esc(detail.bio || "Пока молчит.")}</p>`);
    if (!detail.bio_expandable) return;
    try {
      const out = await apiFetch(`/tavern/living/cards/${detail.id}/bio`, { method: "POST" });
      if (out && out.bio) {
        detail.bio = out.bio;
        detail.bio_expandable = false;
        const body = document.getElementById("living-pop-body");
        if (body) body.innerHTML = `<p>${esc(out.bio)}</p>`;
      }
    } catch (_) {}
  }

  async function onDismiss(detail) {
    if (!detail?.can_dismiss) {
      showToast("Завтра.", "info");
      return;
    }
    const ok = await confirmAction(`Уволить ${detail.name}?`);
    if (!ok) return;
    try {
      await apiFetch(`/tavern/living/cards/${detail.id}/dismiss`, { method: "POST" });
      await closeLivingModal({ skipTick: true });
      await refreshHall();
    } catch (err) {
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
    const payload = await apiFetch(`/tavern/living/hall?mark_seen=${seenOnce ? "0" : "1"}`);
    if (seenOnce && hall?.chalkboard?.length) {
      const have = new Set((payload.chalkboard || []).map((x) => x.id));
      payload.chalkboard = hall.chalkboard.filter((x) => !have.has(x.id)).concat(payload.chalkboard || []);
    }
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
    apiFetch("/tavern/living/spice", { method: "POST" })
      .then((out) => {
        if (out?.ok && out.phrase && hall) {
          const row = (hall.chalkboard || []).find((x) => x.id === out.id);
          if (row) {
            row.line = out.phrase;
            renderHall();
          }
        }
      })
      .catch(() => {});
    if (hall?.needs_art?.length) kickArt();
  }

  window.WaifuApp = Object.assign(window.WaifuApp || {}, {
    bootstrapLivingTavern,
    closeLivingTavernModal: () => closeLivingModal(),
  });
  void VERSION;
})();
