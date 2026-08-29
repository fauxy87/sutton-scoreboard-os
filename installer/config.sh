#!/usr/bin/env bash

configure_scoreos() {

    info "Creating SCOREOS configuration..."

    sudo mkdir -p /etc/scoreos

    if [[ ! -f /etc/scoreos/scoreos.conf ]]; then

        sudo tee /etc/scoreos/scoreos.conf >/dev/null <<EOF
CLUB_NAME=Sutton Cricket Club
HTTP_PORT=8080
DISPLAY=HDMI-A-1
RESOLUTION=1920x1080
BLUETOOTH=auto
STARTUP_DELAY=10
EOF

        success "Configuration created."

    else

        warning "Configuration already exists."

    fi

}
