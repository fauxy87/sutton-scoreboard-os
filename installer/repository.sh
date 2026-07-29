#!/usr/bin/env bash

check_repository() {

    info "Checking SCOREOS repository..."

    if [[ ! -f README.md ]]; then
        error "This does not appear to be the SCOREOS repository."
        exit 1
    fi

    if [[ ! -f requirements.txt ]]; then
        error "requirements.txt not found."
        exit 1
    fi

    success "Repository verified."

}
