#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this installer with sudo:"
    echo "sudo ./install/install.sh"
    exit 1
fi

# Identify the user who invoked sudo.
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    INSTALL_USER="$SUDO_USER"
else
    INSTALL_USER="$(logname 2>/dev/null || true)"
fi

if [[ -z "$INSTALL_USER" || "$INSTALL_USER" == "root" ]]; then
    echo "Unable to determine the normal user account."
    echo "Run the installer from the required user's login using sudo."
    exit 1
fi

INSTALL_GROUP="$(id -gn "$INSTALL_USER")"
INSTALL_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

echo
echo "SCOREOS Installer"
echo "================="
echo "User:       $INSTALL_USER"
echo "Group:      $INSTALL_GROUP"
echo "Home:       $INSTALL_HOME"
echo "Repository: $REPO_DIR"
echo

required_files=(
    "$REPO_DIR/bluetooth/server.py"
    "$REPO_DIR/web/server.py"
    "$REPO_DIR/scripts/start-advertisement.exp"
    "$REPO_DIR/scripts/bluetooth_watchdog.py"
)

for required_file in "${required_files[@]}"; do
    if [[ ! -f "$required_file" ]]; then
        echo "Required file not found:"
        echo "$required_file"
        exit 1
    fi
done

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

install -d \
    -o "$INSTALL_USER" \
    -g "$INSTALL_GROUP" \
    -m 0775 \
    /run/scoreos

echo "Installing SCOREOS services..."

cat > /etc/systemd/system/sutton-scoreboard-advert.service <<SERVICE
[Unit]
Description=Sutton Scoreboard BLE Advertisement
Requires=bluetooth.service
After=bluetooth.service
Before=sutton-scoreboard.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 4
ExecStart=/usr/bin/expect $REPO_DIR/scripts/start-advertisement.exp
RemainAfterExit=yes
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
SERVICE

cat > /etc/systemd/system/sutton-scoreboard.service <<SERVICE
[Unit]
Description=Sutton Scoreboard OS
Requires=bluetooth.service
Requires=sutton-scoreboard-advert.service
After=bluetooth.service
After=sutton-scoreboard-advert.service

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 -u $REPO_DIR/bluetooth/server.py
Restart=always
RestartSec=5
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
SERVICE

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

cat > /etc/systemd/system/scoreos-bluetooth-watchdog.service <<SERVICE
[Unit]
Description=SCOREOS Bluetooth Advertising Watchdog
After=bluetooth.service scoreos-web.service
Wants=bluetooth.service

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 -u $REPO_DIR/scripts/bluetooth_watchdog.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

chmod +x "$REPO_DIR/scripts/start-advertisement.exp"
chmod +x "$REPO_DIR/scripts/bluetooth_watchdog.py"

echo "Checking generated service files..."

systemd-analyze verify \
    /etc/systemd/system/sutton-scoreboard-advert.service \
    /etc/systemd/system/sutton-scoreboard.service \
    /etc/systemd/system/scoreos-web.service \
    /etc/systemd/system/scoreos-bluetooth-watchdog.service

echo "Reloading systemd..."

systemctl daemon-reload

systemctl enable bluetooth.service
systemctl enable sutton-scoreboard-advert.service
systemctl enable sutton-scoreboard.service
systemctl enable scoreos-web.service
systemctl enable scoreos-bluetooth-watchdog.service

echo "Restarting Bluetooth and SCOREOS..."

systemctl restart bluetooth.service
sleep 4

systemctl restart sutton-scoreboard-advert.service
systemctl restart sutton-scoreboard.service
systemctl restart scoreos-web.service
systemctl restart scoreos-bluetooth-watchdog.service

echo
echo "Service status:"
systemctl --no-pager --full is-active bluetooth.service
systemctl --no-pager --full is-active sutton-scoreboard-advert.service
systemctl --no-pager --full is-active sutton-scoreboard.service
systemctl --no-pager --full is-active scoreos-web.service
systemctl --no-pager --full is-active scoreos-bluetooth-watchdog.service

echo
echo "SCOREOS installation complete."
echo
echo "Repository: $REPO_DIR"
echo "Installed for user: $INSTALL_USER"
echo
echo "To configure the hotspot, run:"
echo "sudo $REPO_DIR/install/setup-hotspot.sh"
