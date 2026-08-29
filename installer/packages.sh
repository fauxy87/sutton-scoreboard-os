#!/usr/bin/env bash

install_packages() {

    info "Updating package information..."

    sudo apt update

    info "Installing SCOREOS system dependencies..."

    sudo apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dbus \
        python3-gi \
        python3-serial \
        python3-gpiozero \
        git \
        bluez \
        bluetooth \
        rfkill \
        expect \
        network-manager \
        ffmpeg \
        chromium \
        wlr-randr \
        curl

    success "System packages installed."

}
