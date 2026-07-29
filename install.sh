#!/usr/bin/env bash

set -e

# --------------------------------------------------
# SCOREOS Installer Functions
# --------------------------------------------------

GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m"

print_header() {
    clear
    echo -e "${BLUE}"
    echo "=================================================="
    echo "               SCOREOS INSTALLER"
    echo "=================================================="
    echo -e "${NC}"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}!${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

info() {
    echo -e "${BLUE}>${NC} $1"
}

print_header
info "Starting installation..."
echo

if [[ $EUID -eq 0 ]]; then
    error "Please do not run this installer as root."
    echo "Run it using: ./install.sh"
    exit 1
fi

info "Checking operating system..."

if [[ ! -f /etc/os-release ]]; then
    error "Unable to identify the operating system."
    exit 1
fi

source /etc/os-release

success "Detected: $PRETTY_NAME"

if [[ "$ID" != "debian" && "$ID" != "raspbian" ]]; then
    warning "SCOREOS is designed for Raspberry Pi OS Bookworm."
fi

echo
info "Checking Raspberry Pi hardware..."

if [[ -f /proc/device-tree/model ]]; then
    PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
    success "Detected: $PI_MODEL"
else
    warning "Raspberry Pi hardware could not be detected."
fi

echo
info "Checking internet connection..."

if ping -c 1 -W 3 github.com >/dev/null 2>&1; then
    success "Internet connection available."
else
    error "Unable to reach the internet."
    echo "Check the network connection and try again."
    exit 1
fi

echo
info "Updating package information..."

sudo apt update

echo
info "Installing SCOREOS system dependencies..."

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
success "SCOREOS dependency installation completed successfully."

echo
info "The Python environment will be configured in the next stage."
