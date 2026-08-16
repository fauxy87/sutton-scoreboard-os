#!/usr/bin/env bash

install_services() {

    info "Installing SCOREOS services..."

    if [[ ! -d services ]]; then
        error "The 'services' directory was not found."
        exit 1
    fi

    if [[ -z "${SCOREOS_USER:-}" || -z "${SCOREOS_DIR:-}" ]]; then
        error "SCOREOS environment variables are not set."
        exit 1
    fi

    shopt -s nullglob
    local service_files=(services/*.service)

    if [[ ${#service_files[@]} -eq 0 ]]; then
        error "No .service files were found."
        exit 1
    fi

    for service in "${service_files[@]}"; do
        local service_name
        local temp_service

        service_name="$(basename "$service")"
        temp_service="$(mktemp)"

        sed \
            -e "s|/home/picricket/sutton-scoreboard-os/sutton-scoreboard-os|$SCOREOS_DIR|g" \
            -e "s|/home/picricket/sutton-scoreboard-os|$SCOREOS_DIR|g" \
            -e "s|/home/pi/sutton-scoreboard-os|$SCOREOS_DIR|g" \
            -e "s|{{USER}}|$SCOREOS_USER|g" \
            -e "s|{{INSTALL_DIR}}|$SCOREOS_DIR|g" \
            "$service" > "$temp_service"

        sudo install -m 0644 \
            "$temp_service" \
            "/etc/systemd/system/$service_name"

        rm -f "$temp_service"

        success "Installed $service_name"
    done

    info "Reloading systemd..."
    sudo systemctl daemon-reload

    info "Enabling SCOREOS services..."

    for service in "${service_files[@]}"; do
        local service_name
        service_name="$(basename "$service")"

        if [[ "$service_name" == "scoreos-camera-recorder.service" ]]; then
            sudo systemctl disable "$service_name" >/dev/null 2>&1 || true
            success "Installed $service_name (match-controlled, not enabled at boot)"
            continue
        fi

        sudo systemctl enable "$service_name"
        success "Enabled $service_name"
    done

    success "All SCOREOS services installed."
}
