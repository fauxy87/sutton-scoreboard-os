#!/usr/bin/env bash

run_system_checks() {

    info "Checking operating system..."

    if [[ ! -f /etc/os-release ]]; then
        error "Unable to identify the operating system."
        exit 1
    fi

    source /etc/os-release

    success "Detected: $PRETTY_NAME"

    if [[ "$ID" != "debian" && "$ID" != "raspbian" ]]; then
        warning "SCOREOS is designed for Raspberry Pi OS Trixie or Bookworm."
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
        warning "GitHub did not answer ping; package installation will verify connectivity."
    fi

    echo

}
