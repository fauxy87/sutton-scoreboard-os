#!/usr/bin/env bash

set -e

if [[ "$1" == "--version" ]]; then
    if [[ -f VERSION ]]; then
        cat VERSION
    else
        echo "Unknown"
    fi
    exit 0
fi

if [[ "$1" == "--help" ]]; then
    cat <<EOF
SCOREOS Installer

Usage:
  ./install.sh

Options:
  --help       Show this help
  --version    Show installer version
EOF
    exit 0
fi

source installer/common.sh
source installer/checks.sh
source installer/packages.sh
source installer/python.sh
source installer/services.sh
source installer/config.sh
source installer/health.sh
source installer/repository.sh
source installer/progress.sh
source installer/environment.sh
source installer/bluetooth.sh
source installer/wizard.sh

# --------------------------------------------------
# SCOREOS Installer Functions
# --------------------------------------------------


print_header

if [[ -f VERSION ]]; then
    VERSION=$(tr -d '\r\n' < VERSION)
    info "Version: $VERSION"
    echo
fi

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
    echo "7) Health Check"
    echo "0) Exit"
    echo
}

install_scoreos() {
    info "Starting SCOREOS installation..."
    echo

detect_bluetooth || true

    next_step "Checking repository..."
check_repository

next_step "Running system checks..."
run_system_checks

next_step "Installing system packages..."
install_packages

next_step "Installing Python environment..."
install_python

next_step "Installing SCOREOS services..."
install_services

next_step "Creating configuration..."
configure_scoreos
    echo
    success "SCOREOS installation completed."
    echo

    read -rp "Reboot now? (y/N): " reboot_choice

    if [[ "$reboot_choice" =~ ^[Yy]$ ]]; then
        info "Rebooting Raspberry Pi..."
        sudo reboot
    else
        warning "Please reboot before using SCOREOS."
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
            7) health_check ;;
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
run_setup_wizard
validate_installation
main_menu
