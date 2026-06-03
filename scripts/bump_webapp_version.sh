#!/bin/bash
# Bump waifu-webapp CACHE_VERSION in sw.js and sync ?v= query on shell assets in HTML.
# Usage: ./scripts/bump_webapp_version.sh [waifu-webapp-v26]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SW="${ROOT}/src/waifu_bot/webapp/sw.js"
WEBAPP="${ROOT}/src/waifu_bot/webapp"

if [[ -n "${1:-}" ]]; then
  NEW_VER="$1"
else
  CUR="$(grep -oE 'waifu-webapp-v[0-9]+' "$SW" | head -1)"
  N="$(echo "$CUR" | grep -oE '[0-9]+$')"
  NEW_VER="waifu-webapp-v$((N + 1))"
fi

sed -i "s/const CACHE_VERSION = \"waifu-webapp-v[0-9]*\"/const CACHE_VERSION = \"${NEW_VER}\"/" "$SW"
echo "CACHE_VERSION -> ${NEW_VER}"

python3 - "$WEBAPP" "$NEW_VER" <<'PY'
import re
import sys
from pathlib import Path

webapp = Path(sys.argv[1])
ver = sys.argv[2]
for html in sorted(webapp.glob("*.html")):
    text = html.read_text(encoding="utf-8")

    def bump_attr(m):
        return f'{m.group(1)}="{m.group(2)}?v={ver}"'

    text = re.sub(
        r'(href|src)="((?:\./|/webapp/)?(?:styles\.css|app\.js|pages/[a-z_]+\.js))(?:\?[^"]*)?"',
        bump_attr,
        text,
    )
    html.write_text(text, encoding="utf-8")
    print(html.name)
PY

echo "Updated HTML shell asset URLs in ${WEBAPP}/*.html"
