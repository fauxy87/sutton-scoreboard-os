#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="/home/picricket/sutton-scoreboard-os/sutton-scoreboard-os"
RUN_USER="picricket"

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo:"
    echo "sudo ./install/install.sh"
    exit 1
fi

echo "Installing SCOREOS packages..."

apt update
apt install -y \
    git \
    python3 \
    python3-dbus \
    python3-gi \
    python3-serial \
    bluez \
    bluetooth \
    expect \
    network-manager

echo "Creating runtime folder..."

install -d -o "$RUN_USER" -g "$RUN_USER" /run/scoreos

echo "Installing services..."

install -m 0644 \
    "$REPO_DIR/services/sutton-scoreboard-advert.service" \
    /etc/systemd/system/sutton-scoreboard-advert.service

install -m 0644 \
    "$REPO_DIR/services/sutton-scoreboard.service" \
    /etc/systemd/system/sutton-scoreboard.service

cat > /etc/systemd/system/scoreos-web.service <<SERVICE
[Unit]
Description=SCOREOS Web Interface
After=network.target sutton-scoreboard.service
Wants=sutton-scoreboard.service

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 -u $REPO_DIR/web/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE

chmod +x "$REPO_DIR/scripts/start-advertisement.exp"

echo "Reloading services..."

systemctl daemon-reload

systemctl enable bluetooth.service
systemctl enable sutton-scoreboard-advert.service
systemctl enable sutton-scoreboard.service
systemctl enable scoreos-web.service

echo "Restarting Bluetooth and SCOREOS..."

systemctl restart bluetooth.service
sleep 4

systemctl restart sutton-scoreboard-advert.service
systemctl restart sutton-scoreboard.service
systemctl restart scoreos-web.service

echo
echo "SCOREOS installation complete."
echo
echo "Next run:"
echo "sudo ./install/setup-hotspot.sh"
