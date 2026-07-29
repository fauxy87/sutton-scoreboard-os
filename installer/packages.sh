#!/usr/bin/env bash

install_packages() {

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

    success "System packages installed."

}
