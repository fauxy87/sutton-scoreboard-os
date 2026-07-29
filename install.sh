#!/usr/bin/env bash

set -e

echo "======================================"
echo "        SCOREOS Installer"
echo "======================================"
echo

if [[ $EUID -eq 0 ]]; then
    echo "Please do not run this installer as root."
    echo "Run it using: ./install.sh"
    exit 1
fi

echo "Checking operating system..."

if [[ ! -f /etc/os-release ]]; then
    echo "Unable to identify the operating system."
    exit 1
fi

source /etc/os-release

echo "Detected: $PRETTY_NAME"

if [[ "$ID" != "debian" && "$ID" != "raspbian" ]]; then
    echo "Warning: SCOREOS is designed for Raspberry Pi OS Bookworm."
fi

echo
echo "Checking Raspberry Pi hardware..."

if [[ -f /proc/device-tree/model ]]; then
    PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
    echo "Detected: $PI_MODEL"
else
    echo "Warning: Raspberry Pi hardware could not be detected."
fi

echo
echo "Initial system checks completed successfully."
echo
echo "SCOREOS installation stages will be added next."
