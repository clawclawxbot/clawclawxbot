#!/usr/bin/env bash
# CLAWCLAWX bot — one-shot setup for a fresh Lightsail / Ubuntu / Amazon Linux box.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
USERNAME="$(whoami)"

echo "==> Installing system packages..."
if command -v apt >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3-venv python3-pip unzip
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip unzip
elif command -v yum >/dev/null 2>&1; then
  sudo yum install -y python3 python3-pip unzip
fi

echo "==> Creating Python venv + installing dependencies..."
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "==> Preparing .env..."
[ -f .env ] || cp .env.example .env

echo "==> Installing systemd service..."
sudo bash -c "cat > /etc/systemd/system/clawclawx-bot.service" <<UNIT
[Unit]
Description=CLAWCLAWX Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/bot.py
Restart=always
RestartSec=5
User=$USERNAME

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable clawclawx-bot

echo ""
echo "============================================================"
echo " ✅ Setup selesai!"
echo ""
echo " LANGKAH TERAKHIR (token bot):"
echo "   1) Edit token:  nano $DIR/.env"
echo "      isi  BOT_TOKEN=token_dari_botfather  lalu Ctrl+O, Enter, Ctrl+X"
echo "   2) Start bot:   sudo systemctl restart clawclawx-bot"
echo "   3) Cek status:  sudo systemctl status clawclawx-bot"
echo "   4) Lihat log:   journalctl -u clawclawx-bot -f"
echo "============================================================"
