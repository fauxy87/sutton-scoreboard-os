#!/usr/bin/env bash

# --------------------------------------------------
# SCOREOS Shared Installer Functions
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

pause_menu() {
    echo
    read -rp "Press Enter to return to the menu..."
}
