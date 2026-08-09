/**
 * Mobile shell: auth gate, swipe pager, TG page iframes, steps claim.
 */
(function () {
  const qs = "mobileClient=1";
  const pager = document.getElementById("mobile-pager");
  const tabs = Array.from(document.querySelectorAll(".mobile-tabbar button"));
  let cachedProfile = null;
  const framesLoaded = new Set();

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

  function ensureFrame(id) {
    const frame = document.getElementById(id);
    if (!frame || framesLoaded.has(id)) return;
    const src = frame.getAttribute("data-src");
    if (!src) return;
    frame.src = src;
    framesLoaded.add(id);
  }

  function setTab(i) {
    const idx = Math.max(0, Math.min(3, i | 0));
    const page = pager.children[idx];
    if (page) page.scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
    tabs.forEach((b, j) => b.classList.toggle("active", j === idx));
    if (idx === 0) ensureFrame("frame-profile");
    if (idx === 1) ensureFrame("frame-dungeons");
    if (idx === 3) ensureFrame("frame-inventory");
  }

  tabs.forEach((btn) => {
    btn.addEventListener("click", () => setTab(Number(btn.getAttribute("data-goto") || 0)));
  });

  let scrollT = null;
  pager.addEventListener(
    "scroll",
    () => {
      if (scrollT) clearTimeout(scrollT);
      scrollT = setTimeout(() => {
        const w = pager.clientWidth || 1;
        const i = Math.round(pager.scrollLeft / w);
        tabs.forEach((b, j) => b.classList.toggle("active", j === i));
        if (i === 0) ensureFrame("frame-profile");
        if (i === 1) ensureFrame("frame-dungeons");
        if (i === 3) ensureFrame("frame-inventory");
      }, 80);
    },
    { passive: true }
  );

  document.getElementById("btn-logout")?.addEventListener("click", () => {
    try {
      localStorage.removeItem("waifuDesktopSession");
      window.waifuMobile?.setDesktopSessionToken?.(null);
    } catch (_) {}
    window.location.replace(`/webapp/mobile/login.html?${qs}`);
  });

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
      const b = window.waifuMobile;
      if (b?.getStepSnapshot && (b.__nativeReady || b.__hasPlugin || b.requestActivityPermission)) {
        return b;
      }
      if (b?.getStepSnapshot) return b;
      await new Promise((r) => setTimeout(r, 200));
    }
    return window.waifuMobile || null;
  }

  function setOnboardVisible(show) {
    const el = document.getElementById("waifu-onboard");
    if (el) el.hidden = !show;
  }

  async function refreshHub() {
    try {
      const p = await WaifuApp.apiFetch("/profile");
      cachedProfile = p;
      const pid = p?.player_id ?? p?.id ?? "—";
      document.getElementById("hub-player").textContent = String(pid);
      const mw = p?.main_waifu;
      document.getElementById("hub-waifu").textContent = mw?.name || "—";
      document.getElementById("hub-level").textContent =
        mw?.level != null ? String(mw.level) : "—";
      setOnboardVisible(!mw);
      return p;
    } catch (e) {
      document.getElementById("hub-player").textContent = String(e.message || e);
      setOnboardVisible(false);
      return null;
    }
  }

  /** Fallback list if iframe fails; keeps ?act= for API contract. */
  async function refreshDungeonsFallback() {
    const el = document.getElementById("dungeon-list-fallback");
    if (!el) return;
    try {
      const act = Math.max(1, Math.min(5, Number(cachedProfile?.act || cachedProfile?.max_act || 1) || 1));
      const data = await WaifuApp.apiFetch(`/dungeons?act=${act}`);
      const list = data?.dungeons || data || [];
      if (!Array.isArray(list) || !list.length) {
        el.textContent = "Нет доступных данжей.";
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
    /* Inventory tab uses TG profile iframe; keep API warm for channel remap. */
    try {
      await WaifuApp.apiFetch("/inventory?limit=1&offset=0&economy=activity&client=mobile");
    } catch (_) {
      /* ignore */
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
      ready: !!(bridge.__nativeReady || bridge.__hasPlugin),
    };
  }

  async function updatePerm() {
    const snap = await readSteps();
    const el = document.getElementById("act-perm");
    document.getElementById("act-total").textContent = snap.total != null ? String(snap.total) : "—";
    document.getElementById("act-pending").textContent =
      snap.permission === "unavailable" ? "—" : String(snap.units);
    if (snap.permission === "granted") {
      el.textContent = `Шагомер: OK (${snap.sensor || "sensor"})`;
    } else if (snap.permission === "denied") {
      el.textContent = "Шагомер: отказано — включите в настройках Android";
    } else if (snap.permission === "unavailable") {
      el.textContent =
        "Шагомер: plugin недоступен — сверните и снова откройте приложение (или пересоберите APK)";
    } else {
      el.textContent = "Шагомер: нужно разрешение";
    }
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
            ? `Сегодня ${today} ед. — soft-cap зона (отдача ниже).`
            : `Дневной soft-cap ориентир ~10k шагов (сейчас ${today}).`;
      }
    } catch (e) {
      document.getElementById("activity-hint").textContent = String(e.message || e);
    }
  }

  document.getElementById("act-perm-btn")?.addEventListener("click", async () => {
    const hint = document.getElementById("activity-hint");
    const bridge = await waitBridge(6000);
    if (!bridge?.requestActivityPermission) {
      if (hint) {
        hint.textContent =
          "Мост шагомера не подключён. Сверните приложение и откройте снова — или переустановите APK.";
      }
      await updatePerm();
      return;
    }
    try {
      const r = await bridge.requestActivityPermission();
      if (hint) {
        hint.textContent =
          r?.permission === "granted"
            ? "Доступ к шагомеру выдан"
            : r?.permission === "denied"
              ? "Доступ отклонён"
              : `Статус: ${r?.permission || "unknown"}`;
      }
    } catch (e) {
      if (hint) hint.textContent = String(e.message || e);
    }
    await updatePerm();
  });

  document.getElementById("act-claim")?.addEventListener("click", async () => {
    const btn = document.getElementById("act-claim");
    btn.disabled = true;
    try {
      const bridge = await waitBridge(3000);
      if (!bridge?.getStepSnapshot) {
        document.getElementById("activity-hint").textContent =
          "Нет native-моста — нельзя забрать шаги. Сверните/откройте приложение.";
        return;
      }
      let snap = await readSteps();
      let units = Math.max(0, snap.units);
      let total = snap.total;
      if (units <= 0 && bridge.consumePendingSteps) {
        const c = await bridge.consumePendingSteps();
        units = Number(c?.units || 0);
        total = c?.total ?? total;
      }
      const body = {
        source: "mobile_steps",
        units,
        client_counter_total: total,
      };
      const out = await WaifuApp.apiFetch("/activity/input/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (units > 0 && bridge.consumePendingSteps) {
        await bridge.consumePendingSteps();
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
    const profile = await refreshHub();
    ensureFrame("frame-profile");
    await Promise.all([refreshInventory(), refreshStatus(), updatePerm()]);
    // Warm dungeons API with correct act (iframe uses full TG page).
    try {
      const act = Math.max(1, Math.min(5, Number(profile?.act || profile?.max_act || 1) || 1));
      await WaifuApp.apiFetch(`/dungeons?act=${act}`);
    } catch (_) {
      await refreshDungeonsFallback();
    }
    setInterval(() => {
      if (document.visibilityState === "visible") updatePerm();
    }, 2500);
  })();
})();
