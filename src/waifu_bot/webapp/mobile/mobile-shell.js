/**
 * Mobile shell: auth gate, swipe pager, steps claim, profile/inventory.
 */
(function () {
  const qs = "mobileClient=1";
  const pager = document.getElementById("mobile-pager");
  const tabs = Array.from(document.querySelectorAll(".mobile-tabbar button"));

  function hasSession() {
    try {
      if (window.waifuMobile?.getDesktopSessionToken?.()) return true;
      return !!localStorage.getItem("waifuDesktopSession");
    } catch {
      return false;
    }
  }

  function requireSession() {
    if (!hasSession()) {
      window.location.replace(`/webapp/mobile/login.html?${qs}`);
      return false;
    }
    return true;
  }

  if (!requireSession()) return;

  function setTab(i) {
    const idx = Math.max(0, Math.min(3, i | 0));
    const page = pager.children[idx];
    if (page) page.scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
    tabs.forEach((b, j) => b.classList.toggle("active", j === idx));
  }

  tabs.forEach((btn) => {
    btn.addEventListener("click", () => setTab(Number(btn.getAttribute("data-goto") || 0)));
  });

  // Sync tab highlight on scroll snap
  let scrollT = null;
  pager.addEventListener(
    "scroll",
    () => {
      if (scrollT) clearTimeout(scrollT);
      scrollT = setTimeout(() => {
        const w = pager.clientWidth || 1;
        const i = Math.round(pager.scrollLeft / w);
        tabs.forEach((b, j) => b.classList.toggle("active", j === i));
      }, 80);
    },
    { passive: true }
  );

  // Axis-lock hint: native horizontal pager; vertical scroll stays inside .mobile-page

  document.getElementById("btn-logout")?.addEventListener("click", () => {
    try {
      localStorage.removeItem("waifuDesktopSession");
      window.waifuMobile?.setDesktopSessionToken?.(null);
    } catch (_) {}
    window.location.replace(`/webapp/mobile/login.html?${qs}`);
  });

  // Tutorial once
  const tut = document.getElementById("mobile-tutorial");
  try {
    if (!localStorage.getItem("waifuMobileTutorialV1") && tut) {
      tut.hidden = false;
    }
  } catch (_) {}
  document.getElementById("tutorial-next")?.addEventListener("click", () => {
    try {
      localStorage.setItem("waifuMobileTutorialV1", "1");
    } catch (_) {}
    if (tut) tut.hidden = true;
    setTab(2);
  });

  async function waitBridge(ms) {
    const deadline = Date.now() + (ms || 5000);
    while (Date.now() < deadline) {
      if (window.waifuMobile?.getStepSnapshot) return window.waifuMobile;
      await new Promise((r) => setTimeout(r, 200));
    }
    return window.waifuMobile || null;
  }

  async function refreshHub() {
    try {
      const p = await WaifuApp.apiFetch("/profile");
      document.getElementById("hub-player").textContent = p?.player_id ?? p?.id ?? "—";
      document.getElementById("hub-waifu").textContent = p?.main_waifu?.name || p?.waifu_name || "—";
      document.getElementById("hub-level").textContent =
        p?.main_waifu?.level ?? p?.level ?? "—";
    } catch (e) {
      document.getElementById("hub-player").textContent = String(e.message || e);
    }
  }

  async function refreshDungeons() {
    const el = document.getElementById("dungeon-list");
    try {
      const data = await WaifuApp.apiFetch("/dungeons");
      const list = data?.dungeons || data || [];
      if (!Array.isArray(list) || !list.length) {
        el.textContent = "Нет доступных данжей (или другой формат API).";
        return;
      }
      el.innerHTML = list
        .slice(0, 12)
        .map((d) => {
          const id = d.id ?? d.dungeon_id;
          const name = d.name || d.title || `#${id}`;
          return `<div style="margin:8px 0"><strong>${name}</strong>
            <button type="button" class="mobile-btn secondary" data-dungeon-start="${id}">Старт (activity)</button></div>`;
        })
        .join("");
      el.querySelectorAll("[data-dungeon-start]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-dungeon-start");
          try {
            await WaifuApp.apiFetch(`/dungeons/${id}/start?economy=activity`, { method: "POST" });
            el.insertAdjacentHTML("afterbegin", `<p class="ok">Данж ${id} запущен</p>`);
            setTab(2);
          } catch (e) {
            alert(String(e.message || e));
          }
        });
      });
    } catch (e) {
      el.textContent = String(e.message || e);
    }
  }

  async function refreshInventory() {
    const el = document.getElementById("inv-list");
    const eq = document.getElementById("profile-equip");
    const note = document.getElementById("remap-note");
    try {
      // client=mobile triggers ensure_channel_overlays + resolved view
      const data = await WaifuApp.apiFetch("/inventory?limit=50&offset=0&client=mobile");
      const items = data?.items || data || [];
      if (data?.channel_remap) {
        note.textContent = data.channel_remap.message || "Бонусы чата адаптированы под mobile (sticky).";
      } else {
        note.textContent = "";
      }
      if (!Array.isArray(items) || !items.length) {
        el.textContent = "Инвентарь пуст";
        eq.textContent = "Нет экипа";
        return;
      }
      el.innerHTML = items
        .slice(0, 30)
        .map((it) => {
          const name = it.name || it.item_name || `#${it.id}`;
          const ch = it.resolved_channel || "mobile";
          const bonus = (it.resolved_bonuses || it.affixes || [])
            .slice(0, 3)
            .map((a) => a.name || a.stat || a.effect_key || "?")
            .join(", ");
          return `<div style="margin:8px 0;padding-bottom:8px;border-bottom:1px solid #2a3344">
            <strong>${name}</strong> <span class="muted">[${ch}]</span><br/>
            <span class="muted">${bonus || "база без канальных бонусов"}</span></div>`;
        })
        .join("");
      const equipped = items.filter((it) => it.equipment_slot > 0);
      eq.innerHTML = equipped.length
        ? equipped.map((it) => it.name || `#${it.id}`).join(", ")
        : "Ничего не надето";
    } catch (e) {
      el.textContent = String(e.message || e);
      eq.textContent = "—";
    }
  }

  async function readSteps() {
    const bridge = await waitBridge(3000);
    if (!bridge?.getStepSnapshot) {
      return { units: 0, total: null, permission: "unavailable" };
    }
    const snap = await bridge.getStepSnapshot();
    return {
      units: Number(snap?.deltaSinceLastClaim || snap?.pendingDelta || 0) || 0,
      total: snap?.total != null ? Number(snap.total) : null,
      permission: snap?.permission,
      sensor: snap?.sensor,
    };
  }

  async function updatePerm() {
    const snap = await readSteps();
    const el = document.getElementById("act-perm");
    document.getElementById("act-total").textContent = snap.total != null ? String(snap.total) : "—";
    document.getElementById("act-pending").textContent =
      snap.permission === "unavailable" ? "—" : String(snap.units);
    if (snap.permission === "granted") el.textContent = `Шагомер: OK (${snap.sensor || "sensor"})`;
    else if (snap.permission === "denied") el.textContent = "Шагомер: отказано";
    else if (snap.permission === "unavailable") el.textContent = "Шагомер: plugin недоступен — обновите APK";
    else el.textContent = "Шагомер: нужно разрешение";
  }

  async function refreshStatus() {
    try {
      const st = await WaifuApp.apiFetch("/activity/status");
      document.getElementById("act-buffer").textContent = st.buffer_units ?? 0;
      document.getElementById("act-min").textContent = st.min_chars ?? 3;
      document.getElementById("act-need").textContent = st.units_to_next_hit ?? 0;
      document.getElementById("act-today").textContent = st.units_accepted_today ?? 0;
      const today = Number(st.units_accepted_today || 0);
      const soft = document.getElementById("act-softcap");
      if (soft) {
        soft.textContent =
          today >= 10000
            ? `Сегодня ${today} ед. — soft-cap зона (отдача ниже, см. баланс).`
            : `Дневной soft-cap ориентир ~10k шагов (сейчас ${today}).`;
      }
    } catch (e) {
      document.getElementById("activity-hint").textContent = String(e.message || e);
    }
  }

  document.getElementById("act-perm-btn")?.addEventListener("click", async () => {
    await waitBridge(5000);
    await window.waifuMobile?.requestActivityPermission?.();
    await updatePerm();
  });

  document.getElementById("act-claim")?.addEventListener("click", async () => {
    const btn = document.getElementById("act-claim");
    btn.disabled = true;
    try {
      await waitBridge(2000);
      const snap = await readSteps();
      const body = {
        source: "mobile_steps",
        units: Math.max(0, snap.units),
        client_counter_total: snap.total,
      };
      if (body.units <= 0 && window.waifuMobile?.consumePendingSteps) {
        const c = await window.waifuMobile.consumePendingSteps();
        body.units = Number(c?.units || 0);
        body.client_counter_total = c?.total ?? body.client_counter_total;
      }
      const out = await WaifuApp.apiFetch("/activity/input/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (body.units > 0 && window.waifuMobile?.consumePendingSteps) {
        await window.waifuMobile.consumePendingSteps();
      }
      document.getElementById("activity-hint").textContent = out.hits_applied
        ? `Ударов: ${out.hits_applied}. Буфер: ${out.buffer_left}`
        : `Принято ${out.accepted_units}. До удара: ${out.units_to_next_hit}`;
      await refreshStatus();
      await updatePerm();
    } catch (e) {
      document.getElementById("activity-hint").textContent = String(e.message || e);
    } finally {
      btn.disabled = false;
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshStatus();
      updatePerm();
    }
  });

  (async function boot() {
    await waitBridge(4000);
    await Promise.all([refreshHub(), refreshDungeons(), refreshInventory(), refreshStatus(), updatePerm()]);
    setInterval(() => {
      if (document.visibilityState === "visible") updatePerm();
    }, 2500);
  })();
})();
