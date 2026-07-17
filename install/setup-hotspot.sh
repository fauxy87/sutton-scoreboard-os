#!/usr/bin/env bash
set -Eeuo pipefail

CONNECTION_NAME="SCOREOS-Hotspot"
SSID="SuttonCC-Scoreboard"
PASSWORD="Sutton1877"
INTERFACE="wlan0"

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo:"
    echo "sudo ./install/setup-hotspot.sh"
    exit 1
fi

nmcli connection delete "$CONNECTION_NAME" 2>/dev/null || true

nmcli connection add \
    type wifi \
    ifname "$INTERFACE" \
    con-name "$CONNECTION_NAME" \
    autoconnect no \
    ssid "$SSID"

nmcli connection modify "$CONNECTION_NAME" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel 6 \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.psk "$PASSWORD" \
    ipv4.method shared \
    ipv4.addresses 192.168.4.1/24 \
    ipv6.method disabled

echo
echo "Hotspot profile created."
echo "SSID: $SSID"
echo "Password: $PASSWORD"
echo
echo "Start it with:"
echo "sudo nmcli connection up $CONNECTION_NAME"
