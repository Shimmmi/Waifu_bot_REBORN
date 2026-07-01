#!/bin/bash
# Deploy latest main to production and restart waifu-bot service.
# Requires SSH access to the production host (shimmirpgbot.ru).

set -euo pipefail

HOST="${DEPLOY_HOST:-shimmirpgbot.ru}"
USER="${DEPLOY_USER:-ubuntu}"
REPO_DIR="${DEPLOY_REPO_DIR:-/opt/waifu-bot-REBORN}"
BRANCH="${DEPLOY_BRANCH:-main}"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)

echo "==> Deploying ${BRANCH} to ${USER}@${HOST}:${REPO_DIR}"

ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" bash -s <<EOF
set -euo pipefail
cd "${REPO_DIR}"
echo "==> git fetch && checkout ${BRANCH}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"
if [ -f armory_frontend/package.json ]; then
  echo "==> build armory frontend"
  if command -v npm >/dev/null 2>&1; then
    (cd armory_frontend && npm install && npm run build)
  else
    echo "WARN: npm not found — skip armory frontend build"
  fi
fi
if [ -f webapp_frontend/package.json ]; then
  echo "==> build webapp bundles"
  if command -v npm >/dev/null 2>&1; then
    ./scripts/build_webapp.sh
  else
    echo "WARN: npm not found — skip webapp bundle build"
  fi
fi
echo "==> apply migrations"
PYTHONPATH=${REPO_DIR}/src python3 -m waifu_bot.cli migrate || true
echo "==> restart services"
sudo systemctl restart waifu-bot.service
if systemctl list-unit-files waifu-bot-worker.service >/dev/null 2>&1; then
  sudo systemctl restart waifu-bot-worker.service waifu-bot-scheduler.service 2>/dev/null || true
  if systemctl list-unit-files waifu-bot-llm-worker.service >/dev/null 2>&1; then
    sudo systemctl restart waifu-bot-llm-worker.service 2>/dev/null || true
  fi
fi
sleep 2
systemctl is-active waifu-bot.service
echo "==> health check"
curl -sf http://localhost:8001/health
echo ""
echo "==> update webhook"
PYTHONPATH=${REPO_DIR}/src:/usr/local/lib/python3.12/dist-packages \\
  python3 scripts/update_webhook.py
EOF

echo "==> Done"
