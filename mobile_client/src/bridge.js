/**
 * window.waifuMobile for Capacitor WebView (remote server.url + bundled www).
 * Resolves WaifuStepCounter via Plugins map or Capacitor.registerPlugin.
 */
(function initWaifuMobileBridge(global) {
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
    setDesktopSessionToken(token) {
      writeSession(token);
    },
    async getStepSnapshot() {
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
      const delta =
        lastClaimedTotal == null ? 0 : Math.max(0, cachedTotal - lastClaimedTotal);
      return {
        total: cachedTotal,
        deltaSinceLastClaim: delta,
        pendingDelta: delta,
        permission,
        sensor: snap.sensor || null,
      };
    },
    async consumePendingSteps() {
      const snap = await api.getStepSnapshot();
      const units = Number(snap.deltaSinceLastClaim || 0);
      if (snap.total != null) lastClaimedTotal = Number(snap.total);
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
      return r;
    },
  };

  // Always (re)install so a late Capacitor inject upgrades a cold stub.
  global.waifuMobile = api;
  markReady(!!resolvePlugin());

  // Poll briefly for Capacitor on remote pages where bridge arrives after HTML.
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
