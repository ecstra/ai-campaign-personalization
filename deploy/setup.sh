#!/bin/bash
# One-time server setup for EC2 Ubuntu instance.
# Run as: bash setup.sh
set -e

echo "=== Updating system ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installing Python 3.12 + venv ==="
sudo apt install -y python3.12 python3.12-venv python3-pip

echo "=== Installing Node.js 20 LTS ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

echo "=== Installing Caddy ==="
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy

echo "=== Cloning repository ==="
if [ ! -d /home/ubuntu/app ]; then
    git clone https://github.com/Ravi2k3/ai-campaign-personalization.git /home/ubuntu/app
fi

echo "=== Setting up Python virtual environment ==="
cd /home/ubuntu/app/backend
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Building frontend ==="
cd /home/ubuntu/app/frontend
npm ci
npm run build

echo "=== Installing Caddy config ==="
sudo cp /home/ubuntu/app/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl restart caddy
sudo systemctl enable caddy

echo "=== Installing systemd service ==="
sudo cp /home/ubuntu/app/deploy/outreach-api.service /etc/systemd/system/outreach-api.service
sudo systemctl daemon-reload
sudo systemctl enable outreach-api

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Create /home/ubuntu/app/backend/.env with your environment variables"
echo "  2. Run: sudo systemctl start outreach-api"
echo "  3. Check: sudo systemctl status outreach-api"
echo "  4. Check: sudo systemctl status caddy"
