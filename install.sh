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
echo "Checking internet connection..."

if ping -c 1 -W 3 github.com >/dev/null 2>&1; then
    echo "Internet connection available."
else
    echo "Unable to reach the internet."
    echo "Check the network connection and try again."
    exit 1
fi

echo
echo "Updating package information..."

sudo apt update

echo
echo "Installing SCOREOS system dependencies..."

sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    bluez \
    bluetooth \
    chromium \
    curl

echo
echo "SCOREOS dependency installation completed successfully."
echo
echo "The Python environment will be configured in the next stage."
