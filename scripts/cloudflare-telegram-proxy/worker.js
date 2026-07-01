/**
 * Прокси Bot API: клиент бьётся в Worker по /<SECRET_PREFIX>/bot<token>/<method>,
 * Worker пересылает на https://api.telegram.org/bot<token>/<method>.
 * OIDC JWKS: /<SECRET_PREFIX>/oauth/.well-known/jwks.json → oauth.telegram.org
 * SECRET_PREFIX — wrangler secret (см. README).
 */

const OAUTH_UPSTREAM = {
  "/oauth/.well-known/jwks.json": "https://oauth.telegram.org/.well-known/jwks.json",
  "/oauth/.well-known/openid-configuration":
    "https://oauth.telegram.org/.well-known/openid-configuration",
};

export default {
  async fetch(request, env) {
    const prefix = env.SECRET_PREFIX;
    if (!prefix || typeof prefix !== "string") {
      return new Response("Worker misconfigured: SECRET_PREFIX", { status: 500 });
    }

    const url = new URL(request.url);
    const expected = `/${prefix}`;
    if (!url.pathname.startsWith(`${expected}/`)) {
      return new Response("Not found", { status: 404 });
    }

    const upstreamPath = url.pathname.slice(expected.length);
    const oauthTarget = OAUTH_UPSTREAM[upstreamPath];
    if (oauthTarget) {
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("Method not allowed", { status: 405 });
      }
      return fetch(oauthTarget, { method: request.method, redirect: "manual" });
    }

    if (
      !upstreamPath.startsWith("/bot") &&
      !upstreamPath.startsWith("/file/bot")
    ) {
      return new Response("Not found", { status: 404 });
    }

    const target = `https://api.telegram.org${upstreamPath}${url.search}`;

    const headers = new Headers();
    for (const [key, value] of request.headers) {
      if (key.toLowerCase() === "host") continue;
      headers.append(key, value);
    }

    const init = {
      method: request.method,
      headers,
      redirect: "manual",
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    return fetch(target, init);
  },
};
