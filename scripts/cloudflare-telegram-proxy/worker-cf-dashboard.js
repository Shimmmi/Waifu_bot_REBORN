/**
 * Вставь весь этот файл в редактор Worker (Cloudflare Dashboard → Edit code).
 *
 * Обязательно: Workers → твой Worker → Settings → Variables
 *   Добавь переменную ALLOWED_TOKENS (лучше Encrypt):
 *   значение = твой BOT_TOKEN из BotFather (как в .env), без префикса "bot".
 *   Несколько ботов: токены через запятую без пробелов или с trim.
 *
 * На VPS в .env:
 *   TELEGRAM_API_BASE_URL=https://<имя>.<поддомен>.workers.dev
 *   (без слэша в конце; TELEGRAM_BOT_PROXY не задавать)
 */

const OAUTH_UPSTREAM = {
  "/oauth/.well-known/jwks.json": "https://oauth.telegram.org/.well-known/jwks.json",
  "/oauth/.well-known/openid-configuration":
    "https://oauth.telegram.org/.well-known/openid-configuration",
};

export default {
  async fetch(request, env) {
    return handleRequest(request, env);
  },
};

async function handleRequest(request, env) {
  const url = new URL(request.url);

  if (request.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders() });
  }

  if (url.pathname === "/" || url.pathname === "/health") {
    return new Response(
      JSON.stringify({
        status: "ok",
        service: "telegram-api-proxy",
        hint: "Set ALLOWED_TOKENS; use TELEGRAM_API_BASE_URL=https://this-host",
        oauth_jwks: "/oauth/.well-known/jwks.json",
      }),
      {
        headers: { "Content-Type": "application/json", ...corsHeaders() },
      }
    );
  }

  const pathname = url.pathname;
  const oauthTarget = OAUTH_UPSTREAM[pathname];
  if (oauthTarget) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return jsonError(405, "Method not allowed");
    }
    try {
      const response = await fetch(oauthTarget, {
        method: request.method,
        redirect: "manual",
      });
      const responseHeaders = new Headers(response.headers);
      for (const [k, v] of Object.entries(corsHeaders())) {
        responseHeaders.set(k, v);
      }
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return jsonError(502, "Failed to proxy OIDC", err.message);
    }
  }

  if (
    !pathname.startsWith("/bot") &&
    !pathname.startsWith("/file/bot")
  ) {
    return jsonError(
      400,
      "Invalid path. Expected /bot<token>/<method> or /file/bot<token>/..."
    );
  }

  const allowed = (env.ALLOWED_TOKENS || "").trim();
  if (!allowed) {
    return jsonError(
      503,
      "Worker misconfigured: add ALLOWED_TOKENS in Worker Settings → Variables"
    );
  }

  const token = extractBotToken(pathname);
  if (!token) {
    return jsonError(400, "Could not parse bot token from path");
  }

  const allowList = allowed.split(",").map((t) => t.trim()).filter(Boolean);
  if (!allowList.includes(token)) {
    return jsonError(403, "Token not in ALLOWED_TOKENS");
  }

  const telegramUrl = `https://api.telegram.org${pathname}${url.search}`;

  try {
    const telegramRequest = new Request(telegramUrl, {
      method: request.method,
      headers: filterHeaders(request.headers),
      body:
        request.method !== "GET" && request.method !== "HEAD"
          ? request.body
          : undefined,
    });

    const response = await fetch(telegramRequest);
    const responseHeaders = new Headers(response.headers);
    for (const [k, v] of Object.entries(corsHeaders())) {
      responseHeaders.set(k, v);
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (err) {
    return jsonError(502, "Failed to proxy to Telegram", err.message);
  }
}

/** /bot<token>/... или /file/bot<token>/... */
function extractBotToken(pathname) {
  let m = pathname.match(/^\/bot([^/]+)/);
  if (m) return m[1];
  m = pathname.match(/^\/file\/bot([^/]+)/);
  if (m) return m[1];
  return null;
}

function jsonError(status, message, detail) {
  const body = { error: message };
  if (detail) body.detail = detail;
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  };
}

function filterHeaders(headers) {
  const out = new Headers();
  const allow = new Set([
    "content-type",
    "accept",
    "accept-language",
    "content-length",
    "user-agent",
  ]);
  for (const [key, value] of headers) {
    if (allow.has(key.toLowerCase())) {
      out.append(key, value);
    }
  }
  return out;
}
