#!/usr/bin/env bash

health_check() {

    info "Running SCOREOS health check..."
    echo

    # Check Python
    if command -v python3 >/dev/null 2>&1; then
        success "Python 3 installed"
    else
        error "Python 3 not found"
    fi

    # Check Bluetooth
    if systemctl is-active --quiet bluetooth; then
        success "Bluetooth service running"
    else
        warning "Bluetooth service is not running"
    fi

    # Check Flask Port
    if ss -tln | grep -q ":5000"; then
        success "Ground Control is listening on port 5000"
    else
        warning "Ground Control is not running"
    fi

    # Check Disk Space
    FREE=$(df -h / | awk 'NR==2 {print $4}')
    success "Free disk space: $FREE"

    # Check CPU Temperature (Raspberry Pi)
    if [[ -f /sys/class/thermal/thermal_zone0/temp ]]; then
        TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
        TEMP=$((TEMP/1000))
        success "CPU Temperature: ${TEMP}°C"
    fi

    echo
    success "Health check complete."

}
