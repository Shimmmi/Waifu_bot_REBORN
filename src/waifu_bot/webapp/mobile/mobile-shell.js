/**
 * Mobile shell: auth gate, full TG hub swipe pager, onboarding, background step sync hook.
 */
(function () {
  const qs = "mobileClient=1";
  const HUBS = ["profile", "dungeons", "shop", "tavern", "caravan", "guild", "training", "menu"];
  const FRAME_BY_HUB = {
    profile: "frame-profile",
    dungeons: "frame-dungeons",
    shop: "frame-shop",
    tavern: "frame-tavern",
    caravan: "frame-caravan",
    guild: "frame-guild",
    training: "frame-training",
    menu: "frame-menu",
  };

  const pager = document.getElementById("mobile-pager");
  const tabs = Array.from(document.querySelectorAll(".mobile-tabbar button[data-hub]"));
  const framesLoaded = new Set();
  let cachedProfile = null;
  let lastAutoClaimAt = 0;

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

  function hubIndex(hub) {
    const i = HUBS.indexOf(hub);
    return i >= 0 ? i : 0;
  }

  function ensureFrame(hub) {
    const id = FRAME_BY_HUB[hub];
    const frame = id ? document.getElementById(id) : null;
    if (!frame || framesLoaded.has(id)) return;
    const src = frame.getAttribute("data-src");
    if (!src) return;
    frame.src = src;
    framesLoaded.add(id);
  }

  function setTab(hubOrIndex) {
    const hub = typeof hubOrIndex === "number" ? HUBS[hubOrIndex] || "profile" : String(hubOrIndex || "profile");
    const idx = hubIndex(hub);
    const page = pager.children[idx];
    if (page) page.scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
    tabs.forEach((b) => b.classList.toggle("active", b.getAttribute("data-hub") === hub));
    ensureFrame(hub);
  }

  // Tab bar icons (same assets as TG basement)
  const navBase = "/static/game/ui/nav";
  const ver = window.WAIFU_WEBAPP_VERSION || "waifu-webapp-v45";
  tabs.forEach((btn) => {
    const hub = btn.getAttribute("data-hub");
    const img = document.createElement("img");
    img.className = "nav-icon";
    img.alt = "";
    img.decoding = "async";
    img.src = `${navBase}/${hub}.webp?v=${ver}`;
    btn.appendChild(img);
    btn.addEventListener("click", () => setTab(hub));
  });

  let scrollT = null;
  pager.addEventListener(
    "scroll",
    () => {
      if (scrollT) clearTimeout(scrollT);
      scrollT = setTimeout(() => {
        const w = pager.clientWidth || 1;
        const i = Math.max(0, Math.min(HUBS.length - 1, Math.round(pager.scrollLeft / w)));
        const hub = HUBS[i];
        tabs.forEach((b) => b.classList.toggle("active", b.getAttribute("data-hub") === hub));
        ensureFrame(hub);
      }, 80);
    },
    { passive: true }
  );

  window.addEventListener("message", (ev) => {
    if (ev.origin !== window.location.origin) return;
    const data = ev.data;
    if (!data || data.type !== "waifuMobileNavigate") return;
    const page = String(data.page || "");
    if (HUBS.includes(page)) setTab(page);
  });

  // Edge swipe zones drive the pager without fighting iframe vertical scroll.
  function bindEdge(el, dir) {
    if (!el) return;
    let startX = 0;
    el.addEventListener(
      "touchstart",
      (e) => {
        startX = e.changedTouches?.[0]?.clientX || 0;
      },
      { passive: true }
    );
    el.addEventListener(
      "touchend",
      (e) => {
        const x = e.changedTouches?.[0]?.clientX || 0;
        const dx = x - startX;
        const w = pager.clientWidth || 1;
        const i = Math.round(pager.scrollLeft / w);
        if (dir === "left" && dx > 40) setTab(Math.max(0, i - 1));
        if (dir === "right" && dx < -40) setTab(Math.min(HUBS.length - 1, i + 1));
      },
      { passive: true }
    );
  }
  bindEdge(document.getElementById("edge-left"), "left");
  bindEdge(document.getElementById("edge-right"), "right");

  const tut = document.getElementById("mobile-tutorial");
  try {
    if (!localStorage.getItem("waifuMobileTutorialV1") && tut) {
      tut.hidden = false;
      document.getElementById("tutorial-next")?.addEventListener("click", () => {
        localStorage.setItem("waifuMobileTutorialV1", "1");
        tut.hidden = true;
      });
    }
  } catch {
    /* ignore */
  }

  function setOnboardVisible(show) {
    const el = document.getElementById("waifu-onboard");
    if (el) el.hidden = !show;
  }

  function setProfileError(msg) {
    const el = document.getElementById("profile-error-banner");
    if (!el) return;
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = `Ошибка профиля: ${msg}`;
  }

  async function refreshHub() {
    try {
      const p = await WaifuApp.apiFetch("/profile");
      cachedProfile = p;
      if (p?.profile_error) {
        setProfileError(p.profile_error);
        setOnboardVisible(false);
        return p;
      }
      setProfileError(null);
      const mw = p?.main_waifu;
      setOnboardVisible(!mw);
      if (!mw) {
        // Auto-open generator once per session so staging empty accounts are obvious.
        try {
          if (!sessionStorage.getItem("waifuMobileOnboardRedirected")) {
            sessionStorage.setItem("waifuMobileOnboardRedirected", "1");
            window.location.replace(`/webapp/waifu_generator.html?${qs}`);
            return p;
          }
        } catch {
          /* ignore */
        }
      }
      return p;
    } catch (e) {
      setProfileError(String(e.message || e));
      setOnboardVisible(false);
      return null;
    }
  }

  async function waitBridge(ms) {
    const deadline = Date.now() + (ms || 3000);
    while (Date.now() < deadline) {
      if (window.waifuMobile?.__nativeReady || window.waifuMobile?.getStepSnapshot) {
        return window.waifuMobile;
      }
      await new Promise((r) => setTimeout(r, 200));
    }
    return window.waifuMobile || null;
  }

  async function syncStepsOnResume() {
    const bridge = await waitBridge(2500);
    if (!bridge?.getStepSnapshot || !bridge?.syncBaselineFromServer) return;
    try {
      const status = await WaifuApp.apiFetch("/activity/status?ensure_starter=true");
      const serverLast =
        status?.server_last_counter != null ? Number(status.server_last_counter) : null;
      await bridge.syncBaselineFromServer(serverLast);
      const snap = await bridge.getStepSnapshot();
      const units = Number(snap?.deltaSinceLastClaim || 0) || 0;
      const now = Date.now();
      if (units > 0 && now - lastAutoClaimAt > 15000) {
        lastAutoClaimAt = now;
        const body = {
          source: "mobile_steps",
          units,
          client_counter_total: snap.total != null ? Number(snap.total) : null,
        };
        await WaifuApp.apiFetch("/activity/input/claim", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        await bridge.consumePendingSteps?.();
      }
      await bridge.startBackgroundTracking?.();
    } catch {
      /* ignore — steps are best-effort until attic UI lands */
    }
  }

  // Initial hub from ?hub=
  let startHub = "profile";
  try {
    const hub = new URLSearchParams(window.location.search).get("hub");
    if (hub && HUBS.includes(hub)) startHub = hub;
  } catch {
    /* ignore */
  }
  setTab(startHub);

  (async () => {
    await refreshHub();
    await syncStepsOnResume();
  })();

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      syncStepsOnResume();
    }
  });

  window.WaifuMobileShell = { setTab, refreshHub, hubs: HUBS, cachedProfile: () => cachedProfile };
})();
