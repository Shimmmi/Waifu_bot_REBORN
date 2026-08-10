/**
 * window.waifuMobile for Capacitor WebView (remote server.url + bundled www).
 * Persists step baseline across cold starts; can start Android FGS tracking.
 */
(function initWaifuMobileBridge(global) {
  const PREF_KEY = "waifuStepBaselineV1";
  let lastClaimedTotal = null;
  let cachedTotal = 0;
  let permission = "prompt";
  let pluginRef = null;

  function readSession() {
    try {
      return global.localStorage?.getItem("waifuDesktopSession") || null;
    } catch {
      return null;
    }
  }

  function writeSession(token) {
    try {
      if (token) global.localStorage?.setItem("waifuDesktopSession", String(token));
      else global.localStorage?.removeItem("waifuDesktopSession");
    } catch {
      /* ignore */
    }
  }

  function loadBaseline() {
    try {
      const raw = global.localStorage?.getItem(PREF_KEY);
      if (!raw) return null;
      const o = JSON.parse(raw);
      if (o && Number.isFinite(Number(o.lastClaimedTotal))) return Number(o.lastClaimedTotal);
    } catch {
      /* ignore */
    }
    return null;
  }

  function saveBaseline(total) {
    try {
      global.localStorage?.setItem(
        PREF_KEY,
        JSON.stringify({ lastClaimedTotal: Number(total) || 0, savedAt: Date.now() })
      );
    } catch {
      /* ignore */
    }
  }

  lastClaimedTotal = loadBaseline();

  function resolvePlugin() {
    const Cap = global.Capacitor;
    if (!Cap) return null;
    if (pluginRef) return pluginRef;
    try {
      if (Cap.Plugins && Cap.Plugins.WaifuStepCounter) {
        pluginRef = Cap.Plugins.WaifuStepCounter;
        return pluginRef;
      }
      if (typeof Cap.registerPlugin === "function") {
        pluginRef = Cap.registerPlugin("WaifuStepCounter");
        return pluginRef;
      }
    } catch {
      pluginRef = null;
    }
    return null;
  }

  function markReady(ok) {
    const api = global.waifuMobile;
    if (!api) return;
    api.__nativeReady = !!ok;
    api.__hasCapacitor = !!global.Capacitor;
    api.__hasPlugin = !!ok;
  }

  const api = {
    __nativeReady: false,
    __hasCapacitor: false,
    __hasPlugin: false,
    getDesktopSessionToken() {
      return readSession();
    },
    getAppVersion() {
      return "0.0001";
    },
    setDesktopSessionToken(token) {
      writeSession(token);
    },
    /**
     * Align local baseline with server last_counter so cold-start shows
     * pending = device_total - server_last (not zeroed by memory baseline).
     */
    async syncBaselineFromServer(serverLastCounter) {
      const snap = await api.getStepSnapshot({ skipPrime: true });
      const total = snap.total != null ? Number(snap.total) : null;
      if (total == null || !Number.isFinite(total)) return snap;
      if (serverLastCounter != null && Number.isFinite(Number(serverLastCounter))) {
        const srv = Number(serverLastCounter);
        // Prefer the higher of persisted local baseline and server counter.
        const local = lastClaimedTotal != null ? Number(lastClaimedTotal) : srv;
        lastClaimedTotal = Math.min(total, Math.max(srv, local >= 0 ? local : srv));
      } else if (lastClaimedTotal == null) {
        lastClaimedTotal = total;
      }
      saveBaseline(lastClaimedTotal);
      const delta = Math.max(0, total - Number(lastClaimedTotal || 0));
      return {
        total,
        deltaSinceLastClaim: delta,
        pendingDelta: delta,
        permission: snap.permission,
        sensor: snap.sensor,
      };
    },
    async getStepSnapshot(opts) {
      const skipPrime = !!(opts && opts.skipPrime);
      const plugin = resolvePlugin();
      markReady(!!plugin);
      if (!plugin || typeof plugin.getSnapshot !== "function") {
        return {
          total: cachedTotal,
          deltaSinceLastClaim: 0,
          pendingDelta: 0,
          permission: "unavailable",
          sensor: "none",
        };
      }
      const snap = await plugin.getSnapshot();
      cachedTotal = Number(snap.total || 0);
      permission = snap.permission || permission;
      if (!skipPrime && lastClaimedTotal == null && Number.isFinite(cachedTotal)) {
        // First ever open: baseline to current total (no backlog of boot lifetime).
        lastClaimedTotal = cachedTotal;
        saveBaseline(lastClaimedTotal);
      }
      const baseline = lastClaimedTotal != null ? Number(lastClaimedTotal) : cachedTotal;
      const delta = Math.max(0, cachedTotal - baseline);
      return {
        total: cachedTotal,
        deltaSinceLastClaim: delta,
        pendingDelta: delta,
        permission,
        sensor: snap.sensor || null,
      };
    },
    async consumePendingSteps() {
      const snap = await api.getStepSnapshot({ skipPrime: true });
      const units = Number(snap.deltaSinceLastClaim || 0);
      if (snap.total != null) {
        lastClaimedTotal = Number(snap.total);
        saveBaseline(lastClaimedTotal);
      }
      return { units, total: snap.total };
    },
    async requestActivityPermission() {
      const plugin = resolvePlugin();
      markReady(!!plugin);
      if (!plugin || typeof plugin.requestPermission !== "function") {
        return { permission: "unavailable" };
      }
      const r = await plugin.requestPermission();
      permission = r.permission || permission;
      if (permission === "granted") {
        await api.startBackgroundTracking();
      }
      return r;
    },
    async startBackgroundTracking() {
      const plugin = resolvePlugin();
      if (!plugin || typeof plugin.startBackgroundTracking !== "function") {
        return { ok: false, reason: "unavailable" };
      }
      try {
        return await plugin.startBackgroundTracking();
      } catch (e) {
        return { ok: false, reason: String(e && e.message ? e.message : e) };
      }
    },
    async stopBackgroundTracking() {
      const plugin = resolvePlugin();
      if (!plugin || typeof plugin.stopBackgroundTracking !== "function") {
        return { ok: false };
      }
      try {
        return await plugin.stopBackgroundTracking();
      } catch {
        return { ok: false };
      }
    },
  };

  global.waifuMobile = api;
  markReady(!!resolvePlugin());

  let tries = 0;
  const timer = global.setInterval(() => {
    tries += 1;
    if (resolvePlugin()) {
      markReady(true);
      global.clearInterval(timer);
    } else if (tries >= 20) {
      markReady(false);
      global.clearInterval(timer);
    }
  }, 250);
})(typeof window !== "undefined" ? window : globalThis);
