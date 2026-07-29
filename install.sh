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

}

update_scoreos() {
    info "Update feature coming soon."
}

repair_scoreos() {
    info "Repair feature coming soon."
}

backup_scoreos() {
    info "Backup feature coming soon."
}

restore_scoreos() {
    info "Restore feature coming soon."
}

uninstall_scoreos() {
    warning "Uninstall feature coming soon."
}

main_menu() {
    while true; do
        show_menu
        read -rp "Choice: " choice

        case "$choice" in
            1) install_scoreos ;;
            2) update_scoreos ;;
            3) repair_scoreos ;;
            4) backup_scoreos ;;
            5) restore_scoreos ;;
            6) uninstall_scoreos ;;
            0)
                info "Goodbye!"
                exit 0
                ;;
            *)
                error "Invalid option."
                ;;
        esac

        echo
        read -rp "Press Enter to return to the menu..."
    done
}
main_menu
