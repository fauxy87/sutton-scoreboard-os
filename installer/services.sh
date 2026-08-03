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

    if [[ -z "${BT_ADAPTER:-}" ]]; then
        warning "No Bluetooth adapter detected. Using hci0 as the service default."
        BT_ADAPTER="hci0"
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
            -e "s|{{BT_ADAPTER}}|$BT_ADAPTER|g" \
            "$service" > "$temp_service"

        if [[ "$service_name" == "sutton-scoreboard-advert.service" ]]; then
            if ! grep -qE "start-advertisement\.exp[[:space:]]+$BT_ADAPTER" "$temp_service"; then
                sed -i \
                    "s|start-advertisement\.exp$|start-advertisement.exp $BT_ADAPTER|" \
                    "$temp_service"
            fi
        fi

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

        sudo systemctl enable "$service_name"
        success "Enabled $service_name"
    done

    success "All SCOREOS services installed."
}
