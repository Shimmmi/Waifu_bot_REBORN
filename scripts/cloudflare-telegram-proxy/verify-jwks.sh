#!/usr/bin/env bash
# Verify Cloudflare Worker serves OIDC JWKS (Armory login).
# Usage: ./verify-jwks.sh [worker-host]
set -euo pipefail

HOST="${1:-https://waifu.timurkhazarzhan.workers.dev}"
HOST="${HOST%/}"

echo "Checking $HOST/health ..."
health="$(curl -sS --max-time 10 "$HOST/health")"
echo "$health"

if echo "$health" | grep -q 'oauth_jwks'; then
  echo "OK: Worker health includes oauth_jwks (new code deployed)"
else
  echo "FAIL: Worker health missing oauth_jwks — redeploy worker-cf-dashboard.js in Cloudflare Dashboard"
  exit 1
fi

echo "Checking $HOST/oauth/.well-known/jwks.json ..."
body="$(curl -sS --max-time 15 "$HOST/oauth/.well-known/jwks.json")"
preview="${body:0:120}"
echo "$preview"

if echo "$body" | grep -q '"keys"'; then
  echo "OK: JWKS JSON contains keys"
  exit 0
fi

echo "FAIL: JWKS endpoint did not return keys (got: $preview)"
exit 1
