/**
 * Injected into the WebView as window.waifuMobile (see Android MainActivity / capacitor plugin).
 * Pure-JS fallback used when running remote WebApp without native bridge.
 */
(function initWaifuMobileBridge(global) {
  if (global.waifuMobile) return;

  let lastClaimedTotal = null;
  let cachedTotal = 0;
  let permission = "prompt";

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

  global.waifuMobile = {
    getDesktopSessionToken() {
      return readSession();
    },
    setDesktopSessionToken(token) {
      writeSession(token);
    },
    async getStepSnapshot() {
      // Native plugin overrides this method via Capacitor.
      if (global.Capacitor?.Plugins?.WaifuStepCounter) {
        const snap = await global.Capacitor.Plugins.WaifuStepCounter.getSnapshot();
        cachedTotal = Number(snap.total || 0);
        permission = snap.permission || permission;
        const delta =
          lastClaimedTotal == null ? 0 : Math.max(0, cachedTotal - lastClaimedTotal);
        return {
          total: cachedTotal,
          deltaSinceLastClaim: delta,
          pendingDelta: delta,
          permission,
        };
      }
      return { total: cachedTotal, deltaSinceLastClaim: 0, pendingDelta: 0, permission: "unavailable" };
    },
    async consumePendingSteps() {
      const snap = await global.waifuMobile.getStepSnapshot();
      const units = Number(snap.deltaSinceLastClaim || 0);
      if (snap.total != null) lastClaimedTotal = Number(snap.total);
      return { units, total: snap.total };
    },
    async requestActivityPermission() {
      if (global.Capacitor?.Plugins?.WaifuStepCounter) {
        const r = await global.Capacitor.Plugins.WaifuStepCounter.requestPermission();
        permission = r.permission || permission;
        return r;
      }
      return { permission: "unavailable" };
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
