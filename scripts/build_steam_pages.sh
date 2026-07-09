#!/usr/bin/env bash
# Generate webapp/steam/{shop,dungeons,profile}.html from parent pages.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEBAPP="$ROOT/src/waifu_bot/webapp"
STEAM="$WEBAPP/steam"
VERSION="$(grep -oE 'waifu-webapp-v[0-9]+' "$WEBAPP/sw.js" | head -1 || echo waifu-webapp-v51)"

mkdir -p "$STEAM"

for page in shop dungeons profile; do
  src="$WEBAPP/${page}.html"
  dst="$STEAM/${page}.html"
  if [[ ! -f "$src" ]]; then
    echo "ERROR: missing $src" >&2
    exit 1
  fi
  cp "$src" "$dst"
  # Steam shell class + compact CSS
  sed -i "s/<body class=\"page-${page}\"/<body class=\"page-${page} page-steam-shell\"/" "$dst"
  sed -i "s/<body class=\"page-${page} page-steam-shell\" onload/<body class=\"page-${page} page-steam-shell\" onload/" "$dst" 2>/dev/null || true
  if ! grep -q 'desktop-theme.css' "$dst"; then
    sed -i "0,/<link rel=\"stylesheet\"/s//<link rel=\"stylesheet\" href=\"\/webapp\/desktop-theme.css?v=${VERSION}\" \/>\n    <link rel=\"stylesheet\"/" "$dst"
  else
    sed -i "s|/webapp/desktop-theme.css?v=waifu-webapp-v[0-9]*|/webapp/desktop-theme.css?v=${VERSION}|g" "$dst"
    sed -i "s|\./desktop-theme.css?v=waifu-webapp-v[0-9]*|/webapp/desktop-theme.css?v=${VERSION}|g" "$dst"
  fi
  if ! grep -q 'steam-pages.css' "$dst"; then
    sed -i "0,/<link rel=\"stylesheet\"/s//<link rel=\"stylesheet\" href=\".\/steam-pages.css?v=${VERSION}\" \/>\n    <link rel=\"stylesheet\"/" "$dst"
  else
    sed -i "s|steam-pages.css?v=waifu-webapp-v[0-9]*|steam-pages.css?v=${VERSION}|g" "$dst"
  fi
  # Hidden attic stubs: keep badge IDs for loadProfile/initPage but remove visible chrome
  sed -i 's/<header class="attic"/<header class="attic" style="display:none !important" aria-hidden="true"/' "$dst"
  sed -i 's/<nav class="nav basement"/<nav class="nav basement" style="display:none !important" aria-hidden="true"/' "$dst"
  # Absolute webapp paths: steam/*.html lives under /webapp/steam/ — relative ./vendor breaks.
  sed -i 's|href="./vendor/|href="/webapp/vendor/|g' "$dst"
  sed -i 's|src="./vendor/|src="/webapp/vendor/|g' "$dst"
  sed -i 's|href="./assets/|href="/webapp/assets/|g' "$dst"
  sed -i 's|src="./assets/|src="/webapp/assets/|g' "$dst"

  # Steam profile: compact recreate tab only (survives rebuild; hidden on Telegram via steam-dev-only).
  if [[ "$page" == "profile" ]]; then
    # Drop legacy full-width recreate bar if present from older builds.
    if grep -q 'profile-steam-recreate-bar' "$dst"; then
      python3 - "$dst" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
text2 = re.sub(
    r'\s*<div class="steam-dev-only profile-steam-recreate-bar"[^>]*>.*?</div>\n?',
    "\n",
    text,
    count=1,
    flags=re.S,
)
if text2 != text:
    p.write_text(text2, encoding="utf-8")
PY
    fi
    if ! grep -q 'tab-steam-recreate' "$dst"; then
      sed -i 's|onclick="WaifuApp.resetMainWaifu()" style="display:none">♻️</button>|onclick="WaifuApp.resetMainWaifu()" style="display:none">♻️</button>\n        <button class="tab tab-steam-recreate steam-dev-only" type="button" title="Пересоздать вайфу (dev)" aria-label="Пересоздать основную вайфу" onclick="WaifuApp.resetSteamMainWaifu()" style="display:none">🔄</button>|' "$dst"
    fi
  fi

  echo "  steam/${page}.html"
done

echo "Done. Steam pages in $STEAM/ (re-run after editing shop/dungeons/profile.html)."
