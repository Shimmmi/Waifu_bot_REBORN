#!/usr/bin/env bash
# Minify WebApp JS/CSS (Vite IIFE bundles) and Vue combat island.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="$ROOT/src/waifu_bot/webapp/bundle"

require_file() {
  local path="$1"
  if [[ ! -s "$path" ]]; then
    echo "ERROR: missing or empty bundle: $path" >&2
    exit 1
  fi
}

echo "=== webapp_frontend (app + page IIFE bundles) ==="
if [[ -f "$ROOT/webapp_frontend/package.json" ]]; then
  (cd "$ROOT/webapp_frontend" && npm ci)
  (cd "$ROOT/webapp_frontend" && npx vite build --config vite.app.config.js)
  (cd "$ROOT/webapp_frontend" && npx vite build --config vite.styles.config.js)
  (cd "$ROOT/webapp_frontend" && npx vite build --config vite.dungeons.config.js)
  (cd "$ROOT/webapp_frontend" && npx vite build --config vite.tavern.config.js)
else
  echo "ERROR: webapp_frontend/package.json not found" >&2
  exit 1
fi

echo "=== webapp_combat (Vue island) ==="
if [[ -f "$ROOT/webapp_combat/package.json" ]]; then
  (cd "$ROOT/webapp_combat" && npm ci)
  (cd "$ROOT/webapp_combat" && npx vite build)
else
  echo "ERROR: webapp_combat/package.json not found" >&2
  exit 1
fi

echo "=== verify bundle outputs ==="
require_file "$BUNDLE/app.min.js"
require_file "$BUNDLE/dungeons.min.js"
require_file "$BUNDLE/tavern.min.js"
require_file "$BUNDLE/combat-island.min.js"
require_file "$BUNDLE/styles.min.css"

if rg -q 'process\.env' "$BUNDLE/combat-island.min.js" 2>/dev/null; then
  echo "ERROR: combat-island.min.js still references process.env" >&2
  exit 1
fi

if ! grep -q 'exportWebAppShellGlobals' "$ROOT/src/waifu_bot/webapp/app.js"; then
  echo "ERROR: app.js missing exportWebAppShellGlobals (required for page IIFE bundles)" >&2
  exit 1
fi

if rg -q '\$\{GAME_STATIC_BASE\}' "$BUNDLE/dungeons.min.js" 2>/dev/null; then
  echo "ERROR: dungeons.min.js still references bare GAME_STATIC_BASE" >&2
  exit 1
fi

if ! rg -q 'window\.GAME_STATIC_BASE' "$BUNDLE/dungeons.min.js" 2>/dev/null; then
  echo "ERROR: dungeons.min.js should reference window.GAME_STATIC_BASE" >&2
  exit 1
fi

if ! rg -q 'GAME_STATIC_BASE' "$BUNDLE/app.min.js" 2>/dev/null; then
  echo "WARN: app.min.js may not export GAME_STATIC_BASE to window"
fi

head -c 80 "$BUNDLE/dungeons.min.js" | grep -q 'function\|(' || {
  echo "WARN: dungeons.min.js should be IIFE-wrapped"
}

echo "=== audit shell exports ==="
node "$ROOT/scripts/audit_webapp_shell_exports.mjs"

echo "=== smoke test bundles ==="
node "$ROOT/scripts/smoke_webapp_bundles.mjs"

echo "Done. Bundle output: $BUNDLE/"
ls -la "$BUNDLE/"
