#!/usr/bin/env bash
# Deploy dashboard Worker (ALLOWED_TOKENS, no URL prefix).
# Requires: CLOUDFLARE_API_TOKEN with Workers edit permission.
set -euo pipefail

cd "$(dirname "$0")"

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "CLOUDFLARE_API_TOKEN is not set."
  echo ""
  echo "Manual deploy:"
  echo "  1. Cloudflare Dashboard → Workers → waifu (waifu.timurkhazarzhan.workers.dev)"
  echo "  2. Edit code → paste entire worker-cf-dashboard.js from this folder"
  echo "  3. Settings → Variables → ALLOWED_TOKENS = your BOT_TOKEN"
  echo "  4. Deploy"
  echo "  5. Run: ./verify-jwks.sh"
  exit 1
fi

npx wrangler@3.114.1 deploy -c wrangler-dashboard.toml
echo ""
./verify-jwks.sh
