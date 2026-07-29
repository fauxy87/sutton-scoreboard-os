#!/usr/bin/env bash

install_services() {

    info "Installing SCOREOS services..."

    if [[ ! -d services ]]; then
        error "Services directory not found."
        exit 1
    fi

    for service in services/*.service; do

        if [[ -f "$service" ]]; then
            sudo cp "$service" /etc/systemd/system/
            success "Installed $(basename "$service")"
        fi

    done

    info "Reloading systemd..."

    sudo systemctl daemon-reload

    info "Enabling SCOREOS services..."

    for service in services/*.service; do

        if [[ -f "$service" ]]; then
            SERVICE_NAME=$(basename "$service")
            sudo systemctl enable "$SERVICE_NAME"
            success "Enabled $SERVICE_NAME"
        fi

    done

    success "All services installed."

}
