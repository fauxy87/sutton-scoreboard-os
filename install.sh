#!/usr/bin/env bash

set -e

source installer/common.sh
source installer/checks.sh

# --------------------------------------------------
# SCOREOS Installer Functions
# --------------------------------------------------


print_header
info "Starting installation..."
echo

if [[ $EUID -eq 0 ]]; then
    error "Please do not run this installer as root."
    echo "Run it using: ./install.sh"
    exit 1
fi

show_menu() {
    echo
    echo "=========================================="
    echo "             SCOREOS MENU"
    echo "=========================================="
    echo
    echo "1) Install SCOREOS"
    echo "2) Update SCOREOS"
    echo "3) Repair Installation"
    echo "4) Backup Configuration"
    echo "5) Restore Configuration"
    echo "6) Uninstall SCOREOS"
    echo "0) Exit"
    echo
}

install_scoreos() {

    info "Starting SCOREOS installation..."

    run_system_checks

    info "Updating package information..."
    sudo apt update

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

    success "Dependencies installed successfully."

    info "Python environment configuration will be added in the next stage."

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
