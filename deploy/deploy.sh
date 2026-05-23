#!/usr/bin/env bash
# Update the running deployment: pull code, rebuild frontend, refresh backend
# deps, restart the service. Run after pushing changes:
#
#   bash ~/ai-campaign-personalization/deploy/deploy.sh
#
# If you changed deploy/Caddyfile or deploy/campaign-backend.service, re-copy
# them (see the headers in those files) — this script does not touch them.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "==> Pulling latest code"
git pull

echo "==> Building frontend"
cd "$REPO_DIR/frontend"
npm install
npm run build

echo "==> Updating backend dependencies"
cd "$REPO_DIR/backend"
source venv/bin/activate
pip install -r requirements.txt

echo "==> Restarting backend service"
sudo systemctl restart campaign-backend

echo "==> Done. Recent backend logs:"
sudo systemctl --no-pager status campaign-backend | head -n 15
