#!/usr/bin/env bash

detect_bluetooth() {
    BT_ADAPTER="$(ls /sys/class/bluetooth 2>/dev/null | grep '^hci' | head -n 1)"

    if [[ -z "$BT_ADAPTER" ]]; then
        warning "No Bluetooth adapter detected."
        return 1
    fi

    success "Bluetooth adapter detected: $BT_ADAPTER"
    export BT_ADAPTER
}
