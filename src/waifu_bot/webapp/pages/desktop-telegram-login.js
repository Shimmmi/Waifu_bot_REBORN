"use strict";

/**
 * Telegram OIDC for desktop Electron (popup + post_message) and Capacitor mobile
 * (authorization_code + PKCE via same-window redirect).
 * Exposes window.DesktopTelegramOidc.
 */
(function () {
  const OIDC_ORIGIN = "https://oauth.telegram.org";
  const OIDC_AUTH_URL = `${OIDC_ORIGIN}/auth`;
  const PKCE_STORAGE_KEY = "waifuTgOidcPkce";

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

  function resolvePageRedirectUri() {
    return window.location.origin + window.location.pathname;
  }

  function isNativePlatform() {
    try {
      if (window.Capacitor?.isNativePlatform?.()) return true;
    } catch (_) {
      /* ignore */
    }
    return !!(window.waifuMobile && typeof window.waifuMobile.setDesktopSessionToken === "function");
  }

  function randomUrlSafe(bytes) {
    const arr = new Uint8Array(bytes);
    crypto.getRandomValues(arr);
    let bin = "";
    for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  async function sha256Base64Url(text) {
    const data = new TextEncoder().encode(text);
    const digest = await crypto.subtle.digest("SHA-256", data);
    const bytes = new Uint8Array(digest);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function buildPopupAuthUrl(options) {
    const scope = ["openid", "profile", "telegram:bot_access"];
    // Match Armory OIDC popup: client_id + redirect_uri + origin.
    // Do NOT send bot_id here — it switches Telegram onto the legacy Login Widget.
    const params = new URLSearchParams({
      response_type: "post_message",
      client_id: String(options.clientId),
      redirect_uri: String(options.redirectUri || "").trim(),
      origin: String(options.origin || "").replace(/\/$/, ""),
      scope: scope.join(" "),
    });
    if (options.lang) params.set("lang", options.lang);
    return `${OIDC_AUTH_URL}?${params.toString()}`;
  }

  function buildCodeAuthUrl(options) {
    const scope = ["openid", "profile", "telegram:bot_access"];
    const params = new URLSearchParams({
      response_type: "code",
      client_id: String(options.clientId),
      redirect_uri: String(options.redirectUri || "").trim(),
      scope: scope.join(" "),
      code_challenge: String(options.codeChallenge),
      code_challenge_method: "S256",
      state: String(options.state),
    });
    if (options.lang) params.set("lang", options.lang);
    return `${OIDC_AUTH_URL}?${params.toString()}`;
  }

  function openPopup(options) {
    const clientId = String(options.clientId || "").trim();
    if (!clientId || clientId === "NaN") {
      return Promise.reject(new Error("telegram_bot_not_configured"));
    }
    if (!/^\d{5,}$/.test(clientId)) {
      return Promise.reject(new Error("telegram_bot_not_configured"));
    }
    const redirectUri = String(options.redirectUri || "").trim();
    if (!redirectUri) return Promise.reject(new Error("missing redirect_uri"));

    return new Promise((resolve, reject) => {
      const authUrl = buildPopupAuthUrl({ ...options, clientId, redirectUri });
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

  /**
   * Start Capacitor in-WebView code+PKCE flow (navigates away).
   * Stores verifier/state in sessionStorage for the redirect return.
   */
  async function startCodeRedirect(options) {
    const clientId = String(options.clientId || "").trim();
    if (!clientId || !/^\d{5,}$/.test(clientId)) {
      throw new Error("telegram_bot_not_configured");
    }
    const redirectUri = String(options.redirectUri || "").trim();
    if (!redirectUri) throw new Error("missing redirect_uri");
    if (!window.crypto?.subtle) throw new Error("pkce_unavailable");

    const codeVerifier = randomUrlSafe(64);
    const codeChallenge = await sha256Base64Url(codeVerifier);
    const state = randomUrlSafe(16);
    const payload = {
      code_verifier: codeVerifier,
      state,
      redirect_uri: redirectUri,
      client_id: clientId,
      created_at: Date.now(),
    };
    // sessionStorage for in-WebView return; localStorage backup if OS briefly
    // leaves the WebView (Custom Tabs / App Link) and comes back.
    const raw = JSON.stringify(payload);
    try {
      sessionStorage.setItem(PKCE_STORAGE_KEY, raw);
    } catch (e) {
      /* fall through to localStorage */
    }
    try {
      localStorage.setItem(PKCE_STORAGE_KEY, raw);
    } catch (e) {
      throw new Error("pkce_storage_failed");
    }
    const authUrl = buildCodeAuthUrl({
      clientId,
      redirectUri,
      codeChallenge,
      state,
      lang: options.lang,
    });
    window.location.assign(authUrl);
  }

  function consumePkceReturn(searchParams) {
    const params = searchParams || new URLSearchParams(window.location.search || "");
    const err = params.get("error");
    const code = params.get("code");
    const state = params.get("state");
    if (!err && !code) return null;

    let stored = null;
    try {
      stored = JSON.parse(sessionStorage.getItem(PKCE_STORAGE_KEY) || "null");
    } catch {
      stored = null;
    }
    if (!stored) {
      try {
        stored = JSON.parse(localStorage.getItem(PKCE_STORAGE_KEY) || "null");
      } catch {
        stored = null;
      }
    }
    try {
      sessionStorage.removeItem(PKCE_STORAGE_KEY);
    } catch (_) {
      /* ignore */
    }
    try {
      localStorage.removeItem(PKCE_STORAGE_KEY);
    } catch (_) {
      /* ignore */
    }

    if (err) {
      const desc = params.get("error_description") || err;
      return { error: String(desc) };
    }
    if (!stored || !stored.code_verifier || !stored.redirect_uri) {
      return { error: "pkce_state_missing" };
    }
    if (!state || state !== stored.state) {
      return { error: "pkce_state_mismatch" };
    }
    if (!code) return { error: "missing_code" };
    return {
      code: String(code),
      redirect_uri: String(stored.redirect_uri),
      code_verifier: String(stored.code_verifier),
    };
  }

  function clearOauthQueryFromUrl() {
    try {
      const url = new URL(window.location.href);
      if (!url.searchParams.has("code") && !url.searchParams.has("error")) return;
      url.search = "";
      // Keep mobileClient=1 if present originally via hash-less clean path
      const keep = new URLSearchParams();
      if (new URLSearchParams(window.location.search).has("mobileClient")) {
        keep.set("mobileClient", "1");
      }
      url.search = keep.toString() ? `?${keep.toString()}` : "";
      window.history.replaceState({}, "", url.pathname + url.search);
    } catch (_) {
      /* ignore */
    }
  }

  window.DesktopTelegramOidc = {
    openPopup,
    startCodeRedirect,
    consumePkceReturn,
    clearOauthQueryFromUrl,
    isNativePlatform,
    resolvePageRedirectUri,
  };
})();
