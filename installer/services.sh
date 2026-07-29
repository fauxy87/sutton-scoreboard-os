#!/usr/bin/env bash

install_services() {

    info "Installing SCOREOS services..."

    if [[ ! -d services ]]; then
        error "The 'services' directory was not found."
        exit 1
    fi

    shopt -s nullglob
    local service_files=(services/*.service)

    if [[ ${#service_files[@]} -eq 0 ]]; then
        error "No .service files were found."
        exit 1
    fi

    for service in "${service_files[@]}"; do
        sudo cp "$service" /etc/systemd/system/
        success "Installed $(basename "$service")"
    done

    info "Reloading systemd..."
    sudo systemctl daemon-reload

    info "Enabling SCOREOS services..."

    for service in "${service_files[@]}"; do
        local service_name
        service_name=$(basename "$service")

        sudo systemctl enable "$service_name"
        success "Enabled $service_name"
    done

    success "All SCOREOS services installed."

}
