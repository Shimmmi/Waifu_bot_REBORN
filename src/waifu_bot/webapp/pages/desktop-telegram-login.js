"use strict";

/**
 * Telegram OIDC popup for desktop Electron login (port of armory telegramOidcPopup.ts).
 * Exposes window.DesktopTelegramOidc.openPopup({ clientId, redirectUri, origin }).
 */
(function () {
  const OIDC_ORIGIN = "https://oauth.telegram.org";
  const OIDC_AUTH_URL = `${OIDC_ORIGIN}/auth`;

  function decodeJwtPayload(token) {
    try {
      const parts = token.split(".");
      if (parts.length !== 3) return null;
      let payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const pad = payload.length % 4;
      if (pad) payload += "=".repeat(4 - pad);
      return JSON.parse(atob(payload));
    } catch {
      return null;
    }
  }

  function looksLikeJwt(token) {
    const parts = token.split(".");
    return parts.length === 3 && parts[0].startsWith("eyJ");
  }

  function extractIdToken(data) {
    const { result } = data;
    if (typeof result === "string") return result;
    if (result && typeof result === "object" && typeof result.id_token === "string") {
      return result.id_token;
    }
    if (typeof data.id_token === "string") return data.id_token;
    return null;
  }

  function buildResult(data) {
    if (data.error) throw new Error(String(data.error));
    const idToken = extractIdToken(data);
    if (!idToken) throw new Error("missing id_token");
    if (!looksLikeJwt(idToken) || !decodeJwtPayload(idToken)) {
      throw new Error("malformed id_token");
    }
    return { id_token: idToken };
  }

  function buildAuthUrl(options) {
    const scope = ["openid", "profile", "telegram:bot_access"];
    const params = new URLSearchParams({
      response_type: "post_message",
      client_id: String(options.clientId),
      redirect_uri: options.redirectUri,
      origin: options.origin,
      scope: scope.join(" "),
    });
    if (options.lang) params.set("lang", options.lang);
    return `${OIDC_AUTH_URL}?${params.toString()}`;
  }

  function openPopup(options) {
    const redirectUri = String(options.redirectUri || "").trim();
    if (!redirectUri) return Promise.reject(new Error("missing redirect_uri"));

    return new Promise((resolve, reject) => {
      const authUrl = buildAuthUrl({ ...options, redirectUri });
      const width = 550;
      const height = 650;
      const left =
        Math.max(0, (screen.width - width) / 2) + (screen.availLeft || 0);
      const top =
        Math.max(0, (screen.height - height) / 2) + (screen.availTop || 0);
      const features = `width=${width},height=${height},left=${left},top=${top},status=0,location=0,menubar=0,toolbar=0`;

      let finished = false;
      let popup = null;
      let pollTimer = null;

      const cleanup = () => {
        window.removeEventListener("message", onMessage);
        if (pollTimer != null) clearTimeout(pollTimer);
      };

      const finish = (fn) => {
        if (finished) return;
        finished = true;
        cleanup();
        fn();
      };

      const onMessage = (event) => {
        if (event.origin !== OIDC_ORIGIN) return;
        if (popup && event.source !== popup) return;
        let data;
        try {
          data = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
        } catch {
          return;
        }
        if (!data || data.event !== "auth_result") return;
        try {
          finish(() => resolve(buildResult(data)));
        } catch (err) {
          finish(() => reject(err));
        }
      };

      window.addEventListener("message", onMessage);
      popup = window.open(authUrl, "telegram_oidc_login", features);
      if (!popup) {
        cleanup();
        reject(new Error("popup_blocked"));
        return;
      }
      popup.focus();

      const pollClosed = () => {
        if (finished) return;
        if (!popup || popup.closed) {
          finish(() => reject(new Error("popup_closed")));
          return;
        }
        pollTimer = setTimeout(pollClosed, 200);
      };
      pollClosed();
    });
  }

  window.DesktopTelegramOidc = {
    openPopup,
    resolvePageRedirectUri: () => window.location.origin + window.location.pathname,
  };
})();
