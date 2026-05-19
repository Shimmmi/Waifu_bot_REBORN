#!/usr/bin/env bash
# Проверка, что в OpenAPI объявлен POST /profile/main-waifu/paperdoll (после деплоя).
# Usage: ./scripts/verify_paperdoll_route.sh [BASE_URL]
set -euo pipefail
BASE="${1:-https://shimmirpgbot.ru}"
URL="${BASE%/}/api/openapi.json"
echo "Fetching ${URL} ..."
TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT
if ! curl -fsS "$URL" -o "${TMP}"; then
  echo "FAIL: could not fetch OpenAPI" >&2
  exit 1
fi
if ! grep -q '"/profile/main-waifu/paperdoll"' "${TMP}"; then
  echo "FAIL: path /profile/main-waifu/paperdoll missing in OpenAPI (old backend build?)." >&2
  exit 1
fi
if ! grep -q '"/profile/main-waifu/paperdoll/regenerate"' "${TMP}"; then
  echo "FAIL: path /profile/main-waifu/paperdoll/regenerate missing in OpenAPI." >&2
  exit 1
fi
echo "OK: paperdoll + paperdoll/regenerate paths listed in OpenAPI."
exit 0
