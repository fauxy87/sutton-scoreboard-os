#!/usr/bin/env bash

run_setup_wizard() {

    clear

clear

VERSION_NUMBER=$(grep "^Version:" VERSION | cut -d' ' -f2)

echo
echo "======================================================"
echo
echo "              SCOREOS Setup Wizard"
echo
echo "                  Version $VERSION_NUMBER"
echo
echo "======================================================"
echo

    next_step "Checking Environment..."

    sleep 1

    success "User: $SCOREOS_USER"
    success "Install Directory: $SCOREOS_DIR"

    if [[ -n "${BT_ADAPTER:-}" ]]; then
        success "Bluetooth Adapter: $BT_ADAPTER"
    else
        warning "Bluetooth Adapter: None Detected"
    fi

    echo
}

validate_installation() {

    echo
    next_step "Validating Installer..."

    command -v git >/dev/null \
        && success "Git Installed" \
        || error "Git Missing"

    command -v python3 >/dev/null \
        && success "Python Installed" \
        || error "Python Missing"

    [[ -f VERSION ]] \
        && success "VERSION file found" \
        || error "VERSION file missing"

    [[ -d services ]] \
        && success "Services folder found" \
        || error "Services folder missing"

    [[ -d installer ]] \
        && success "Installer folder found" \
        || error "Installer folder missing"

    echo
}
